# -*- coding: utf-8 -*-
# 模块说明：维护页独立 HTTP 服务：503 页面、状态接口与管理员恢复
"""FilePortal 更新维护页（独立进程，不依赖 server 包）。

更新模式期间占用原来文件服务的端口，所有请求都返回 503 + 维护页，
这样外部打开网址时看到的是“正在更新”，而不是连接失败。
"""

import argparse
import configparser
import hmac
import html
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def _home_dir():
    """返回可写数据目录。

    - 源码版：app/ 目录；
    - Windows 单文件版：FILEPORTAL_HOME 指向 EXE 旁的 FilePortalData；
    - 其它冻结环境：使用 __file__ 所在目录兜底。
    """
    env = os.environ.get("FILEPORTAL_HOME")
    if env:
        return os.path.abspath(env)
    if getattr(sys, "frozen", False) and os.name == "nt":
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE = _home_dir()
CONFIG = os.path.join(BASE, "config.ini")
LOG_DIR = os.path.join(BASE, "runtime", "logs")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
FLAGS = (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
         if os.name == "nt" else 0)

_RESUME_MUTEX = threading.Lock()
_RESUME_FAILS = 0
_RESUME_LOCK_UNTIL = 0.0

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>文件服务正在更新</title>
<style>
*{box-sizing:border-box}
html,body{height:100%%;margin:0}
body{display:flex;align-items:center;justify-content:center;padding:24px;
  font:14px/1.75 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  color:#183248;background:linear-gradient(135deg,#0b4f86,#1279b8 48%%,#0d95a6);
  background-attachment:fixed;background-size:cover;background-repeat:no-repeat;
  overscroll-behavior-y:contain}
.card{width:100%%;max-width:520px;background:rgba(255,255,255,.94);border-radius:18px;
  box-shadow:0 18px 50px rgba(4,30,55,.28);padding:30px 28px 24px;text-align:center}
.logo{width:56px;height:56px;margin:0 auto 14px;border-radius:16px;
  background:linear-gradient(135deg,#0f6fbd,#0d95a6);display:flex;align-items:center;
  justify-content:center;color:#fff;font-size:26px;font-weight:700}
h1{margin:0 0 8px;font-size:23px;letter-spacing:.5px;color:#0b4f86}
.sub{margin:0 0 18px;font-size:14px;color:#5d7486}
.status{display:inline-flex;align-items:center;gap:8px;background:#eef7fc;color:#0f6fbd;
  border:1px solid #d7ebf7;border-radius:999px;padding:7px 13px;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%%;background:#19a974;animation:pulse 1.4s infinite}
@keyframes pulse{0%%{opacity:.35}50%%{opacity:1}100%%{opacity:.35}}
.msg{margin:18px 0 0;color:#3d5668;font-size:14px;line-height:1.9;text-align:left}
.msg b{color:#0b4f86}
.tip{margin:16px 0 0;padding:11px 13px;border-radius:10px;background:#f7fafc;
  border:1px dashed #d8e5ef;color:#7a8c9b;font-size:12.5px;text-align:left}
.err{margin:16px 0 0;padding:10px 12px;border-radius:9px;background:#fdecec;
  color:#c0392b;font-size:13px;text-align:left;line-height:1.65}
.resume{margin:18px 0 0;padding:16px 16px 14px;border:1px solid #d7e6f2;border-radius:13px;
  background:#f8fbfe;text-align:left}
.rh{margin:0 0 5px;font-size:14px;font-weight:700;color:#0b4f86}
.rt{margin:0 0 12px;color:#738798;font-size:12.5px;line-height:1.7}
.resume label{display:block;margin:0 0 6px;font-size:12.5px;color:#4d687c}
.resume input{width:100%%;height:44px;border:1px solid #cfe0ed;border-radius:10px;
  padding:0 12px;font-size:15px;color:#183248;background:#fff;outline:none}
.resume input:focus{border-color:#0f6fbd;box-shadow:0 0 0 3px rgba(15,111,189,.13)}
.resume button{width:100%%;height:45px;margin-top:12px;border:0;border-radius:10px;cursor:pointer;
  background:linear-gradient(135deg,#0f6fbd,#0d95a6);color:#fff;font-size:14.5px;font-weight:600}
.resume button:hover{filter:brightness(1.05)}
.foot{margin-top:20px;padding-top:14px;border-top:1px solid #e8f0f5;
  color:#98a8b4;font-size:12px}
@media (max-width:480px){.card{padding:24px 18px 20px}h1{font-size:20px}.msg{font-size:13.5px}}
</style></head>
<body>
<div class="card">
  <div class="logo">FP</div>
  <h1>文件服务正在更新</h1>
  <p class="sub">该服务当前处于维护状态，暂时无法访问</p>
  <div class="status"><span class="dot"></span>正在更新维护，请稍后再试</div>
  %(error)s
  <div class="msg">
    为避免文件被占用或数据不一致，文件服务已暂时停止。<br>
    <b>更新完成后，本页面会自动刷新；</b>如果没有自动恢复，请手动重新打开本页。
  </div>
  <div class="resume">
    <div class="rh">管理员恢复</div>
    <p class="rt">输入最高权限密码并确认后，维护页会退出并自动重新启动文件服务，无需再打开终端或启动器。</p>
    <form method="post" action="/__update__/resume" autocomplete="off">
      <label for="password">最高权限密码</label>
      <input id="password" name="password" type="password" maxlength="128"
             placeholder="请输入管理员最高权限密码" required>
      <button type="submit">恢复正常服务</button>
    </form>
  </div>
  <div class="tip">如果你不是管理员，请不要反复刷新或尝试上传；更新期间不会丢失已有文件。<br>
    管理完成后会恢复正常访问，无需重新登录以外的额外操作。</div>
  <div class="foot">FilePortal · 更新维护模式 · %(time)s</div>
</div>
</body></html>"""

RESUMING_PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="4;url=/">
<title>正在恢复正常服务</title>
<style>
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:flex;align-items:center;justify-content:center;padding:24px;
  font:14px/1.75 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  color:#183248;background:linear-gradient(135deg,#0b4f86,#1279b8 48%,#0d95a6);
  background-attachment:fixed;background-size:cover;background-repeat:no-repeat}
.card{width:100%;max-width:520px;background:rgba(255,255,255,.95);border-radius:18px;
  box-shadow:0 18px 50px rgba(4,30,55,.28);padding:30px 28px 24px;text-align:center}
.logo{width:56px;height:56px;margin:0 auto 14px;border-radius:16px;
  background:linear-gradient(135deg,#0f6fbd,#0d95a6);display:flex;align-items:center;
  justify-content:center;color:#fff;font-size:26px;font-weight:700}
h1{margin:0 0 8px;font-size:23px;letter-spacing:.5px;color:#0b4f86}
.sub{margin:0 0 18px;font-size:14px;color:#5d7486}
.status{display:inline-flex;align-items:center;gap:8px;background:#eef7fc;color:#0f6fbd;
  border:1px solid #d7ebf7;border-radius:999px;padding:7px 13px;font-size:13px}
.dot{width:8px;height:8px;border-radius:50%;background:#19a974;animation:pulse 1.4s infinite}
@keyframes pulse{0%{opacity:.35}50%{opacity:1}100%{opacity:.35}}
.msg{margin:18px 0 0;color:#3d5668;font-size:14px;line-height:1.9;text-align:left}
.foot{margin-top:20px;padding-top:14px;border-top:1px solid #e8f0f5;
  color:#98a8b4;font-size:12px}
</style></head>
<body>
<div class="card">
  <div class="logo">FP</div>
  <h1>正在恢复正常服务</h1>
  <p class="sub">密码校验通过，维护页正在退出，文件服务即将重新启动。</p>
  <div class="status"><span class="dot"></span>正在恢复，请不要关闭本页</div>
  <div class="msg">
    本页会在 4 秒后自动刷新。若仍显示维护页，请稍等几秒再刷新；<br>
    若长时间无法打开，请查看 <b>runtime/logs/_service_restore.log</b>。
  </div>
  <div class="foot">FilePortal · 正在退出维护模式</div>
</div>
</body></html>"""


def _resume_locked():
    with _RESUME_MUTEX:
        return time.time() < _RESUME_LOCK_UNTIL


def _note_resume_fail():
    global _RESUME_FAILS, _RESUME_LOCK_UNTIL
    with _RESUME_MUTEX:
        _RESUME_FAILS += 1
        if _RESUME_FAILS >= 5:
            _RESUME_FAILS = 0
            _RESUME_LOCK_UNTIL = time.time() + 60


def _reset_resume_fail():
    global _RESUME_FAILS, _RESUME_LOCK_UNTIL
    with _RESUME_MUTEX:
        _RESUME_FAILS = 0
        _RESUME_LOCK_UNTIL = 0.0


def admin_password_ok(value):
    """与正常服务一致：admin_password 优先，留空回退最高权限密码 pw_full。"""
    given = (value or "").strip().casefold()
    if not given:
        return False
    cfg = read_config()
    for key in ("admin_password", "pw_full"):
        candidate = (cfg.get(key) or "").strip().casefold()
        if candidate and hmac.compare_digest(given, candidate):
            return True
    return False


def spawn_resume(delay=1.2):
    """让响应先回到浏览器，再由独立进程停止维护页并拉起正常服务。

    单文件 EXE 不能直接执行 update_mode.py，所以冻结版改为启动自身
    的 --update-mode --resume 分支；源码版仍走脚本。
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        logf = open(os.path.join(LOG_DIR, "_update_mode.log"), "a",
                    encoding="utf-8", errors="ignore")
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--update-mode", "--resume",
                   "--delay", str(delay)]
        else:
            cmd = [sys.executable, os.path.join(BASE, "update_mode.py"),
                   "--resume", "--delay", str(delay)]
        subprocess.Popen(
            cmd,
            cwd=BASE, stdin=subprocess.DEVNULL, stdout=logf,
            stderr=subprocess.STDOUT, close_fds=True, creationflags=FLAGS)
        return True
    except Exception:
        return False
    finally:
        try:
            if 'logf' in locals() and logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:
            pass


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


def config_port():
    try:
        return int(read_config().get("port") or 8000)
    except (TypeError, ValueError):
        return 8000


def config_host():
    return read_config().get("host") or "0.0.0.0"


def ssl_files():
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


class Handler(BaseHTTPRequestHandler):
    server_version = "FilePortalMaintenance/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _headers(self, status, ctype, length, extra=None, retry="30"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-FilePortal-Mode", "maintenance")
        if retry:
            self.send_header("Retry-After", str(retry))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.close_connection = True

    def _status(self):
        body = json.dumps({"ok": True, "mode": "maintenance", "port": self.server.server_port},
                          ensure_ascii=False).encode("utf-8")
        self._headers(200, "application/json; charset=utf-8", len(body), retry=None)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _page(self, error="", status=503):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        error_html = ""
        if error:
            error_html = '<div class="err">%s</div>' % html.escape(error)
        body = (PAGE % {"time": html.escape(stamp), "error": error_html}).encode("utf-8")
        self._headers(status, "text/html; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _resuming(self):
        body = RESUMING_PAGE.encode("utf-8")
        self._headers(200, "text/html; charset=utf-8", len(body), retry=None)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_form(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0 or length > 8192:
            return {}
        try:
            data = self.rfile.read(length)
            parsed = urllib.parse.parse_qs(data.decode("utf-8", "ignore"), keep_blank_values=True)
        except Exception:
            return {}
        return {k: (v[0] if v else "") for k, v in parsed.items()}

    def _handle_resume(self):
        if _resume_locked():
            self._page("密码错误次数过多，请 60 秒后再试。", 429)
            return
        form = self._read_form()
        password = form.get("password") or form.get("admin_password") or ""
        if not admin_password_ok(password):
            _note_resume_fail()
            self._page("密码不正确，请重试。", 403)
            return
        _reset_resume_fail()
        if not spawn_resume():
            self._page("密码正确，但恢复进程启动失败；请检查 runtime/logs/_update_mode.log。", 500)
            return
        self._resuming()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/__update__/status":
            self._status()
        elif path == "/healthz":
            body = json.dumps({"ok": False, "mode": "maintenance"}).encode("utf-8")
            self._headers(503, "application/json; charset=utf-8", len(body))
            if self.command != "HEAD":
                self.wfile.write(body)
        else:
            self._page()

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/__update__/resume":
            self._handle_resume()
            return
        self._page()

    def do_PUT(self):
        self._page()

    def do_DELETE(self):
        self._page()


class MaintenanceServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv=None):
    ap = argparse.ArgumentParser(description="FilePortal maintenance page")
    ap.add_argument("--port", type=int, default=config_port())
    ap.add_argument("--host", default=config_host())
    args = ap.parse_args(argv)

    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        s = socket.create_connection(("127.0.0.1", args.port), timeout=0.8)
        s.close()
        print("[错误] 端口 %d 已有程序在监听；更新模式不会覆盖正在运行的服务。" % args.port)
        return 1
    except OSError:
        pass

    try:
        httpd = MaintenanceServer((args.host, args.port), Handler)
    except OSError as exc:
        print("[错误] 无法在 %s:%d 上启动维护页：%s" % (args.host, args.port, exc))
        return 1

    cert, key = ssl_files()
    if cert:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
            print("[信息] HTTPS 维护页已启用：%s" % cert)
        except Exception as exc:
            print("[警告] HTTPS 证书加载失败，维护页退回 HTTP：%s" % exc)

    print("[信息] 更新维护页已启动：%s://%s:%d" %
          ("https" if cert else "http", args.host, args.port))
    try:
        httpd.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n维护页已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
