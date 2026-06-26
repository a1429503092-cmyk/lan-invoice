# -*- coding: utf-8 -*-
"""通用工具函数"""

import os
import hashlib
import shutil

from logger import getLogger

log = getLogger(__name__)


def file_md5(filepath: str) -> str | None:
    """计算文件 MD5，失败返回 None"""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _find_md5_in_dir(directory: str, target_md5: str) -> str | None:
    """在目录中搜索具有指定 MD5 的文件，返回路径或 None"""
    if not os.path.isdir(directory):
        return None
    for fname in os.listdir(directory):
        fp = os.path.join(directory, fname)
        if not os.path.isfile(fp):
            continue
        if file_md5(fp) == target_md5:
            return fp
    return None


def copy_file_to_dir(src: str, dst_dir: str) -> str:
    """复制文件到目标目录；MD5 去重：内容相同则复用已有文件。失败返回原路径。"""
    if not src or not os.path.isfile(src):
        log.warning("文件复制跳过: 源文件无效 %s", src)
        return src
    src_md5 = file_md5(src)
    if src_md5:
        existing = _find_md5_in_dir(dst_dir, src_md5)
        if existing:
            log.info("MD5 去重: %s → %s", os.path.basename(src), existing)
            return existing
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
