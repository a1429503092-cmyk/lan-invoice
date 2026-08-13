# -*- coding: utf-8 -*-
"""更新检查 — 从 Gitee Releases 获取最新版本信息"""

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


GITEE_API = "https://gitee.com/api/v5/repos/GUYI33/lan-invoice/releases/latest"


class UpdateChecker(QObject):

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._current = current_version
        self._skipped: str = ""
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_reply)

    def set_skipped_version(self, ver: str):
        self._skipped = ver

    def check(self):
        req = QNetworkRequest(QUrl(GITEE_API))
        req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        self._nam.get(req)

    def _on_reply(self, reply: QNetworkReply):
        if reply.error() != QNetworkReply.NoError:
            self.check_finished.emit(False, "", "")
            reply.deleteLater()
            return
        try:
            import json
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag = data.get("tag_name", "").lstrip("v")
            if not tag:
                return
            # 优先使用直接下载链接（assets），无附件时回退到 tag 页面
            download_url = ""
            assets = data.get("assets") or []
            if assets:
                download_url = assets[0].get("browser_download_url", "")
            if not download_url:
                download_url = f"https://gitee.com/GUYI33/lan-invoice/releases/tag/v{tag}"
            if self._version_gt(tag, self._current):
                if self._skipped and tag == self._skipped:
                    self.check_finished.emit(True, self._current, "")
                else:
                    self.new_version_found.emit(tag, download_url)
            else:
                self.check_finished.emit(True, self._current, "")
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            self.check_finished.emit(False, "", "")
        finally:
            reply.deleteLater()

    @staticmethod
    def _version_gt(a: str, b: str) -> bool:
        """判断版本号 a 是否大于 b，支持 x.y.z 格式"""
        try:
            from itertools import zip_longest
            for x, y in zip_longest(a.split("."), b.split("."), fillvalue="0"):
                if int(x) > int(y):
                    return True
                if int(x) < int(y):
                    return False
            return False
        except ValueError:
            return a != b

    from PyQt5.QtCore import pyqtSignal
    new_version_found = pyqtSignal(str, str)
    check_finished = pyqtSignal(bool, str, str)
