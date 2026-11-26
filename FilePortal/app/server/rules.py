# -*- coding: utf-8 -*-
# 模块说明：登录规则 JSON 的读取、校验和保存
"""登录规则：rules.json 里一条条写「什么姓名 + 什么密码 → 哪些权限 / 只能看哪一层目录」。

为什么单独放一个文件：
  · 后台页面（Admin 登录后进去的那个）直接读写它，改完下一次登录立刻生效，不用重启；
  · 你也可以用记事本手改，格式就是普通 JSON；
  · 文件丢了 / 写坏了，不会崩，退回 config.ini 里 [密码] 那套老规矩。

规则的匹配顺序是从上往下，第一条匹配上的说了算。都不匹配 → 走老规矩。
"""

import hmac
import json
import os
import tempfile

from . import settings
from .settings import (ROLE_FULL, ROLE_STUDY, ROLE_READ, role_perms, role_root,
                       parse_perms, ALL_PERMS, is_blocked)

# JSON 里允许出现的键
_FIELDS = ("name", "password", "perms", "root", "note")
_LOAD_ERROR = None

TEMPLATE_HEAD = {
    "_help": [
        "登录规则（网页后台 /admin 里也能改，改完立刻生效，不用重启）。",
        "name      访问人姓名：写具体名字=必须是这个人；空着写 * = 谁都行；写 !名字 = 除了这个人都行。",
        "password  该规则的密码（大小写不敏感）。",
        "perms     权限，可用 download,preview,zip,upload,mkdir,rename,delete，用英文逗号隔开；留空=只读。",
        "root      能看到的目录：空 = 整个投射根；填子目录（相对投射根，用 / 分隔）= 只能看这一层及其下面。",
        "note      备注，只给自己看。",
        "规则从上往下匹配，谁先匹配上就用谁。都不匹配时，再用 config.ini 里 [密码] 那套老规矩。",
    ],
}


def _clean_rule(raw):
    """把页面上/文件里读到的一条规则收拾干净，非法条目返回 None"""
    if not isinstance(raw, dict):
        return None
    rule = {}
    for k in _FIELDS:
        v = raw.get(k)
        rule[k] = ("" if v is None else str(v)).strip()
    rule["password"] = rule["password"].strip()
    if not rule["password"]:
        return None                      # 没密码的规则没有意义
    name = rule["name"]
    if name in ("*", "任何", "任意", "所有人", "any", "ANY"):
        rule["name"] = "*"
    rule["root"] = rule["root"].replace("\\", "/").strip().strip("/")
    if ":" in rule["root"] or ".." in rule["root"].split("/"):
        rule["root"] = ""                # 路径写歪了就当整根，别让它跳出投射目录
    rule["_perms_set"] = parse_perms(rule["perms"])
    return rule


def fingerprint():
    """规则文件的"版本指纹"（改时间 + 大小）。登录时写进 Cookie，
    每次带 Cookie 访问都对比一遍：规则一改，之前发出去的会话立刻作废，
    这样后台把某条规则删了，那个人当前已经登录的页面也就没权限了。"""
    try:
        st = os.stat(settings.RULES_FILE)
        return "%d_%d" % (st.st_mtime_ns, st.st_size)
    except OSError:
        return "0_0"


def load():
    """读 rules.json，返回 [rule...]（按文件顺序）"""
    global _LOAD_ERROR
    path = settings.RULES_FILE
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        _LOAD_ERROR = None
        return []
    except (OSError, ValueError) as exc:
        _LOAD_ERROR = "rules.json 读取失败：%s" % exc
        return []
    raw = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        _LOAD_ERROR = "rules.json 结构不正确，拒绝覆盖"
        return []
    out = []
    for item in raw:
        rule = _clean_rule(item)
        if rule:
            out.append(rule)
    _LOAD_ERROR = None
    return out


def load_error():
    return _LOAD_ERROR


def save(rules):
    """把规则写回 rules.json（原子替换，写一半断电也不会把文件写坏）"""
    if _LOAD_ERROR:
        raise RuntimeError(_LOAD_ERROR + "；已停止写入，请检查 data/rules.json 的格式")
    cleaned = [dict((k, r.get(k, "")) for k in _FIELDS) for r in rules]
    data = dict(TEMPLATE_HEAD)
    data["rules"] = cleaned
    path = settings.RULES_FILE
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".rules-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _pw_eq(given, stored):
    """密码比较：沿用 config.ini 的约定（不区分大小写），但用常量时间比较，
    避免逐字符提前返回泄露前缀。"""
    a = (given or "").strip().casefold().encode("utf-8", "replace")
    b = (stored or "").strip().casefold().encode("utf-8", "replace")
    return bool(a) and hmac.compare_digest(a, b)


def _name_hit(rule_name, who):
    """姓名匹配：* / !名字 / 具体名字"""
    who = (who or "").strip()
    rn = (rule_name or "").strip()
    if rn in ("", "*"):
        return True
    if rn.startswith("!"):
        return who.casefold() != rn[1:].strip().casefold()
    if rn.casefold() == who.casefold():
        return True
    return False


def match(who, pw):
    """按规则判身份。命中返回 grant 字典，否则 None。

    grant = {"name", "role", "root", "perms"(set), "admin"(bool), "note"}
    """
    name = (who or "").strip()
    pw_text = (pw or "").strip()
    if not name or not pw_text:
        return None
    if is_blocked(name):
        return None
    for rule in load():
        if not _name_hit(rule.get("name", ""), name):
            continue
        if not _pw_eq(pw_text, rule["password"]):
            continue
        perms = set(rule.get("_perms_set") or ())
        role = ROLE_FULL if len(perms & {"delete", "rename"}) else \
               (ROLE_STUDY if rule.get("root") else ROLE_READ)
        return {
            "name": name,
            "role": role,
            "root": rule.get("root", ""),
            "perms": perms,
            "admin": False,
            "note": rule.get("note", ""),
        }
    return None


def builtin_grant(who, pw):
    """没有规则命中时，按 config.ini 的老规矩（PW_FULL / PW_STUDY / PW_READ / 旧密码）"""
    name = (who or "").strip()
    pw_text = (pw or "").strip()
    if not pw_text or is_blocked(name):
        return None

    def mk(role, root=""):
        return {"name": name, "role": role, "root": root,
                "perms": set(role_perms(role)), "admin": False, "note": ""}

    if settings.PW_FULL and _pw_eq(pw_text, settings.PW_FULL):
        if not settings.NAME_FULL or name == settings.NAME_FULL:
            return mk(ROLE_FULL)
    if settings.PW_STUDY and _pw_eq(pw_text, settings.PW_STUDY):
        return mk(ROLE_STUDY)
    if settings.PW_READ and _pw_eq(pw_text, settings.PW_READ):
        return mk(ROLE_READ)
    if settings.Config.password and _pw_eq(pw_text, settings.Config.password):
        # 旧密码只给「主人姓名」使用，避免名单里任何人拿到旧密码就变成全权限
        if not settings.NAME_FULL or name == settings.NAME_FULL:
            return mk(ROLE_FULL)
    return None


def admin_grant(who, pw):
    """后台专用：姓名必须是 admin_name（默认 Admin，大小写不敏感），密码必须是最高权限密码"""
    name = (who or "").strip()
    pw_text = (pw or "").strip()
    if not name or not pw_text:
        return None
    if name.casefold() != settings.ADMIN_NAME.strip().casefold():
        return None
    best = [p for p in (settings.PW_ADMIN, settings.PW_FULL) if p]
    for p in best:
        if _pw_eq(pw_text, p):
            return {"name": name, "role": ROLE_FULL, "root": "", "perms": set(ALL_PERMS),
                    "admin": True, "note": "网页后台"}
    return None


def grant_for(who, pw):
    """登录入口：后台身份 → 规则 → 老规矩"""
    return admin_grant(who, pw) or match(who, pw) or builtin_grant(who, pw)


def grant_root(grant, base_root=None):
    """grant 对应的访问根（root 为空 = 整个投射根）"""
    base = os.path.abspath(base_root or settings.Config.root)
    sub = (grant.get("root") or "").strip().strip("/")
    if not sub:
        return base
    return os.path.join(base, *[p for p in sub.split("/") if p and p != "."])


def grant_role(grant):
    return (grant or {}).get("role") or ROLE_READ
