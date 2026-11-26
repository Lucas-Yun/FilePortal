# -*- coding: utf-8 -*-
# 模块说明：SVG 图标加载、缓存与目录变更检测
"""图标：扩展名 → 图标名 → assets/images/ 目录里的某一个 svg 文件。

想换图标：直接把 images 里对应的 .svg 覆盖掉（重启或等 2 秒后刷新页面即可生效）。
想给某类扩展名换图标：改下面的 EXT_ICON。
"""

import os
import re
import threading
import time

from .fsutil import ext_of
from . import settings

# 图标目录：运行数据目录下的 assets/images（源码版就是 app/assets/images）
IMG_DIR = os.path.join(settings.ASSETS_DIR, "images")

EXT_ICON = {
    # 文档
    "doc": "i-doc", "docx": "i-doc", "docm": "i-doc", "rtf": "i-doc",
    "odt": "i-doc", "wps": "i-doc", "pages": "i-doc",
    # 表格
    "xls": "i-sheet", "xlsx": "i-sheet", "xlsm": "i-sheet", "xlsb": "i-sheet",
    "csv": "i-sheet", "et": "i-sheet", "ods": "i-sheet", "numbers": "i-sheet",
    # 演示
    "ppt": "i-slides", "pptx": "i-slides", "pptm": "i-slides", "pps": "i-slides",
    "ppsx": "i-slides", "dps": "i-slides", "odp": "i-slides", "key": "i-slides",
    # PDF
    "pdf": "i-pdf",
    # 图片
    "png": "i-image", "jpg": "i-image", "jpeg": "i-image", "gif": "i-image",
    "bmp": "i-image", "webp": "i-image", "svg": "i-image", "ico": "i-image",
    "avif": "i-image", "heic": "i-image", "tif": "i-image", "tiff": "i-image",
    "raw": "i-image", "cr2": "i-image", "nef": "i-image",
    # 视频
    "mp4": "i-video", "mkv": "i-video", "avi": "i-video", "mov": "i-video",
    "wmv": "i-video", "flv": "i-video", "webm": "i-video", "m4v": "i-video",
    "ts": "i-video", "rmvb": "i-video", "3gp": "i-video",
    # 音频
    "mp3": "i-audio", "wav": "i-audio", "flac": "i-audio", "aac": "i-audio",
    "m4a": "i-audio", "ogg": "i-audio", "wma": "i-audio", "ape": "i-audio",
    "opus": "i-audio", "mid": "i-audio",
    # 压缩包
    "zip": "i-archive", "rar": "i-archive", "7z": "i-archive", "tar": "i-archive",
    "gz": "i-archive", "bz2": "i-archive", "xz": "i-archive", "cab": "i-archive",
    # 代码 / 源码
    "py": "i-code", "pyw": "i-code", "c": "i-code", "cpp": "i-code",
    "cc": "i-code", "h": "i-code", "hpp": "i-code", "js": "i-code",
    "mjs": "i-code", "ts": "i-code", "tsx": "i-code", "jsx": "i-code",
    "java": "i-code", "go": "i-code", "rs": "i-code", "cs": "i-code",
    "php": "i-code", "rb": "i-code", "kt": "i-code", "swift": "i-code",
    "lua": "i-code", "sh": "i-code", "bat": "i-code", "cmd": "i-code",
    "ps1": "i-code", "html": "i-code", "htm": "i-code", "css": "i-code",
    "scss": "i-code", "vue": "i-code", "ino": "i-code", "asm": "i-code",
    "m": "i-code", "sql": "i-code",
    # 程序 / 安装包
    "exe": "i-exe", "msi": "i-exe", "dll": "i-exe", "sys": "i-exe",
    "com": "i-exe", "appx": "i-exe", "deb": "i-exe", "rpm": "i-exe",
    "dmg": "i-exe", "pkg": "i-exe",
    # 安卓
    "apk": "i-apk", "aab": "i-apk", "xapk": "i-apk",
    # 数据库
    "db": "i-db", "sqlite": "i-db", "sqlite3": "i-db", "mdb": "i-db",
    "accdb": "i-db", "frm": "i-db",
    # 字体
    "ttf": "i-font", "otf": "i-font", "woff": "i-font", "woff2": "i-font",
    "ttc": "i-font", "fon": "i-font",
    # 设计
    "psd": "i-design", "ai": "i-design", "fig": "i-design", "sketch": "i-design",
    "cdr": "i-design", "xd": "i-design", "afdesign": "i-design", "procreate": "i-design",
    # 工程 / 建模
    "kicad_pcb": "i-cad", "kicad_sch": "i-cad", "kicad_pro": "i-cad",
    "sch": "i-cad", "brd": "i-cad", "pcbdoc": "i-cad", "dwg": "i-cad",
    "dxf": "i-cad", "step": "i-cad", "stp": "i-cad", "iges": "i-cad",
    "igs": "i-cad", "f3d": "i-cad", "stl": "i-cad", "obj": "i-cad",
    "gbr": "i-cad", "slk": "i-cad",
    # 文本 / 配置
    "txt": "i-text", "log": "i-text", "md": "i-text", "markdown": "i-text",
    "ini": "i-text", "cfg": "i-text", "conf": "i-text", "yml": "i-text",
    "yaml": "i-text", "toml": "i-text", "json": "i-text", "xml": "i-text",
    "reg": "i-text",
    # 镜像 / 虚拟磁盘
    "iso": "i-disc", "img": "i-disc", "vhd": "i-disc", "vhdx": "i-disc",
    "vmdk": "i-disc", "ova": "i-disc", "ovf": "i-disc", "wim": "i-disc",
    # 快捷方式 / 链接
    "lnk": "i-link", "url": "i-link", "torrent": "i-link", "m3u": "i-link",
}


ICON_COLOR = {
    "i-folder": "#f0a92b",
    "i-doc": "#2b579a",
    "i-sheet": "#1e8449",
    "i-slides": "#d24726",
    "i-pdf": "#cf3c33",
    "i-image": "#0f97a5",
    "i-video": "#e0473a",
    "i-audio": "#c2387f",
    "i-archive": "#8a6d3b",
    "i-code": "#0b7285",
    "i-exe": "#5c6b7a",
    "i-apk": "#2ea05f",
    "i-db": "#336791",
    "i-font": "#b8860b",
    "i-text": "#607d8b",
    "i-cad": "#455a64",
    "i-design": "#c2185b",
    "i-disc": "#546e7a",
    "i-link": "#2c7be5",
    "i-file": "#8a94a6",
}


ICON_NAME = {
    "i-folder": "文件夹", "i-doc": "文档", "i-sheet": "表格", "i-slides": "演示文稿",
    "i-pdf": "PDF", "i-image": "图片", "i-video": "视频", "i-audio": "音频",
    "i-archive": "压缩包", "i-code": "代码", "i-exe": "程序", "i-apk": "安卓安装包",
    "i-db": "数据库", "i-font": "字体", "i-text": "文本", "i-cad": "工程文件",
    "i-design": "设计文件", "i-disc": "磁盘镜像", "i-link": "快捷方式", "i-file": "文件",
}


def icon_for(name, is_dir):
    if is_dir:
        return "i-folder", ICON_COLOR["i-folder"]
    sym = EXT_ICON.get(ext_of(name), "i-file")
    return sym, ICON_COLOR.get(sym, ICON_COLOR["i-file"])


# --------------------------------------------------------------------------- #
# 从 images/ 目录加载图标，拼成内联 sprite
#   images/folder.svg  →  <symbol id="i-folder">
#   修改 / 新增 / 删除 svg 后，最多 2 秒就生效，刷新页面即可看到，不用重启服务
# --------------------------------------------------------------------------- #
_SVG_RE = re.compile(r"<svg\b([^>]*)>(.*)</svg>", re.S | re.I)
_VB_RE = re.compile(r'viewBox\s*=\s*["\']([^"\']+)["\']', re.I)

_cache_lock = threading.Lock()
_cache = {"stamp": None, "html": "", "checked": 0.0}


def list_icon_files():
    try:
        return sorted(fn for fn in os.listdir(IMG_DIR) if fn.lower().endswith(".svg"))
    except OSError:
        return []


def _stamp():
    parts = []
    for fn in list_icon_files():
        try:
            parts.append("%s:%d" % (fn, int(os.path.getmtime(os.path.join(IMG_DIR, fn)))))
        except OSError:
            pass
    return tuple(parts)


def _symbol_of(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    m = _SVG_RE.search(text)
    if not m:
        return None
    vb = _VB_RE.search(m.group(1))
    return (vb.group(1) if vb else "0 0 24 24"), m.group(2).strip()


def get_sprite():
    """images/*.svg → 内联 <svg><symbol>...；2 秒检查一次是否需要重建"""
    now = time.time()
    with _cache_lock:
        if now - _cache["checked"] < 2.0 and _cache["html"]:
            return _cache["html"]
        stamp = _stamp()
        _cache["checked"] = now
        if stamp == _cache["stamp"] and _cache["html"]:
            return _cache["html"]
        blocks = []
        for fn in list_icon_files():
            data = _symbol_of(os.path.join(IMG_DIR, fn))
            if not data:
                continue
            view_box, inner = data
            blocks.append('<symbol id="i-%s" viewBox="%s">%s</symbol>'
                          % (fn[:-4], view_box, inner))
        _cache["stamp"] = stamp
        _cache["html"] = ('<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">\n'
                          + "\n".join(blocks) + "\n</svg>")
        return _cache["html"]


def icon_file_text(name):
    """返回 images/<name>.svg 的原文（给 /img/xxx.svg 用），不存在返回 None"""
    if not name:
        return None
    target = name + ".svg"
    for fn in list_icon_files():
        if fn != target:
            continue
        path = os.path.join(IMG_DIR, fn)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None
    return None


def icon_image_path(name):
    """images 里的一张图片（png / jpg / gif / webp / svg），给 /img/xxx.png 用。
    只从 images 目录的实际文件列表里取，防止有人用 ../../ 往外读。"""
    if not name:
        return None
    try:
        entries = os.listdir(IMG_DIR)
    except OSError:
        return None
    for fn in entries:
        if fn != name:
            continue
        path = os.path.join(IMG_DIR, fn)
        if os.path.isfile(path):
            return path
    return None

