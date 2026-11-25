# -*- coding: utf-8 -*-
"""文件服务平台 · 运维控制台

双击「launcher.sh」即运行本程序（Linux 下在终端执行 ./launcher.sh）。

设计说明：
  · 服务本体（app.py）以后台进程运行，标准输出写入 log 目录下的 _stdout.log，
    本窗口仅显示所执行的命令及其结果，不显示访问日志。
  · 仅当执行 logs 命令时输出日志（logs -f 为持续跟踪模式）。
  · 关闭窗口不会终止服务（服务为独立进程）；停止服务请执行 stop。
  · 本程序仅依赖 Python 标准库，且不导入服务自身模块；
    即使 server\\ 内代码出现异常，控制台仍可正常查看日志、修改端口及停止服务。
"""

import configparser
import http.cookiejar
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT = os.environ.get("FILEPORTAL_HOME") or os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(PROJECT, "config.ini")
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
LOG_DIR = os.path.join(PROJECT, "runtime", "logs")
CACHE_DIR = os.path.join(PROJECT, "runtime", "cache")
STDOUT_LOG = os.path.join(LOG_DIR, "_stdout.log")
BLACKLIST = os.path.join(PROJECT, "data", "lists", "blacklist")
IS_WIN = os.name == "nt"

if not IS_WIN:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import linux_service  # noqa: E402

FALLBACK = {
    "port": "8000",
    "host": "0.0.0.0",
    "projection_root": "",
    "root": "",
    "admin_name": "Admin",
    "pw_full": "",
    "whitelist_dir": "data/lists/whitelist",
    "blacklist_dir": "data/lists/blacklist",
    "file_threads": "16",
    "zip_threads": "12",
    "request_timeout": "60",
    "dl_token_hours": "12",
}

CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008
NEW_GROUP = 0x00000200


# --------------------------------------------------------------------------- #
# 配置（只用标准库解析，不依赖 server 包）
# --------------------------------------------------------------------------- #
def read_ini():
    cfg = configparser.ConfigParser(interpolation=None)
    out = {}
    try:
        cfg.read(CONFIG, encoding="utf-8-sig")
    except Exception:
        return out
    for sec in cfg.sections():
        for k, v in cfg.items(sec):
            out[k.strip().lower()] = v.strip()
    return out


def get(key, default=""):
    val = read_ini().get(key.lower())
    if val is None or val == "":
        return FALLBACK.get(key.lower(), default)
    return val


_PORT_OVERRIDE = None       # --port 临时端口（调试用），非 None 时整个控制台都用它


def port():
    if _PORT_OVERRIDE:
        return _PORT_OVERRIDE
    try:
        return int(get("port"))
    except ValueError:
        return 8000


def admin_name():
    return get("admin_name", "Admin") or "Admin"


# --------------------------------------------------------------------------- #
# 端口 / 进程探测
# --------------------------------------------------------------------------- #
def is_listening(p=None):
    p = p or port()
    try:
        with socket.create_connection(("127.0.0.1", p), timeout=0.6):
            return True
    except OSError:
        return False


def _netstat_pid(p):
    if not IS_WIN:
        return linux_service.pid_on_port(p)
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                             timeout=15).stdout.decode("utf-8", "ignore")
    except Exception:
        return None
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        host = parts[1].strip()
        if host.startswith("["):        # IPv6 形如 [::]:8000，跳过
            continue
        if host.rsplit(":", 1)[-1] != str(p):
            continue
        try:
            return int(parts[-1])
        except ValueError:
            return None
    return None


def _proc_name(pid):
    if not IS_WIN:
        cmd = linux_service.proc_cmdline(pid)
        return os.path.basename(cmd.split(" ")[0]) if cmd else ""
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                             capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
    except Exception:                             # noqa: BLE001
        return ""
    return out.strip().split(",")[0].strip('"') if out.strip() else ""


def _service_pid():
    """当前监听端口的进程 PID（只认 python / py，避免误杀别的程序）"""
    pid = _netstat_pid(port())
    if not pid:
        return None
    if not IS_WIN:
        cmd = linux_service.proc_cmdline(pid)
        return pid if ("app.py" in cmd or "linux_launcher.py" in cmd or "FilePortal" in cmd) else None
    name = _proc_name(pid)
    if "python" in name.lower() or name.lower().startswith("py"):
        return pid
    return None


# --------------------------------------------------------------------------- #
# 起 / 停
# --------------------------------------------------------------------------- #
def start(p=None, quiet=False):
    p = p or port()
    if is_listening(p):
        if not quiet:
            print("  服务已在运行（%s:%d），无需重复启动。" % (_lan_hint(), p))
        return True
    if not os.path.exists(APP):
        print("  [错误] 未找到 app.py：%s" % APP)
        return False
    os.makedirs(LOG_DIR, exist_ok=True)
    if not IS_WIN:
        if linux_service.start_service(PROJECT, p, STDOUT_LOG):
            if not quiet:
                print("  服务已启动：http://127.0.0.1:%d" % p)
                print("  局域网地址：%s" % _lan_addrs(p))
                print("  （服务在后台运行，关闭本窗口不会停止；停止服务请执行 stop）")
            return True
        print("  [错误] 启动失败，请查看 %s" % STDOUT_LOG)
        return False
    try:
        logf = open(STDOUT_LOG, "a", encoding="utf-8", errors="ignore")
    except OSError:
        logf = subprocess.DEVNULL
    cmd = [sys.executable, APP, "--port", str(p)]
    try:
        subprocess.Popen(cmd, cwd=PROJECT, stdout=logf, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, close_fds=True,
                         creationflags=DETACHED | NEW_GROUP | CREATE_NO_WINDOW)
    except Exception as exc:                      # noqa: BLE001
        print("  [错误] 启动失败：%s" % exc)
        return False
    finally:
        try:
            logf.close()      # 子进程自己持有句柄，这里可以关
        except Exception:     # noqa: BLE001
            pass
    for _ in range(20):       # 最多等 5 秒
        time.sleep(0.25)
        if is_listening(p):
            break
    else:
        print("  [警告] 服务未能启动（端口 %d 未处于监听状态）。" % p)
        print("         如需查看启动错误，请执行 logs 或直接打开 %s" % STDOUT_LOG)
        return False
    if not quiet:
        print("  服务已启动：http://127.0.0.1:%d" % p)
        print("  局域网地址：%s" % _lan_addrs(p))
        print("  （服务在后台运行，关闭本窗口不会停止；停止服务请执行 stop）")
    return True


def stop(quiet=False):
    p = port()
    pid = _service_pid()
    if not pid and not IS_WIN:
        if is_listening(p):
            print("  [提示] 端口 %d 已被其他程序占用（非本服务），本次操作不对其进行处理。" % p)
        else:
            if not quiet:
                print("  服务当前未运行。")
        return True
    if not pid:
        if is_listening(p):
            print("  [提示] 端口 %d 已被其他程序占用（非本服务），本次操作不对其进行处理。" % p)
        else:
            if not quiet:
                print("  服务当前未运行。")
        return True
    if not IS_WIN:
        if linux_service.stop_service(p):
            if not quiet:
                print("  服务已停止（PID %d）。" % pid)
            return True
        print("  [错误] 停止失败，请手动结束 PID %d。" % pid)
        return False
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=20)
    except Exception as exc:                      # noqa: BLE001
        print("  [错误] 停止失败：%s" % exc)
        return False
    for _ in range(20):
        time.sleep(0.25)
        if not is_listening(p):
            break
    if not quiet:
        print("  服务已停止（PID %d）。" % pid)
    return True


def restart():
    print("  正在重启服务")
    stop(quiet=True)
    time.sleep(0.6)
    return start()


# --------------------------------------------------------------------------- #
# 地址
# --------------------------------------------------------------------------- #
def _lan_addrs(p=None):
    p = p or port()
    hosts = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip not in hosts:
                hosts.append(ip)
    except Exception:                             # noqa: BLE001
        pass
    try:                                          # 补一个"默认出口"网卡的地址
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("223.5.5.5", 53))
        ip = s.getsockname()[0]
        if ip and ip not in hosts:
            hosts.insert(0, ip)
        s.close()
    except Exception:                             # noqa: BLE001
        pass
    items = ["http://%s:%d" % (ip, p) for ip in hosts if not ip.startswith("127.")]
    return "  ".join(items) or "（未检测到局域网地址，请检查网络适配器）"


def _lan_hint():
    return "127.0.0.1"


def cmd_addr():
    p = port()
    print("  本机：    http://127.0.0.1:%d" % p)
    print("  局域网：  %s" % _lan_addrs(p))
    print("  外网：    在内网穿透服务中将外部端口映射至本机 %d 端口" % p)
    https_p = get("https_port", "0")
    if https_p and https_p != "0":
        print("  HTTPS：   https://127.0.0.1:%s" % https_p)


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
def _newest_log():
    files = []
    if os.path.isdir(LOG_DIR):
        for name in os.listdir(LOG_DIR):
            path = os.path.join(LOG_DIR, name)
            if os.path.isfile(path) and name.lower().endswith(".log") and not name.startswith("_"):
                files.append((os.path.getmtime(path), path))
    return max(files)[1] if files else None


def _read_lines(path, count):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return lines[-count:]


def cmd_logs(arg=""):
    files = []
    if os.path.isdir(LOG_DIR):
        for name in os.listdir(LOG_DIR):
            path = os.path.join(LOG_DIR, name)
            if os.path.isfile(path) and name.lower().endswith(".log") and not name.startswith("_"):
                files.append((os.path.getmtime(path), path))
    if not files:
        print("  log 目录中暂无日志文件（服务尚未被访问）。")
        return
    path = max(files)[1]
    print("  ── %s ──" % os.path.basename(path))
    arg = (arg or "").strip()
    if arg.startswith("-f") or arg == "follow":
        follow_log(path)
        return
    count = 40
    m = re.search(r"\d+", arg)
    if m:
        count = max(1, min(2000, int(m.group(0))))
    for line in _read_lines(path, count):
        print("  " + line.rstrip())
    print("  ── 已显示最后 %d 行；持续跟踪请使用 logs -f ──" % count)


def follow_log(path):
    print("  （持续跟踪中，按 Ctrl+C 退出跟踪）")
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            fh.seek(0, 2)
            while True:
                line = fh.readline()
                if not line:
                    time.sleep(0.4)
                    continue
                print("  " + line.rstrip())
    except KeyboardInterrupt:
        print("\n  已退出日志跟踪。")


# --------------------------------------------------------------------------- #
# 解除登录防护（走后台接口，不需要重启）
# --------------------------------------------------------------------------- #
def cmd_unlock():
    p = port()
    if not is_listening(p):
        print("  服务当前未运行，请先执行 start 启动服务后再解除防护。")
        return
    pw = get("pw_full")
    if not pw:
        print("  config.ini 中的 pw_full 为空，无法以管理身份登录。")
        return
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base = "http://127.0.0.1:%d" % p
    try:
        data = urllib.parse.urlencode({"who": admin_name(), "pw": pw}).encode()
        opener.open(base + "/login", data, timeout=10).read()
        req = urllib.request.Request(base + "/admin/unlock", data=b"", method="POST")
        raw = opener.open(req, timeout=10).read().decode("utf-8", "ignore")
        try:
            res = json.loads(raw)
            print("  " + (res.get("msg") or "已解除登录防护"))
        except ValueError:
            print("  已解除登录防护（服务返回：%s）" % raw[:80])
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            print("  请求被拒绝：姓名与后台身份 %s 不符，或 pw_full 不正确。" % admin_name())
        elif exc.code == 429:
            print("  后台登录同样受全站限速限制，请稍候重试。")
        else:
            print("  操作失败：HTTP %s" % exc.code)
    except Exception as exc:                      # noqa: BLE001
        print("  操作失败：%s" % exc)


# --------------------------------------------------------------------------- #
# 改端口 / 看配置 / 打开文件
# --------------------------------------------------------------------------- #
def cmd_port(value):
    if not value:
        print("  当前端口：%d" % port())
        print("  修改方式：port 8001")
        return
    if not value.isdigit() or not (1 <= int(value) <= 65535):
        print("  端口须为 1~65535 之间的整数。")
        return
    new = int(value)
    try:
        with open(CONFIG, encoding="utf-8-sig") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print("  无法读取 config.ini：%s" % exc)
        return
    section = ""
    done = False
    for i, line in enumerate(lines):
        m = re.match(r"\s*\[(.+?)\]", line)
        if m:
            section = m.group(1).strip()
            continue
        if section.startswith("服务器"):
            m = re.match(r"^(\s*port\s*=\s*)(\S+)(.*)$", line, re.I)
            if m:
                lines[i] = m.group(1) + str(new) + m.group(3).replace("\n", "") + "\n"
                done = True
                break
    if not done:
        print("  未在 config.ini 的 [服务器] 节中找到 port 配置项，请手动修改。")
        return
    try:
        with open(CONFIG, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
    except OSError as exc:
        print("  写入失败：%s" % exc)
        return
    print("  config.ini 中的端口已更新为 %d。" % new)
    print("  生效方式：执行 restart；同时须将内网穿透的目标端口同步调整为 %d。" % new)


def cmd_config():
    p = port()
    rows = [
        ("端口 port", str(p)),
        ("投射目录 projection_root", get("projection_root") or get("root")),
        ("云盘目录 cloud_root", get("cloud_root")),
        ("后台身份 admin_name", admin_name()),
        ("同时处理请求 workers", get("workers") or "自动"),
        ("文件下载并发 file_threads", get("file_threads")),
        ("打包下载并发 zip_threads", get("zip_threads")),
        ("请求超时 request_timeout", get("request_timeout") + " 秒"),
        ("下载通行证有效期 dl_token_hours", get("dl_token_hours") + " 小时"),
        ("白名单开关 whitelist_enforce", get("whitelist_enforce", "1")),
        ("白名单目录 whitelist_dir", get("whitelist_dir", "data/lists/whitelist")),
        ("黑名单目录 blacklist_dir", get("blacklist_dir", "data/lists/blacklist")),
        ("HTTPS 端口 https_port", get("https_port", "0")),
    ]
    print("  ── 当前关键配置 ──")
    for k, v in rows:
        print("  %-34s %s" % (k, v))
    print("  （全部可配置项位于 config.ini；亦可登录管理控制台在线修改）")


def cmd_status():
    p = port()
    pid = _service_pid()
    running = is_listening(p)
    print("  ── 服务状态 ──")
    if running and pid:
        print("  状态：运行中   PID %d   端口 %d" % (pid, p))
        print("  地址：http://127.0.0.1:%d   %s" % (p, _lan_addrs(p)))
    elif running:
        print("  状态：端口 %d 处于监听状态，但并非本服务（由其他程序占用）" % p)
    else:
        print("  状态：未运行（执行 start 启动）")
    log = _newest_log()
    print("  当日日志：%s" % (os.path.basename(log) if log else "（暂无）"))
    print("  目录：%s" % PROJECT)


def cmd_open():
    p = port()
    target = "http://127.0.0.1:%d" % p
    try:
        if IS_WIN:
            os.startfile(target)                  # noqa: S606
        elif not linux_service.open_target(target):
            raise OSError("未找到 xdg-open/gio，请手动打开 %s" % target)
        print("  已通过默认浏览器打开 %s" % target)
    except Exception as exc:                      # noqa: BLE001
        print("  打开失败：%s" % exc)


def cmd_edit(which=""):
    target = BLACKLIST if which.strip().lower() in ("black", "黑名单") else CONFIG
    if not os.path.exists(target):
        print("  未找到文件：%s" % target)
        return
    try:
        if IS_WIN:
            os.startfile(target)                  # noqa: S606
        elif os.path.isdir(target):
            print("  黑名单目录：%s" % target)
            return
        else:
            print("  请用编辑器打开：%s" % target)
            print("  提示：nano %s 或 gedit %s" % (target, target))
            return
        if os.path.isdir(target):
            print("  已打开黑名单目录：%s" % target)
        else:
            print("  已通过记事本打开 %s" % os.path.basename(target))
    except Exception as exc:                      # noqa: BLE001
        print("  打开失败：%s" % exc)


def cmd_white():
    path = get("whitelist_dir", "data/lists/whitelist")
    if not os.path.isabs(path):
        path = os.path.join(PROJECT, path)
    os.makedirs(path, exist_ok=True)
    if IS_WIN:
        try:
            os.startfile(path)                    # noqa: S606
            print("  已打开白名单目录：%s" % path)
        except Exception as exc:                  # noqa: BLE001
            print("  打开失败：%s" % exc)
    else:
        print("  白名单目录：%s" % path)


def cmd_cache():
    if not os.path.isdir(CACHE_DIR):
        print("  cache 目录不存在，暂无可清理内容。")
        return
    count, size = 0, 0
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if os.path.isfile(path):
            try:
                size += os.path.getsize(path)
                os.remove(path)
                count += 1
            except OSError:
                pass
    print("  已清理打包缓存 %d 个文件，释放空间 %.1f MB。" % (count, size / 1048576.0))


def cmd_online():
    """当前有效登录会话，按姓名汇总；直接读 sessions.json，不依赖服务进程。"""
    print("  ── 当前在线用户 ──")
    path = os.path.join(PROJECT, "data", "sessions.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        raw = payload.get("sessions") if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError):
        raw = {}
    window = 30 * 60
    now = time.time()
    groups = {}
    for _key, item in (raw or {}).items():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        base_kind = "cloud" if str(item.get("kind") or "") == "cloud" else "normal"
        rows = item.get("entries")
        if not isinstance(rows, list):
            rows = [item]
        seen_sids = set()
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
            if not sid or not ts or sid in seen_sids:
                continue
            if now - seen > window:
                continue
            seen_sids.add(sid)
            kind = "cloud" if str(row.get("kind") or base_kind) == "cloud" else "normal"
            key = name.casefold()
            g = groups.setdefault(key, {"name": name, "kinds": set(),
                                        "devices": 0, "last": 0})
            g["kinds"].add(kind)
            g["devices"] += 1
            g["last"] = max(g["last"], seen)
    users = sorted(groups.values(), key=lambda x: (x["name"].casefold(), -x["last"]))
    total = sum(u["devices"] for u in users)
    if not users:
        print("  当前没有最近 30 分钟内活跃的登录用户。")
        return
    print("  共 %d 人 / %d 台设备（最近 30 分钟活跃）" % (len(users), total))
    for u in users:
        kind = "个人云盘" if "cloud" in u["kinds"] else "普通访问"
        last = time.strftime("%Y-%m-%d %H:%M", time.localtime(u["last"]))
        print("  · %s（%s，%d 台设备）最近活跃 %s" % (u["name"], kind, u["devices"], last))


# --------------------------------------------------------------------------- #
# 帮助
# --------------------------------------------------------------------------- #
HELP = """  ── 可用命令 ──
  start              启动服务（若已在运行则不执行任何操作）
  stop               停止服务
  restart            重启服务（修改 config.ini 后使用）
  status             查看运行状态、PID、端口及当日日志文件
  online             查看当前在线用户（最近 30 分钟活跃）
  logs [行数]        查看当日日志（默认最后 40 行）
  logs -f            持续跟踪日志，Ctrl+C 退出
  unlock             解除登录防护（重置失败锁定与全站限速，无需重启）
  port               查看当前端口；port 8001 将端口改为 8001
  config             查看关键配置（端口、并发、超时、白名单等）
  edit               打开 config.ini（Linux 下按终端提示用编辑器打开）
  black              打开 data/lists/blacklist 黑名单目录
  white              打开 data/lists/whitelist 白名单目录
  cache              清空打包缓存（cache 目录）
  addr               输出本机、局域网及外网访问地址
  open               通过浏览器打开本机页面
  clear              清屏
  help               显示本帮助
  exit               退出控制台（服务继续在后台运行）"""


def dispatch(line):
    """返回 False 表示退出"""
    if not line:
        return True
    low = line.lower()
    parts = low.split()
    cmd = parts[0]
    arg = " ".join(line.split()[1:])
    cn = {
        "启动": "start", "停止": "stop", "重启": "restart", "状态": "status",
        "日志": "logs", "解锁": "unlock", "端口": "port", "配置": "config",
        "在线": "online", "在线用户": "online", "用户": "online",
        "编辑": "edit", "缓存": "cache", "地址": "addr", "打开": "open",
        "帮助": "help", "退出": "exit",
    }
    cmd = cn.get(cmd, cmd)

    if cmd in ("help", "?", "h"):
        print(HELP)
    elif cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        restart()
    elif cmd == "status":
        cmd_status()
    elif cmd in ("online", "users", "who"):
        cmd_online()
    elif cmd in ("logs", "log"):
        cmd_logs(arg)
    elif cmd in ("unlock", "unban", "reset"):
        cmd_unlock()
    elif cmd == "port":
        cmd_port(arg.strip())
    elif cmd in ("config", "cfg"):
        cmd_config()
    elif cmd == "edit":
        cmd_edit(arg)
    elif cmd in ("black", "blacklist"):
        cmd_edit("black")
    elif cmd in ("white", "whitelist"):
        cmd_white()
    elif cmd == "cache":
        cmd_cache()
    elif cmd == "addr":
        cmd_addr()
    elif cmd == "open":
        cmd_open()
    elif cmd in ("clear", "cls"):
        os.system("cls" if IS_WIN else "clear")
    elif cmd in ("exit", "quit", "q"):
        return False
    else:
        print("  无法识别的命令：%s（执行 help 查看可用命令）" % cmd)
    return True


def main():
    # 可选：--port N 临时用别的端口起一次（调试用，不改 config.ini）
    global _PORT_OVERRIDE
    override = None
    argv = sys.argv[1:]
    if "--port" in argv:
        try:
            override = int(argv[argv.index("--port") + 1])
        except (IndexError, ValueError):
            override = None
    if override:
        _PORT_OVERRIDE = override

    p = port()
    print("=" * 66)
    print("  文件服务平台 · 运维控制台")
    print("  投射目录：%s" % (get("projection_root") or get("root")))
    print("  端口：%d    项目：%s" % (p, PROJECT))
    print("=" * 66)

    if override:
        start(override, quiet=True)
        if is_listening(override):
            print("  已按临时端口 %d 启动（config.ini 未作修改）。" % override)
    else:
        if is_listening(p):
            print("  服务已在运行（127.0.0.1:%d），当前进入控制模式。" % p)
        else:
            start(p)

    print("  执行 help 查看命令。服务以后台进程运行，关闭窗口不会停止；停止服务请执行 stop。\n")

    try:
        while True:
            try:
                line = input("文件服务平台> ").strip()
            except EOFError:
                break
            if not dispatch(line):
                break
    except KeyboardInterrupt:
        print()
    finally:
        pid = _service_pid()
        if pid:
            print("  （服务仍在后台运行，PID %d；如需停止，请重新打开控制台并执行 stop。）" % pid)
        else:
            print("  （服务已停止。）")


if __name__ == "__main__":
    main()
