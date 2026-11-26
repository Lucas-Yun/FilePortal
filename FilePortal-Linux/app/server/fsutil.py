# -*- coding: utf-8 -*-
# 模块说明：路径安全、目录扫描、文件信息和大小格式化
"""文件系统相关的小工具：大小格式化、MIME、路径安全解析、目录扫描（带短缓存）。"""

import collections
import mimetypes
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime

from . import blocked
from . import settings
from .settings import (CHUNK, HIDDEN_NAMES, LIST_CACHE_MAX,
                       LIST_CACHE_SECONDS, Config)

MIME_EXTRA = {
    ".md": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".ini": "text/plain; charset=utf-8",
    ".cfg": "text/plain; charset=utf-8",
    ".conf": "text/plain; charset=utf-8",
    ".yml": "text/plain; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".py": "text/plain; charset=utf-8",
    ".c": "text/plain; charset=utf-8",
    ".cpp": "text/plain; charset=utf-8",
    ".h": "text/plain; charset=utf-8",
    ".hpp": "text/plain; charset=utf-8",
    ".js": "text/plain; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".java": "text/plain; charset=utf-8",
    ".html": "text/plain; charset=utf-8",
    ".css": "text/plain; charset=utf-8",
    ".ino": "text/plain; charset=utf-8",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".apk": "application/vnd.android.package-archive",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".kicad_pcb": "application/octet-stream",
    ".kicad_sch": "application/octet-stream",
}

IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico", "avif"}
VIDEO_EXT = {"mp4", "webm", "ogv", "m4v", "mov", "mkv", "avi", "wmv", "flv"}
AUDIO_EXT = {"mp3", "wav", "ogg", "m4a", "aac", "flac", "wma", "ape", "opus"}
TEXT_EXT = {
    "txt", "md", "log", "ini", "cfg", "conf", "yml", "yaml", "json", "xml",
    "csv", "py", "c", "cpp", "h", "hpp", "js", "ts", "java", "go", "rs", "cs",
    "php", "rb", "kt", "swift", "lua", "sh", "bat", "ps1", "html", "htm",
    "css", "sql", "ino", "m", "asm", "vue", "toml",
}

# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def human_size(n):
    if n is None:
        return ""
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < step or unit == "TB":
            if unit == "B":
                return "%d B" % n
            return "%.1f %s" % (n, unit)
        n /= step
    return ""


def fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def ext_of(name):
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[1].lower()


def preview_kind(name):
    e = ext_of(name)
    if e in IMAGE_EXT:
        return "image"
    if e in VIDEO_EXT:
        return "video"
    if e in AUDIO_EXT:
        return "audio"
    if e == "pdf":
        return "pdf"
    if e in TEXT_EXT:
        return "text"
    return "other"


def guess_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in MIME_EXTRA:
        return MIME_EXTRA[ext]
    ctype, _ = mimetypes.guess_type(path)
    return ctype or "application/octet-stream"


_KIND_WORD = {
    "image": ("png", "jpg", "jpeg", "gif", "bmp", "webp", "ico", "tif", "tiff", "heic"),
    "video": ("mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "ts"),
    "audio": ("mp3", "wav", "flac", "m4a", "aac", "ogg", "wma"),
    "document": ("pdf", "doc", "docx", "txt", "md", "wps", "rtf", "epub"),
    "sheet": ("xls", "xlsx", "csv", "et"),
    "slides": ("ppt", "pptx", "dps"),
    "archive": ("zip", "rar", "7z", "tar", "gz"),
    "code": ("py", "js", "html", "htm", "c", "cpp", "h", "java", "json", "xml", "sh", "bat"),
}


def _kind_word(ext):
    e = (ext or "").lower().lstrip(".")
    for word, exts in _KIND_WORD.items():
        if e in exts:
            return word
    return "file"


def _ascii_fallback_name(name):
    """给只认 filename="" 的老浏览器准备的名字。

    老设备（学习机、功能机浏览器、部分安卓 WebView）不认 RFC 5987 的 filename*，
    只看 filename=""，而中文只能变成一串下划线 —— 于是下载出来叫「____9.5.pdf」。
    这里把能认的英文/数字留下（比如「九年级数学9.5.pdf」→「9.5.pdf」），
    全中文的名字就按文件类型给个朴素的名字（image.png / document.pdf / sheet.xlsx），
    实在判断不出来才叫 file + 扩展名。
    """
    ext = os.path.splitext(name)[1] or ""
    ext = re.sub(r"[^\x20-\x7e]", "", ext)
    base = os.path.splitext(name)[0]
    out = re.sub(r"[^\x20-\x7e]", "", base)
    out = re.sub(r'[\\/:*?"<>|]+', "_", out)
    out = re.sub(r"[\s_]{2,}", "_", out).strip(" ._-")
    if not out:
        out = _kind_word(ext)
    if len(out) > 90:
        out = out[:90].rstrip(" ._-") or _kind_word(ext)
    return out + ext


def content_disposition(name, inline=False, ascii_only=False):
    kind = "inline" if inline else "attachment"
    fallback = _ascii_fallback_name(name or "file").replace('"', "_") or "file"
    if ascii_only:
        return '%s; filename="%s"' % (kind, fallback)
    return "%s; filename=\"%s\"; filename*=UTF-8''%s" % (
        kind, fallback, urllib.parse.quote(name, safe=""),
    )


def q(s):
    return urllib.parse.quote(s, safe="")

def sanitize_segment(seg):
    seg = seg.replace("\\", "/").split("/")[-1]
    seg = re.sub(r'[\x00-\x1f<>:"|?*]', "_", seg).strip().rstrip(".")
    if seg in ("", ".", ".."):
        return ""
    # Windows 保留设备名：CON、PRN、AUX、NUL、COM1~9、LPT1~9（带扩展名同样不行）
    stem = seg.split(".", 1)[0].strip().casefold()
    if stem in {"con", "prn", "aux", "nul"} or \
            (stem[:3] in ("com", "lpt") and stem[3:].isdigit()
             and 1 <= int(stem[3:] or 0) <= 9):
        seg = "_" + seg
    if len(seg) > 120:
        base, ext = os.path.splitext(seg)
        seg = base[:120 - len(ext)] + ext
    return seg

def resolve(rel, root=None):
    """把 URL 里的相对路径转换成磁盘绝对路径，并确保不出 root（默认 Config.root）。"""
    root = os.path.abspath(root or Config.root)
    rel = (rel or "").replace("\\", "/").strip("/")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    for p in parts:
        if p == ".." or ":" in p:
            return None
        # 隐藏项（.trash / cache / blocked_paths.txt / .session_secret / sessions.json 等）
        # 只在列表里不显示是不够的：直接拼 URL 也必须拒绝
        if p.lower() in HIDDEN_NAMES or p.startswith("~$"):
            return None
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(
        os.path.abspath(os.path.join(root, *parts)) if parts else root)
    # CodeQL-recognized containment guard: normalize first, then require the
    # root itself or a direct child. commonpath alone is not recognized.
    if path_real != root_real and not path_real.startswith(
            root_real.rstrip("\\/") + os.sep):
        return None
    if is_self_dir(path_real, root):
        return None
    # 屏蔽清单：任何人、任何权限都取不到；命中目录时其下所有内容一并拒绝
    if blocked.is_blocked(path_real):
        return None
    return path_real


# --------------------------------------------------------------------------- #
# 自我保护：本程序自己所在的文件夹（FilePortal）如果正好在投射范围里，
# 网页上不列出、也不允许访问 —— 免得别人把日志和代码看走或删掉。
# --------------------------------------------------------------------------- #
PROJECT_DIR = settings.PROJECT_DIR
_PROJECT_REAL = os.path.realpath(PROJECT_DIR)
_PROJECT_NORM = os.path.normcase(PROJECT_DIR)


def _project_exposed(root=None):
    """项目目录是否落在投射范围内（落在里面才需要保护）"""
    root_real = os.path.realpath(os.path.abspath(root or Config.root))
    if _PROJECT_REAL == root_real:
        return False
    return _PROJECT_REAL.startswith(root_real.rstrip("\\/") + os.sep)


def is_self_dir(path_real, root=None):
    if not _project_exposed(root):
        return False
    return path_real == _PROJECT_REAL or path_real.startswith(_PROJECT_REAL + os.sep)


def rel_of(path):
    rel = os.path.relpath(path, Config.root).replace("\\", "/")
    return "" if rel == "." else rel

def _scan_entries(abspath):
    """读取目录，返回 [(name, is_dir, stat), ...]；出错时抛出 OSError。"""
    items = []
    hide_self = _project_exposed() and os.path.normcase(abspath) == os.path.normcase(os.path.dirname(PROJECT_DIR))
    with os.scandir(abspath) as it:
        for e in it:
            name = e.name
            if name.lower() in HIDDEN_NAMES or name.startswith("~$"):
                continue
            full = os.path.join(abspath, name)
            if blocked.is_blocked(full):
                continue
            if hide_self and os.path.normcase(full) == _PROJECT_NORM:
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                st = None
            try:
                is_dir = e.is_dir()
            except OSError:
                is_dir = False
            items.append((name, is_dir, st))
    return items


# --------------------------------------------------------------------------- #
# 目录清单短缓存：多个客户端同时刷同一个大文件夹时，不会反复扫盘把机器拖死
# --------------------------------------------------------------------------- #
_LIST_TTL = LIST_CACHE_SECONDS      # 秒数来自 config.ini（0 = 不缓存）
_LIST_MAX = LIST_CACHE_MAX
_list_cache = {}
_list_lock = threading.Lock()


def scan_entries(abspath):
    if _LIST_TTL <= 0:
        return _scan_entries(abspath)
    now = time.time()
    ver = blocked.version()
    with _list_lock:
        hit = _list_cache.get(abspath)
        if hit and hit[0] > now and hit[2] == ver:
            return hit[1]
    entries = _scan_entries(abspath)
    with _list_lock:
        if len(_list_cache) > _LIST_MAX:
            _list_cache.clear()
        _list_cache[abspath] = (now + _LIST_TTL, entries, ver)
    return entries


def invalidate_dir(path, parent_too=True):
    """任何写操作之后调用，让缓存立刻失效"""
    with _list_lock:
        _list_cache.pop(path, None)
        if parent_too:
            _list_cache.pop(os.path.dirname(path), None)


def invalidate_all():
    with _list_lock:
        _list_cache.clear()


# --------------------------------------------------------------------------- #
# 跨子目录搜索（在 base 这一层及其下面所有层里找名字含 kw 的项）
#   · 有预算：最多扫多少项、最多花多少秒、最多返回多少条 —— 有人搜个"的"字
#     也不会把整块盘扫穿、把本机拖死；
#   · 不进符号链接 / 目录联接（避免绕圈），也不进本程序自己的目录。
# --------------------------------------------------------------------------- #
def search_entries(base_abs, kw, limit=400, max_scan=200000, budget_seconds=4.0,
                   root=None):
    """广度优先地扫（先浅后深），这样不深的地方几毫秒就能出结果，不用等整棵树扫完。"""
    low = (kw or "").strip().lower()
    if not low:
        return [], 0, False
    root_abs = os.path.abspath(root or Config.root)
    t0 = time.monotonic()
    out = []
    scanned = 0
    truncated = False
    queue = collections.deque([(base_abs, "")])
    while queue:
        if len(out) >= limit:
            truncated = True
            break
        if time.monotonic() - t0 > budget_seconds or scanned >= max_scan:
            truncated = True
            break
        directory, rel_dir = queue.popleft()
        try:
            entries = _scan_entries(directory)
        except OSError:
            continue
        dirs = []
        for name, is_dir, st in entries:
            scanned += 1
            if scanned >= max_scan:
                truncated = True
                break
            rel = (rel_dir + "/" + name) if rel_dir else name
            if low in name.lower():
                out.append((rel, name, is_dir, st))
                if len(out) >= limit:
                    truncated = True
                    break
            if is_dir:
                full = os.path.join(directory, name)
                if st is not None and hasattr(st, "st_file_attributes") and \
                        (st.st_file_attributes & 0x400):
                    continue                       # 目录联接 / 重解析点：不跟，免得绕圈
                if is_self_dir(os.path.realpath(full), root_abs):
                    continue                       # 本程序自己的目录：永远不露面
                if blocked.is_blocked(full):
                    continue                       # 屏蔽目录：不进入、不列子项
                dirs.append((full, rel))
        queue.extend(dirs)
    # 命中排序：开头匹配的优先，其次文件夹优先，再按名字长短
    out.sort(key=lambda t: (0 if t[1].lower().startswith(low) else 1, 0 if t[2] else 1,
                            len(t[1]), t[1].lower()))
    return out, scanned, truncated
