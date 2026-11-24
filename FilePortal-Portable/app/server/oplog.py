# -*- coding: utf-8 -*-
"""操作日志：记录各访问者在何目录下新增、删除或重命名的对象。

日志文件存放于程序目录下的 runtime/logs/，按自然日归档，文件名为 YYYYMMDD.log，
同一自然日内的全部事件追加写入同一文件；跨日自动切换至新文件。
"""

import os
import socket
import sys
import threading
import time
from datetime import datetime

from .settings import SERVER_VERSION, Config, PROJECT_DIR, integer


# --------------------------------------------------------------------------- #
# 操作日志：每一次新增 / 删除 / 重命名均记录一条，按自然日归档于运行目录的 log 目录
# --------------------------------------------------------------------------- #
LOG_DIR = os.path.join(PROJECT_DIR, "runtime", "logs")
LOG_FILE = None          # 当前正在写入的日志文件（跨日时切换）
LOG_DATE = None          # 当前日志文件对应的自然日（YYYYMMDD）
LOG_LOCK = threading.Lock()


def _daily_path(day=None):
    day = day or time.strftime("%Y%m%d")
    return os.path.join(LOG_DIR, day + ".log"), day


def _cleanup_old():
    """只清理 YYYYMMDD.log 形式的按天日志，超过 log_days 的删掉。"""
    try:
        days = max(7, integer("log_days", 1, 3650))
        deadline = time.time() - days * 86400
        for name in os.listdir(LOG_DIR):
            if len(name) != 12 or not name.endswith(".log") or not name[:8].isdigit():
                continue
            full = os.path.join(LOG_DIR, name)
            try:
                if os.path.isfile(full) and os.path.getmtime(full) < deadline:
                    os.remove(full)
            except OSError:
                pass
    except OSError:
        pass


def _ensure_today():
    """确保 LOG_FILE 指向当日文件；返回 (path, day)"""
    global LOG_FILE, LOG_DATE
    path, day = _daily_path()
    if LOG_FILE and LOG_DATE == day:
        return path, day
    LOG_FILE, LOG_DATE = path, day
    return path, day


def init_log():
    """初始化日志：定位当日文件，文件不存在时写入头部说明并返回路径"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _cleanup_old()
        path, day = _ensure_today()
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("# file-portal operation log (UTF-8, one event per line)\n")
                fh.write("# format: TIMESTAMP | LEVEL | user= | ip= | op= | path= [| key=value ...]\n")
                fh.write("# date=%s | pid=%d | host=%s:%d | root=%s | version=%s\n"
                         % (day, os.getpid(), socket.gethostname(),
                            Config.port, Config.root, SERVER_VERSION))
                fh.write("# " + "-" * 76 + "\n")
        return path
    except OSError as exc:
        LOG_FILE = None
        sys.stderr.write("! log directory not writable (%s), operation logging disabled\n" % exc)
    return LOG_FILE


def write_log(level, who, ip, op, path, extra=""):
    """写一行结构化日志：TIMESTAMP | LEVEL | user= | ip= | op= | path= [| extra]

    跨自然日时自动切换至新文件，并补写头部说明。
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    tail = (" | " + extra) if extra else ""
    line = '%s | %-5s | user=%s | ip=%s | op=%s | path="%s"%s\n' % (ts, level, who, ip, op, path, tail)
    with LOG_LOCK:
        if not LOG_FILE:
            return
        try:
            day = time.strftime("%Y%m%d")
            if LOG_DATE != day or not os.path.exists(LOG_FILE):
                init_log()
            if not LOG_FILE:
                return
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass


def sanitize_who(raw):
    """访问者姓名：去除控制字符与竖线（避免破坏日志分列），限长 24 字"""
    s = "".join(ch for ch in (raw or "") if ch.isprintable()).strip()
    s = s.replace("|", "丨").replace("\r", " ").replace("\n", " ")
    s = " ".join(s.split())[:24]
    return s or "匿名访客"
