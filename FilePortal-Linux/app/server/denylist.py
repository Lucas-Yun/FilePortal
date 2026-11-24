# -*- coding: utf-8 -*-
"""Blacklist (denied visitor names).

The blacklist is a directory, just like the whitelist. Any supported file placed
inside it is merged into one name list:

- .txt / .csv / .md      plain text: names separated by spaces, newlines, commas,
                         semicolons, or tabs
- .xlsx / .xlsm         Excel: any row, column, or table; empty cells are skipped
- .docx                 Word: paragraphs and table cells

The admin page edits only ``manual.txt``. Other files in the folder are read-only
from the application's point of view, so a roster exported by someone else can be
dropped in without being rewritten.
"""

import os
import tempfile
import threading
import time

from . import roster, settings

MANUAL_FILE = "manual.txt"
MANUAL_HEAD = """# Blacklist manual file. One name per line.
# Lines starting with # or // are comments.
# Other .txt / .csv / .xlsx / .xlsm / .docx files in this folder are merged automatically.
"""

_lock = threading.Lock()
_cache = {"stamp": None, "map": {}}
_version = 0


def dir_path():
    name = (settings.raw("blacklist_dir") or "data/lists/blacklist").strip() or "data/lists/blacklist"
    return name if os.path.isabs(name) else os.path.join(settings.PROJECT_DIR, name)


def manual_path():
    return os.path.join(dir_path(), MANUAL_FILE)


def ensure_dir():
    try:
        os.makedirs(dir_path(), exist_ok=True)
    except OSError:
        return
    if not os.path.exists(manual_path()):
        try:
            with open(manual_path(), "w", encoding="utf-8") as fh:
                fh.write(MANUAL_HEAD)
        except OSError:
            pass


def _stamp():
    d = dir_path()
    try:
        st = os.stat(d)
        base = [st.st_mtime_ns]
        for fn in os.listdir(d):
            try:
                base.append(os.stat(os.path.join(d, fn)).st_mtime_ns)
            except OSError:
                pass
        return tuple(base)
    except OSError:
        return (0,)


def data():
    """Cached ``{lowercase: (display name, source file)}`` mapping."""
    ensure_dir()
    stamp = _stamp()
    with _lock:
        if _cache["stamp"] != stamp:
            _cache["map"] = roster.scan_dir(dir_path())
            _cache["stamp"] = stamp
        return dict(_cache["map"])


def names():
    """Sorted ``[(display name, source file)]`` list."""
    return sorted(data().values(), key=lambda t: (t[1], t[0]))


def count():
    return len(data())


def reload():
    global _version
    with _lock:
        _cache["stamp"] = None
        _cache["map"] = {}
        _version += 1
    data()


def is_blocked(name):
    """Return True if the exact name is present in any blacklist file."""
    key = (name or "").strip().casefold()
    return bool(key) and key in data()


def read_manual_text():
    ensure_dir()
    try:
        with open(manual_path(), "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError:
        return MANUAL_HEAD


def _atomic_write(text):
    p = manual_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".blacklist-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def write_manual_text(text_value):
    """Save the editable manual blacklist text and reload immediately."""
    body = (text_value or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    if not body.strip():
        body = MANUAL_HEAD
    _atomic_write(body)
    reload()
    return count()


def add_manual(name):
    name = roster.clean_name(name)
    if not name:
        return False, "这个名字看起来不像人名"
    if is_blocked(name):
        return False, "「%s」已经在黑名单中（可能在 manual.txt 或其它名单文件里）" % name
    current = read_manual_text().rstrip("\n")
    body = (current + "\n" + name + "\n") if current.strip() else (MANUAL_HEAD + name + "\n")
    write_manual_text(body)
    return True, "已加入黑名单：%s" % name


def remove_manual(name):
    """Remove a name from manual.txt only; names in Excel/Word remain in force."""
    target = (name or "").strip().casefold()
    if not target:
        return False, 0
    text = read_manual_text()
    keep = []
    removed = 0
    for line in text.splitlines():
        if line.strip().casefold() == target:
            removed += 1
        else:
            keep.append(line)
    if removed:
        write_manual_text("\n".join(keep) + "\n")
    return removed > 0, removed
