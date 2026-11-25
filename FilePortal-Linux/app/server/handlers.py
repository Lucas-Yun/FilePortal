# -*- coding: utf-8 -*-
"""HTTP 请求处理：路由与各个接口的实现。"""

import hashlib
import hmac
import html
import json
import math
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler

from .settings import *
from . import settings
from .fsutil import *
from . import fsutil
from .icons import *
from .oplog import write_log, sanitize_who
from .views import (build_login, build_page, build_error,
                    build_notice, build_apply, build_setpw)
from . import zcache
from . import blocked
from . import thumbs
from . import rules as rulesmod
from . import roster
from . import sessions
from . import i18n

MAX_FORM_BYTES = 2 * 1024 * 1024          # 登录/后台等普通表单上限
MAX_AVATAR_BYTES = 12 * 1024 * 1024       # 头像请求体硬上限（真正的配置上限另算）
from . import dltoken
from . import adminui
from . import accounts
from . import trash

# 下载并发闸门：全站同时最多这么多条下载连接，超了排队等（等不到就 503）。
# 两台设备同时下同一个文件、配置 32 的话，服务端只能喂 32 条，自然就各摊一半，
# 谁也不会把本机的上行/磁盘吃干净。
FILE_STREAMS = threading.BoundedSemaphore(FILE_THREADS)
ZIP_STREAMS = threading.BoundedSemaphore(ZIP_THREADS)


def _rel_for_log(path, base=None):
    """日志里的路径统一相对根目录，中文照写。
    云空间用户的根在 cloud_root 下（不在存储根里），所以两个根都试一下。"""
    roots = [base or Config.root]
    try:
        roots.append(accounts.cloud_root())
    except Exception:  # noqa: BLE001
        pass
    for root in roots:
        try:
            rel = os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            continue
        if not rel.startswith(".."):
            return "" if rel == "." else rel
    try:
        return os.path.relpath(path, Config.root).replace("\\", "/")
    except ValueError:
        return path


def _dir_size(path, budget_seconds=5.0, max_items=200000):
    """递归算文件夹总大小。有预算：时间或条目数超了就停，返回 (字节, 文件数, 是否截断)"""
    total = 0
    count = 0
    truncated = False
    t0 = time.monotonic()
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.lower() in HIDDEN_NAMES or e.name.startswith("~$"):
                        continue
                    if blocked.is_blocked(e.path):
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        continue
                    if count >= max_items or (time.monotonic() - t0) > budget_seconds:
                        truncated = True
                        return total, count, truncated
        except OSError:
            continue
    return total, count, truncated


def _trash_items(root):
    items = []
    for m in trash.listing(root, limit=200):
        try:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(m.get("deleted") or 0)))
        except (ValueError, TypeError, OSError):
            when = ""
        items.append({"id": m.get("id") or "", "name": m.get("name") or "",
                      "rel": m.get("rel") or "", "dir": bool(m.get("dir")),
                      "size": m.get("size") or 0, "deleted": when,
                      "who": m.get("who") or ""})
    return items


class LoginGuard:
    """防密码暴力破解的闸门 —— 刻意与 IP 无关。

    为什么不用 IP：本机配了端口映射 / 内网穿透，从服务端看所有请求的来源
    都是 127.0.0.1，按 IP 封禁等于一封就把整站封死，谁都进不来。

    所以换成三条同时生效、都会自动恢复的规则：
      ① 全站令牌桶  —— 所有设备合起来每分钟最多 LOGIN_RATE_PER_MINUTE 次尝试；
      ② 姓名级连错锁 —— 同一个访问者姓名连错 LOGIN_MAX_FAILS 次，锁
         LOGIN_LOCK_SECONDS 秒；再错就翻倍，最多锁到 LOGIN_LOCK_MAX_SECONDS 秒；
      ③ 错误递增拖延 —— 每错一次多等一会儿再回话（最多 LOGIN_FAIL_DELAY_MAX_MS），
         把脚本爆破从"每秒几十次"磨到"每次一两秒"。
    对正常访问者：密码正确就一路畅通，且成功一次会把该姓名的错误记录清零。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._names = {}                     # 姓名(小写) -> 失败记录
        self._tokens = float(max(1, LOGIN_BURST))
        self._stamp = time.time()
        self.total_fails = 0                 # 全站累计失败次数（写日志用）

    # ---------- ① 全站令牌桶 ----------
    def take_token(self):
        """拿到一次尝试机会就返回 (True, 0)，拿不到返回 (False, 还差几秒)"""
        rate = max(LOGIN_RATE_PER_MINUTE, 1) / 60.0
        with self._lock:
            now = time.time()
            self._tokens = min(float(LOGIN_BURST), self._tokens + (now - self._stamp) * rate)
            self._stamp = now
            if self._tokens < 1.0:
                return False, max(1, int(math.ceil((1.0 - self._tokens) / rate)))
            self._tokens -= 1.0
            return True, 0

    # ---------- ② 姓名级连错锁 ----------
    @staticmethod
    def _key(who):
        return (who or "").strip().casefold() or "(未填姓名)"

    def locked_for(self, who):
        """这个姓名还被锁着多少秒；0 = 没锁"""
        with self._lock:
            rec = self._names.get(self._key(who))
            if not rec:
                return 0
            left = rec["until"] - time.time()
            return int(math.ceil(left)) if left > 0 else 0

    def note_fail(self, who):
        """记一次失败。刚好触发锁定就返回锁的秒数，否则 0"""
        key = self._key(who)
        now = time.time()
        with self._lock:
            self._gc(now)
            rec = self._names.get(key)
            if rec is None:
                rec = {"fails": 0, "until": 0.0, "rounds": 0, "seen": now}
                self._names[key] = rec
            rec["fails"] += 1
            rec["seen"] = now
            self.total_fails += 1
            if rec["fails"] >= LOGIN_MAX_FAILS:
                rec["rounds"] += 1
                rec["fails"] = 0
                dur = min(LOGIN_LOCK_SECONDS * (2 ** (rec["rounds"] - 1)),
                          LOGIN_LOCK_MAX_SECONDS)
                rec["until"] = now + dur
                return dur
            return 0

    def note_ok(self, who):
        """登录成功：把这个姓名的错误记录清零"""
        with self._lock:
            self._names.pop(self._key(who), None)

    def reset(self):
        """全站解锁：所有姓名的锁、错误计数、令牌桶一起恢复（后台「解除登录防护」用）"""
        with self._lock:
            self._names.clear()
            self._tokens = float(LOGIN_BURST)
            self._stamp = time.time()
            self.total_fails = 0

    def delay_seconds(self, who):
        """这次失败后回话前要多等几秒（越错越久，有上限）"""
        if LOGIN_FAIL_DELAY_MS <= 0:
            return 0.0
        with self._lock:
            rec = self._names.get(self._key(who))
            fails = rec["fails"] if rec else 0
        ms = LOGIN_FAIL_DELAY_MS * (1 + fails)
        return min(ms, LOGIN_FAIL_DELAY_MAX_MS) / 1000.0

    def _gc(self, now):
        """随便乱填的姓名会刷出很多条记录，攒太多时清掉早就过期的"""
        if len(self._names) < 3000:
            return
        dead = [k for k, r in self._names.items()
                if r["until"] <= now and now - r["seen"] > 3600]
        for k in dead:
            self._names.pop(k, None)


GUARD = LoginGuard()


class Handler(BaseHTTPRequestHandler):
    server_version = SERVER_VERSION
    protocol_version = "HTTP/1.1"

    # 关掉 Nagle：小包不再攒着等确认，穿透/公网下的延迟明显小一截
    disable_nagle_algorithm = True

    # 单个连接超过这么多秒没动静就断开，防止半死的连接一直占着线程
    timeout = REQUEST_TIMEOUT
    workers_limit = 16
    _tok_me = None                                          # 带签名通行证来的临时身份
    zip_slots = threading.BoundedSemaphore(ZIP_SLOTS)       # 同时打包几个文件夹
    upload_slots = threading.BoundedSemaphore(UPLOAD_SLOTS)  # 同时接收几个上传

    # ---------------- 基础 ----------------
    def log_message(self, fmt, *args):
        # 打包成 noconsole EXE 后 sys.stderr 可能是 None，不能直接写，否则每个请求都会在响应前崩溃。
        stream = sys.stderr or sys.stdout
        if stream is None:
            return
        try:
            stream.write("%s  %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        except Exception:
            pass

    def _cookies(self):
        raw = self.headers.get("Cookie") or ""
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _session_info(self, tok):
        """校验 Cookie，通过则返回身份字典 {name, role, root, perms, admin}，否则 None"""
        self._session_error = ""
        parts = (tok or "").split(".")
        if len(parts) != 3:
            return None
        ts, b64, mac = parts
        try:
            ts_i = int(ts)
        except ValueError:
            return None
        if time.time() - ts_i > SESSION_TTL:
            self._session_error = "登录已过期，请重新登录。"
            return None
        want = hmac.new(SESSION_SECRET, (ts + "." + b64).encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(mac, want):
            self._session_error = "登录状态已失效，请重新登录。"
            return None
        try:
            payload = urllib.parse.unquote(b64)
        except Exception:  # noqa: BLE001
            payload = ""
        info = None
        sid = ""
        if payload.startswith("{"):
            try:
                data = json.loads(payload)
            except ValueError:
                data = None
            if isinstance(data, dict):
                if str(data.get("fp") or "") != rulesmod.fingerprint():
                    self._session_error = "登录状态已失效，请重新登录。"
                    return None            # 规则改过了：旧会话一律作废，重新登录
                sid = str(data.get("sid") or "")
                perms = set(p for p in str(data.get("perms") or "").split(",") if p)
                if not perms:
                    perms = set(role_perms(data.get("role") or ROLE_READ))
                info = {"name": data.get("name") or "", "role": data.get("role") or ROLE_FULL,
                        "root": data.get("root") or "", "perms": perms,
                        "admin": bool(data.get("admin")),
                        "cloud": data.get("cl") or "", "sid": sid}
        if info is None:
            # 更老的 Cookie（name|role 那种）没有规则指纹，一律当作过期：重新登录一次就行
            self._session_error = "登录状态已失效，请重新登录。"
            return None
        info["name"] = sanitize_who(info["name"])
        if is_blocked(info["name"]):
            # 已经被拉黑，老 Cookie 也一并失效
            self._session_error = "该账号已被禁止访问。"
            return None
        if info.get("cloud"):
            # 云空间用户：账号还在才认，账号被删掉立刻失效
            if not accounts.exists(info["cloud"]):
                self._session_error = "该账号已不存在，请重新登录。"
                return None
            d = accounts.user_dir(info["cloud"])
            if not d:
                self._session_error = "该账号已不存在，请重新登录。"
                return None
            info["abs"] = d
            info["perms"] = accounts.all_perms()
        # 会话校验：Admin 不参与；普通账号允许多设备，云空间账号只认当前唯一会话。
        if not info.get("admin"):
            kind = "cloud" if info.get("cloud") else "normal"
            ok, why = sessions.validate(info["name"], sid, kind)
            if not ok:
                if why == "replaced":
                    self._session_error = "该账号已在其他设备登录，当前设备已自动退出。"
                elif why == "expired":
                    self._session_error = "登录已过期，请重新登录。"
                else:
                    self._session_error = "登录状态已失效，请重新登录。"
                return None
        return info

    def _me(self):
        if getattr(self, "_tok_me", None):
            # 这一次请求是拿"下载通行证"来的（系统下载器不带 Cookie），身份就从签名里取
            return self._tok_me
        return self._session_info(self._cookies().get("fs_session", "")) or {}

    def is_authed(self):
        return bool(self._me())

    def who(self):
        """当前访问者姓名（用于写日志）"""
        return self._me().get("name") or "未知"

    def role(self):
        """当前访问人的角色（网页上不显示，只用来决定权限）"""
        return self._me().get("role")

    def admin(self):
        """是不是后台身份（Admin + 最高权限密码）"""
        return bool(self._me().get("admin"))

    def root(self):
        """当前访问人能看到的根目录（规则里写了子目录就限制在那里；云空间用户是自己的目录）"""
        me = self._me()
        if not me:
            return role_root(ROLE_READ, Config.root)
        if me.get("abs"):
            return me["abs"]
        return rulesmod.grant_root(me, Config.root)

    def can(self, cap):
        me = self._me()
        perms = me.get("perms") or role_perms(ROLE_READ)
        return cap in perms

    def deny(self, msg="当前身份不具备该操作权限"):
        self.send_body(msg, 403, "text/plain; charset=utf-8")

    def send_body(self, body, status=200, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str) and ctype.lower().startswith("text/html"):
            body = i18n.render(body, i18n.current_lang(self.headers.get("Cookie")))
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: blob:; "
                         "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                         "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, str(v).replace("\r", "").replace("\n", ""))
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location, extra=None):
        self.send_response(303)
        self.send_header("Location", str(location).replace("\r", "").replace("\n", ""))
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, str(v).replace("\r", "").replace("\n", ""))
        self.end_headers()
        self.close_connection = True

    def send_json(self, obj, status=200):
        self.send_body(obj if isinstance(obj, (str, bytes)) else
                       json.dumps(obj, ensure_ascii=False),
                       status=status, ctype="application/json; charset=utf-8")

    def read_form(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" in ctype:
            parsed = urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
            return {k: v[0] for k, v in parsed.items()}
        return {}

    # ---------------- 路由 ----------------
    def do_GET(self):
        self._tok_me = None          # 每条请求都从干净状态开始（同一条连接可能发多个请求）
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            # 只给重启脚本/本机探活使用，不返回配置、账号、目录等任何业务信息
            self.send_json({"ok": True, "service": SERVER_VERSION, "pid": os.getpid()})
            return
        if path == "/favicon.ico":
            self.send_body(b"", 204)
            return
        if path.startswith("/img/") and path.endswith(".svg"):
            name = path[5:-4]
            text = icon_file_text(name)
            if text is None:
                self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                return
            self.send_body(text.encode("utf-8"), 200, "image/svg+xml; charset=utf-8",
                           {"Cache-Control": "public, max-age=3600"})
            return
        if path.startswith("/img/") and path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            # assets/images 里的位图（例如页脚的国徽 guohui.png），同样只认该目录下的单层文件名
            fpath = icon_image_path(path[5:])
            if fpath is None:
                self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                return
            try:
                with open(fpath, "rb") as fh:
                    data = fh.read()
            except OSError:
                self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                return
            ctype = guess_type(fpath)
            if not ctype.startswith("image/"):
                ctype = "application/octet-stream"
            self.send_body(data, 200, ctype, {"Cache-Control": "public, max-age=3600"})
            return
        if path == "/login":
            if self.is_authed():
                self.redirect("/browse")
            else:
                note = (qs.get("msg") or [""])[0] or getattr(self, "_session_error", "")
                self.send_body(build_login(note=note))
            return
        if path == "/logout":
            me = self._session_info(self._cookies().get("fs_session", "")) or {}
            if me.get("name") and me.get("sid"):
                sessions.release(me["name"], me["sid"])
            self.redirect("/login", {"Set-Cookie": "fs_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})
            return
        # 注册三步：① 须知（必须读几秒）→ ② 只填姓名提交申请 → ③ 凭管理员验证码设密码
        if path == "/register":
            if not settings.flag("register_enabled"):
                self.send_body(build_login("注册功能当前未开放"), 404)
                return
            if self.is_authed():
                self.redirect("/browse")
                return
            dev = self._cookies().get("fsdev") or secrets.token_hex(8)
            again = ((qs.get("again") or ["0"])[0] == "1"
                     and bool(self._cookies().get("fsnotice")))
            self.send_body(build_notice(settings.integer("register_notice_seconds", 0, 60), again),
                           extra={"Set-Cookie":
                                  "fsdev=%s; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax" % dev})
            return
        if path == "/register/apply":
            if not settings.flag("register_enabled"):
                self.send_body(build_login("注册功能当前未开放"), 404)
                return
            if self.is_authed():
                self.redirect("/browse")
                return
            # 必须先在须知页点过「同意」（服务端发过 fsnotice Cookie），避免直接跳到这一步
            if not self._cookies().get("fsnotice"):
                self.redirect("/register")
                return
            self.send_body(build_apply((qs.get("msg") or [""])[0],
                                       (qs.get("ok") or ["0"])[0] == "1",
                                       (qs.get("who") or [""])[0]))
            return
        if path == "/register/set":
            if not settings.flag("register_enabled"):
                self.send_body(build_login("注册功能当前未开放"), 404)
                return
            if self.is_authed():
                self.redirect("/browse")
                return
            self.send_body(build_setpw((qs.get("msg") or [""])[0],
                                       (qs.get("ok") or ["0"])[0] == "1",
                                       (qs.get("who") or [""])[0],
                                       (qs.get("code") or [""])[0]))
            return
        if path == "/avatar":
            # 当前登录人自己的头像（云空间用户没设过就是默认头像）；不做缓存，换完立刻能看到
            me = self._session_info(self._cookies().get("fs_session", ""))
            name = (me or {}).get("cloud") or ""
            fpath = accounts.avatar_file(name) if name else None
            if fpath:
                try:
                    with open(fpath, "rb") as fh:
                        data = fh.read()
                except OSError:
                    data = b""
                if data:
                    ctype = accounts.avatar_type(fpath)
                    extra = {"Cache-Control": "no-store"}
                    if ctype == "image/svg+xml":
                        # SVG 头像只作为 <img> 资源使用，禁止其内部脚本与外部请求
                        extra["Content-Security-Policy"] = ("default-src 'none'; "
                                                            "style-src 'unsafe-inline'; img-src data:")
                    self.send_body(data, 200, ctype, extra)
                    return
            text = icon_file_text("avatar_default")
            if text is None:
                self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                return
            self.send_body(text.encode("utf-8"), 200, "image/svg+xml; charset=utf-8",
                           {"Cache-Control": "no-store"})
            return
        if path == "/d" or path.startswith("/d/"):
            # 兼容下载：这一条刻意放在登录校验前面 —— 它是给"不带 Cookie 的系统下载器"用的，
            # 通行证在链接里（签名 + 有效期），所以不需要会话 Cookie。
            rel = (qs.get("p") or [""])[0]
            tok = (qs.get("t") or [""])[0]
            info = dltoken.read(tok)
            if not info:
                write_log("WARN", "未知", self._client_ip(), "DL_COMPAT_DENIED", rel,
                          'reason=bad_or_expired_token ua="%s"' % self._ua())
                self.send_body("下载链接已失效，请返回文件列表页重新发起下载", 403,
                               "text/plain; charset=utf-8")
                return
            if "download" not in info.get("perms", set()):
                self.send_body("当前身份不具备下载权限", 403, "text/plain; charset=utf-8")
                return
            root = os.path.realpath(info.get("root") or Config.root)
            base_root = os.path.realpath(Config.root)
            target = None
            if root == base_root or root.startswith(base_root.rstrip("\\/") + os.sep):
                target = resolve(rel, root)
                if target is not None:
                    target = os.path.realpath(target)
                    if not target.startswith(base_root.rstrip("\\/") + os.sep):
                        target = None
            if target is None or not os.path.isfile(target):
                self.send_body("文件不存在", 404, "text/plain; charset=utf-8")
                return
            hint = urllib.parse.unquote(path[3:].strip("/"))
            prefer_zh = (qs.get("nm") or ["ascii"])[0] != "ascii"
            write_log("INFO", info.get("name") or "未知", self._client_ip(), "DL_COMPAT", rel,
                      'hint=%s ua="%s" range=%s' % (hint or "-", self._ua(),
                                                     (self.headers.get("Range") or "-")[:40]))
            self.send_compat_file(target, hint, prefer_zh=prefer_zh)
            return

        # 下载 / 打包 / 预览 这三条支持"通行证"：URL 里带 t=签名 时不需要 Cookie
        # （学习机、手机的系统下载器是另一个进程，不会把浏览器的登录 Cookie 带过去）
        tok_q = (qs.get("t") or [""])[0]
        if tok_q and path in ("/download", "/raw", "/zip", "/zipmulti"):
            info = dltoken.read(tok_q)
            if info:
                self._tok_me = {"name": info.get("name") or "未知",
                                "root": info.get("root") or "",
                                "perms": set(info.get("perms") or []),
                                "role": None, "admin": False}
            else:
                write_log("WARN", "未知", self._client_ip(), "TOKEN_DENIED", path,
                          'reason=bad_or_expired_token ua="%s"' % self._ua())
                self.send_body("下载链接已失效，请返回文件列表页重新发起下载", 403,
                               "text/plain; charset=utf-8")
                return

        if not self.is_authed():
            if path.startswith("/api/") or path in ("/download", "/raw", "/zip", "/zipmulti"):
                self.send_body("登录状态无效或已过期，请返回首页重新登录", 401, "text/plain; charset=utf-8")
                return
            self.send_body(build_login(getattr(self, "_session_error", "")))
            return

        try:
            if path == "/admin":
                if not self.admin():
                    # 不是后台身份：不解释、不提示，就当作没有这个页面
                    self.send_body(build_error("页面不存在", "所请求的页面不存在。"), 404)
                    return
                try:
                    saved = int((qs.get("saved") or ["0"])[0])
                except ValueError:
                    saved = 0
                warn = (qs.get("warn") or [""])[0]
                if not warn:
                    warn = (qs.get("msg") or [""])[0]
                self.send_body(adminui.build_admin_page(self._me(), saved=saved, warn=warn))
                return
            if path in ("/", "/browse"):
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None:
                    self.send_body(build_error("路径不合法", "该路径超出允许访问的目录范围。"), 403)
                    return
                if not os.path.exists(target):
                    self.send_body(build_error("目录不存在", "该目录可能已被移动、重命名或删除。"), 404)
                    return
                if os.path.isfile(target):
                    self.redirect("/download?p=" + q(rel))
                    return
                sort_key = (qs.get("sort") or ["name"])[0]
                if sort_key not in ("name", "mtime", "size", "type"):
                    sort_key = "name"
                order = "desc" if (qs.get("order") or ["asc"])[0] == "desc" else "asc"
                kw = (qs.get("q") or [""])[0].strip()[:80]
                try:
                    page_no = int((qs.get("page") or ["1"])[0])
                except ValueError:
                    page_no = 1
                me = self._me()
                avatar = "/img/avatar_default.svg"
                if me.get("cloud"):
                    avatar = "/avatar"
                elif (me.get("name") or "") == (NAME_FULL or "").strip():
                    avatar = "/img/lock.svg"
                self.send_body(build_page(rel.strip("/"), target, sort_key, order, kw, page_no,
                                          root=self.root(), role=self.role(),
                                          perms=me.get("perms"), admin=self.admin(),
                                          who=me.get("name") or "", avatar=avatar,
                                          can_avatar=bool(me.get("cloud"))))
                return
            if path == "/download" or path == "/raw":
                if not self.can("download" if path == "/download" else "preview"):
                    self.deny("当前身份不具备下载权限")
                    return
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.isfile(target):
                    self.send_body("文件不存在", 404, "text/plain; charset=utf-8")
                    return
                if path == "/download":
                    write_log("INFO", self.who(), self._client_ip(), "DL", rel,
                              'mode=session ua="%s" range=%s' % (self._ua(),
                                                                 (self.headers.get("Range") or "-")[:40]))
                ascii_name = (qs.get("nm") or [""])[0] == "ascii"
                self.send_file(target, inline=(path == "/raw"),
                               slot=None if path == "/raw" else "file",
                               ascii_only=ascii_name)
                return
            if path == "/thumb":
                # 列表缩略图：优先用服务端生成的小图；生成不了再退回原图（仅限小文件）
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.isfile(target):
                    self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                    return
                ctype = guess_type(target)
                if not ctype.startswith("image/"):
                    self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                    return
                thumb = thumbs.get(target)
                if thumb:
                    self.send_file(thumb, inline=True)
                    return
                try:
                    if os.path.getsize(target) > 3 * 1024 * 1024:
                        self.send_body("413 Too Large", 413, "text/plain; charset=utf-8")
                        return
                    with open(target, "rb") as fh:
                        data = fh.read()
                except OSError:
                    self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
                    return
                self.send_body(data, 200, ctype, {"Cache-Control": "private, max-age=600"})
                return
            if path == "/api/info":
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.exists(target):
                    self.send_json({"ok": False, "error": "文件不存在"})
                    return
                is_dir = os.path.isdir(target)
                name = os.path.basename(target.rstrip("\\/")) or target
                try:
                    st = os.stat(target)
                except OSError:
                    st = None
                info = {"ok": True, "name": name, "rel": rel, "dir": is_dir,
                        "type": "文件夹" if is_dir else (ext_of(name).upper() + " 文件" if ext_of(name) else "文件"),
                        "size_text": "" if is_dir else human_size(st.st_size if st else 0),
                        "mtime": fmt_time(st.st_mtime) if st else "",
                        "link": ("/zip?p=" if is_dir else "/download?p=") + q(rel)}
                self.send_json(info)
                return
            if path == "/api/du":
                # 算文件夹总大小：有预算，别把一块大盘扫穿（games 那种目录也能安全点）
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.isdir(target):
                    self.send_json({"ok": False, "error": "目录不存在"})
                    return
                total, n, cut = _dir_size(target)
                self.send_json({"ok": True, "size": total, "size_text": human_size(total),
                                "count": n, "truncated": 1 if cut else 0})
                return
            if path == "/api/trash":
                op = (qs.get("op") or ["list"])[0]
                if op == "empty":
                    n = trash.empty(self.root())
                    write_log("INFO", self.who(), self._client_ip(), "TRASH_EMPTY", "",
                              "removed=%d" % n)
                    self.send_json({"ok": True, "msg": "已清空回收站（共 %d 项）" % n})
                    return
                self.send_json({"ok": True, "items": _trash_items(self.root())})
                return
            if path == "/zipprobe":
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.isdir(target):
                    self.send_json({"ok": False, "reason": "目录不存在"})
                    return
                built, size = zcache.probe(target)
                self.send_json({"ok": bool(built), "size": size,
                                "threads": ZIP_THREADS,
                                "max_mb": ZIP_CACHE_MAX_MB})
                return
            if path == "/zipmulti":
                if not self.can("download"):
                    self.deny("当前身份不具备下载权限")
                    return
                rels = qs.get("p") or []
                targets, has_dir = [], False
                for rel in rels:
                    target = resolve(rel, self.root())
                    if target is None or not (os.path.isfile(target) or os.path.isdir(target)):
                        continue
                    has_dir = has_dir or os.path.isdir(target)
                    targets.append((rel, target))
                if not targets:
                    self.send_body("没有可打包的文件", 404, "text/plain; charset=utf-8")
                    return
                if has_dir and not self.can("zip"):
                    self.deny("当前身份不具备打包下载权限")
                    return
                if (qs.get("probe") or ["0"])[0] == "1":
                    self.send_json({"ok": False, "reason": "stream"})
                    return
                used, items = {}, []
                for _rel, target in targets:
                    top = os.path.basename(target) or "file"
                    if top in used:
                        used[top] += 1
                        stem, ext = os.path.splitext(top)
                        top = "%s (%d)%s" % (stem, used[top], ext)
                    else:
                        used[top] = 1
                    items.append((target, top))
                write_log("INFO", self.who(), self._client_ip(), "DL_MULTI", "",
                          "count=%d ua=\"%s\"" % (len(items), self._ua()))
                self.send_zip_multi(items, "批量下载.zip", ascii_only=((qs.get("nm") or [""])[0] == "ascii"))
                return
            if path == "/zip":
                if not self.can("zip"):
                    self.deny("当前身份不具备打包下载权限")
                    return
                rel = (qs.get("p") or [""])[0]
                target = resolve(rel, self.root())
                if target is None or not os.path.isdir(target):
                    self.send_body("目录不存在", 404, "text/plain; charset=utf-8")
                    return
                folder_name = os.path.basename(target) or "root"
                ascii_name = (qs.get("nm") or [""])[0] == "ascii"
                if (qs.get("mt") or ["0"])[0] == "1":
                    # 并发下载模式：先落成缓存 zip，长度固定后前端就能用 Range 分片并行扒
                    if (qs.get("probe") or ["0"])[0] == "1":
                        built, size = zcache.probe(target)
                        self.send_json({"ok": bool(built), "size": size,
                                        "threads": ZIP_THREADS})
                        return
                    built, _size = zcache.probe(target)
                    if built:
                        self.send_file(built, filename="%s.zip" % folder_name, slot="zip",
                                       ascii_only=ascii_name)
                        return
                self.send_zip(target, folder_name, ascii_only=ascii_name)
                return
            self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            try:
                self.send_body("服务器错误：%s" % html.escape(str(exc)), 500, "text/plain; charset=utf-8")
            except Exception:
                self.close_connection = True

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        # 跨站请求防护：现代浏览器会带 Sec-Fetch-Site。管理后台的写操作只允许同源页面提交。
        fetch_site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if fetch_site and fetch_site not in ("same-origin", "none"):
            self.send_body("跨站请求被拒绝", 403, "text/plain; charset=utf-8")
            return
        origin = (self.headers.get("Origin") or "").strip()
        if origin and not fetch_site:
            try:
                if urllib.parse.urlsplit(origin).netloc != (self.headers.get("Host") or ""):
                    self.send_body("跨站请求被拒绝", 403, "text/plain; charset=utf-8")
                    return
            except ValueError:
                self.send_body("请求来源不合法", 400, "text/plain; charset=utf-8")
                return
        try:
            # 普通表单先卡请求体大小，避免公开的登录/注册接口被超大 body 占满内存。
            # 上传和头像走各自的上限检查，不在这里拦。
            if path not in ("/api/upload", "/api/avatar"):
                try:
                    cl = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    cl = 0
                if cl > MAX_FORM_BYTES:
                    self.send_body("请求体过大", 413, "text/plain; charset=utf-8")
                    return
            if path == "/admin/unlock":
                # 解除登录防护：清掉所有姓名的连错锁、把全站令牌桶填满、失败计数归零。
                # 只有后台身份能用；控制台（console.py）用 Admin + PW_FULL 登录后调这个。
                if not self.admin():
                    self.send_body("权限不足", 403, "text/plain; charset=utf-8")
                    return
                GUARD.reset()
                write_log("INFO", self.who(), self._client_ip(), "ADMIN_UNLOCK", "",
                          "fails_total_reset=1")
                self.send_json({"ok": True, "msg": "登录防护已解除（失败锁定与全站限速已重置）"})
                return
            if path == "/admin/roster":
                # 白名单 / 黑名单的加人、撤人（后台页上的小按钮直接提交到这里）
                if not self.admin():
                    self.send_body("权限不足", 403, "text/plain; charset=utf-8")
                    return
                form = self.read_form()
                op = (form.get("op") or "").strip()
                name = (form.get("name") or "").strip()
                msg = adminui.do_roster(op, name)
                write_log("INFO", self.who(), self._client_ip(), "ROSTER_" + (op.upper() or "UNKNOWN"),
                          "", 'name="%s" msg="%s"' % (name.replace('"', "'"),
                                                      msg.replace('"', "'")))
                self.redirect("/admin?msg=" + urllib.parse.quote(msg))
                return
            if path == "/admin/account":
                # 云空间账号与开通申请的管理：通过 / 拒绝 / 彻底删除账号 / 手动建号
                if not self.admin():
                    self.send_body("权限不足", 403, "text/plain; charset=utf-8")
                    return
                form = self.read_form()
                op = (form.get("op") or "").strip()
                msg = adminui.do_account(op, form)
                write_log("INFO", self.who(), self._client_ip(),
                          "ACCOUNT_" + (op.upper() or "UNKNOWN"), "",
                          'msg="%s"' % msg.replace('"', "'"))
                self.redirect("/admin?msg=" + urllib.parse.quote(msg))
                return
            if path == "/admin/save":
                if not self.admin():
                    self.send_body("权限不足", 403, "text/plain; charset=utf-8")
                    return
                form = self.read_form()
                me = self._me() or {}      # 先记下自己是谁（改完规则后旧会话就失效了）
                changed, msgs = adminui.apply_form(form)
                restarting = str(form.get("do_restart") or "") in ("1", "on", "true")
                if restarting:
                    ok = adminui.restart_service()
                    write_log("INFO", self.who(), self._client_ip(), "ADMIN_RESTART", "",
                              'ok=%s changed=%d' % (1 if ok else 0, changed))
                    self.send_json({"ok": ok, "changed": changed, "msgs": msgs})
                    if ok:
                        def _bye():
                            time.sleep(0.8)
                            os._exit(0)
                        threading.Thread(target=_bye, daemon=True).start()
                    return
                write_log("INFO", self.who(), self._client_ip(), "ADMIN_SAVE", "",
                          'changed=%d note="%s"' % (changed, "；".join(msgs).replace('"', "'")))
                warn = "；".join(msgs + (["端口、并发、超时等参数需重启服务后生效"] if changed else []))
                # 规则文件刚被改过 → 全站旧会话都作废了，包括当前这个后台会话。
                # 立刻按现在的规则给自己重发一张新 Cookie，免得一保存就被踢回登录页。
                me = me or {}
                keep = me if me.get("admin") else None
                headers = {}
                if keep:
                    headers["Set-Cookie"] = ("fs_session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax"
                                             % (self._make_token(keep), SESSION_TTL))
                self.redirect("/admin?saved=%d&warn=%s" % (changed, urllib.parse.quote(warn)), headers)
                return

            if path == "/register":
                # 第①步：须知页点「同意」——记一个 30 分钟有效的记号，之后才能进申请页
                if not settings.flag("register_enabled"):
                    self.send_body("注册功能当前未开放", 404, "text/plain; charset=utf-8")
                    return
                form = self.read_form()
                if (form.get("agree") or "") not in ("1", "on"):
                    self.redirect("/register")
                    return
                self.redirect("/register/apply",
                              {"Set-Cookie":
                               "fsnotice=1; Path=/; Max-Age=1800; HttpOnly; SameSite=Lax"})
                return

            if path == "/register/apply":
                # 第②步：只填姓名提交申请（管理员审批通过后才生成验证码）
                if not settings.flag("register_enabled"):
                    self.send_body("注册功能当前未开放", 404, "text/plain; charset=utf-8")
                    return
                if not self._cookies().get("fsnotice"):
                    self.redirect("/register")
                    return
                form = self.read_form()
                who = sanitize_who(form.get("who") or "")
                remark = "".join(ch for ch in (form.get("remark") or "") if ch.isprintable())
                remark = " ".join(remark.split())[:200]
                device = self._cookies().get("fsdev") or ""
                ok, msg = accounts.submit(who, device, remark)
                write_log("INFO" if ok else "WARN", who, self._client_ip(),
                          "REGISTER_APPLY" if ok else "REGISTER_DENIED", "",
                          'msg="%s" device=%s' % (msg.replace('"', "'"), device or "-"))
                if ok:
                    self.redirect("/register/apply?ok=1&msg=" + urllib.parse.quote(msg))
                else:
                    self.send_body(build_apply(msg, False, who, remark), 200)
                return

            if path == "/register/set":
                # 第③步：姓名 + 管理员给的 4 位验证码 + 自己设的密码 → 真正建号
                if not settings.flag("register_enabled"):
                    self.send_body("注册功能当前未开放", 404, "text/plain; charset=utf-8")
                    return
                form = self.read_form()
                who = sanitize_who(form.get("who") or "")
                code = (form.get("code") or "").strip()
                pw = (form.get("pw") or "").strip()
                pw2 = (form.get("pw2") or "").strip()
                if pw != pw2:
                    self.send_body(build_setpw("两次输入的密码不一致", False, who, code), 400)
                    return
                ok, msg = accounts.complete(who, code, pw)
                write_log("INFO" if ok else "WARN", who, self._client_ip(),
                          "REGISTER_SET" if ok else "REGISTER_SET_DENIED", "",
                          'msg="%s"' % msg.replace('"', "'"))
                if ok:
                    self.redirect("/login?msg=" + urllib.parse.quote(msg))
                else:
                    self.send_body(build_setpw(msg, False, who, code), 200)
                return

            if path == "/login":
                form = self.read_form()
                pw = (form.get("pw") or "").strip()
                who = sanitize_who(form.get("who") or "")
                ip = self._client_ip()

                # ① 这个姓名是不是还在锁定里（与 IP 无关，过期自动解除）
                locked = GUARD.locked_for(who)
                if locked:
                    write_log("WARN", who, ip, "LOGIN_LOCKED", "",
                              "retry_after=%ds fails_total=%d role=none"
                              % (locked, GUARD.total_fails))
                    self.send_body(build_login("密码错误次数过多，请于 %d 秒后重试" % locked, who),
                                   429)
                    return
                # ② 全站限速：所有设备合起来算，超额就让大家一起歇几秒
                allowed, wait = GUARD.take_token()
                if not allowed:
                    write_log("WARN", who, ip, "LOGIN_THROTTLED", "",
                              "retry_after=%ds fails_total=%d role=none"
                              % (wait, GUARD.total_fails))
                    self.send_body(build_login("登录请求过于频繁，请于 %d 秒后重试" % wait, who),
                                   429)
                    return

                if is_blocked(who):
                    # 黑名单：密码对不对都不让进，只回一句「禁止访问」
                    GUARD.note_fail(who)
                    write_log("ERROR", who, ip, "LOGIN_BLOCKED",
                              "", "reason=blacklist role=none")
                    self.send_body(build_login("禁止访问", who), 403)
                    return
                if roster.enforced() and who.casefold() != ADMIN_NAME.strip().casefold() \
                        and not accounts.exists(who) and not roster.has(who):
                    # 白名单：名单里没这个名字，密码对不对都不给进（后台身份 Admin 例外，
                    # 免得把管理员自己漏掉之后进不了后台）
                    GUARD.note_fail(who)
                    write_log("WARN", who, ip, "LOGIN_NOT_ALLOWED", "",
                              "reason=not_in_whitelist whitelist=%d role=none" % roster.count())
                    self.send_body(build_login("该姓名不在允许名单内", who), 403)
                    return
                if not pw:
                    # 空密码直接算一次失败，不往下走
                    lock_dur = GUARD.note_fail(who)
                    write_log("WARN", who, ip, "LOGIN_FAILED", "",
                              "reason=empty_password fails_total=%d role=none"
                              % GUARD.total_fails)
                    msg = ("密码错误次数过多，请于 %d 秒后重试" % lock_dur) if lock_dur \
                        else "请输入访问密码"
                    self.send_body(build_login(msg, who), 429 if lock_dur else 200)
                    return

                grant = self._grant_for(who, pw)
                if grant:
                    GUARD.note_ok(who)
                    sid = secrets.token_hex(16)
                    grant["sid"] = sid
                    if not grant.get("admin"):
                        kind = "cloud" if grant.get("cl") else "normal"
                        ok, why = sessions.claim(grant.get("name") or who, sid, kind)
                        if not ok:
                            write_log("WARN", who, ip, "SESSION_INVALID", "",
                                      "reason=invalid_session kind=%s role=%s"
                                      % (kind, grant.get("role")))
                            self.send_body(build_login(
                                "登录状态异常，请重新登录。", who), 409)
                            return
                        if why == "replaced":
                            write_log("INFO", who, ip, "SESSION_REPLACED", "",
                                      "reason=new_cloud_login kind=cloud old_session=released")
                    token = self._make_token(grant)
                    cookie = ("fs_session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax"
                              % (token, SESSION_TTL))
                    write_log("INFO", who, ip, "LOGIN_OK", "",
                              "role=%s access_root=%s admin=%s cloud=%s"
                              % (grant.get("role"), grant.get("root") or "(全部目录)",
                                 1 if grant.get("admin") else 0, grant.get("cl") or "-"))
                    self.redirect("/admin" if grant.get("admin") else "/browse",
                                  {"Set-Cookie": cookie})
                else:
                    lock_dur = GUARD.note_fail(who)
                    # ③ 越错越慢，把脚本爆破的速度磨下来（正常人手打几乎感觉不到）
                    delay = GUARD.delay_seconds(who)
                    if delay:
                        time.sleep(delay)
                    if lock_dur:
                        write_log("WARN", who, ip, "LOGIN_LOCKED", "",
                                  "reason=too_many_fails lock=%ds fails_total=%d role=none"
                                  % (lock_dur, GUARD.total_fails))
                        # 提示一律相同：不透露是姓名不对还是密码不对
                        self.send_body(build_login("密码错误次数过多，请于 %d 秒后重试" % lock_dur,
                                                   who), 429)
                    else:
                        write_log("WARN", who, ip, "LOGIN_FAILED", "",
                                  "reason=bad_password fails_total=%d role=none"
                                  % GUARD.total_fails)
                        # 提示一律相同：不透露是姓名不对还是密码不对
                        self.send_body(build_login("密码不正确，请重新输入", who), 200)
                return

            if not self.is_authed():
                self.send_body("登录状态无效或已过期", 401, "text/plain; charset=utf-8")
                return

            if path == "/api/avatar":
                # 换自己的头像：前端多数格式会先缩成 256×256 PNG；浏览器解不开的按原格式直传
                me = self._me()
                if not me.get("cloud"):
                    self.send_json({"ok": False, "error": "只有云空间账号才能改自己的头像"}, 403)
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_AVATAR_BYTES:
                    self.send_json({"ok": False, "error": "图片超出大小限制或未接收到内容"}, 413)
                    return
                data = self.rfile.read(length)
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                # 按文件头判真实格式，不轻信 Content-Type
                ext = accounts.detect_avatar_format(data, ctype)
                if not ext:
                    self.send_json({"ok": False, "error": "无法识别图片格式，请改用 PNG / JPG / JPEG / WEBP / GIF / BMP / ICO / SVG / AVIF"}, 400)
                    return
                ok, msg = accounts.set_avatar(me["cloud"], data, ext)
                write_log("INFO" if ok else "WARN", self.who(), self._client_ip(),
                          "AVATAR_SET" if ok else "AVATAR_FAIL", "",
                          'msg="%s" bytes=%d' % (msg.replace('"', "'"), len(data)))
                self.send_json({"ok": ok, "msg": msg, "error": None if ok else msg},
                               200 if ok else 400)
                return

            form = self.read_form()
            if path == "/api/mkdir":
                if not self.can("mkdir"):
                    self.deny()
                    return
                rel_dir = form.get("p") or ""
                name = sanitize_segment(form.get("name") or "")
                if not name:
                    self.send_body("名称不合法，请检查输入", 400, "text/plain; charset=utf-8")
                    return
                base = resolve(rel_dir, self.root())
                if base is None or not os.path.isdir(base):
                    self.send_body("路径不合法", 400, "text/plain; charset=utf-8")
                    return
                newp = os.path.join(base, name)
                if blocked.is_blocked(newp):
                    self.send_body("名称不可用", 400, "text/plain; charset=utf-8")
                    return
                if os.path.exists(newp):
                    self.send_body("同名目录已存在", 400, "text/plain; charset=utf-8")
                    return
                os.makedirs(newp)
                invalidate_dir(base)
                write_log("INFO", self.who(), self._client_ip(), "MKDIR",
                          _rel_for_log(newp), "role=%s" % self.role())
                self.send_json({"ok": True, "name": name})
                return

            if path == "/api/rename":
                if not self.can("rename"):
                    self.deny()
                    return
                rel = form.get("p") or ""
                name = sanitize_segment(form.get("name") or "")
                target = resolve(rel, self.root())
                if target is None or not os.path.exists(target) or not name:
                    self.send_body("请求参数不合法", 400, "text/plain; charset=utf-8")
                    return
                parent = os.path.dirname(target)
                newp = os.path.join(parent, name)
                if blocked.is_blocked(newp):
                    self.send_body("名称不可用", 400, "text/plain; charset=utf-8")
                    return
                if os.path.exists(newp):
                    self.send_body("同名文件已存在", 400, "text/plain; charset=utf-8")
                    return
                os.rename(target, newp)
                invalidate_dir(parent)
                write_log("INFO", self.who(), self._client_ip(),
                          "RENAME_DIR" if os.path.isdir(newp) else "RENAME_FILE",
                          _rel_for_log(target),
                          'target="%s" role=%s' % (_rel_for_log(newp), self.role()))
                self.send_json({"ok": True, "name": name})
                return

            if path == "/api/delete":
                if not self.can("delete"):
                    self.deny()
                    return
                rel = form.get("p") or ""
                target = resolve(rel, self.root())
                if target is None or target == os.path.abspath(self.root()) or not os.path.exists(target):
                    self.send_body("请求参数不合法", 400, "text/plain; charset=utf-8")
                    return
                is_dir = os.path.isdir(target) and not os.path.islink(target)
                fsize = 0
                if not is_dir:
                    try:
                        fsize = os.path.getsize(target)
                    except OSError:
                        fsize = 0
                # 删除 = 挪进回收站（.trash 目录，列表里看不到，可在「回收站」还原）
                try:
                    trash.put(self.root(), target, self.who())
                except OSError as exc:
                    self.send_body("删除失败（文件可能正被别的程序占用）：%s" % exc, 500,
                                   "text/plain; charset=utf-8")
                    return
                invalidate_dir(os.path.dirname(target))
                write_log("INFO", self.who(), self._client_ip(),
                          "DELETE_DIR" if is_dir else "DELETE_FILE",
                          _rel_for_log(target),
                          ('size="%s" ' % human_size(fsize) if not is_dir else "") +
                          "role=%s to=trash" % self.role())
                self.send_json({"ok": True, "msg": "已删除，可在回收站中还原"})
                return

            if path == "/api/move":
                # 剪切粘贴 / 批量移动：同盘就是改名（走文件系统元数据，不搬字节，很快）
                if not (self.can("delete") and (self.can("upload") or self.can("mkdir"))):
                    self.deny()
                    return
                src_rel = form.get("src") or ""
                dst_rel = form.get("dst") or ""
                src = resolve(src_rel, self.root())
                dst_dir = resolve(dst_rel, self.root())
                if src is None or dst_dir is None or not os.path.exists(src) or not os.path.isdir(dst_dir):
                    self.send_body("请求参数不合法", 400, "text/plain; charset=utf-8")
                    return
                if os.path.abspath(src) == os.path.abspath(dst_dir):
                    self.send_json({"ok": True, "msg": "该项目已在当前目录中"})
                    return
                # 不能把文件夹挪进它自己（或者它的子文件夹）里面
                if os.path.isdir(src) and os.path.abspath(dst_dir).startswith(
                        os.path.abspath(src) + os.sep):
                    self.send_body("不能将目录移动到其自身或其子目录内", 400, "text/plain; charset=utf-8")
                    return
                name = os.path.basename(src.rstrip("\\/"))
                newp = os.path.join(dst_dir, name)
                if blocked.is_blocked(newp):
                    self.send_body("目标名称不可用", 400, "text/plain; charset=utf-8")
                    return
                if os.path.exists(newp):
                    self.send_body("目标目录中已存在同名项目「%s」" % name, 409,
                                   "text/plain; charset=utf-8")
                    return
                try:
                    shutil.move(src, newp)
                except OSError as exc:
                    self.send_body("移动失败：%s" % exc, 500, "text/plain; charset=utf-8")
                    return
                invalidate_dir(os.path.dirname(src))
                invalidate_dir(dst_dir)
                write_log("INFO", self.who(), self._client_ip(), "MOVE",
                          _rel_for_log(src), 'target="%s" role=%s'
                          % (_rel_for_log(newp), self.role()))
                self.send_json({"ok": True, "msg": "已完成移动", "to": _rel_for_log(newp)})
                return

            if path == "/api/trash":
                if not self.can("delete"):
                    self.deny()
                    return
                op = (form.get("op") or "").strip()
                tid = (form.get("id") or "").strip()
                if op == "restore":
                    ok, msg = trash.restore(self.root(), tid)
                elif op == "purge":
                    ok, msg = trash.purge(self.root(), tid)
                elif op == "empty":
                    n = trash.empty(self.root())
                    ok, msg = True, "已清空回收站（共 %d 项）" % n
                else:
                    ok, msg = False, "无法识别的操作"
                write_log("INFO" if ok else "WARN", self.who(), self._client_ip(),
                          "TRASH_" + (op.upper() or "UNKNOWN"), "",
                          'msg="%s" id=%s' % (msg.replace('"', "'"), tid or "-"))
                self.send_json({"ok": ok, "msg": msg, "error": None if ok else msg},
                               200 if ok else 400)
                return

            self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            try:
                write_log("ERROR", self.who(), self._client_ip(), "API_FAILED",
                          path.lstrip("/"), 'error="%s"' % str(exc).replace('"', "'"))
            except Exception:
                pass
            try:
                self.send_body("操作失败：%s" % html.escape(str(exc)), 500, "text/plain; charset=utf-8")
            except Exception:
                self.close_connection = True

    def do_PUT(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path != "/api/upload":
            self.send_body("404 Not Found", 404, "text/plain; charset=utf-8")
            return
        if not self.is_authed():
            self.send_body("登录状态无效或已过期", 401, "text/plain; charset=utf-8")
            return
        if not self.can("upload"):
            self.deny("当前身份不具备上传权限")
            return
        if not Handler.upload_slots.acquire(blocking=False):
            self.send_body("并发上传请求过多，请稍后重试", 503, "text/plain; charset=utf-8")
            self.close_connection = True
            return
        try:
            self._upload(qs)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        finally:
            Handler.upload_slots.release()

    def _upload(self, qs):
        rel_dir = ""
        raw_name = ""
        try:
            rel_dir = (qs.get("p") or [""])[0]
            raw_name = (qs.get("name") or [""])[0]
            base = resolve(rel_dir, self.root())
            if base is None:
                self.send_body("目标目录路径不合法", 400, "text/plain; charset=utf-8")
                return
            root_real = os.path.realpath(self.root())
            base_root = os.path.realpath(Config.root)
            if not (root_real == base_root or root_real.startswith(
                    base_root.rstrip("\\/") + os.sep)):
                self.send_body("目标目录路径不合法", 400, "text/plain; charset=utf-8")
                return
            base_real = os.path.realpath(base)
            if not (base_real == base_root or base_real.startswith(base_root.rstrip("\\/") + os.sep)):
                self.send_body("目标目录路径不合法", 400, "text/plain; charset=utf-8")
                return
            if not os.path.isdir(base_real):
                self.send_body("目标目录路径不合法", 400, "text/plain; charset=utf-8")
                return
            # 支持 "子目录/文件" 形式（整文件夹上传）
            segs = [sanitize_segment(s) for s in raw_name.replace("\\", "/").split("/")]
            segs = [s for s in segs if s]
            if not segs:
                self.send_body("文件名不合法", 400, "text/plain; charset=utf-8")
                return
            dirs = segs[:-1]
            final_name = segs[-1]
            target_dir = base_real
            for d in dirs:
                target_dir = os.path.realpath(os.path.join(target_dir, d))
                if blocked.is_blocked(target_dir):
                    self.send_body("目标目录不可用", 400, "text/plain; charset=utf-8")
                    return
                if not target_dir.startswith(base_root.rstrip("\\/") + os.sep):
                    self.send_body("路径不合法", 400, "text/plain; charset=utf-8")
                    return
                os.makedirs(target_dir, exist_ok=True)

            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0:
                self.send_body("请求缺少 Content-Length 头", 411, "text/plain; charset=utf-8")
                return
            if UPLOAD_MAX_MB and length > UPLOAD_MAX_MB * 1024 * 1024:
                self.send_body("单个文件超过上传上限（%d MB）" % UPLOAD_MAX_MB, 413,
                               "text/plain; charset=utf-8")
                return
            if USER_QUOTA_MB and (self._me() or {}).get("cloud"):
                used, _n, _cut = _dir_size(self.root(), budget_seconds=8.0)
                if used + length > USER_QUOTA_MB * 1024 * 1024:
                    self.send_body("云空间容量不足（每账号上限 %d MB，已用 %s）"
                                   % (USER_QUOTA_MB, human_size(used)), 413,
                                   "text/plain; charset=utf-8")
                    return

            final = os.path.realpath(os.path.join(target_dir, final_name))
            if not final.startswith(base_root.rstrip("\\/") + os.sep):
                self.send_body("文件名不合法", 400, "text/plain; charset=utf-8")
                return
            if blocked.is_blocked(final):
                self.send_body("文件名不可用", 400, "text/plain; charset=utf-8")
                return
            if os.path.exists(final):
                base_name, ext = os.path.splitext(final_name)
                i = 1
                while True:
                    cand = os.path.realpath(os.path.join(
                        target_dir, "%s(%d)%s" % (base_name, i, ext)))
                    if not cand.startswith(base_root.rstrip("\\/") + os.sep):
                        self.send_body("文件名不合法", 400, "text/plain; charset=utf-8")
                        return
                    if not os.path.exists(cand):
                        final = cand
                        break
                    i += 1

            final = os.path.realpath(final)
            if not final.startswith(base_root.rstrip("\\/") + os.sep):
                self.send_body("文件名不合法", 400, "text/plain; charset=utf-8")
                return

            tmp = os.path.realpath(os.path.join(
                target_dir, ".upload-%s.tmp" % secrets.token_hex(6)))
            if not tmp.startswith(base_root.rstrip("\\/") + os.sep):
                self.send_body("上传临时路径不合法", 400, "text/plain; charset=utf-8")
                return
            remaining = length
            try:
                with open(tmp, "wb") as fh:
                    while remaining > 0:
                        chunk = self.rfile.read(min(CHUNK, remaining))
                        if not chunk:
                            break
                        fh.write(chunk)
                        remaining -= len(chunk)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            if remaining > 0:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                write_log("WARN", self.who(), self._client_ip(), "UPLOAD_ABORTED",
                          "/".join([x for x in (rel_dir, raw_name) if x]),
                          "received=%s expected=%s" % (human_size(length - remaining), human_size(length)))
                self.send_body("上传过程中断", 400, "text/plain; charset=utf-8")
                return
            os.replace(tmp, final)
            invalidate_dir(target_dir)
            write_log("INFO", self.who(), self._client_ip(), "UPLOAD_FILE",
                      _rel_for_log(final),
                      'size="%s" bytes=%d role=%s' % (human_size(length), length, self.role()))
            self.send_json({"ok": True, "name": os.path.basename(final), "size": length})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as exc:  # noqa: BLE001
            write_log("ERROR", self.who(), self._client_ip(), "UPLOAD_FAILED",
                      "/".join([x for x in (rel_dir, raw_name) if x]),
                      'error="%s"' % str(exc).replace('"', "'"))
            try:
                self.send_json({"ok": False, "error": str(exc)}, 500)
            except Exception:
                self.close_connection = True

    # ---------------- 登录限制 ----------------
    # 注意：走端口映射（内网穿透）时所有请求的来源 IP 都是 127.0.0.1，
    # 所以这里一律不按 IP 封禁，改成三道互不相干的闸门：
    #   ① 全站令牌桶：所有设备合起来，每分钟最多 LOGIN_RATE_PER_MINUTE 次尝试；
    #   ② 按「访问者姓名」失败计数：连错 LOGIN_MAX_FAILS 次锁一会儿，再错翻倍；
    #   ③ 错误递增拖延：每错一次多等一会儿才回话，把脚本爆破的速度磨下来。
    # 三条都是"过一会儿自动恢复"的，不会把谁永久关在门外。

    @staticmethod
    def _grant_for(who, pw):
        """按「姓名 + 密码」判身份。
        顺序：先看是不是云空间账号（密码是各自设的哈希）→ 再走 rules.json / config.ini 那三套。
        不能通过返回 None；通过返回身份字典。黑名单里的姓名一律不给进。"""
        if accounts.verify(who, pw):
            d = accounts.user_dir(who)
            if d:
                return {"name": who, "role": ROLE_FULL, "root": "", "abs": d,
                        "perms": accounts.all_perms(), "admin": False, "cl": who}
        return rulesmod.grant_for(who, pw)

    def _client_ip(self):
        """仅用于写日志，不参与任何封禁判断"""
        fwd = self.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0]

    def _make_token(self, grant):
        """身份塞进 Cookie：姓名 / 角色 / 能看的目录 / 权限 / 是否后台。
        签名保证客户端改不了。"""
        payload = json.dumps({
            "name": (grant or {}).get("name") or "",
            "role": (grant or {}).get("role") or ROLE_FULL,
            "root": (grant or {}).get("root") or "",
            "perms": ",".join(sorted((grant or {}).get("perms") or [])),
            "admin": bool((grant or {}).get("admin")),
            "cl": (grant or {}).get("cl") or "",
            "sid": (grant or {}).get("sid") or "",
            "fp": rulesmod.fingerprint(),
        }, ensure_ascii=False, separators=(",", ":"))
        ts = str(int(time.time()))
        # 把 payload 里可能出现的 "." 一并转义，保证 Cookie 永远是"时间.载荷.签名"三段
        b64 = urllib.parse.quote(payload, safe="").replace(".", "%2E")
        mac = hmac.new(SESSION_SECRET, (ts + "." + b64).encode(), hashlib.sha256).hexdigest()[:32]
        return "%s.%s.%s" % (ts, b64, mac)

    # ---------------- 文件发送（支持断点 / Range） ----------------
    def _ua(self):
        """只看日志用：把客户端的浏览器标识截一下，方便排查哪台设备在怎么下载"""
        return (self.headers.get("User-Agent") or "-")[:150].replace('"', "'")

    def send_compat_file(self, abspath, hint="", prefer_zh=False):
        """兼容下载：给"系统下载器"那一类客户端用。

        和普通下载的区别（都是为了让老设备认得出来）：
          - Content-Type 固定 application/octet-stream（不猜图片/PDF，免得被当预览打开）
          - 文件名只给纯 ASCII 的那一个（老下载器解析 filename*=UTF-8'' 会出错）
          - 明确 Accept-Ranges: none，不支持分段（老下载器分段逻辑经常把文件拼坏）
          - 一条连接发完就关，长连接/分块传输都别用
        """
        acquired = FILE_STREAMS.acquire(timeout=60)
        if not acquired:
            self.send_body("并发下载请求过多，请稍后重试", 503, "text/plain; charset=utf-8")
            self.close_connection = True
            return
        try:
            name = str(hint or os.path.basename(abspath)).replace("\r", "").replace("\n", "")
            base_root = os.path.realpath(Config.root)
            abspath = os.path.realpath(abspath)
            if not abspath.startswith(base_root.rstrip("\\/") + os.sep):
                self.send_body("文件路径不合法", 403, "text/plain; charset=utf-8")
                return
            try:
                size = os.path.getsize(abspath)
                mtime = os.path.getmtime(abspath)
            except OSError:
                self.send_body("文件不可读（权限不足或被占用）", 403, "text/plain; charset=utf-8")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition",
                             content_disposition(name, ascii_only=not prefer_zh))
            self.send_header("Accept-Ranges", "none")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Last-Modified", self.date_time_string(mtime))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if self.command == "HEAD":
                return
            sent = 0
            with open(abspath, "rb") as fh:
                while sent < size:
                    chunk = fh.read(min(CHUNK, size - sent))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            FILE_STREAMS.release()

    def send_file(self, abspath, inline=False, filename=None, slot=None, ascii_only=False):
        gate = {"file": FILE_STREAMS, "zip": ZIP_STREAMS}.get(slot)
        if gate is not None:
            if not gate.acquire(timeout=90):
                self.send_body("并发下载请求过多，请稍后重试", 503, "text/plain; charset=utf-8")
                self.close_connection = True
                return
        try:
            self._send_file(abspath, inline, filename, ascii_only)
        finally:
            if gate is not None:
                gate.release()

    def _send_file(self, abspath, inline=False, filename=None, ascii_only=False):
        name = filename or os.path.basename(abspath)
        try:
            size = os.path.getsize(abspath)
            mtime = os.path.getmtime(abspath)
        except OSError:
            self.send_body("文件不可读（权限不足或被占用）", 403, "text/plain; charset=utf-8")
            return
        ctype = guess_type(abspath)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range") or ""
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                g1, g2 = m.group(1), m.group(2)
                if g1:
                    start = int(g1)
                    end = int(g2) if g2 else size - 1
                elif g2:
                    start = max(0, size - int(g2))
                    end = size - 1
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", self.date_time_string(mtime))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Disposition",
                         content_disposition(name, inline, ascii_only=ascii_only))
        if inline:
            # /raw 可能返回用户上传的 SVG/HTML；加沙箱 CSP，禁止其执行脚本或发外部请求
            self.send_header("Content-Security-Policy",
                             "sandbox; default-src 'none'; img-src data:; style-src 'unsafe-inline'")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        if inline:
            self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command == "HEAD":
            return
        with open(abspath, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    # ---------------- 目录打包下载（边压缩边发送） ----------------
    def send_zip(self, abspath, rootname, ascii_only=False):
        if not self.zip_slots.acquire(blocking=False):
            self.send_body("服务器正在处理其他打包任务，请稍后重试", 503, "text/plain; charset=utf-8")
            self.close_connection = True
            return
        try:
            self._send_zip(abspath, rootname, ascii_only)
        finally:
            self.zip_slots.release()

    def _send_zip(self, abspath, rootname, ascii_only=False):
        self._stream_zip([(abspath, os.path.basename(abspath) or "root")],
                         "%s.zip" % rootname, ascii_only)

    def send_zip_multi(self, items, zip_name, ascii_only=False):
        if not self.zip_slots.acquire(blocking=False):
            self.send_body("服务器正在处理其他打包任务，请稍后重试", 503, "text/plain; charset=utf-8")
            self.close_connection = True
            return
        try:
            self._stream_zip(items, zip_name, ascii_only)
        finally:
            self.zip_slots.release()

    def _stream_zip(self, items, zip_name, ascii_only=False):
        class ChunkWriter:
            def __init__(self, wfile):
                self.w = wfile
                self.n = 0
                self.start = 0

            def write(self, b):
                if b:
                    # 一次 write 发完「长度 + 内容 + 结尾」，别拆成三次系统调用
                    self.w.write(b"%x\r\n" % len(b) + b + b"\r\n")
                    self.n += len(b)
                return len(b)

            def tell(self):
                return self.n

            def flush(self):
                try:
                    self.w.flush()
                except Exception:
                    pass

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition",
                         content_disposition(zip_name, ascii_only=ascii_only))
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        writer = ChunkWriter(self.wfile)
        store_ext = IMAGE_EXT | VIDEO_EXT | AUDIO_EXT | {"zip", "rar", "7z", "apk", "exe", "iso", "pdf"}
        try:
            with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                root_real = os.path.realpath(self.root())
                for path, top in items:
                    if blocked.is_blocked(path) or os.path.islink(path):
                        continue
                    if os.path.isdir(path):
                        for dirpath, dirnames, filenames in os.walk(path):
                            dirnames[:] = [d for d in dirnames
                                           if d.lower() not in HIDDEN_NAMES
                                           and not blocked.is_blocked(os.path.join(dirpath, d))
                                           and not os.path.islink(os.path.join(dirpath, d))]
                            rel_dir = os.path.relpath(dirpath, path)
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
                                if rel_dir == ".":
                                    # 根目录下的文件必须放在同名的顶层文件夹里，
                                    # 否则所有根级文件都会被写成同一个 arc 名称，ZIP 会出现重复条目。
                                    arc = top + "/" + fn
                                else:
                                    arc = top + "/" + rel_dir.replace("\\", "/") + "/" + fn
                                try:
                                    zip_type = (zipfile.ZIP_STORED if ext_of(fn) in store_ext
                                                else zipfile.ZIP_DEFLATED)
                                    self._zip_add(zf, full, arc, zip_type)
                                except (OSError, ValueError, zipfile.BadZipFile):
                                    continue
                    elif os.path.isfile(path):
                        try:
                            zip_type = (zipfile.ZIP_STORED if ext_of(top) in store_ext
                                        else zipfile.ZIP_DEFLATED)
                            self._zip_add(zf, path, top, zip_type)
                        except (OSError, ValueError, zipfile.BadZipFile):
                            continue
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                self.close_connection = True

    @staticmethod
    def _zip_add(zf, full, arc, zip_type):
        """把一个文件塞进 zip。不用 zf.write()：它内部按 8KB 拷，走公网/穿透时
        发出去就是一串小包，速度会掉得很难看；这里按 CHUNK（256KB）整块读整块写。"""
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
