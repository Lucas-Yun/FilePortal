# -*- coding: utf-8 -*-
"""自建多用户云空间：账号、开通申请、头像。

设计要点（都是使用者明确要求过的）：
  · 每个用户一个独立文件夹，建在 config.ini → [云空间] cloud_root 下面，互相看不见；
  · 一个用户名对一个密码，密码只存 PBKDF2 指纹（哈希 + 随机盐），管理员也看不到明文；
  · 权限固定「全部权限」，不跟 rules.json 里那三套密码混在一起；
  · 新用户先提交申请（只填姓名）→ 管理员在 /admin 点「通过」时生成 4 位验证码 →
    申请人凭「姓名 + 验证码」自己设密码，这一步走完账号才真正建出来；
  · 申请一天只允许一次（按设备 + 按名字各算一遍，超了直接提示）；
  · 头像存在 data/avatars/ 里（这个目录不在投射范围内，网页上取不到别人的头像）。

数据文件 accounts.json 放在数据目录（同样不在投射范围里）：
  {
    "users": [ {name, key, hash, created, avatar, enabled} ... ],
    "apps":  [ {id, name, key, created, day, device,
                status:"pending"|"approved", code:"1234", code_tries} ... ],
    "recent":[ {key, day, device, kind:"apply"} ... ]      # 只用来算「一天一次」
  }
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import threading
import time

from . import settings

ACCOUNTS_FILE = os.path.join(settings.DATA_DIR, "accounts.json")
AVATAR_DIR = os.path.join(settings.DATA_DIR, "avatars")

_ITER = 180000
_LOCK = threading.RLock()
_LOAD_ERROR = None

_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"admin", "administrator", "root", "system", "anonymous", "guest", "匿名访客"}

# 验证码最多允许错几次（按姓名记，不按 IP 记——端口映射时 IP 全是 127.0.0.1）
_CODE_MAX_TRIES = 8


def _app_status(app):
    """申请状态：pending（待审）/ approved（已通过、等申请人自己设密码）"""
    return (app.get("status") or "pending").strip().lower()


# --------------------------------------------------------------------------- #
# 基础
# --------------------------------------------------------------------------- #
def cloud_root():
    raw = (settings.raw("cloud_root") or "").strip()
    if not raw:
        raw = r"D:\CLOUDPAN"
    if not os.path.isabs(raw):
        raw = os.path.join(settings.PROJECT_DIR, raw)
    return os.path.abspath(raw)


def _ensure_cloud_root():
    try:
        os.makedirs(cloud_root(), exist_ok=True)
    except OSError:
        pass
    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
    except OSError:
        pass


def valid_name(name):
    """用户名：2~24 个字符，中文/字母/数字/下划线/短横线/点都行，不能带路径符号"""
    name = (name or "").strip()
    if not (2 <= len(name) <= 24):
        return False
    if _BAD_CHARS.search(name) or name.startswith("."):
        return False
    if name.casefold() in _RESERVED:
        return False
    if name.casefold() == (settings.ADMIN_NAME or "").casefold():
        return False
    if name.casefold() == (settings.NAME_FULL or "").casefold():
        return False
    return True


def user_dir(name):
    """某个用户的云空间目录（绝对路径）；名字不合法返回 None"""
    if not valid_name(name):
        return None
    name = (name or "").strip()
    safe_name = os.path.basename(name)
    if safe_name != name or safe_name in ("", ".", ".."):
        return None
    root = os.path.realpath(cloud_root())
    path = os.path.realpath(os.path.join(root, safe_name))
    if not path.startswith(root.rstrip("\\/") + os.sep):
        return None
    _ensure_cloud_root()
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return None
    return path


def all_perms():
    from .settings import ROLE_PERMS, ROLE_FULL
    return set(ROLE_PERMS.get(ROLE_FULL, set()))


# --------------------------------------------------------------------------- #
# 密码指纹
# --------------------------------------------------------------------------- #
def _hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), salt.encode("utf-8"), _ITER)
    return "pbkdf2_sha256$%d$%s$%s" % (_ITER, salt, dk.hex())


def _check_pw(pw, stored):
    try:
        algo, iters, salt, digest = (stored or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (pw or "").encode("utf-8"), salt.encode("utf-8"), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# 数据文件
# --------------------------------------------------------------------------- #
def _blank():
    return {"version": 1, "users": [], "apps": [], "recent": []}


def load_error():
    """最近一次读取账号文件是否失败；后台/调用方可以据此停止写操作。"""
    return _LOAD_ERROR


def _load():
    global _LOAD_ERROR
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        _LOAD_ERROR = None
        return _blank()
    except (OSError, ValueError) as exc:
        _LOAD_ERROR = "accounts.json 读取失败：%s" % exc
        return _blank()
    if not isinstance(data, dict):
        _LOAD_ERROR = "accounts.json 顶层不是对象，拒绝覆盖"
        return _blank()
    for key in ("users", "apps", "recent"):
        if not isinstance(data.get(key), list):
            data[key] = []
    _LOAD_ERROR = None
    return data


def _save(data):
    global _LOAD_ERROR
    if _LOAD_ERROR:
        raise RuntimeError(_LOAD_ERROR + "；已停止写入，请检查 data/accounts.json 的格式")
    path = ACCOUNTS_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    _LOAD_ERROR = None


def _find_user(data, name):
    key = (name or "").strip().casefold()
    for u in data["users"]:
        if u.get("key") == key:
            return u
    return None


def _find_app(data, name=None, app_id=None, device=None):
    out = []
    for a in data["apps"]:
        if app_id and a.get("id") == app_id:
            out.append(a)
            continue
        if name and a.get("key") == name.strip().casefold():
            out.append(a)
            continue
        if device and a.get("device") == device:
            out.append(a)
    return out


# --------------------------------------------------------------------------- #
# 对外：查 / 建 / 删
# --------------------------------------------------------------------------- #
def exists(name):
    with _LOCK:
        return _find_user(_load(), name) is not None


def verify(name, pw):
    """用户名 + 密码对不对。只看启用状态的账号。"""
    with _LOCK:
        u = _find_user(_load(), name)
    if not u or not u.get("enabled", True):
        return False
    return _check_pw(pw, u.get("hash") or "")


def users():
    """后台展示用：[{name, created, avatar}]"""
    with _LOCK:
        data = _load()
    out = []
    for u in data["users"]:
        if not u.get("enabled", True):
            continue
        try:
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(u.get("created") or 0)))
        except (ValueError, TypeError, OSError):
            created = ""
        out.append({"name": u.get("name") or "", "created": created,
                    "avatar": bool(u.get("avatar")), "key": u.get("key") or ""})
    out.sort(key=lambda x: x["name"].casefold())
    return out


def count():
    with _LOCK:
        data = _load()
    return sum(1 for u in data["users"] if u.get("enabled", True))


def create(name, pw):
    """直接创建账号（供后台手动开通使用）"""
    name = (name or "").strip()
    if not valid_name(name):
        return False, "用户名不合法：2~24 个字，不能带 \\ / : * ? \" < > |"
    pw = pw or ""
    if len(pw) < 8:
        return False, "密码长度不足（至少 8 位）"
    if len(pw) > 128:
        return False, "密码过长（最多 128 位）"
    with _LOCK:
        data = _load()
        if _find_user(data, name):
            return False, "「%s」该姓名已被注册" % name
        data["users"].append({
            "name": name, "key": name.casefold(), "hash": _hash_pw(pw),
            "created": time.time(), "avatar": "", "enabled": True,
        })
        # 顺手把同名的申请清掉
        data["apps"] = [a for a in data["apps"] if a.get("key") != name.casefold()]
        _save(data)
    user_dir(name)
    return True, "已创建云空间账号：%s" % name


def _user_folder(name):
    """定位用户目录；不创建，不在云空间根内或名字非法则返回 None"""
    name = (name or "").strip()
    if not valid_name(name):
        return None
    root = os.path.realpath(cloud_root())
    path = os.path.join(root, name)
    real = os.path.realpath(path)
    try:
        if os.path.commonpath([root, real]) != root or real == root:
            return None
    except ValueError:
        return None
    return path


def _rmtree_fix(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def _purge_folder(path):
    """删除用户目录；不存在视为成功。失败抛 OSError 由调用方处理。"""
    if not path or not os.path.exists(path):
        return
    if os.path.islink(path):
        os.remove(path)
        return
    try:
        shutil.rmtree(path, onexc=_rmtree_fix)
    except TypeError:
        shutil.rmtree(path, onerror=_rmtree_fix)


def delete_user(name):
    """彻底删除云空间账号：账号、申请记录、头像、个人目录一并清除。

    先移除账号（旧会话立即失效），再删除目录；目录删不掉时恢复账号，避免
    “账号没了但文件还在”的半完成状态。整个过程持有账号锁，避免同名重新注册
    后目录被误删。
    """
    with _LOCK:
        data = _load()
        u = _find_user(data, name)
        if not u:
            return False, "没有这个账号"
        key = u.get("key") or ""
        uname = (u.get("name") or name or "").strip()
        folder = _user_folder(uname)
        if folder is None:
            return False, "账号名不合法，无法定位其云空间目录，已取消删除"
        snapshot = dict(u)
        gone_apps = [a for a in data.get("apps", []) if a.get("key") == key]
        gone_recent = [r for r in data.get("recent", []) if r.get("key") == key]
        data["users"] = [x for x in data["users"] if x.get("key") != key]
        data["apps"] = [a for a in data.get("apps", []) if a.get("key") != key]
        data["recent"] = [r for r in data.get("recent", []) if r.get("key") != key]
        _save(data)
        try:
            _purge_folder(folder)
        except OSError as exc:
            data2 = _load()
            if not _find_user(data2, key):
                data2["users"].append(snapshot)
            for a in gone_apps:
                if not _find_app(data2, app_id=a.get("id")):
                    data2.setdefault("apps", []).append(a)
            have = {(r.get("key"), r.get("day"), r.get("kind")) for r in data2.get("recent", [])}
            for r in gone_recent:
                if (r.get("key"), r.get("day"), r.get("kind")) not in have:
                    data2.setdefault("recent", []).append(r)
            _save(data2)
            return False, "账号目录删除失败，账号已恢复：%s" % exc
        av = snapshot.get("avatar") or ""
        if av:
            try:
                os.remove(os.path.join(AVATAR_DIR, av))
            except OSError:
                pass
        return True, "已彻底删除「%s」：账号、开通记录、头像及云空间目录均已删除" % uname


# --------------------------------------------------------------------------- #
# 开通申请（一天一次）
# --------------------------------------------------------------------------- #
def _today():
    return time.strftime("%Y-%m-%d")


def _prune_recent(data):
    keep = [r for r in data.get("recent", []) if r.get("day") == _today()]
    data["recent"] = keep[-400:]


def submit(name, device="", remark=""):
    """提交申请（只填姓名与选填备注，不填密码）。返回 (ok, msg)

    流程：申请 → 管理员审批通过（生成 4 位验证码）→ 申请人凭姓名 + 验证码设置密码。
    所以这里不再收密码，密码要等验证码核对通过后才由申请人自己设。
    """
    name = (name or "").strip()
    remark = " ".join((remark or "").split())[:200]
    if not valid_name(name):
        return False, "姓名不合法：2~24 个字，不能带 \\ / : * ? \" < > |"
    if settings.is_blocked(name):
        return False, "该姓名当前不可用"
    limit = settings.integer("register_daily_limit", 1, 20)
    with _LOCK:
        data = _load()
        if _find_user(data, name):
            return False, "「%s」已经注册过了，可直接登录" % name
        mine = [a for a in data["apps"] if a.get("key") == name.casefold()]
        if any(_app_status(a) == "approved" for a in mine):
            return False, "「%s」已经通过审批了，请到「凭验证码设置密码」页面完成注册" % name
        if mine:
            return False, "「%s」的申请正在等待管理员审核，无需重复提交" % name
        _prune_recent(data)
        used = 0
        for r in data["recent"]:
            if r.get("key") == name.casefold() or (device and r.get("device") == device):
                used += 1
        if used >= limit:
            _save(data)
            return False, "今日申请次数已达上限（每天最多 %d 次），请次日再试" % limit
        data["apps"].append({
            "id": secrets.token_hex(4), "name": name, "key": name.casefold(),
            "created": time.time(), "day": _today(), "device": device or "",
            "status": "pending", "code": "", "hash": "", "code_tries": 0,
            "remark": remark,
        })
        data["recent"].append({"key": name.casefold(), "day": _today(),
                               "device": device or "", "kind": "apply"})
        _save(data)
    return True, "申请已提交。管理员审批通过后将生成 4 位验证码，届时可继续设置密码。"


def applications():
    """后台用：还没审批的申请"""
    with _LOCK:
        data = _load()
    out = []
    for a in data["apps"]:
        if _app_status(a) != "pending":
            continue
        try:
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(a.get("created") or 0)))
        except (ValueError, TypeError, OSError):
            created = ""
        out.append({"id": a.get("id") or "", "name": a.get("name") or "",
                    "created": created, "day": a.get("day") or "",
                    "remark": a.get("remark") or ""})
    out.sort(key=lambda x: x["created"])
    return out


def approved():
    """后台用：已通过审批、还没自己设密码的申请（带验证码）"""
    with _LOCK:
        data = _load()
    out = []
    for a in data["apps"]:
        if _app_status(a) != "approved":
            continue
        try:
            created = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(a.get("created") or 0)))
        except (ValueError, TypeError, OSError):
            created = ""
        out.append({"id": a.get("id") or "", "name": a.get("name") or "",
                    "code": a.get("code") or "", "created": created,
                    "remark": a.get("remark") or ""})
    out.sort(key=lambda x: x["created"])
    return out


def _new_code():
    """4 位数字验证码（允许 0 开头，按字符串比对）"""
    return "%04d" % secrets.randbelow(10000)


def approve(app_id):
    """通过申请：只生成验证码，不建号。真正建号要等申请人自己凭验证码设密码。"""
    with _LOCK:
        data = _load()
        app = next((a for a in data["apps"] if a.get("id") == app_id), None)
        if not app:
            return False, "该申请不存在（可能已被处理）"
        if _app_status(app) == "approved":
            return True, "「%s」已经通过审批，验证码是 %s" % (app.get("name") or "",
                                                              app.get("code") or "")
        app["status"] = "approved"
        app["code"] = _new_code()
        app["code_ts"] = time.time()
        app["code_tries"] = 0
        app["hash"] = ""
        _save(data)
    return True, "已通过「%s」，验证码 %s（请将该验证码告知申请人）" % (
        app.get("name") or "", app.get("code") or "")


def regenerate(app_id):
    """换一个新的验证码（申请人说没收到、或者输错太多次时用）"""
    with _LOCK:
        data = _load()
        app = next((a for a in data["apps"] if a.get("id") == app_id), None)
        if not app or _app_status(app) != "approved":
            return False, "该申请尚未通过审批，无法更换验证码"
        app["code"] = _new_code()
        app["code_ts"] = time.time()
        app["code_tries"] = 0
        _save(data)
        return True, "验证码已更新：%s" % (app.get("code") or "")


def complete(name, code, pw):
    """凭姓名 + 4 位验证码 + 自己设的密码，完成注册（真正建号）"""
    name = (name or "").strip()
    code = (code or "").strip()
    pw = pw or ""
    if not valid_name(name):
        return False, "姓名不合法：2~24 个字，不能带 \\ / : * ? \" < > |"
    if len(pw) < 8:
        return False, "密码长度不足（至少 8 位）"
    if len(pw) > 128:
        return False, "密码过长（最多 128 位）"
    if not (code.isdigit() and len(code) == 4):
        return False, "验证码为 4 位数字，请按管理员提供的内容填写"
    if settings.is_blocked(name):
        return False, "该姓名当前不可用"
    with _LOCK:
        data = _load()
        if _find_user(data, name):
            return False, "「%s」已经注册过了，可直接登录" % name
        app = None
        for a in data["apps"]:
            if a.get("key") == name.casefold() and _app_status(a) == "approved":
                app = a
                break
        if not app:
            return False, "未找到已通过的申请：请先提交申请并等待管理员审批"
        if int(app.get("code_tries") or 0) >= _CODE_MAX_TRIES:
            return False, "验证码错误次数过多，请联系管理员更换验证码"
        if not hmac.compare_digest(str(app.get("code") or ""), code):
            app["code_tries"] = int(app.get("code_tries") or 0) + 1
            _save(data)
            left = _CODE_MAX_TRIES - app["code_tries"]
            return False, "验证码不正确（剩余 %d 次机会，超出后需由管理员更换验证码）" % left
        data["users"].append({
            "name": name, "key": name.casefold(), "hash": _hash_pw(pw),
            "created": time.time(), "avatar": "", "enabled": True,
        })
        data["apps"] = [a for a in data["apps"] if a.get("id") != app.get("id")]
        _save(data)
    user_dir(name)
    return True, "注册成功，现可使用「%s」与所设密码登录" % name


def reject(app_id):
    with _LOCK:
        data = _load()
        name = next((a.get("name") for a in data["apps"] if a.get("id") == app_id), "")
        data["apps"] = [a for a in data["apps"] if a.get("id") != app_id]
        _save(data)
    return True, "已拒绝申请：%s" % (name or app_id)


# --------------------------------------------------------------------------- #
# 头像
# --------------------------------------------------------------------------- #
_ALLOWED_AVATAR = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
                   ".ico": "image/x-icon", ".svg": "image/svg+xml", ".avif": "image/avif"}


def avatar_file(name):
    with _LOCK:
        u = _find_user(_load(), name)
        fn = (u or {}).get("avatar") or ""
    if not fn:
        return None
    path = os.path.join(AVATAR_DIR, fn)
    return path if os.path.isfile(path) else None


def avatar_type(path):
    return _ALLOWED_AVATAR.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


def detect_avatar_format(data, ctype=""):
    """按文件头识别头像真实格式，返回扩展名；无法识别返回 None。"""
    ctype = (ctype or "").split(";")[0].strip().lower()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"
    if data[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    head = data[:8192].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head[:1] == b"<":
        if b"<svg" in head.lower():
            return ".svg"
        return None
    return {"image/png": ".png", "image/jpeg": ".jpg",
            "image/webp": ".webp", "image/gif": ".gif",
            "image/bmp": ".bmp", "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
            "image/svg+xml": ".svg", "image/avif": ".avif"}.get(ctype)


def set_avatar(name, data, ext):
    ext = (ext or "").lower()
    if ext not in _ALLOWED_AVATAR:
        return False, "头像支持 PNG / JPG / JPEG / WEBP / GIF / BMP / ICO / SVG / AVIF 格式"
    limit = settings.integer("avatar_max_kb", 64, 10240) * 1024
    if not data:
        return False, "未接收到图片数据"
    if len(data) > limit:
        return False, "图片超出大小限制（上限 %d KB）" % (limit // 1024)
    with _LOCK:
        u = _find_user(_load(), name)
        if not u:
            return False, "没有这个账号"
        old = u.get("avatar") or ""
        fn = "%s_%s%s" % (hashlib.sha1((u.get("key") or name).encode("utf-8")).hexdigest()[:12],
                          secrets.token_hex(4), ext)
        _ensure_cloud_root()
        target = os.path.join(AVATAR_DIR, fn)
        try:
            with open(target, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            return False, "头像保存失败：%s" % exc
        data2 = _load()
        u2 = _find_user(data2, name)
        if u2 is None:
            try:
                os.remove(target)
            except OSError:
                pass
            return False, "账号状态已变更，请重新登录后重试"
        u2["avatar"] = fn
        _save(data2)
    if old and old != fn:
        try:
            os.remove(os.path.join(AVATAR_DIR, old))
        except OSError:
            pass
    return True, "头像已更新"


def clear_avatar(name):
    with _LOCK:
        data = _load()
        u = _find_user(data, name)
        if not u:
            return False, "没有这个账号"
        old = u.get("avatar") or ""
        u["avatar"] = ""
        _save(data)
    if old:
        try:
            os.remove(os.path.join(AVATAR_DIR, old))
        except OSError:
            pass
    return True, "已恢复为默认头像"
