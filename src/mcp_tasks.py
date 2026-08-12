# -*- coding: utf-8 -*-
"""MCP Tasks 扩展 — 异步任务管理器

实现 io.modelcontextprotocol/tasks 扩展，用于长时间运行的操作
（如批量导入 100+ PDF）不阻塞 MCP 连接。
"""

import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from typing import Callable, Any

from logger import getLogger

log = getLogger(__name__)

# ── 常量 ────────────────────────────────────

DEFAULT_POLL_INTERVAL_MS = 2000   # 建议轮询间隔
DEFAULT_TTL_MS = 3_600_000        # 任务存活时间（1 小时）
CLEANUP_INTERVAL_S = 300          # 清理周期（5 分钟）


# ── 任务数据模型 ────────────────────────────

@dataclass
class Task:
    id: str
    name: str
    status: str  # working | completed | failed | cancelled
    created_at: float
    ttl_ms: int = DEFAULT_TTL_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    progress: int = 0           # 0-100
    status_message: str = ""    # 可读进度描述
    result: Any = None
    error: dict | None = None

    _future: Future | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def to_dict(self) -> dict:
        """返回符合 MCP Tasks 协议的 Task 对象。"""
        d = {
            "taskId": self.id,
            "status": self.status,
            "createdAt": self.created_at,
            "ttlMs": self.ttl_ms,
            "pollIntervalMs": self.poll_interval_ms,
        }
        if self.progress > 0:
            d["progress"] = self.progress
        if self.status_message:
            d["statusMessage"] = self.status_message
        if self.status == "completed" and self.result is not None:
            d["result"] = self.result
        if self.status == "failed" and self.error:
            d["error"] = self.error
        return d

    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    def set_progress(self, pct: int, message: str = ""):
        with self._lock:
            self.progress = max(0, min(100, pct))
            if message:
                self.status_message = message

    def set_result(self, result: Any):
        with self._lock:
            self.status = "completed"
            self.result = result
            self.progress = 100

    def set_error(self, code: int, message: str):
        with self._lock:
            self.status = "failed"
            self.error = {"code": code, "message": message}

    def set_cancelled(self):
        with self._lock:
            self.status = "cancelled"
            self.status_message = "已取消"


# ── 任务管理器 ──────────────────────────────

class TaskManager:
    """管理 MCP Tasks 的生命周期：创建、轮询、取消、清理。"""

    def __init__(self, max_workers: int = 4):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._cleanup_thread: threading.Thread | None = None
        self._running = True
        self._start_cleanup()

    def submit(self, name: str, fn: Callable, *args, **kwargs) -> str:
        """提交一个新任务，返回 taskId。"""
        task_id = uuid.uuid4().hex[:12]
        task = Task(
            id=task_id,
            name=name,
            status="working",
            created_at=time.time(),
            status_message="排队中...",
        )
        with self._lock:
            self._tasks[task_id] = task

        future = self._executor.submit(self._run, task, fn, *args, **kwargs)
        task._future = future
        log.debug("任务已提交: %s (%s)", task_id, name)
        return task_id

    def get(self, task_id: str) -> dict | None:
        """获取任务状态，用于响应 tasks/get。"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    def cancel(self, task_id: str) -> bool:
        """请求取消任务。返回 True 表示已发送取消信号。"""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        with task._lock:
            if task.is_terminal():
                return False  # 已结束，无法取消
        if task._future:
            cancelled = task._future.cancel()
            if cancelled:
                task.set_cancelled()
            return cancelled
        return False

    def shutdown(self):
        """关闭管理器，等待所有运行中任务完成。"""
        self._running = False
        self._executor.shutdown(wait=True)

    # ── 内部 ────────────────────────────────

    def _run(self, task: Task, fn: Callable, *args, **kwargs):
        """在线程池中执行任务函数。fn 签名为 fn(task: Task, *args, **kwargs) -> result"""
        try:
            task.set_progress(0, "处理中...")
            result = fn(task, *args, **kwargs)
            task.set_result(result)
            log.info("任务完成: %s", task.id)
        except Exception as e:
            task.set_error(-32603, str(e))
            log.warning("任务失败: %s | %s", task.id, e)

    def _start_cleanup(self):
        """后台线程：定期清理过期的已完成任务。"""
        def _clean_loop():
            while self._running:
                time.sleep(CLEANUP_INTERVAL_S)
                now = time.time()
                with self._lock:
                    expired = [
                        tid for tid, t in self._tasks.items()
                        if t.is_terminal()
                        and (now - t.created_at) * 1000 > t.ttl_ms
                    ]
                    for tid in expired:
                        del self._tasks[tid]
                if expired:
                    log.debug("任务清理: %d 个过期", len(expired))

        self._cleanup_thread = threading.Thread(target=_clean_loop, daemon=True)
        self._cleanup_thread.start()


# ── 全局单例 ────────────────────────────────

_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
