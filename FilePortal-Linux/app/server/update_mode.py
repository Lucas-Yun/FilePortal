# -*- coding: utf-8 -*-
# 模块说明：维护模式控制：停服务、挂维护页、跨平台进程管理
"""更新模式控制：停掉文件服务、在同一个端口挂一张“正在更新”的维护页。

普通启动器（launcher.bat）启动前会先执行 `--stop`，
所以再次双击普通启动器时会自动退出更新模式并恢复正常服务。
"""

import argparse
import configparser
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

def _home_dir():
    """定位可写数据目录；单文件 EXE 由启动器设置 FILEPORTAL_HOME。"""
    env = os.environ.get("FILEPORTAL_HOME")
    if env:
        return os.path.abspath(env)
    if getattr(sys, "frozen", False) and os.name == "nt":
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE = _home_dir()
CONFIG = os.path.join(BASE, "config.ini")
APP = os.path.join(BASE, "app.py")
UPDATE_SERVER = os.path.join(BASE, "update_server.py")
UPDATE_CLI = os.path.join(BASE, "update_mode.py")
RUNTIME = os.path.join(BASE, "runtime")
LOG_DIR = os.path.join(RUNTIME, "logs")
LOG = os.path.join(LOG_DIR, "_update_mode.log")
PID_FILE = os.path.join(RUNTIME, "update_mode.pid")
STATE_FILE = os.path.join(RUNTIME, "update_mode.json")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
FLAGS = (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
         if os.name == "nt" else 0)


def read_config():
    cfg = configparser.ConfigParser(interpolation=None)
    out = {}
    try:
        cfg.read(CONFIG, encoding="utf-8-sig")
        for sec in cfg.sections():
            for key, val in cfg.items(sec):
                out[key.strip().lower()] = val.strip()
    except Exception:
        pass
    return out


def port():
    try:
        return int(read_config().get("port") or 8000)
    except (TypeError, ValueError):
        return 8000


def host():
    return read_config().get("host") or "0.0.0.0"


def _ssl_files():
    cfg = read_config()
    cert = cfg.get("certfile") or ""
    key = cfg.get("keyfile") or cert
    if cert and not os.path.isabs(cert):
        cert = os.path.join(BASE, cert)
    if key and not os.path.isabs(key):
        key = os.path.join(BASE, key)
    if cert and key and os.path.isfile(cert) and os.path.isfile(key):
        return cert, key
    return "", ""


def _scheme():
    return "https" if _ssl_files()[0] else "http"


def _status_url():
    return "%s://127.0.0.1:%d/__update__/status" % (_scheme(), port())


def is_maintenance():
    """Read the maintenance marker from the HTTP service itself."""
    try:
        ctx = ssl._create_unverified_context() if _scheme() == "https" else None
        with urllib.request.urlopen(_status_url(), timeout=1.5, context=ctx) as resp:
            if (resp.headers.get("X-FilePortal-Mode") or "").lower() != "maintenance":
                return False
            body = resp.read(512).decode("utf-8", "ignore")
            try:
                data = json.loads(body)
            except ValueError:
                data = {}
            return bool(data.get("ok") and data.get("mode") == "maintenance")
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _pid_on_port(p=None):
    """找出监听指定端口的 PID。

    Windows 用 netstat，Linux 优先用 ss（大多数发行版自带），
    macOS/无 ss 的环境回退 lsof。找不到时返回 None。
    """
    p = p or port()
    if os.name == "nt":
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                 capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
        except Exception:
            return None
        for line in out.splitlines():
            if "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local = parts[1].strip()
            if local.startswith("["):
                continue
            if local.rsplit(":", 1)[-1] != str(p):
                continue
            try:
                return int(parts[-1])
            except ValueError:
                return None
        return None

    # Linux / macOS
    for cmd in (["ss", "-ltnp"], ["lsof", "-nP", "-iTCP:%d" % p, "-sTCP:LISTEN"]):
        try:
            out = subprocess.run(cmd, capture_output=True, timeout=10).stdout.decode("utf-8", "ignore")
        except Exception:
            continue
        if cmd[0] == "ss":
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                # ss 的 Local Address:Port 在第 4 列；必须先确认端口，
                # 否则会把任意一个带 pid= 的进程当成目标。
                if parts[3].rsplit(":", 1)[-1] != str(p):
                    continue
                if "pid=" in line:
                    try:
                        return int(line.split("pid=", 1)[1].split(",", 1)[0])
                    except ValueError:
                        continue
            continue
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    continue
    return None


def _proc_name(pid):
    """返回进程名；Linux/macOS 读 /proc 或 ps，Windows 用 tasklist。"""
    if not pid:
        return ""
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid,
                                  "/FO", "CSV", "/NH"],
                                 capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
        except Exception:
            return ""
        line = out.strip().splitlines()[0] if out.strip() else ""
        return line.split(",")[0].strip('"') if line else ""
    try:
        with open("/proc/%d/comm" % pid, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read().strip()
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                             capture_output=True, timeout=10).stdout.decode("utf-8", "ignore")
        return out.strip()
    except Exception:
        return ""


def _is_python(pid):
    """同时识别源码版 python 和单文件版 FilePortal.exe，避免误杀别的程序。"""
    name = _proc_name(pid).casefold()
    if not name:
        return False
    return ("python" in name or name.startswith("py")
            or "fileportal" in name)


def _kill_process(pid, tree=False):
    """只杀目标进程；Windows 可带 tree，Linux 不依赖外部命令。"""
    if not pid:
        return False
    if os.name == "nt":
        args = ["taskkill", "/PID", str(pid), "/F"]
        if tree:
            args.insert(3, "/T")
        try:
            subprocess.run(args, capture_output=True, timeout=20)
        except Exception:
            return False
        return True
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception:
        return False
    for _ in range(20):
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    try:
        import signal
        os.kill(pid, signal.SIGKILL)
    except Exception:
        return False
    return True


# 兼容旧名（维护页停止也只需要杀自身）
def _kill_tree(pid):
    return _kill_process(pid, tree=False)


def _wait_port_free(p=None, timeout=10.0):
    p = p or port()
    end = time.time() + timeout
    while time.time() < end:
        if _pid_on_port(p) is None:
            return True
        time.sleep(0.25)
    return _pid_on_port(p) is None


def _pid_alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                             capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
        return str(pid) in out and "No tasks" not in out and "没有运行" not in out
    except Exception:
        return False


def _write_state(pid):
    try:
        os.makedirs(RUNTIME, exist_ok=True)
        with open(PID_FILE, "w", encoding="ascii") as fh:
            fh.write(str(pid or ""))
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"pid": pid, "port": port(), "started": int(time.time())},
                      fh, ensure_ascii=False)
    except OSError:
        pass


def _clear_state():
    for path in (PID_FILE, STATE_FILE):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def child_env():
    """给子进程一份干净环境：去掉 PyInstaller 父进程的 PYTHONHOME/PYTHONPATH。

    单文件版父进程会把临时解包目录写进这两个变量；子进程再启动同一 EXE 时
    若继承它们，会拿旧目录当 stdlib，直接启动失败。所有拉起 EXE/python 的
    地方都应使用本函数。
    """
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "_MEIPASS2"):
        env.pop(key, None)
    # 明确让 PyInstaller 子进程重新解包，不能复用即将退出的父进程 _MEI 目录。
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def start_update_server():
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        logf = open(LOG, "a", encoding="utf-8", errors="ignore")
    except OSError:
        logf = subprocess.DEVNULL
    if getattr(sys, "frozen", False):
        # 单文件版：同一 EXE 用 --maintenance-server 进入内置维护页
        cmd = [sys.executable, "--maintenance-server",
               "--port", str(port()), "--host", host()]
    else:
        cmd = [sys.executable, UPDATE_SERVER, "--port", str(port()), "--host", host()]
    try:
        proc = subprocess.Popen(
            cmd, cwd=BASE, stdin=subprocess.DEVNULL, stdout=logf,
            stderr=subprocess.STDOUT, close_fds=True, creationflags=FLAGS,
            env=child_env())
    except Exception as exc:
        print("  [ERROR] Could not start the maintenance server: %s" % exc)
        return None
    finally:
        try:
            if logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass
    return proc.pid


def enter(delay=0.0):
    if delay > 0:
        time.sleep(delay)
    p = port()
    if is_maintenance():
        print("  [INFO] Update mode is already running on port %d." % p)
        return 0

    pid = _pid_on_port(p)
    if pid:
        name = _proc_name(pid) or "unknown"
        if not _is_python(pid):
            print("  [ERROR] Port %d is held by %s (PID %d), not FilePortal." % (p, name, pid))
            print("          Stop that program first; refusing to kill an unrelated process.")
            return 1
        print("  [INFO] Stopping File Service Platform (PID %d)..." % pid)
        if not _kill_tree(pid) or not _wait_port_free(p, 12):
            print("  [ERROR] Could not stop the file service / release port %d." % p)
            return 1
    else:
        print("  [INFO] File Service Platform is not running; port %d is free." % p)

    pid = start_update_server()
    if not pid:
        print("  [ERROR] Maintenance server did not start.")
        return 1
    for _ in range(40):
        if is_maintenance():
            _write_state(pid)
            print("  [OK] Update mode is active on %s://127.0.0.1:%d" % (_scheme(), p))
            print("       Open the maintenance page in a browser; the admin can restore from there.")
            return 0
        time.sleep(0.25)
    if not _pid_alive(pid):
        print("  [ERROR] Maintenance server exited. See %s" % LOG)
    else:
        print("  [ERROR] Maintenance page did not answer on port %d. See %s" % (p, LOG))
    _kill_tree(pid)
    _clear_state()
    return 1


def stop():
    p = port()
    pid = _pid_on_port(p)
    if not pid:
        _clear_state()
        print("  [INFO] Update mode is not running.")
        return 0
    if not is_maintenance():
        if _is_python(pid):
            print("  [INFO] File Service Platform is running normally; update mode is not active.")
        else:
            print("  [INFO] Port %d is held by another program; nothing to stop." % p)
        _clear_state()
        return 0
    print("  [INFO] Leaving update mode; stopping maintenance page (PID %d)..." % pid)
    if not _kill_tree(pid) or not _wait_port_free(p, 10):
        print("  [ERROR] Could not stop the maintenance page / release port %d." % p)
        return 1
    _clear_state()
    print("  [OK] Update mode stopped; port %d is free." % p)
    return 0


def _health_url():
    return "%s://127.0.0.1:%d/healthz" % (_scheme(), port())


def _service_ready(timeout=1.2):
    try:
        ctx = ssl._create_unverified_context() if _scheme() == "https" else None
        with urllib.request.urlopen(_health_url(), timeout=timeout, context=ctx) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_file_service():
    """正常服务启动：维护页退出后重新拉起 app.py 或单文件 EXE。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        logf = open(os.path.join(LOG_DIR, "_service_restore.log"), "a",
                    encoding="utf-8", errors="ignore")
    except OSError:
        logf = subprocess.DEVNULL
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--service"]
    else:
        cmd = [sys.executable, APP]
    try:
        proc = subprocess.Popen(
            cmd, cwd=BASE, stdin=subprocess.DEVNULL,
            stdout=logf, stderr=subprocess.STDOUT, close_fds=True,
            creationflags=FLAGS, env=child_env())
        return proc.pid
    except Exception as exc:
        print("  [ERROR] Could not start the file service: %s" % exc)
        return None
    finally:
        try:
            if logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass


def resume(delay=0.0):
    """网页管理员验证密码后：停维护页 -> 重新拉起正常服务。"""
    if delay > 0:
        time.sleep(delay)
    p = port()
    if not is_maintenance():
        pid = _pid_on_port(p)
        if pid and _is_python(pid):
            print("  [INFO] File Service Platform is already running normally (PID %d)." % pid)
            return 0
        if pid:
            print("  [ERROR] Port %d is held by %s (PID %d), not FilePortal."
                  % (p, _proc_name(pid) or "unknown", pid))
            return 1
        print("  [INFO] Neither maintenance page nor file service is running on port %d." % p)
        return 1

    if stop() != 0:
        return 1

    pid = start_file_service()
    if not pid:
        print("  [ERROR] Maintenance page stopped, but the file service did not start.")
        enter(0)          # 启动失败时把维护页挂回去，方便管理员重试
        return 1
    for _ in range(40):
        if _service_ready():
            print("  [OK] File Service Platform restored on %s://127.0.0.1:%d (PID %d)."
                  % (_scheme(), p, pid))
            return 0
        time.sleep(0.25)
    if not _pid_alive(pid):
        print("  [ERROR] File service process exited before becoming ready.")
        enter(0)
        return 1
    print("  [WARN] File service process started (PID %d), but /healthz is not ready yet. See %s"
          % (pid, os.path.join(LOG_DIR, "_service_restore.log")))
    return 0


def spawn_enter(delay=2.0):
    """网页后台按钮：先让响应返回，再异步切换维护页。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        logf = open(LOG, "a", encoding="utf-8", errors="ignore")
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--update-mode", "--enter",
                   "--delay", str(delay)]
        else:
            cmd = [sys.executable, UPDATE_CLI, "--enter", "--delay", str(delay)]
        subprocess.Popen(
            cmd,
            cwd=BASE, stdin=subprocess.DEVNULL, stdout=logf,
            stderr=subprocess.STDOUT, close_fds=True, creationflags=FLAGS,
            env=child_env())
        return True
    except Exception:
        return False
    finally:
        try:
            if 'logf' in locals() and logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass


def status():
    pid = _pid_on_port()
    active = is_maintenance()
    print("  Port: %d" % port())
    print("  Mode: %s" % ("update mode" if active else
                         ("file service" if pid else "stopped")))
    if pid:
        print("  PID: %d (%s)" % (pid, _proc_name(pid) or "unknown"))
    if active:
        print("  URL: %s://127.0.0.1:%d" % (_scheme(), port()))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="FilePortal update mode")
    ap.add_argument("--enter", action="store_true", help="stop the file service and show the maintenance page")
    ap.add_argument("--resume", action="store_true",
                    help="stop the maintenance page and restart the normal file service")
    ap.add_argument("--stop", action="store_true", help="stop the maintenance page and free the port")
    ap.add_argument("--status", action="store_true", help="show current mode")
    ap.add_argument("--delay", type=float, default=0.0, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.enter:
        return enter(args.delay)
    if args.resume:
        return resume(args.delay)
    if args.stop:
        return stop()
    return status()


if __name__ == "__main__":
    sys.exit(main())
