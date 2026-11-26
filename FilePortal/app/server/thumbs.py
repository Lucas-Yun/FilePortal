# -*- coding: utf-8 -*-
# 模块说明：图片缩略图生成与缓存
"""服务端缩略图：列表不再把 3MB 原图直接塞给手机。

只处理常见位图，结果落在 cache/thumbs/<sha1>.jpg；缓存按原图路径 + 大小 +
修改时间失效。原图超过 thumb_source_max_mb 或 Pillow 打不开时返回 None，
调用方再决定是否退回原图。
"""
import hashlib
import os
import tempfile
import threading
import time

from . import settings

CACHE_DIR = os.path.join(settings.PROJECT_DIR, "runtime", "cache", "thumbs")
_LOCK = threading.Lock()


def _key(path, st):
    raw = "%s|%d|%d" % (os.path.realpath(path).lower(), st.st_size, int(st.st_mtime_ns))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def cleanup():
    try:
        if not os.path.isdir(CACHE_DIR):
            return
        deadline = time.time() - 7 * 86400
        for name in os.listdir(CACHE_DIR):
            full = os.path.join(CACHE_DIR, name)
            try:
                if os.path.isfile(full) and os.path.getmtime(full) < deadline:
                    os.remove(full)
            except OSError:
                pass
    except OSError:
        pass


def get(path):
    """返回缩略图绝对路径；无法生成时返回 None。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    if st.st_size > settings.THUMB_SOURCE_MAX_MB * 1024 * 1024:
        return None
    key = _key(path, st)
    out = os.path.join(CACHE_DIR, key + ".jpg")
    if os.path.isfile(out):
        try:
            os.utime(out, None)
            return out
        except OSError:
            pass
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cleanup()
        im = Image.open(path)
        im.seek(0)
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            # 透明 PNG 铺白底，避免保存 JPEG 时变黑
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.getchannel("A"))
            im = bg
        elif im.mode == "L":
            im = im.convert("RGB")
        im.thumbnail((settings.THUMB_MAX_PX, settings.THUMB_MAX_PX), Image.Resampling.LANCZOS)
        fd, tmp = tempfile.mkstemp(dir=CACHE_DIR, prefix=".thumb-", suffix=".jpg")
        os.close(fd)
        try:
            im.save(tmp, "JPEG", quality=82, optimize=True, progressive=True)
            with _LOCK:
                os.replace(tmp, out)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        return out
    except Exception:
        return None
