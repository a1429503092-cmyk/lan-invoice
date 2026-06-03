# -*- coding: utf-8 -*-
"""图标生成器 — 蓝印档案室风格

设计约束：
- 色彩：档案蓝 #2879D0 / 白 #FFFFFF / 墨色 #1A2130 / 警示红 #DC2626 / 通过绿 #16A34A
- 风格：锐利几何、2px 线宽、无渐变、无投影、微圆角
- 尺寸：常规 24×24，小号 16×16，应用图标 256×256
"""

import os
import math
from PIL import Image, ImageDraw

# ── 设计系统色彩 ──────────────────────────────
ACCENT   = (0x28, 0x79, 0xD0)   # #2879D0 档案蓝
INK      = (0x1A, 0x21, 0x30)   # #1A2130 正文墨色
RED      = (0xDC, 0x26, 0x26)   # #DC2626 警示红
GREEN    = (0x16, 0xA3, 0x4A)   # #16A34A 通过绿
WHITE    = (0xFF, 0xFF, 0xFF)   # 白
BG       = (0xF2, 0xF4, 0xF6)   # 冷灰底
LIGHT_BG = (0xE8, 0xF1, 0xFB)   # 浅蓝底
MUTED    = (0x8F, 0x99, 0xA8)   # 三级灰文

ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src", "ui", "icons")
OS_MKDIR = os.makedirs(ICON_DIR, exist_ok=True)


def draw_rounded_rect(draw, xy, r, fill=None, outline=None, width=1):
    """绘制圆角矩形"""
    x1, y1, x2, y2 = xy
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    # 圆角
    draw.pieslice([x1, y1, x1 + 2 * r, y1 + 2 * r], 180, 270, fill=fill)
    draw.pieslice([x2 - 2 * r, y1, x2, y1 + 2 * r], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - 2 * r, x1 + 2 * r, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - 2 * r, y2 - 2 * r, x2, y2], 0, 90, fill=fill)
    # 矩形主体
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)
    # 边框
    if outline:
        draw.arc([x1, y1, x1 + 2 * r, y1 + 2 * r], 180, 270, fill=outline, width=width)
        draw.arc([x2 - 2 * r, y1, x2, y1 + 2 * r], 270, 360, fill=outline, width=width)
        draw.arc([x1, y2 - 2 * r, x1 + 2 * r, y2], 90, 180, fill=outline, width=width)
        draw.arc([x2 - 2 * r, y2 - 2 * r, x2, y2], 0, 90, fill=outline, width=width)
        draw.line([x1 + r, y1, x2 - r, y1], fill=outline, width=width)
        draw.line([x1 + r, y2, x2 - r, y2], fill=outline, width=width)
        draw.line([x1, y1 + r, x1, y2 - r], fill=outline, width=width)
        draw.line([x2, y1 + r, x2, y2 - r], fill=outline, width=width)


def new_icon(size=24):
    """创建透明背景的新图标"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def save_both(name, fn_24, fn_16=None):
    """生成 24px 和 16px 两个尺寸"""
    img24, d24 = new_icon(24)
    fn_24(img24, d24)
    path24 = os.path.join(ICON_DIR, f"{name}.png")
    img24.save(path24)
    print(f"  {name}.png (24×24)")

    if fn_16 is None:
        # 自动缩小
        img16 = img24.resize((16, 16), Image.LANCZOS)
    else:
        img16, d16 = new_icon(16)
        fn_16(img16, d16)
    path16 = os.path.join(ICON_DIR, f"{name}_16.png")
    img16.save(path16)
    print(f"  {name}_16.png (16×16)")


# ══════════════════════════════════════════════
# 各图标绘制函数
# ══════════════════════════════════════════════

def icon_folder(img, d):
    """文件夹 — 打开的文件夹形状"""
    S = img.size[0]
    # 文件夹标签
    d.rectangle([2, 4, 8, 6], fill=ACCENT)
    # 文件夹主体 (微圆角)
    draw_rounded_rect(d, (2, 6, S - 2, S - 2), r=1, fill=ACCENT)
    # 高光线
    d.rectangle([3, 4, 5, 6], fill=ACCENT)

def icon_folder_16(img, d):
    d.rectangle([1, 3, 5, 5], fill=ACCENT)
    draw_rounded_rect(d, (1, 5, 14, 14), r=1, fill=ACCENT)


def icon_clear(img, d):
    """清空 — X 删除符号"""
    S = img.size[0]
    cx, cy = S // 2, S // 2
    r = 9
    # 圆形背景
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=None, outline=MUTED, width=2)
    # X 标记
    off = 4
    d.line([cx - off, cy - off, cx + off, cy + off], fill=MUTED, width=2)
    d.line([cx + off, cy - off, cx - off, cy + off], fill=MUTED, width=2)

def icon_clear_16(img, d):
    cx, cy = 8, 8
    d.ellipse([1, 1, 14, 14], outline=MUTED, width=1)
    d.line([5, 5, 10, 10], fill=MUTED, width=2)
    d.line([10, 5, 5, 10], fill=MUTED, width=2)


def icon_settings(img, d):
    """设置 — 齿轮"""
    S = img.size[0]
    cx, cy = S // 2, S // 2
    r_outer, r_inner = 8, 4
    # 中心圆
    d.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
              outline=INK, width=2)
    # 齿
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = cx + (r_inner + 1) * math.cos(rad)
        y1 = cy + (r_inner + 1) * math.sin(rad)
        x2 = cx + r_outer * math.cos(rad)
        y2 = cy + r_outer * math.sin(rad)
        d.line([x1, y1, x2, y2], fill=INK, width=2)
    # 外环
    d.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
              outline=INK, width=2)

def icon_settings_16(img, d):
    cx, cy = 8, 8
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], outline=INK, width=1)
    for a in range(0, 360, 60):
        rad = math.radians(a)
        x1 = cx + 2.5 * math.cos(rad); y1 = cy + 2.5 * math.sin(rad)
        x2 = cx + 5.5 * math.cos(rad); y2 = cy + 5.5 * math.sin(rad)
        d.line([x1, y1, x2, y2], fill=INK, width=1)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=INK, width=1)


def icon_export(img, d):
    """导出 — 简洁向上的箭头 + 底部横托盘"""
    S = img.size[0]
    # 底盘
    d.rectangle([4, S - 5, S - 4, S - 2], fill=ACCENT)
    # 上箭头
    cx = S // 2
    # 箭头尖
    d.polygon([(cx, 2), (cx - 6, 13), (cx + 6, 13)], fill=ACCENT)
    # 箭头身（略窄于三角形底边，使其视觉上从三角形内穿出）
    d.rectangle([cx - 2, 11, cx + 2, S - 5], fill=ACCENT)

def icon_export_16(img, d):
    d.rectangle([2, 12, 13, 14], fill=ACCENT)
    d.polygon([(8, 1), (4, 8), (12, 8)], fill=ACCENT)
    d.rectangle([7, 7, 9, 12], fill=ACCENT)


def icon_camera(img, d):
    """相机 — 拍照图标"""
    S = img.size[0]
    # 相机主体
    draw_rounded_rect(d, (2, 7, S - 2, S - 3), r=2, fill=INK)
    # 镜头
    r_lens = 4
    cx, cy = S // 2, S // 2 + 2
    d.ellipse([cx - r_lens, cy - r_lens, cx + r_lens, cy + r_lens],
              outline=WHITE, width=2)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=WHITE)
    # 闪光灯/顶部
    d.rectangle([8, 5, S - 6, 7], fill=INK)

def icon_camera_16(img, d):
    draw_rounded_rect(d, (1, 5, 14, 14), r=1, fill=INK)
    d.ellipse([5, 7, 11, 13], outline=WHITE, width=1)
    d.ellipse([7, 9, 9, 11], fill=WHITE)
    d.rectangle([6, 3, 10, 5], fill=INK)


def icon_clipboard(img, d):
    """剪贴板 — 粘贴板"""
    S = img.size[0]
    # 板体
    draw_rounded_rect(d, (3, 7, S - 3, S - 2), r=1, fill=INK)
    # 顶部夹子
    d.rectangle([7, 3, S - 7, 7], fill=INK)
    # 内容线
    for y_off in [10, 13, 16]:
        d.line([6, y_off, S - 6, y_off], fill=WHITE, width=1)

def icon_clipboard_16(img, d):
    draw_rounded_rect(d, (2, 5, 13, 14), r=1, fill=INK)
    d.rectangle([5, 2, 10, 5], fill=INK)
    for y in [7, 9, 11]:
        d.line([4, y, 11, y], fill=WHITE, width=1)


def icon_search(img, d):
    """搜索 — 放大镜"""
    S = img.size[0]
    # 镜片
    cx, cy = 10, 10
    r = 6
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INK, width=2)
    # 手柄
    d.line([14, 14, S - 2, S - 2], fill=INK, width=3)

def icon_search_16(img, d):
    d.ellipse([2, 2, 10, 10], outline=INK, width=1)
    d.line([9, 9, 14, 14], fill=INK, width=2)


def icon_delete(img, d):
    """删除 — 垃圾桶"""
    S = img.size[0]
    # 桶盖
    d.rectangle([5, 4, S - 5, 6], fill=RED)
    d.rectangle([3, 6, S - 3, 7], fill=RED)
    # 桶体
    draw_rounded_rect(d, (6, 7, S - 6, S - 3), r=1, fill=RED)
    # 竖线
    d.line([S // 2 - 2, 9, S // 2 - 2, S - 6], fill=WHITE, width=1)
    d.line([S // 2 + 2, 9, S // 2 + 2, S - 6], fill=WHITE, width=1)

def icon_delete_16(img, d):
    d.rectangle([3, 3, 12, 4], fill=RED)
    d.rectangle([2, 4, 13, 5], fill=RED)
    draw_rounded_rect(d, (4, 5, 11, 14), r=1, fill=RED)
    d.line([7, 7, 7, 12], fill=WHITE, width=1)
    d.line([8, 7, 8, 12], fill=WHITE, width=1)


def icon_document(img, d):
    """文档 — 合同文件"""
    S = img.size[0]
    # 文档主体
    draw_rounded_rect(d, (4, 3, S - 4, S - 3), r=1, fill=INK)
    # 折角
    d.polygon([(S - 6, 3), (S - 6, 8), (S - 9, 3)], fill=LIGHT_BG)
    d.line([S - 6, 3, S - 6, 8, S - 9, 3], fill=INK, width=1)
    # 内容线
    for y_off, w in [(7, S - 10), (10, S - 12), (13, S - 8), (16, S - 10)]:
        d.line([7, y_off, w, y_off], fill=WHITE, width=1)

def icon_document_16(img, d):
    draw_rounded_rect(d, (2, 2, 12, 13), r=1, fill=INK)
    d.polygon([(10, 2), (10, 5), (8, 2)], fill=LIGHT_BG)
    for y, w in [(5, 9), (7, 10), (9, 8)]:
        d.line([4, y, w, y], fill=WHITE, width=1)


def icon_save(img, d):
    """保存 — 下载箭头"""
    S = img.size[0]
    # 向下箭头
    cx = S // 2
    d.polygon([(cx, S - 3), (cx - 7, S - 9), (cx + 7, S - 9)], fill=ACCENT)
    # 箭头身
    d.rectangle([cx - 2, 4, cx + 2, S - 7], fill=ACCENT)

def icon_save_16(img, d):
    d.polygon([(8, 14), (2, 8), (14, 8)], fill=ACCENT)
    d.rectangle([6, 2, 9, 8], fill=ACCENT)


def icon_package(img, d):
    """打包 — 盒子"""
    S = img.size[0]
    # 盒体
    draw_rounded_rect(d, (3, 8, S - 3, S - 3), r=1, fill=INK)
    # 盒盖
    d.polygon([(3, 8), (S // 2, 2), (S - 3, 8)], fill=INK)
    # 高光线
    d.line([S // 2, 3, S // 2, S - 4], fill=WHITE, width=1)

def icon_package_16(img, d):
    draw_rounded_rect(d, (2, 5, 13, 14), r=1, fill=INK)
    d.polygon([(2, 5), (8, 1), (13, 5)], fill=INK)
    d.line([8, 2, 8, 13], fill=WHITE, width=1)


def icon_warning(img, d):
    """警告 — 三角感叹号"""
    S = img.size[0]
    # 三角
    d.polygon([(S // 2, 2), (2, S - 2), (S - 2, S - 2)], outline=RED, fill=None)
    d.polygon([(S // 2, 3), (3, S - 3), (S - 3, S - 3)], fill=RED)
    # 中心镂白感叹号
    d.rectangle([S // 2 - 2, 9, S // 2 + 2, 14], fill=WHITE)
    d.rectangle([S // 2 - 2, 16, S // 2 + 2, 16], fill=WHITE)

def icon_warning_16(img, d):
    d.polygon([(8, 1), (1, 14), (14, 14)], fill=RED)
    d.rectangle([7, 6, 9, 9], fill=WHITE)
    d.rectangle([7, 10, 9, 10], fill=WHITE)


def icon_check(img, d):
    """确认 — 对勾"""
    S = img.size[0]
    # 绿色圆形背景
    d.ellipse([2, 2, S - 2, S - 2], fill=GREEN)
    # 白色对勾
    pts = [(7, 13), (10, 18), (18, 8)]
    d.line(pts, fill=WHITE, width=3)

def icon_check_16(img, d):
    d.ellipse([1, 1, 14, 14], fill=GREEN)
    d.line([(5, 8), (7, 11), (11, 5)], fill=WHITE, width=2)


def icon_add(img, d):
    """添加 — 加号"""
    S = img.size[0]
    # 圆形背景
    d.ellipse([2, 2, S - 2, S - 2], fill=ACCENT)
    # 白色加号
    cx = S // 2
    d.rectangle([cx - 3, 8, cx + 4, 16], fill=WHITE)
    d.rectangle([8, cx - 3, 16, cx + 4], fill=WHITE)

def icon_add_16(img, d):
    d.ellipse([1, 1, 14, 14], fill=ACCENT)
    d.rectangle([6, 4, 10, 12], fill=WHITE)
    d.rectangle([4, 6, 12, 10], fill=WHITE)


def icon_arrow_left(img, d):
    """左箭头"""
    S = img.size[0]
    d.polygon([(S - 4, 3), (4, S // 2), (S - 4, S - 3)], fill=INK)

def icon_arrow_left_16(img, d):
    d.polygon([(11, 2), (3, 8), (11, 14)], fill=INK)


def icon_arrow_right(img, d):
    """右箭头"""
    S = img.size[0]
    d.polygon([(4, 3), (S - 4, S // 2), (4, S - 3)], fill=INK)

def icon_arrow_right_16(img, d):
    d.polygon([(5, 2), (13, 8), (5, 14)], fill=INK)


def icon_dot_blue(img, d):
    """蓝色圆点"""
    d.ellipse([6, 6, 18, 18], fill=ACCENT)

def icon_dot_blue_16(img, d):
    d.ellipse([4, 4, 12, 12], fill=ACCENT)


def icon_dot_red(img, d):
    """红色圆点"""
    d.ellipse([6, 6, 18, 18], fill=RED)

def icon_dot_red_16(img, d):
    d.ellipse([4, 4, 12, 12], fill=RED)


def icon_note(img, d):
    """备注 — 便签/笔"""
    S = img.size[0]
    # 便签纸
    draw_rounded_rect(d, (3, 3, S - 5, S - 5), r=1, fill=LIGHT_BG, outline=ACCENT, width=1)
    # 内容线
    for y_off in [7, 10, 13]:
        d.line([6, y_off, S - 8, y_off], fill=ACCENT, width=1)
    # 笔尖
    d.polygon([(S - 5, S - 5), (S - 1, S - 1), (S - 3, 17)], fill=INK)

def icon_note_16(img, d):
    draw_rounded_rect(d, (2, 2, 10, 10), r=1, fill=LIGHT_BG, outline=ACCENT, width=1)
    for y in [5, 7, 9]:
        d.line([4, y, 8, y], fill=ACCENT, width=1)
    d.polygon([(10, 10), (14, 14), (12, 10)], fill=INK)


def icon_paperclip(img, d):
    """附件 — 回形针"""
    S = img.size[0]
    # 外弧
    d.ellipse([5, 2, S - 1, 18], outline=INK, width=2)
    # 遮盖内圈
    d.ellipse([8, 5, S - 4, 15], fill=(0, 0, 0, 0), outline=INK, width=1)
    d.rectangle([S - 4, 10, S + 2, 15], fill=(0, 0, 0, 0))
    # 竖线
    d.line([6, 4, 6, 17], fill=INK, width=2)
    d.line([6, 17, 8, 20], fill=INK, width=2)
    # 顶部横线
    d.line([6, 4, 14, 4], fill=INK, width=2)

def icon_paperclip_16(img, d):
    d.ellipse([3, 1, 10, 12], outline=INK, width=1)
    d.ellipse([5, 3, 8, 10], fill=(0, 0, 0, 0), outline=INK, width=1)
    d.line([4, 3, 4, 12], fill=INK, width=1)
    d.line([4, 12, 6, 14], fill=INK, width=1)
    d.line([4, 3, 9, 3], fill=INK, width=1)


def icon_app_icon(img, d):
    """应用图标 256×256 — 蓝底白色发票文档 + 对勾"""
    S = img.size[0]
    # 圆角方形背景，档案蓝
    bg_r = 48
    draw_rounded_rect(d, (8, 8, S - 8, S - 8), r=bg_r, fill=ACCENT)

    # 白色文档
    doc_x, doc_y = 60, 40
    doc_w, doc_h = 136, 170
    doc_r = 16
    draw_rounded_rect(d, (doc_x, doc_y, doc_x + doc_w, doc_y + doc_h),
                       r=doc_r, fill=WHITE)
    # 文档折角
    fold_s = 36
    d.polygon([
        (doc_x + doc_w - fold_s, doc_y),
        (doc_x + doc_w - fold_s, doc_y + fold_s),
        (doc_x + doc_w, doc_y + fold_s),
    ], fill=LIGHT_BG)
    d.line([
        (doc_x + doc_w - fold_s, doc_y),
        (doc_x + doc_w - fold_s, doc_y + fold_s),
        (doc_x + doc_w, doc_y + fold_s),
    ], fill=ACCENT, width=3)

    # 文档上的线条 (模拟发票内容)
    line_color = (0x8F, 0x99, 0xA8, 200)
    lx = doc_x + 28
    for i, (w_pct, y_off) in enumerate([
        (0.5, 50), (0.7, 80), (0.6, 110), (0.4, 140), (0.3, 165)
    ]):
        lw = int(doc_w * w_pct) - 28
        d.rectangle([lx, doc_y + y_off, lx + lw, doc_y + y_off + 8],
                     fill=line_color)

    # 右下角绿色对勾圆形
    check_cx, check_cy = 172, 178
    check_r = 44
    d.ellipse([check_cx - check_r, check_cy - check_r,
               check_cx + check_r, check_cy + check_r], fill=GREEN)
    # 白色对勾
    pts = [
        (check_cx - 18, check_cy + 2),
        (check_cx - 4, check_cy + 18),
        (check_cx + 20, check_cy - 14),
    ]
    d.line(pts, fill=WHITE, width=12)


# ══════════════════════════════════════════════
# 批量生成
# ══════════════════════════════════════════════

ICONS = [
    # (name, fn_24, fn_16_or_None)
    ("folder",     icon_folder,     icon_folder_16),
    ("clear",      icon_clear,      icon_clear_16),
    ("settings",   icon_settings,   icon_settings_16),
    ("export",     icon_export,     icon_export_16),
    ("camera",     icon_camera,     icon_camera_16),
    ("clipboard",  icon_clipboard,  icon_clipboard_16),
    ("search",     icon_search,     icon_search_16),
    ("delete",     icon_delete,     icon_delete_16),
    ("document",   icon_document,   icon_document_16),
    ("save",       icon_save,       icon_save_16),
    ("package",    icon_package,    icon_package_16),
    ("warning",    icon_warning,    icon_warning_16),
    ("check",      icon_check,      icon_check_16),
    ("add",        icon_add,        icon_add_16),
    ("arrow_left", icon_arrow_left, icon_arrow_left_16),
    ("arrow_right",icon_arrow_right,icon_arrow_right_16),
    ("dot_blue",   icon_dot_blue,   icon_dot_blue_16),
    ("dot_red",    icon_dot_red,    icon_dot_red_16),
    ("note",       icon_note,       icon_note_16),
    ("paperclip",  icon_paperclip,  icon_paperclip_16),
]


def generate_app_icon():
    """生成应用图标 (256×256)"""
    img, d = new_icon(256)
    icon_app_icon(img, d)
    path = os.path.join(ICON_DIR, "app_icon.png")
    img.save(path)
    print(f"  app_icon.png (256×256)")
    return img


def generate_ico(app_img):
    """从 app_icon.png 生成 icon.ico"""
    root = os.path.dirname(os.path.dirname(ICON_DIR))
    ico_path = os.path.join(root, "icon.ico")

    # 生成多尺寸 ICO: 256, 128, 64, 48, 32, 16
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    frames = []
    for sz in sizes:
        frames.append(app_img.resize(sz, Image.LANCZOS))

    frames[0].save(ico_path, format="ICO", sizes=[(f.width, f.height) for f in frames],
                   append_images=frames[1:])
    print(f"  icon.ico ({', '.join(f'{w}×{h}' for w, h in sizes)})")


if __name__ == "__main__":
    print("生成图标 — 蓝印档案室风格")
    print(f"输出目录: {ICON_DIR}\n")

    print("[应用图标]")
    app_img = generate_app_icon()
    generate_ico(app_img)

    print("\n[功能图标]")
    for name, fn24, fn16 in ICONS:
        save_both(name, fn24, fn16)

    print(f"\n完成 — 共生成 {len(ICONS) * 2 + 2} 个图标文件")
