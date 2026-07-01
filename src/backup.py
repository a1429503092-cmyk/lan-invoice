# -*- coding: utf-8 -*-
"""多分区隐藏备份服务 — 自动扫描、防抖复制、完整性验证、自动恢复"""

import os
import re
import shutil
import sqlite3
import time
from datetime import datetime

from logger import getLogger

log = getLogger(__name__)

_BACKUP_DIR_NAME = ".lan-invoice-backup"
_BACKUP_PATTERN = re.compile(r"^(?:invoices_(\d{8}_\d{6})\.db|data_(\d{8}_\d{6}))$")
_DEBOUNCE_SECONDS = 5


class BackupService:
    """在多个分区创建隐藏备份，支持防抖、恢复和清理"""

    def __init__(self, roots: list[str] | None = None):
        self._roots = roots
        self._roots_cache: list[str] | None = None
        self._last_backup_time: float = 0
        self._hidden_set: set[str] = set()

    # ── 分区探测 ──────────────────────────────

    def _get_roots(self) -> list[str]:
        if self._roots is not None:
            return self._roots
        if self._roots_cache is not None:
            return self._roots_cache
        self._roots_cache = self._detect_local_fixed_drives()
        return self._roots_cache

    @staticmethod
    def _detect_local_fixed_drives() -> list[str]:
        import sys
        if sys.platform != "win32":
            return [os.path.expanduser("~")]
        roots = []
        import string
        import ctypes
        DRIVE_FIXED = 3
        for letter in string.ascii_uppercase:
            p = f"{letter}:\\"
            try:
                # 仅选固定磁盘（本地硬盘），跳过网络/可移动/光驱
                dt = ctypes.windll.kernel32.GetDriveTypeW(p)
                if dt == DRIVE_FIXED:
                    roots.append(p)
            except Exception:
                pass
        return roots

    # ── 备份目录 ──────────────────────────────

    def get_backup_dirs(self) -> list[str]:
        dirs = []
        for root in self._get_roots():
            if not os.path.exists(root):
                continue
            d = os.path.join(root, _BACKUP_DIR_NAME)
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                continue
            if d not in self._hidden_set:
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(d, 2)
                except Exception:
                    pass
                self._hidden_set.add(d)
            dirs.append(d)
        return dirs

    # ── 备份 ──────────────────────────────────

    def force_backup(self, db_path: str) -> int:
        """绕过防抖强制执行一次备份（供关闭窗口等关键时机使用）"""
        self._last_backup_time = 0
        return self.backup(db_path)

    def backup(self, db_path: str) -> int:
        if not os.path.exists(db_path):
            log.warning("备份跳过：源文件不存在 %s", db_path)
            return 0
        now = time.time()
        if now - self._last_backup_time < _DEBOUNCE_SECONDS:
            return 0
        self._last_backup_time = now
        dirs = self.get_backup_dirs()
        data_dir = os.path.dirname(db_path)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        count = 0
        for d in dirs:
            sub = os.path.join(d, f"data_{ts}")
            try:
                os.makedirs(sub, exist_ok=True)
                # 复制整个数据目录（含 DB、PDF 发票、附件等所有文件）
                self._copy_tree(data_dir, sub)
                count += 1
            except OSError as e:
                log.warning("备份失败: %s → %s | %s", data_dir, sub, e)
        if count > 0:
            log.info("备份完成: %d 份 (含完整数据目录)", count)
        return count

    @staticmethod
    def _copy_tree(src: str, dst: str):
        """递归复制目录树，跳过 WAL/SHM 临时文件"""
        for entry in os.listdir(src):
            s = os.path.join(src, entry)
            d = os.path.join(dst, entry)
            if os.path.isdir(s):
                os.makedirs(d, exist_ok=True)
                BackupService._copy_tree(s, d)
            elif os.path.isfile(s):
                # 跳过 SQLite WAL/SHM 临时文件
                if entry.endswith(("-wal", "-shm")):
                    continue
                # 同名文件存在则跳过（不覆盖）
                if not os.path.exists(d):
                    shutil.copy2(s, d)

    # ── 恢复 ──────────────────────────────────

    def restore(self, db_path: str) -> bool:
        dirs = self.get_backup_dirs()
        latest = self._find_latest_valid_backup(dirs)
        if not latest:
            log.warning("无有效备份，无法恢复: %s", db_path)
            return False
        try:
            target_dir = os.path.dirname(db_path) or "."
            os.makedirs(target_dir, exist_ok=True)
            if os.path.isdir(latest):
                # 新格式：data_TIMESTAMP/ 目录，复制全部文件
                self._copy_tree(latest, target_dir)
            else:
                # 旧格式：单个 .db 文件
                shutil.copy2(latest, db_path)
            log.info("已从备份恢复: %s", latest)
            return True
        except OSError as e:
            log.error("恢复失败: %s → %s | %s", latest, db_path, e)
            return False

    def _find_latest_valid_backup(self, backup_dirs: list[str]) -> str | None:
        candidates = []
        for d in backup_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                m = _BACKUP_PATTERN.match(f)
                if m:
                    ts = m.group(1) or m.group(2) or ""
                    candidates.append((ts, os.path.join(d, f)))
        candidates.sort(key=lambda x: x[0], reverse=True)
        for _, fp in candidates:
            if os.path.isdir(fp):
                # 新格式目录
                db = os.path.join(fp, "invoices.db")
                if os.path.exists(db) and self._check_integrity(db):
                    return fp
            elif self._check_integrity(fp):
                return fp
        return None

    @staticmethod
    def _check_integrity(db_path: str) -> bool:
        try:
            with sqlite3.connect(db_path) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return result[0] == "ok"
        except sqlite3.Error:
            return False

    # ── 清理 ──────────────────────────────────

    def cleanup(self, keep_days: int = 30, min_keep: int = 3,
                max_keep: int = 30) -> int:
        cutoff = time.time() - keep_days * 86400
        dirs = self.get_backup_dirs()
        removed = 0
        for d in dirs:
            backups = []
            for f in os.listdir(d):
                m = _BACKUP_PATTERN.match(f)
                if m:
                    fp = os.path.join(d, f)
                    mtime = os.path.getmtime(fp)
                    backups.append((mtime, fp))
            backups.sort(key=lambda x: x[0], reverse=True)
            for i, (mtime, fp) in enumerate(backups):
                if i < min_keep:
                    continue
                if i >= max_keep or mtime < cutoff:
                    try:
                        if os.path.isdir(fp):
                            shutil.rmtree(fp)
                        else:
                            os.remove(fp)
                        removed += 1
                    except OSError:
                        pass
        if removed > 0:
            log.info("清理过期备份: %d 个", removed)
        return removed

    # ── 统计 ──────────────────────────────────

    def get_stats(self) -> dict:
        """返回所有分区的备份统计：份数、分区数、最近时间、总大小"""
        dirs = self.get_backup_dirs()
        entries = []
        for d in dirs:
            if not os.path.isdir(d):
                continue
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for f in names:
                m = _BACKUP_PATTERN.match(f)
                if not m:
                    continue
                fp = os.path.join(d, f)
                # 新格式：data_TIMESTAMP/ 目录（内含 invoices.db）
                if os.path.isdir(fp) and os.path.exists(os.path.join(fp, "invoices.db")):
                    entries.append((os.path.getmtime(fp), fp, d))
                # 旧格式：invoices_TIMESTAMP.db 单文件
                elif os.path.isfile(fp) and f.endswith(".db"):
                    entries.append((os.path.getmtime(fp), fp, d))

        if not entries:
            return {"count": 0, "partitions": 0, "latest": None, "size": 0}

        entries.sort(key=lambda x: x[0], reverse=True)
        latest_time = entries[0][0]
        partitions = set(e[2] for e in entries)
        total_size = 0
        for _, fp, _ in entries:
            total_size = self._count_size(fp, total_size)

        return {
            "count": len(entries),
            "partitions": len(partitions),
            "latest": datetime.fromtimestamp(latest_time).strftime("%Y-%m-%d %H:%M:%S"),
            "size": total_size,
        }

    @staticmethod
    def _count_size(fp: str, total_size: int) -> int:
        """递归统计路径大小，容错处理"""
        if os.path.isfile(fp):
            try:
                return total_size + os.path.getsize(fp)
            except OSError:
                return total_size
        try:
            for dirpath, _, filenames in os.walk(fp):
                for fn in filenames:
                    try:
                        total_size += os.path.getsize(os.path.join(dirpath, fn))
                    except OSError:
                        pass
        except OSError:
            pass
        return total_size
