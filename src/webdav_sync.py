# -*- coding: utf-8 -*-
"""WebDAV 增量备份 — MD5 manifest 驱动，仅同步变更文件"""

import os
import json
import hashlib
from typing import Callable

from logger import getLogger

log = getLogger(__name__)


class SyncManifest:
    """增量同步清单：记录每个文件的 MD5，用于计算增量"""

    def __init__(self, data_dir: str):
        self._path = os.path.join(data_dir, "sync_manifest.json")
        self._files: dict[str, str] = {}  # relpath → md5
        self._pending: dict[str, str] | None = None  # 待提交的快照

    def load(self):
        try:
            with open(self._path, encoding="utf-8") as f:
                self._files = json.load(f)
        except (OSError, json.JSONDecodeError):
            self._files = {}

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._files, f, ensure_ascii=False)
        except OSError as e:
            log.warning("同步清单保存失败: %s", e)

    def scan(self, data_dir: str) -> dict[str, list[str]]:
        """扫描数据目录，返回 {added, modified, deleted}。不修改 _files。"""
        current: dict[str, str] = {}
        for root, _dirs, files in os.walk(data_dir):
            for f in files:
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, data_dir).replace("\\", "/")
                if rel.startswith("sync_manifest."):
                    continue
                current[rel] = _md5(fp)

        added = [r for r, m in current.items() if r not in self._files]
        modified = [r for r, m in current.items() if r in self._files and self._files[r] != m]
        deleted = [r for r in self._files if r not in current]
        self._pending = current  # 暂存，等同步成功后再 commit
        return {"added": added, "modified": modified, "deleted": deleted}

    def commit(self):
        """确认当前扫描结果已成功同步"""
        if self._pending is not None:
            self._files = self._pending
            self._pending = None
            self.save()

    def rollback(self):
        """放弃当前扫描结果"""
        self._pending = None


def _md5(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_client(webdav_url: str, username: str = "", password: str = ""):
    """创建 webdavclient3 实例"""
    opts = {"webdav_hostname": webdav_url.rstrip("/"),
            "webdav_login": username,
            "webdav_password": password,
            "webdav_timeout": 30}
    from webdav3.client import Client as DavClient
    return DavClient(opts)


def test_connection(webdav_url: str, username: str = "", password: str = "") -> bool:
    """测试 WebDAV 连接"""
    try:
        client = _make_client(webdav_url, username, password)
        return client.check()
    except Exception:
        return False


def sync_to_webdav(data_dir: str, webdav_url: str, username: str = "",
                   password: str = "", progress: Callable[[str], None] = None) -> dict:
    """增量同步数据目录到 WebDAV"""
    if not webdav_url:
        return {"error": "未配置 WebDAV"}

    def report(msg):
        if progress:
            progress(msg)
        log.info(msg)

    try:
        client = _make_client(webdav_url, username, password)
    except ImportError:
        report("WebDAV 依赖未安装 (webdavclient3)")
        return {"error": "缺少依赖", "failed": 0}

    if not client.check():
        report("WebDAV 连接失败，跳过同步")
        return {"error": "连接失败", "failed": 0}

    manifest = SyncManifest(data_dir)
    manifest.load()

    report("扫描本地文件…")
    diff = manifest.scan(data_dir)

    total = len(diff["added"]) + len(diff["modified"]) + len(diff["deleted"])
    if total == 0:
        report("无变更，跳过同步")
        manifest.rollback()
        return {"added": 0, "modified": 0, "deleted": 0, "failed": 0}

    report(f"同步 {total} 文件 (新增 {len(diff['added'])} "
           f"修改 {len(diff['modified'])} 删除 {len(diff['deleted'])})")

    failed = 0
    for rel in diff["deleted"]:
        try:
            client.clean(rel)
        except Exception as e:
            log.warning("远程删除失败 %s: %s", rel, e)
            failed += 1

    for rel in diff["added"] + diff["modified"]:
        try:
            lp = os.path.join(data_dir, rel)
            if os.path.isfile(lp):
                # force=True 自动递归创建远程子目录
                client.upload_sync(remote_path=rel, local_path=lp)
        except Exception as e:
            log.warning("上传失败 %s: %s", rel, e)
            failed += 1

    result = {"added": len(diff["added"]), "modified": len(diff["modified"]),
              "deleted": len(diff["deleted"]), "failed": failed}

    if failed == 0:
        manifest.commit()
    else:
        report(f"同步有 {failed} 个失败，清单未更新，下次重试")
        manifest.rollback()

    report(f"同步完成: {result}")
    return result


def restore_from_webdav(data_dir: str, webdav_url: str, username: str = "",
                        password: str = "", progress: Callable[[str], None] = None) -> bool:
    """从 WebDAV 一键恢复整个数据目录"""
    try:
        client = _make_client(webdav_url, username, password)
    except (ImportError, Exception):
        return False

    def report(msg):
        if progress:
            progress(msg)

    report("获取远程文件列表…")
    try:
        files = client.list(remote_path="/")
        files = [f for f in files if f and not f.endswith("/")]
    except Exception:
        return False

    if not files:
        report("远程无文件")
        return False

    report(f"恢复 {len(files)} 个文件…")
    count = 0
    for rel in files:
        rel = rel.lstrip("/")
        lp = os.path.join(data_dir, rel)
        try:
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            client.download_sync(remote_path=rel, local_path=lp)
            count += 1
        except Exception as e:
            log.warning("下载失败 %s: %s", rel, e)

    report(f"恢复完成: {count}/{len(files)}")
    return count > 0
