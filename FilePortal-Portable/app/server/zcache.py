# -*- coding: utf-8 -*-
# 模块说明：ZIP 打包缓存、摘要校验和并发控制
"""打包缓存：把文件夹先压成一个临时 zip 放在 cache 目录里。

为什么要这么做——流式打包是"边压边发"，总长度事先不知道，浏览器就无法用
Range 开多线程；先落成一个文件之后，长度固定、支持 Range，前端才能开
多条连接同时扒，速度才上得去。文件夹太大（超过 zip_cache_max_mb）就不缓存，
继续走原来的边压边发，不然会吃掉几十 GB 硬盘。
"""
import hashlib
import os
import shutil
import threading
import time
import zipfile

from . import blocked
from .fsutil import (AUDIO_EXT, HIDDEN_NAMES, IMAGE_EXT, VIDEO_EXT, ext_of)
from .settings import CHUNK, PROJECT_DIR, ZIP_CACHE_MAX_MB, ZIP_CACHE_MINUTES

CACHE_DIR = os.path.join(PROJECT_DIR, "runtime", "cache")

_STORE_EXT = IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | {
    "zip", "rar", "7z", "apk", "exe", "iso", "pdf", "gz", "bz2", "xz", "mp4", "mkv"
}

_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = _locks[key] = threading.Lock()
        return lk


def _walk(root):
    """遍历（跳过隐藏文件/屏蔽路径），返回 (文件列表, 总字节, 最新修改时间, 清单指纹)"""
    files = []
    total = 0
    newest = 0.0
    manifest = []
    root_real = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in HIDDEN_NAMES
                       and not blocked.is_blocked(os.path.join(dirpath, d))
                       and not os.path.islink(os.path.join(dirpath, d))]
        for fn in filenames:
            if fn.lower() in HIDDEN_NAMES or fn.startswith("~$"):
                continue
            full = os.path.join(dirpath, fn)
            if blocked.is_blocked(full) or os.path.islink(full):
                continue
            try:
                real = os.path.realpath(full)
                if os.path.commonpath([root_real, real]) != root_real:
                    continue
            except ValueError:
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            files.append(full)
            total += st.st_size
            if st.st_mtime > newest:
                newest = st.st_mtime
            try:
                rel = os.path.relpath(full, root).replace("\\", "/")
            except ValueError:
                rel = full
            manifest.append("%s|%d|%d" % (rel, st.st_size, int(st.st_mtime_ns)))
    manifest.sort()
    digest = hashlib.sha1("\n".join(manifest).encode("utf-8", "replace")).hexdigest()
    return files, total, newest, digest


def _key(root, total, newest, manifest_digest):
    # 除了总大小/最新时间，还把完整文件清单和屏蔽表版本纳入 key：
    # 同样大小、同样时间被替换内容时不会命旧包；屏蔽规则变化后也不会发出旧包。
    raw = "%s|%d|%.0f|%s|%d" % (os.path.realpath(root).lower(), total, newest,
                                manifest_digest, blocked.version())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def cleanup():
    """删掉过期缓存（每次用到缓存时顺手扫一遍，很便宜）"""
    if not os.path.isdir(CACHE_DIR):
        return
    deadline = time.time() - ZIP_CACHE_MINUTES * 60
    for name in os.listdir(CACHE_DIR):
        full = os.path.join(CACHE_DIR, name)
        try:
            if os.path.isfile(full) and os.path.getmtime(full) < deadline:
                os.remove(full)
        except OSError:
            pass


def clear():
    """屏蔽规则或配置变了：把所有打包缓存作废，防止发出含旧内容的 ZIP。"""
    if not os.path.isdir(CACHE_DIR):
        return
    for name in os.listdir(CACHE_DIR):
        full = os.path.join(CACHE_DIR, name)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except OSError:
            pass


def probe(root):
    """能不能缓存？能就返回 (命中/生成后的文件路径, 字节数)，不能返回 (None, 0)"""
    files, total, newest, digest = _walk(root)
    if not files or total <= 0:
        return None, 0
    if total > ZIP_CACHE_MAX_MB * 1024 * 1024:
        return None, 0   # 太大：继续边压边发，别占硬盘
    try:
        free = shutil.disk_usage(CACHE_DIR if os.path.isdir(CACHE_DIR) else os.path.dirname(CACHE_DIR)).free
    except OSError:
        free = 0
    if free < total * 1.15 + 64 * 1024 * 1024:
        return None, 0   # 磁盘不够，不冒险

    os.makedirs(CACHE_DIR, exist_ok=True)
    cleanup()
    key = _key(root, total, newest, digest)
    out = os.path.join(CACHE_DIR, key + ".zip")
    if os.path.isfile(out):
        try:
            os.utime(out, None)      # 摸一下，别被当成过期
            return out, os.path.getsize(out)
        except OSError:
            pass

    lk = _lock_for(key)
    with lk:
        if os.path.isfile(out):
            return out, os.path.getsize(out)
        tmp = out + ".part%d" % threading.get_ident()
        try:
            _build(root, files, tmp)
            os.replace(tmp, out)
            return out, os.path.getsize(out)
        except (OSError, ValueError, zipfile.BadZipFile):
            try:
                os.remove(tmp)
            except OSError:
                pass
            return None, 0


def _build(root, files, out_path):
    base_parent = os.path.dirname(root)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6) as zf:
        for full in files:
            arc = os.path.relpath(full, base_parent).replace("\\", "/")
            zip_type = zipfile.ZIP_STORED if ext_of(full) in _STORE_EXT else zipfile.ZIP_DEFLATED
            st = os.stat(full)
            info = zipfile.ZipInfo(arc, date_time=time.localtime(st.st_mtime)[:6])
            info.compress_type = zip_type
            info.external_attr = (st.st_mode & 0xFFFF) << 16
            with open(full, "rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                while True:
                    buf = src.read(CHUNK)
                    if not buf:
                        break
                    dst.write(buf)
