# -*- coding: utf-8 -*-
"""Small POSIX helpers for the Linux edition: PID lookup, start/stop, openers."""
import os
import re
import signal
import socket
import subprocess
import sys
import time


def is_listening(port):
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.6):
            return True
    except OSError:
        return False


def _pid_from_proc(port):
    """Read /proc/net/tcp{,6}, then find the process holding the socket inode."""
    inodes = set()
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(name, encoding="ascii", errors="ignore") as fh:
                for line in fh.readlines()[1:]:
                    parts = line.split()
                    if len(parts) < 10 or parts[3] != "0A":  # 0A = LISTEN
                        continue
                    local = parts[1]
                    if ":" not in local:
                        continue
                    if int(local.rsplit(":", 1)[1], 16) != int(port):
                        continue
                    inodes.add(parts[9])
        except OSError:
            continue
    if not inodes:
        return None
    wanted = {"socket:[%s]" % inode for inode in inodes}
    for pid_dir in os.listdir("/proc"):
        if not pid_dir.isdigit():
            continue
        fd_dir = "/proc/%s/fd" % pid_dir
        try:
            for fd in os.listdir(fd_dir):
                try:
                    link = os.readlink(os.path.join(fd_dir, fd))
                except OSError:
                    continue
                if link in wanted:
                    return int(pid_dir)
        except OSError:
            continue
    return None


def pid_on_port(port):
    try:
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True,
                             timeout=8).stdout
        for line in out.splitlines():
            if (":%d " % int(port)) not in line and (":%d" % int(port)) not in line:
                continue
            m = re.search(r"pid=(\d+)", line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return _pid_from_proc(port)


def proc_cmdline(pid):
    try:
        with open("/proc/%d/cmdline" % int(pid), "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "ignore")
    except OSError:
        return ""


def start_service(app_dir, port, stdout_log):
    os.makedirs(os.path.dirname(stdout_log), exist_ok=True)
    try:
        logf = open(stdout_log, "a", encoding="utf-8", errors="ignore")
    except OSError:
        logf = subprocess.DEVNULL
    try:
        subprocess.Popen(
            [sys.executable, os.path.join(app_dir, "app.py"), "--port", str(int(port))],
            cwd=app_dir, stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True,
        )
    except Exception:
        try:
            if logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass
        return False
    finally:
        try:
            if logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass
    for _ in range(40):
        time.sleep(0.25)
        if is_listening(port):
            return True
    return False


def stop_service(port):
    pid = pid_on_port(port)
    if not pid:
        return not is_listening(port)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(30):
        time.sleep(0.25)
        if not is_listening(port):
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    for _ in range(20):
        time.sleep(0.2)
        if not is_listening(port):
            return True
    return False


def open_target(target):
    """Open a URL/file with the desktop opener; return True on success."""
    for cmd in (["xdg-open", target], ["gio", "open", target]):
        try:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return True
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return False
