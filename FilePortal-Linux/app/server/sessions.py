# -*- coding: utf-8 -*-
"""会话登记表：记录当前有效的登录会话。

规则：
- 普通访问账号（规则 / config.ini 里的姓名）：同一姓名允许在多台设备同时登录，不再互相排斥。
- 云空间账号（个人私有云盘）：仍然保持单会话，新登录顶掉旧登录，旧会话下次请求时自动退回登录页。
- Admin 后台身份不参与，避免管理后台把自己锁在门外。

登记表只保存「姓名、会话编号、登录时间、类型」，不保存密码。
写入 data/sessions.json，服务重启后仍能识别原来的活动会话。
"""

import json
import os
import threading
import time

from . import settings

FILE_NAME = "sessions.json"
ONLINE_WINDOW = 30 * 60   # 最近 30 分钟内有请求才算“在线”
_lock = threading.RLock()
_cache = {}
_loaded = False


def path():
    return os.path.join(settings.DATA_DIR, FILE_NAME)


def _key(name):
    return (name or "").strip().casefold()


def _ttl():
    return int(settings.SESSION_TTL)


def _load_locked():
    global _loaded, _cache
    if _loaded:
        return
    _loaded = True
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("sessions") if isinstance(data, dict) else None
        if isinstance(entries, dict):
            for key, item in entries.items():
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                kind = str(item.get("kind") or "normal").strip()
                rows = item.get("entries")
                if not isinstance(rows, list):
                    # 兼容旧版：一个姓名只有一条 {"sid", "ts", "kind"}
                    rows = [{"sid": item.get("sid"), "ts": item.get("ts"),
                             "kind": kind}]
                cleaned, seen_set = [], set()
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    sid = str(row.get("sid") or "").strip()
                    try:
                        ts = int(row.get("ts") or 0)
                    except (TypeError, ValueError):
                        ts = 0
                    try:
                        seen = int(row.get("seen") or ts)
                    except (TypeError, ValueError):
                        seen = ts
                    row_kind = "cloud" if str(row.get("kind") or kind) == "cloud" else "normal"
                    if sid and ts and sid not in seen_set:
                        seen_set.add(sid)
                        cleaned.append({"sid": sid, "ts": ts, "seen": max(ts, seen),
                                        "kind": row_kind})
                if cleaned:
                    _cache[_key(name)] = {"name": name, "entries": cleaned}
    except (OSError, ValueError, TypeError):
        _cache = {}
    _cleanup_locked(time.time())


def _save_locked():
    data = {"version": 2, "sessions": _cache}
    tmp = path() + ".tmp"
    try:
        os.makedirs(os.path.dirname(path()), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, path())
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _cleanup_locked(now=None):
    now = time.time() if now is None else now
    ttl = _ttl()
    changed = False
    for key, item in list(_cache.items()):
        alive = [e for e in item.get("entries") or [] if now - e.get("ts", 0) <= ttl]
        if alive:
            if len(alive) != len(item.get("entries") or []):
                item["entries"] = alive
                changed = True
        else:
            _cache.pop(key, None)
            changed = True
    if changed:
        _save_locked()


def claim(name, sid, kind="normal"):
    """登记一次登录。

    返回 (ok, reason)：
      - ("new", "new")           登记成功（普通账号允许多台设备各保留自己的会话）
      - ("same", "same")         同一会话重复登记
      - ("replaced", "replaced") 云空间账号新登录，旧会话被顶掉
      - (False, "invalid")       姓名或会话编号为空
    """
    key = _key(name)
    if not key or not sid:
        return False, "invalid"
    with _lock:
        _load_locked()
        _cleanup_locked()
        old = _cache.get(key)
        rows = list(old.get("entries") or []) if old else []
        if any(e.get("sid") == sid for e in rows):
            return True, "same"
        ts = int(time.time())
        if kind == "cloud":
            # 个人云盘保持单会话：新登录整体替换旧会话
            _cache[key] = {"name": (name or "").strip(),
                           "entries": [{"sid": sid, "ts": ts, "seen": ts,
                                        "kind": "cloud"}]}
            _save_locked()
            return True, "replaced" if rows else "new"
        # 普通访问账号：同一姓名可多设备同时在线，各自登记一个会话
        if not old:
            old = {"name": (name or "").strip(), "entries": []}
        old["entries"] = rows
        old["entries"].append({"sid": sid, "ts": ts, "seen": ts, "kind": "normal"})
        _cache[key] = old
        _save_locked()
        return True, "new"


def validate(name, sid, kind="normal"):
    """校验 Cookie 里的会话编号是否仍是有效会话。

    返回 (ok, reason)：reason 为 ok / missing / replaced / expired。
    普通账号允许多个会话；云空间账号只认当前唯一会话。
    """
    key = _key(name)
    if not key or not sid:
        return False, "missing"
    with _lock:
        _load_locked()
        now = time.time()
        item = _cache.get(key)
        if not item:
            return False, "missing"
        rows = item.get("entries") or []
        for entry in rows:
            if entry.get("sid") != sid:
                continue
            if now - entry.get("ts", 0) > _ttl():
                item["entries"] = [e for e in rows if e.get("sid") != sid]
                if not item["entries"]:
                    _cache.pop(key, None)
                _save_locked()
                return False, "expired"
            # 记录最近活动时间（5 分钟节流写盘），用于后台“当前在线”判断；
            # 会话有效期仍按登录时间 ts 计算，不会因为浏览而无限续期。
            if now - entry.get("seen", entry.get("ts", 0)) > 300:
                entry["seen"] = int(now)
                _save_locked()
            return True, "ok"
        if kind == "cloud":
            return False, "replaced"
        return False, "missing"


def release(name, sid):
    """注销时移除自己的会话；不影响同一姓名的其他设备。"""
    key = _key(name)
    if not key or not sid:
        return False
    with _lock:
        _load_locked()
        item = _cache.get(key)
        if not item:
            return False
        rows = item.get("entries") or []
        keep = [e for e in rows if e.get("sid") != sid]
        if len(keep) == len(rows):
            return False
        if keep:
            item["entries"] = keep
        else:
            _cache.pop(key, None)
        _save_locked()
        return True


def reset(name=None):
    """强制释放某个姓名（name 为空则全部释放）的活动会话。"""
    with _lock:
        _load_locked()
        if name is None:
            n = sum(len(item.get("entries") or []) for item in _cache.values())
            _cache.clear()
        else:
            key = _key(name)
            item = _cache.pop(key, None)
            n = len(item.get("entries") or []) if item else 0
        _save_locked()
        return n


def snapshot():
    """返回当前活动会话的只读快照，供排查使用。"""
    with _lock:
        _load_locked()
        _cleanup_locked()
        out = []
        for item in _cache.values():
            for entry in item.get("entries") or []:
                out.append({"name": item.get("name") or "",
                            "sid": entry.get("sid") or "",
                            "ts": entry.get("ts") or 0,
                            "seen": entry.get("seen") or entry.get("ts") or 0,
                            "kind": entry.get("kind") or "normal"})
        return sorted(out, key=lambda x: ((x.get("name") or "").casefold(),
                                          x.get("ts") or 0))


def online():
    """按姓名汇总“最近 30 分钟内有请求”的登录会话，供后台卡片和控制台使用。"""
    now = time.time()
    with _lock:
        _load_locked()
        _cleanup_locked(now)
        out = []
        for item in _cache.values():
            rows = [e for e in (item.get("entries") or [])
                    if now - (e.get("seen") or e.get("ts") or 0) <= ONLINE_WINDOW]
            if not rows:
                continue
            stamps = [int(e.get("seen") or e.get("ts") or 0) for e in rows]
            kinds = {str(e.get("kind") or "normal") for e in rows}
            out.append({"name": item.get("name") or "",
                        "kind": "cloud" if "cloud" in kinds else "normal",
                        "devices": len(rows),
                        "last": max(stamps),
                        "first": min(int(e.get("ts") or 0) for e in rows)})
        return sorted(out, key=lambda x: (x["name"].casefold(),
                                          -x["last"]))
