# -*- coding: utf-8 -*-
"""通用工具函数"""

import os
import shutil


def copy_file_to_dir(src: str, dst_dir: str) -> str:
    """复制文件到目标目录，自动处理重名冲突；返回目标路径。失败返回原路径。"""
    if not src or not os.path.isfile(src):
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
    except OSError:
        return src
