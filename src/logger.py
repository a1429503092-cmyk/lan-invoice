# -*- coding: utf-8 -*-
"""
日志系统 — 集中配置，统一管理

用法:
    # 1. main() 开头一次性初始化
    from logger import setup_logging
    setup_logging(gui_error_callback=_show_error)

    # 2. 各模块获取 logger
    from logger import getLogger, log_call
    log = getLogger(__name__)

    # 3. 记录日志
    log.info("发票解析完成，共 %d 张", count)
    log.warning("文件不存在: %s", path)
    log.error("导出失败", exc_info=True)

    # 4. 函数耗时装饰
    @log_call
    def parse_invoice_pdf(path):
        ...

    # 5. 退出前
    from logger import shutdown_logging
    shutdown_logging()
"""

import sys
import os
import logging
import logging.handlers
import functools
import time
import traceback


# ── 路径 ────────────────────────────────────────

def _app_root() -> str:
    """项目根目录（打包后为 exe 所在目录，开发时为 src/ 的父目录）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：src/ 的父目录
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_dir() -> str:
    """日志目录：开发→项目根目录/logs，打包→%APPDATA%/lan-invoice/logs"""
    if getattr(sys, 'frozen', False):
        # 打包后统一写到用户目录，避免 UAC 权限问题
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                            "lan-invoice", "logs")
    # 开发环境：项目根目录/logs
    return os.path.join(_app_root(), "logs")


LOG_DIR = _log_dir()
LOG_FILE = os.path.join(LOG_DIR, "invoice_tool.log")

# ── 全局状态 ────────────────────────────────────

_excepthook_original = None
_gui_callback = None


# ── 对外 API ────────────────────────────────────

def getLogger(name: str | None = None) -> logging.Logger:
    """获取 Logger（等价于 logging.getLogger，统一入口）"""
    return logging.getLogger(name)


def setup_logging(gui_error_callback=None, stdout: bool = True) -> None:
    """
    集中配置日志系统。应在 main() 中 QApplication 创建后调用一次。

    gui_error_callback: 未捕获异常时弹出 GUI 错误对话框的回调
                       签名: callback(title: str, message: str)
    stdout: 是否同时输出到控制台。MCP 模式（stdio 协议）必须传 False——
            stdout 是 JSON-RPC 数据通道，混入日志会破坏协议
    """
    global _gui_callback
    _gui_callback = gui_error_callback

    os.makedirs(LOG_DIR, exist_ok=True)

    # ── 格式 ──────────────────────────────────
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── 文件处理器：DEBUG+ │ 5MB × 5 备份 ────
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # ── 配置根 Logger ─────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(file_handler)

    # ── 控制台处理器：INFO+（开发用）──────────
    # MCP/HTTP 无头模式不接控制台：stdout 可能是协议通道或父进程管道
    if stdout:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # ── 压制第三方库 DEBUG 噪音 ───────────────
    for noisy in ("pdfminer", "PIL", "fitz"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # ── 安装钩子 ──────────────────────────────
    _install_excepthook()
    _install_qt_message_handler()

    # ── 启动标记 ──────────────────────────────
    log = logging.getLogger("invoice_tool")
    log.info("=" * 50)
    log.info("日志系统就绪 | %s", "打包版" if getattr(sys, 'frozen', False) else "开发版")
    log.info("日志文件: %s", LOG_FILE)
    log.info("Python %s | 平台 %s", sys.version.split()[0], sys.platform)
    log.info("=" * 50)


def shutdown_logging():
    """应用退出前关闭日志，确保缓存写入磁盘"""
    log = logging.getLogger("invoice_tool")
    log.info("日志系统关闭")
    logging.shutdown()


# ── sys.excepthook ──────────────────────────────

def _install_excepthook():
    """替换 sys.excepthook：所有未捕获异常 → 日志 + GUI 弹窗"""
    global _excepthook_original
    _excepthook_original = sys.excepthook

    def excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        root_logger = logging.getLogger("invoice_tool")
        root_logger.critical("未捕获异常\n%s", tb_text)

        if _gui_callback is not None:
            try:
                _gui_callback("程序错误",
                              f"发票归档遇到未预期的错误：\n\n{exc_value}")
            except Exception:
                pass

        # 恢复原始行为
        if _excepthook_original is not None and \
           _excepthook_original is not sys.__excepthook__:
            _excepthook_original(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook


# ── Qt 消息处理器 ───────────────────────────────

def _install_qt_message_handler():
    """将 Qt C++ 层的 qDebug/qWarning/qCritical 转发到 Python logging"""
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
    except ImportError:
        return

    LEVEL_MAP = {
        QtMsgType.QtDebugMsg:    logging.DEBUG,
        QtMsgType.QtInfoMsg:     logging.INFO,
        QtMsgType.QtWarningMsg:  logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg:    logging.CRITICAL,
    }

    def handler(qt_msg_type, context, message):
        level = LEVEL_MAP.get(qt_msg_type, logging.WARNING)
        logger = logging.getLogger("qt")
        extra = ""
        if context.file:
            extra += f" [{context.file}"
            if context.line:
                extra += f":{context.line}"
            extra += "]"
        logger.log(level, "[Qt]%s %s", extra, message)

    qInstallMessageHandler(handler)


# ── 函数耗时装饰器 ─────────────────────────────

def log_call(func):
    """
    同步函数耗时日志装饰器。
    DEBUG: 进入/退出 + 耗时
    ERROR: 异常时记录完整 traceback
    """
    func_logger = logging.getLogger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        args_repr = _compact_args(args, kwargs)
        func_logger.debug("→ %s(%s)", func.__qualname__, args_repr)
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            func_logger.debug("← %s (%.3fs)", func.__qualname__, elapsed)
            return result
        except Exception:
            elapsed = time.perf_counter() - start
            func_logger.error("✗ %s 失败 (%.3fs)",
                              func.__qualname__, elapsed, exc_info=True)
            raise

    return wrapper


def log_thread(method):
    """
    QThread.run() 专用装饰器：记录线程生命周期（INFO 级别）。
    异常不 re-raise（QThread 会吞掉异常）。
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        logger = logging.getLogger(type(self).__module__)
        name = type(self).__name__
        logger.info("▶ %s 启动", name)
        start = time.perf_counter()
        try:
            result = method(self, *args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info("■ %s 完成 (%.3fs)", name, elapsed)
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error("✗ %s 异常 (%.3fs): %s", name, elapsed, e, exc_info=True)
            return None

    return wrapper


def _compact_args(args, kwargs) -> str:
    """缩短参数表示，避免日志过长"""
    parts = []
    for a in args:
        if isinstance(a, str):
            parts.append(repr(a[:80] + "…" if len(a) > 80 else a))
        else:
            parts.append(type(a).__name__)
    for k, v in kwargs.items():
        parts.append(f"{k}={type(v).__name__}")
    return ", ".join(parts) if parts else ""
