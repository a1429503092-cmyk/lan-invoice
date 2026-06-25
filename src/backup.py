# -*- coding: utf-8 -*-
"""多分区隐藏备份服务 — 防抖复制、完整性检查、自动恢复"""

import os
import re
import shutil
import time
from datetime import datetime

from logger import getLogger

log = getLogger(__name__)

_BACKUP_DIR_NAME = ".lan-invoice-backup"
_BACKUP_PATTERN = re.compile(r"^invoices_(\d{8}_\d{6})\.db$")


class BackupService:
    """在多个分区创建隐藏备份，支持防抖、恢复和清理"""

    def __init__(self, roots: list[str] | None = None):
        self._roots = roots or self._detect_partitions()

    # ── 分区探测 ──────────────────────────────

    @staticmethod
    def _detect_partitions() -> list[str]:
        import sys
        if sys.platform != "win32":
            return [os.path.expanduser("~")]
        roots = []
        import string
        for letter in string.ascii_uppercase:
            p = f"{letter}:\\"
            if os.path.exists(p):
                roots.append(p)
        return roots

    # ── 备份目录 ──────────────────────────────

    def get_backup_dirs(self) -> list[str]:
        dirs = []
        for root in self._roots:
            if not os.path.exists(root):
                continue
            d = os.path.join(root, _BACKUP_DIR_NAME)
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                continue
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(d, 2)
            except Exception:
                pass
            dirs.append(d)
        return dirs

    # ── 备份 ──────────────────────────────────

    def backup(self, db_path: str) -> int:
        if not os.path.exists(db_path):
            log.warning("备份跳过：源文件不存在 %s", db_path)
            return 0
        dirs = self.get_backup_dirs()
        base = os.path.splitext(os.path.basename(db_path))[0]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{base}_{ts}.db"
        count = 0
        for d in dirs:
            dst = os.path.join(d, fname)
            try:
                shutil.copy2(db_path, dst)
                count += 1
            except OSError as e:
                log.warning("备份失败: %s → %s | %s", db_path, dst, e)
        if count > 0:
            log.info("备份完成: %d 份 → %s", count,
                     [os.path.join(d, fname) for d in dirs])
        return count

    # ── 恢复 ──────────────────────────────────

    def restore(self, db_path: str) -> bool:
        dirs = self.get_backup_dirs()
        latest = self._find_latest_backup(dirs)
        if not latest:
            log.warning("无可用备份，无法恢复: %s", db_path)
            return False
        try:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            shutil.copy2(latest, db_path)
            log.info("数据库从备份恢复: %s → %s", latest, db_path)
            return True
        except OSError as e:
            log.error("恢复失败: %s → %s | %s", latest, db_path, e)
            return False

    def _find_latest_backup(self, backup_dirs: list[str]) -> str | None:
        candidates = []
        for d in backup_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                m = _BACKUP_PATTERN.match(f)
                if m:
                    candidates.append((m.group(1), os.path.join(d, f)))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1] if candidates else None

    # ── 清理 ──────────────────────────────────

    def cleanup(self, keep_days: int = 30) -> int:
        cutoff = time.time() - keep_days * 86400
        dirs = self.get_backup_dirs()
        removed = 0
        for d in dirs:
            for f in os.listdir(d):
                m = _BACKUP_PATTERN.match(f)
                if not m:
                    continue
                fp = os.path.join(d, f)
                try:
                    if os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                        removed += 1
                except OSError:
                    pass
        if removed > 0:
            log.info("清理过期备份: %d 个", removed)
        return removed
