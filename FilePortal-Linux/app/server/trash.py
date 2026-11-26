# -*- coding: utf-8 -*-
# 模块说明：回收站文件的移入、恢复和清理
r"""回收站：网页上点「删除」不再直接抹掉，而是挪进 <存储根目录>\.trash。

这样误删还能还原；超过 config.ini 里 trash_days 天的才真正清掉。
.trash 在 HIDDEN_NAMES 里，所以网页列表、搜索、打包都不会把它算进去。

每个被删的东西对应两个文件：
  .trash/<id>__<原名>      东西本身（文件夹就整个挪过来）
  .trash/<id>.json         原位置等元信息
"""

import json
import os
import re
import secrets
import shutil
import time

from . import blocked, settings
from .fsutil import sanitize_segment

TRASH_NAME = ".trash"
_META_EXT = ".json"
_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")


def trash_dir(root):
    return os.path.join(root, TRASH_NAME)


def _new_id():
    # 秒级时间戳 + PID 在同一秒批量删除时会撞 ID，直接覆盖 meta/payload；
    # 改用随机 16 位十六进制，碰撞概率可以忽略。
    return secrets.token_hex(8)


def _read_meta(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_meta(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _cleanup(root):
    """按「删除时间」清过期条目，而不是按文件原始 mtime。

    文件被移动时 Windows 会保留原 mtime，旧资料今天删进回收站，原始 mtime
    可能已经是几年前；拿 payload 的 mtime 判断会把刚删的东西立刻清掉。
    """
    days = settings.integer("trash_days", 1, 3650)
    d = trash_dir(root)
    if not os.path.isdir(d):
        return
    deadline = time.time() - days * 86400
    for fn in os.listdir(d):
        if not fn.endswith(_META_EXT):
            continue
        full = os.path.join(d, fn)
        meta = _read_meta(full)
        if not meta:
            continue
        try:
            deleted = float(meta.get("deleted") or 0)
        except (TypeError, ValueError):
            deleted = 0
        if deleted and deleted < deadline:
            src = _payload_path(d, meta)
            if src:
                try:
                    if os.path.isdir(src):
                        shutil.rmtree(src, ignore_errors=True)
                    else:
                        os.remove(src)
                except OSError:
                    pass
            try:
                os.remove(full)
            except OSError:
                pass


def put(root, abs_path, who=""):
    """把 abs_path 挪进回收站，返回元信息 dict；失败抛 OSError"""
    if blocked.is_blocked(abs_path):
        raise OSError("该路径已被屏蔽，不能删除")
    d = trash_dir(root)
    os.makedirs(d, exist_ok=True)
    tid = _new_id()
    name = os.path.basename(abs_path.rstrip("\\/"))
    target = os.path.join(d, "%s__%s" % (tid, name))
    rel = os.path.relpath(abs_path, root).replace("\\", "/")
    try:
        st = os.stat(abs_path)
        size = st.st_size if not os.path.isdir(abs_path) else 0
        mtime = st.st_mtime
    except OSError:
        size, mtime = 0, time.time()
    is_dir = os.path.isdir(abs_path)
    try:
        os.replace(abs_path, target)
    except OSError:
        shutil.move(abs_path, target)
    meta = {"id": tid, "name": name, "rel": rel, "dir": is_dir, "size": size,
            "mtime": mtime, "deleted": time.time(), "who": who}
    _write_meta(os.path.join(d, tid + _META_EXT), meta)
    return meta


def listing(root, limit=200):
    """最近删的排在前面"""
    _cleanup(root)
    d = trash_dir(root)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        if not fn.endswith(_META_EXT):
            continue
        meta = _read_meta(os.path.join(d, fn))
        if not meta:
            continue
        rel = (meta.get("rel") or "").replace("/", os.sep)
        if rel and blocked.is_blocked(os.path.join(root, rel)):
            continue
        meta["exists"] = os.path.exists(os.path.join(d, "%s__%s" % (meta.get("id"), meta.get("name")))) \
            or _payload_path(d, meta) is not None
        out.append(meta)
    out.sort(key=lambda m: -(m.get("deleted") or 0))
    return out[:limit]


def _payload_path(d, meta):
    exact = os.path.join(d, "%s__%s" % (meta.get("id") or "", meta.get("name") or ""))
    if os.path.exists(exact):
        return exact
    tid = meta.get("id") or ""
    if not tid:
        return None
    for fn in os.listdir(d):
        if fn.startswith(tid + "__") and not fn.endswith(_META_EXT):
            return os.path.join(d, fn)
    return None


def restore(root, tid):
    """还原到原来的位置（原位置同名东西已经存在时，自动改名加 (N)）"""
    if not _ID_RE.match(tid or ""):
        return False, "回收站记录编号无效"
    d = trash_dir(root)
    meta = _read_meta(os.path.join(d, tid + _META_EXT))
    if not meta:
        return False, "未找到该记录（可能已被清除）"
    src = _payload_path(d, meta)
    if not src:
        return False, "回收站中的该项已不存在"
    rel = (meta.get("rel") or "").replace("\\", "/").strip("/")
    original = os.path.join(root, rel.replace("/", os.sep)) if rel else root
    if blocked.is_blocked(original):
        return False, "原位置已被屏蔽，不能还原"
    parent_rel, _, base = rel.rpartition("/")
    parent = os.path.join(root, parent_rel) if parent_rel else root
    base = sanitize_segment(base or meta.get("name") or "restored")
    if not base:
        return False, "原文件名不可用，无法还原"
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        return False, "原目录无法恢复：%s" % exc
    target = os.path.join(parent, base)
    if os.path.exists(target):
        stem, ext = os.path.splitext(base)
        n = 1
        while os.path.exists(os.path.join(parent, "%s (%d)%s" % (stem, n, ext))):
            n += 1
        target = os.path.join(parent, "%s (%d)%s" % (stem, n, ext))
    try:
        os.replace(src, target)
    except OSError:
        try:
            shutil.move(src, target)
        except (OSError, shutil.Error) as exc:
            return False, "还原失败：%s" % exc
    try:
        os.remove(os.path.join(d, tid + _META_EXT))
    except OSError:
        pass
    return True, "已还原到 %s" % (rel or base)


def purge(root, tid):
    if not _ID_RE.match(tid or ""):
        return False, "回收站记录编号无效"
    d = trash_dir(root)
    meta = _read_meta(os.path.join(d, tid + _META_EXT))
    if meta:
        rel = (meta.get("rel") or "").replace("/", os.sep)
        if rel and blocked.is_blocked(os.path.join(root, rel)):
            return False, "该项所在路径已被屏蔽，不能操作"
    src = _payload_path(d, meta) if meta else None
    removed = False
    if src:
        try:
            if os.path.isdir(src):
                shutil.rmtree(src, ignore_errors=True)
            else:
                os.remove(src)
            removed = True
        except OSError:
            pass
    try:
        os.remove(os.path.join(d, tid + _META_EXT))
    except OSError:
        pass
    return removed, "已彻底删除" if removed else "该项已不在回收站中"


def empty(root):
    d = trash_dir(root)
    if not os.path.isdir(d):
        return 0
    n = 0
    for fn in os.listdir(d):
        if not fn.endswith(_META_EXT):
            continue
        tid = fn[:-len(_META_EXT)]
        ok, _msg = purge(root, tid)
        if ok:
            n += 1
    return n
