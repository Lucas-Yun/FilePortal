# 模块说明：下载直链临时令牌的签发与校验
"""带签名的下载直链（给不带 Cookie 的老设备 / 学习机下载器用）。

为什么要它：
  某些设备的"系统下载器"是另一个进程在拉文件，它只拿到一个网址，
  不会把浏览器的登录 Cookie 带过去 → 服务端看到的是"没登录"，于是下载失败、
  保存成一个叫 file / null 的怪文件。所以下载链接里直接带一张"临时通行证"：
  /d/<文件名>?p=<路径>&t=<签名>，下载器不需要 Cookie 也能下。

签名里包含：谁、能看哪一层目录、有哪些权限、什么时候过期。
过期时间由 config.ini 的 [下载] dl_token_hours 控制（默认 12 小时）。
"""

import base64
import binascii
import hashlib
import hmac
import json
import time

from . import settings


def _sign(raw):
    return hmac.new(settings.SESSION_SECRET, ("dl." + raw).encode(),
                    hashlib.sha256).hexdigest()[:24]


def _rule_fingerprint():
    try:
        from . import rules
        return rules.fingerprint()
    except Exception:  # noqa: BLE001
        return "0_0"


def make(grant):
    """给一个身份（姓名 / root / perms）签发下载直链，返回 t 参数"""
    if not grant:
        return ""
    hours = 12
    try:
        hours = int(settings.raw("dl_token_hours") or 12)
    except ValueError:
        hours = 12
    hours = max(1, min(24 * 30, hours))
    payload = {
        "n": grant.get("name") or "",
        "r": grant.get("root") or "",
        "p": sorted(grant.get("perms") or []),
        "e": int(time.time()) + hours * 3600,
        "f": _rule_fingerprint(),
    }
    raw = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return raw + "." + _sign(raw)


def read(tok):
    """校验 t 参数，通过返回 {name, root, perms}，否则 None"""
    tok = (tok or "").strip()
    if "." not in tok:
        return None
    raw, _, sig = tok.rpartition(".")
    if not raw or not sig or not hmac.compare_digest(sig, _sign(raw)):
        return None
    try:
        pad = "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode(raw + pad).decode("utf-8"))
    except (ValueError, TypeError, binascii.Error):
        return None
    if not isinstance(data, dict):
        return None
    try:
        if int(data.get("e") or 0) < int(time.time()):
            return None
    except (TypeError, ValueError):
        return None
    if str(data.get("f") or "") != _rule_fingerprint():
        return None
    try:
        from .settings import is_blocked
        if is_blocked(str(data.get("n") or "")):
            return None
    except Exception:  # noqa: BLE001
        return None
    perms = data.get("p")
    return {"name": str(data.get("n") or ""),
            "root": str(data.get("r") or ""),
            "perms": set(str(p) for p in perms) if isinstance(perms, list) else set()}
