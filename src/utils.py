# -*- coding: utf-8 -*-
"""通用工具函数"""

import os
import shutil

from logger import getLogger

log = getLogger(__name__)


def copy_file_to_dir(src: str, dst_dir: str) -> str:
    """复制文件到目标目录，自动处理重名冲突；返回目标路径。失败返回原路径。"""
    if not src or not os.path.isfile(src):
        log.warning("文件复制跳过: 源文件无效 %s", src)
        return src
    os.makedirs(dst_dir, exist_ok=True)
    fname = os.path.basename(src)
    dst = os.path.join(dst_dir, fname)
    counter = 1
    while os.path.exists(dst):
        name, ext = os.path.splitext(fname)
        dst = os.path.join(dst_dir, f"{name}_{counter}{ext}")
        counter += 1
    try:
        shutil.copy2(src, dst)
        return dst
    except OSError as e:
        log.error("文件复制失败: %s → %s | %s", src, dst_dir, e)
        return src


def safe_float(val) -> float:
    """安全转为 float，失败返回 0.0"""
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0
