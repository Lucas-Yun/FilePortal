# -*- coding: utf-8 -*-
"""网页后台（配置界面）：只有用 Admin + 最高权限密码登录的人能看到和打开。

里面能改的东西都落在项目根目录的文件里：
  · config.ini    —— 原样改值，注释和排版都保留（改完提示重启才生效）
  · rules.json    —— 登录规则，加一条删一条都行（下一次登录立刻生效，不用重启）
  · data/lists/blacklist/ —— 黑名单目录，支持 txt/csv/xlsx/docx，合并成一份姓名名单
"""

import html
import os
import subprocess
import sys
import tempfile
import time

from . import accounts, blocked, denylist, fsutil, sessions, settings, rules, zcache

# --------------------------------------------------------------------------- #
# 可配置项（分节、键、标签、类型、说明）
# kind: text / int / flag / pw / area
# --------------------------------------------------------------------------- #
FIELDS = [
    ("服务器", "port", "端口", "int", "修改后需重启服务；内网穿透映射的目标端口须同步调整"),
    ("服务器", "host", "监听地址", "text", "0.0.0.0 表示监听全部网卡，通常无需修改"),
    ("服务器", "workers", "同时处理请求数", "text", "留空表示按 CPU 核数自动计算"),
    ("服务器", "zip_slots", "同时打包数", "int", ""),
    ("服务器", "upload_slots", "同时上传数", "int", ""),
    ("服务器", "per_page", "每页条数", "int", "列表每页显示的条目数"),
    ("服务器", "list_cache_seconds", "列表缓存秒数", "text", "0 表示关闭该功能"),
    ("服务器", "request_timeout", "请求超时秒数", "int", ""),
    ("服务器", "https_port", "额外 HTTPS 端口", "int", "0 表示不启用；填写 8443 等端口可同时提供 HTTP 与 HTTPS 服务"),
    ("服务器", "certfile", "证书文件（PEM）", "text", "留空表示仅提供 HTTP 服务"),
    ("服务器", "keyfile", "私钥文件（PEM）", "text", ""),
    ("服务器", "admin_name", "后台姓名", "text", "用这个名字 + 最高权限密码登录就能进本页"),
    ("下载", "file_threads", "文件下载并发", "int", "全站并发下载连接上限"),
    ("下载", "zip_threads", "打包下载并发", "int", ""),
    ("下载", "threaded_max_mb", "并发下载上限 MB", "int", "超过该大小的文件交由浏览器原生下载处理"),
    ("下载", "zip_cache_max_mb", "打包缓存上限 MB", "int", "超过该上限时改为边压缩边传输"),
    ("下载", "zip_cache_minutes", "打包缓存保留分钟", "int", ""),
    ("下载", "save_picker", "另存为直写", "flag", "1 表示通过“另存为”直写绕开浏览器下载拦截（推荐）"),
    ("页脚", "show_footer", "显示页脚", "flag", "true 或 false"),
    ("页脚", "site_code", "站点编号", "text", ""),
    ("页脚", "icp_no", "ICP 备案号", "text", ""),
    ("页脚", "icp_url", "ICP 链接", "text", ""),
    ("页脚", "police_no", "公安备案号", "text", ""),
    ("页脚", "police_url", "公安备案链接", "text", ""),
    ("密码", "pw_full", "最高权限密码", "pw", "仅当访问者姓名等于「主人姓名」时可用"),
    ("密码", "admin_password", "后台专用密码", "pw",
     "Admin 姓名 + 这个密码进后台；留空则沿用最高权限密码，旧密码不能再进后台"),
    ("密码", "full_name", "主人姓名", "text", ""),
    ("密码", "pw_study", "学习资料密码", "pw", "任意姓名配合该密码仅可访问学习资料目录"),
    ("密码", "pw_read", "只读密码", "pw", ""),
    ("密码", "legacy_password", "旧密码", "pw", "旧版本使用的密码，留空表示停用"),
    ("密码", "study_subpath", "学习资料子目录", "text", "相对存储根目录，以 / 分隔"),
    ("密码", "session_days", "登录保持天数", "int", ""),
    ("名单", "whitelist_dir", "白名单文件夹", "text",
     "相对程序目录；其中的 txt/csv/xlsx/docx 文件均会被解析为姓名名单（修改即时生效）"),
    ("名单", "blacklist_dir", "黑名单文件夹", "text",
     "相对程序目录；其中的 txt/csv/xlsx/docx 文件均会被解析为禁止名单（修改即时生效）"),
    ("名单", "whitelist_enforce", "白名单生效", "flag",
     "1 表示仅名单内人员可访问；0 表示白名单不生效"),
    ("下载", "dl_token_hours", "下载直链有效期（小时）", "int",
     "供兼容模式及旧设备下载使用的临时凭证，过期后需返回列表页重新发起"),
    ("防爆破", "login_max_fails", "连续失败多少次后触发锁定", "int", ""),
    ("防爆破", "login_lock_seconds", "首次锁定时长（秒）", "int", ""),
    ("防爆破", "login_lock_max_seconds", "锁定时长上限（秒）", "int", ""),
    ("防爆破", "login_rate_per_minute", "全站每分钟允许的登录请求上限", "int", ""),
    ("防爆破", "login_burst", "允许的突发请求次数", "int", ""),
    ("防爆破", "login_fail_delay_ms", "单次失败的延迟时长（毫秒）", "int", ""),
    ("防爆破", "login_fail_delay_max_ms", "延迟时长上限（毫秒）", "int", ""),
    ("权限", "full_perms", "最高权限包含", "text", "以英文逗号分隔；规则文件中的规则优先级更高"),
    ("权限", "study_perms", "学习资料权限包含", "text", ""),
    ("权限", "read_perms", "只读权限包含", "text", ""),
    ("云盘", "cloud_root", "云空间根目录", "text",
     "建议使用纯英文路径，如 D:\\CLOUDPAN；每位用户在其下拥有一个同名目录"),
    ("云盘", "register_enabled", "开放注册", "flag",
     "1 表示登录页显示「开通申请」入口；0 表示仅管理员可手动开通"),
    ("云盘", "register_notice_seconds", "注册须知必须读几秒", "int",
     "该时长内「同意」按钮不可点击；0 表示无需等待"),
    ("云盘", "contact_wechat", "联系微信", "text",
     "显示在开通须知页；留空则不显示"),
    ("云盘", "contact_phone", "联系电话", "text",
     "显示在开通须知页；留空则不显示"),
    ("云盘", "contact_email", "联系邮箱", "text",
     "显示在开通须知页；留空则不显示"),
    ("云盘", "register_daily_limit", "每设备每天最多申请几次", "int",
     "按设备与姓名分别计数，防止重复提交申请"),
    ("云盘", "avatar_max_kb", "头像上限 KB", "int", ""),
    ("云盘", "upload_parallel", "同时上传几个文件", "int",
     "前端同时上传的文件数（1~8），数值过大易造成带宽争用"),
    ("云盘", "upload_max_mb", "单文件上传上限 MB", "int",
     "0 表示不限制；超过上限的请求会在写入前拒绝"),
    ("云盘", "user_quota_mb", "每个云账号容量上限 MB", "int",
     "0 表示不限制；按云空间账号目录统计"),
    ("下载", "thumb_source_max_mb", "缩略图原图上限 MB", "int",
     "超过该大小的图片不生成缩略图，列表使用类型图标"),
    ("下载", "thumb_max_px", "缩略图最长边像素", "int", ""),
    ("日志", "log_days", "操作日志保留天数", "int",
     "只清理 YYYYMMDD.log 形式的按天日志；最小 7 天"),
]

PERM_KEYS = ["download", "preview", "zip", "upload", "mkdir", "rename", "delete"]
PERM_LABEL = {"download": "下载", "preview": "预览", "zip": "打包", "upload": "上传",
              "mkdir": "新建目录", "rename": "重命名", "delete": "删除"}

REQUIRE_RESTART = {"port", "host", "workers", "zip_slots", "upload_slots", "per_page",
                   "list_cache_seconds", "request_timeout", "https_port", "certfile",
                   "keyfile", "admin_name", "session_days", "login_max_fails",
                   "login_lock_seconds", "login_lock_max_seconds", "login_rate_per_minute",
                   "login_burst", "login_fail_delay_ms", "login_fail_delay_max_ms",
                   "pw_full", "pw_study", "pw_read", "legacy_password", "admin_password",
                   "full_name", "study_subpath", "upload_max_mb", "user_quota_mb",
                   "thumb_source_max_mb", "thumb_max_px", "log_days"}

# --------------------------------------------------------------------------- #
# config.ini 原地改写（保留注释、空行、顺序）
# --------------------------------------------------------------------------- #
_SECTION_RE = None
_KEY_RE = None


def _compile():
    global _SECTION_RE, _KEY_RE
    import re
    _SECTION_RE = re.compile(r"^\s*\[(.+?)\]\s*$")
    # 值 = 等号后面整段（只去尾部空白）。注意不能按 '#' 切注释：
    # 像 https://.../#/Integrated/index 这种网址里带 # 的值会被切坏、越存越长。
    _KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_.\-]+)(\s*=\s*)(.*)$")


def set_config_values(values):
    """values: {(节, 键): 新值}。返回实际改了几个键。

    只动目标键那一行，注释、顺序、别的行一个字节都不碰。
    """
    if not values:
        return 0
    _compile()
    path = settings.CONFIG_FILE
    try:
        with open(path, encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []

    want = {}
    for (sec, key), val in values.items():
        want.setdefault(sec.strip(), {})[key.strip().lower()] = "" if val is None else str(val)

    changed = 0
    cur = None
    seen = {}
    out = []
    pending_insert = {}      # 节 -> [(键, 值)]  该节里原来没有、需要补的
    for raw in lines:
        m = _SECTION_RE.match(raw)
        if m:
            # 换节：把上一节没写到的键补在这一节的末尾
            if cur and pending_insert.get(cur):
                for k, v in pending_insert.pop(cur):
                    out.append("%s = %s" % (k, v))
                    changed += 1
            cur = m.group(1).strip()
            out.append(raw)
            continue
        if cur is not None and cur in want:
            km = _KEY_RE.match(raw)
            if km:
                key = km.group(2).strip().lower()
                if key in want[cur]:
                    val = want[cur][key]
                    newline = "%s%s%s%s" % (km.group(1), km.group(2), km.group(3), val)
                    if newline != raw:
                        changed += 1
                    out.append(newline)
                    seen.setdefault(cur, set()).add(key)
                    continue
            out.append(raw)
            continue
        out.append(raw)

    if cur and pending_insert.get(cur):
        for k, v in pending_insert.pop(cur):
            out.append("%s = %s" % (k, v))
            changed += 1

    # 补上「这个节里本来是空的、或者根本没有这个键」的情况
    missing = {}
    for sec, kv in want.items():
        for key, val in kv.items():
            if key not in seen.get(sec, set()):
                missing.setdefault(sec, []).append((key, val))

    if missing:
        # 在对应节的最后一个非空行后面插入；找不到这一节就在文件末尾新起一节
        out2 = []
        cur = None
        for raw in out:
            m = _SECTION_RE.match(raw)
            if m:
                if cur and cur in missing:
                    for k, v in missing.pop(cur):
                        out2.append("%s = %s" % (k, v))
                        changed += 1
                cur = m.group(1).strip()
            out2.append(raw)
        if cur and cur in missing:
            for k, v in missing.pop(cur):
                out2.append("%s = %s" % (k, v))
                changed += 1
        for sec, kv in missing.items():
            out2.append("")
            out2.append("[%s]" % sec)
            for k, v in kv:
                out2.append("%s = %s" % (k, v))
                changed += 1
        out = out2

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".config-", suffix=".ini")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(out).rstrip("\n") + "\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return changed


# --------------------------------------------------------------------------- #
# 黑名单
# --------------------------------------------------------------------------- #
def read_blacklist():
    """Return the editable manual blacklist file (not the merged list)."""
    return denylist.read_manual_text()


def write_blacklist(text_value):
    denylist.write_manual_text(text_value)


# --------------------------------------------------------------------------- #
# 表单 → 落盘
# --------------------------------------------------------------------------- #
def apply_form(form):
    """把后台页面提交上来的东西写进文件。返回 (改了配置几项, 提示消息列表)"""
    values = {}
    for sec, key, _label, _kind, _hint in FIELDS:
        name = "cfg|%s|%s" % (sec, key)
        if name not in form:
            continue
        values[(sec, key)] = form[name]
    changed = set_config_values(values)

    msgs = []
    # 规则
    if "rules_present" in form:
        new_rules = []
        idx = []
        for k in form:
            if k.startswith("rule_name_"):
                idx.append(k[len("rule_name_"):])
        idx.sort(key=lambda s: int(s) if s.isdigit() else 0)
        for i in idx:
            name = (form.get("rule_name_" + i) or "").strip()
            pw = (form.get("rule_pw_" + i) or "").strip()
            perms = [p for p in PERM_KEYS if form.get("rperm_%s_%s" % (i, p))]
            root = (form.get("rule_root_" + i) or "").strip()
            note = (form.get("rule_note_" + i) or "").strip()
            if not (name or pw):
                continue
            if not pw:
                msgs.append("存在未填写密码的规则，已跳过")
                continue
            new_rules.append({"name": name, "password": pw,
                              "perms": ",".join(perms), "root": root, "note": note})
        # 内容没变就别写文件：rules.json 一动，全站已登录的人都会被要求重新登录
        def _key(r):
            return (str(r.get("name", "")).strip(),
                    str(r.get("password", "")).strip(),
                    ",".join(sorted(settings.parse_perms(r.get("perms", "")))),
                    str(r.get("root", "")).replace("\\", "/").strip().strip("/"),
                    str(r.get("note", "")).strip())
        old = [_key(r) for r in rules.load()]
        if old == [_key(r) for r in new_rules]:
            msgs.append("规则未发生变化（共 %d 条）" % len(new_rules))
        else:
            try:
                rules.save(new_rules)
                msgs.append("规则已保存（共 %d 条），此前登录的会话需重新登录" % len(new_rules))
            except RuntimeError as exc:
                msgs.append("规则未保存：%s" % exc)

    if "blacklist" in form:
        write_blacklist(form.get("blacklist"))
        msgs.append("黑名单已保存")

    if "blocked_paths" in form:
        try:
            n = blocked.write_text(form.get("blocked_paths"))
            fsutil.invalidate_all()
            zcache.clear()
            msgs.append("屏蔽路径已保存（共 %d 条），列表缓存已刷新" % n)
        except OSError as exc:
            msgs.append("屏蔽路径保存失败：%s" % exc)

    if accounts.load_error():
        msgs.append("警告：%s；账号写入已停止，请检查 data/accounts.json 的格式" % accounts.load_error())
    if rules.load_error():
        msgs.append("警告：%s；规则写入已停止，请检查 data/rules.json 的格式" % rules.load_error())

    return changed, msgs


def restart_notice():
    return ("以下改动需要重启服务才生效：%s"
            % "、".join(sorted({k for (_s, k, _l, _kind, _h) in FIELDS
                              if k in REQUIRE_RESTART})[:6]) + " 等")


def _ago(ts):
    """把登录时间写成“刚刚 / N 分钟前 / N 小时前 / N 天前”。"""
    delta = max(0, int(time.time() - (ts or 0)))
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return "%d 分钟前" % (delta // 60)
    if delta < 86400:
        return "%d 小时前" % (delta // 3600)
    return "%d 天前" % (delta // 86400)


def online_card():
    """后台首屏直接显示当前有效登录会话。"""
    users = sessions.online()
    total_devices = sum(int(u.get("devices") or 0) for u in users)
    if users:
        rows = []
        for u in users:
            name = u.get("name") or ""
            cloud = u.get("kind") == "cloud"
            kind_text = "个人云盘" if cloud else "普通访问"
            rows.append(
                '<div class="ouser"><span class="oav">%s</span>'
                '<div class="nm"><b>%s</b><span>%s · %d 台设备 · %s登录</span></div></div>'
                % (html.escape(name[:1] or "?"), html.escape(name),
                   kind_text, int(u.get("devices") or 0), _ago(u.get("last")))
            )
        body = '<div class="online">%s</div>' % "".join(rows)
    else:
        body = '<div class="empty">当前没有已登记的在线用户</div>'
    return """
<div class="card"><h2>当前在线用户<span class="tip">%(n)d 人 · %(d)d 台设备 · 最近 30 分钟活跃</span></h2>
 <div class="body">
  %(body)s
  <div class="note" style="margin:10px 0 0">按最近 30 分钟内有请求的登录会话统计；刷新本页即可更新。Admin 后台身份不登记会话。</div>
 </div>
</div>
""" % {"n": len(users), "d": total_devices, "body": body}


# --------------------------------------------------------------------------- #
# 白名单 / 黑名单 的增删卡片（各自是独立小表单，提交到 /admin/roster）
# --------------------------------------------------------------------------- #
def _chip(name, src, op, label, title=""):
    return ('<form method="post" action="/admin/roster" class="chip">'
            '<input type="hidden" name="op" value="%s">'
            '<input type="hidden" name="name" value="%s">'
            '<span title="%s">%s%s</span>'
            '<button type="submit" class="x" title="%s">%s</button></form>'
            % (op, html.escape(name, quote=True), html.escape(title or src or "", quote=True),
               html.escape(name), ('<i>%s</i>' % html.escape(src)) if src else "",
               html.escape(title or label, quote=True), label))


def _blacklist_names():
    return [name for name, _src in denylist.names()]


CHIP_INITIAL_LIMIT = 48   # 首屏最多渲染多少个小圆片，其余放入惰性 template，避免上千个表单拖慢页面


def _disabled_files():
    """白名单目录里以 .disabled 结尾、已被程序忽略的名单文件。"""
    from . import roster
    d = roster.dir_path()
    try:
        return sorted(fn for fn in os.listdir(d)
                      if fn.lower().endswith(".disabled") and not fn.startswith("."))
    except OSError:
        return []


def _chips_box(box_id, chips, count, empty_text):
    """名字小圆片区域：人少时全部渲染；人多时只渲染前一段，其余点击时再插入。"""
    if not count:
        return '<div class="chips">%s</div>' % empty_text
    if count <= CHIP_INITIAL_LIMIT:
        return '<div class="chips">%s</div>' % "".join(chips)
    visible = "".join(chips[:CHIP_INITIAL_LIMIT])
    rest = "".join(chips[CHIP_INITIAL_LIMIT:])
    return ('<div class="chips" id="%s">%s</div>'
            '<template id="%sRest">%s</template>'
            '<button type="button" class="more" data-box="%s"'
            ' onclick="expandChips(this)">显示全部（%d 个，先显示前 %d 个）</button>'
            % (box_id, visible, box_id, rest, box_id, count, CHIP_INITIAL_LIMIT))


def roster_cards():
    """白名单 / 黑名单 两张卡片（网页上直接加人、撤人）"""
    from . import roster
    roster.ensure_dir()
    denylist.ensure_dir()
    wl = roster.names()
    bl = denylist.names()
    wl_chips = [_chip(n, s, "del_white", "移出", "从手动名单里移出") for n, s in wl]
    bl_chips = [_chip(n, s, "del_black", "解除", "只删除 manual.txt 中的记录") for n, s in bl]
    wl_box = _chips_box("wlChips", wl_chips, len(wl),
                        '<div class="empty">名单当前为空（空名单表示不限制访问）</div>')
    bl_box = _chips_box("blChips", bl_chips, len(bl),
                        '<div class="empty">黑名单当前为空</div>')
    disabled = _disabled_files()
    disabled_html = ""
    if disabled:
        disabled_html = ('<div class="note disabled-note">已停用名单文件：%s（程序已忽略）</div>'
                         % "、".join('<code>%s</code>' % html.escape(fn) for fn in disabled))
    return """
<div class="card"><h2>白名单<span class="tip">当前 %(wlc)d 个姓名 · 修改即时生效</span></h2>
 <div class="body">
  <div class="note">白名单目录：<b>%(wldir)s</b>（支持 .txt / .csv / .xlsx / .xlsm / .docx 格式，
   姓名之间以空格、换行或逗号分隔，Excel 横向一行或纵向一列均可解析）。
   名单非空时仅名单内人员可访问，其他人员即使密码正确亦无法进入；管理身份 <b>%(admin)s</b> 始终放行。
   空白名单表示不作限制。</div>
  %(dis)s
  %(wlbox)s
  <form method="post" action="/admin/roster" class="mini">
   <input type="hidden" name="op" value="add_white">
   <input type="text" name="name" placeholder="要加入白名单的姓名" maxlength="32">
   <button type="submit" class="btn">添加</button>
  </form>
  <div class="note" style="margin-top:8px">此处增删仅作用于「%(man)s」文件；Excel/Word 名单中的姓名请修改原文件。
   临时停用某个名单文件：在文件名末尾加 <code>.disabled</code>（如 <code>roster-2018.xlsx.disabled</code>），程序会立即忽略；恢复时去掉这个后缀即可。</div>
 </div>
</div>
<div class="card"><h2>黑名单<span class="tip">当前 %(blc)d 个姓名 · 修改即时生效</span></h2>
 <div class="body">
  <div class="note">黑名单目录：<b>%(bldir)s</b>（支持 .txt / .csv / .xlsx / .xlsm / .docx 格式，多个文件自动合并；
   空白名单表示不拦截任何人）。列入黑名单的姓名（无论是否在白名单内）：一律禁止访问，不受密码校验结果影响。</div>
  %(blbox)s
  <form method="post" action="/admin/roster" class="mini">
   <input type="hidden" name="op" value="add_black">
   <input type="text" name="name" placeholder="要加入黑名单的姓名" maxlength="32">
   <button type="submit" class="btn red">加入黑名单</button>
  </form>
  <div class="note" style="margin-top:8px">此处增删仅作用于「%(bman)s」文件；Excel/Word 名单中的姓名请修改原文件。</div>
 </div>
</div>
""" % {"wlc": len(wl), "blc": len(bl), "wlbox": wl_box, "blbox": bl_box, "dis": disabled_html,
       "wldir": html.escape(roster.dir_path()), "bldir": html.escape(denylist.dir_path()),
       "man": html.escape(roster.MANUAL_FILE), "bman": html.escape(denylist.MANUAL_FILE),
       "admin": html.escape(settings.ADMIN_NAME)}


def do_roster(op, name):
    """处理 /admin/roster 的四种操作，返回给用户看的提示"""
    from . import roster
    name = (name or "").strip()
    if not name:
        return "姓名不能为空"
    if op == "add_white":
        ok, msg = roster.add_manual(name)
        return msg if ok else msg
    if op == "del_white":
        removed, n = roster.remove_manual(name)
        if removed:
            return "已从白名单移出：%s" % name
        return ("「%s」不在手动名单文件中（可能记录于 Excel/Word 名单）；"
                "请修改原文件，或将其加入黑名单" % name)
    if op == "add_black":
        ok, msg = denylist.add_manual(name)
        return msg
    if op == "del_black":
        removed, n = denylist.remove_manual(name)
        if removed:
            return "已从黑名单移除：%s" % name
        if denylist.is_blocked(name):
            return ("「%s」来自 Excel/Word 等外部名单文件，不能在这里删除；"
                    "请修改原文件。" % name)
        return "黑名单中不存在「%s」" % name
    return "无法识别的操作"


def accounts_card():
    """多用户云空间：待审申请 + 已通过（带验证码）+ 已开通账号"""
    from . import accounts
    apps = accounts.applications()
    passed = accounts.approved()
    users = accounts.users()
    app_html = ""
    if apps:
        for a in apps:
            remark = a.get("remark") or ""
            remark_line = ('<div class="meta" style="white-space:pre-wrap;margin-top:4px">'
                           '备注：%s</div>' % html.escape(remark)) if remark else ""
            app_html += ('<div class="acct"><span class="nm">%s</span>'
                         '<span class="meta">申请于 %s</span>%s'
                         '<form method="post" action="/admin/account" style="margin:0">'
                         '<input type="hidden" name="op" value="approve">'
                         '<input type="hidden" name="id" value="%s">'
                         '<button class="btn" type="submit">通过</button></form>'
                         '<form method="post" action="/admin/account" style="margin:0">'
                         '<input type="hidden" name="op" value="reject">'
                         '<input type="hidden" name="id" value="%s">'
                         '<button class="btn gray" type="submit">拒绝</button></form></div>'
                         % (html.escape(a["name"]), html.escape(a["created"]), remark_line,
                            html.escape(a["id"]), html.escape(a["id"])))
    else:
        app_html = '<div class="empty">暂无待审核申请</div>'
    pass_html = ""
    for a in passed:
        remark = a.get("remark") or ""
        remark_line = ('<div class="meta" style="white-space:pre-wrap;margin-top:4px">'
                       '备注：%s</div>' % html.escape(remark)) if remark else ""
        pass_html += ('<div class="acct"><span class="nm">%s</span>'
                      '<span class="meta">通过于 %s · 验证码 '
                      '<code style="font-size:15px;font-weight:700;letter-spacing:2px;'
                      'color:#0f6fbd;background:#eef6fc;padding:1px 7px;border-radius:5px">%s</code>'
                      '</span>%s'
                      '<form method="post" action="/admin/account" style="margin:0">'
                      '<input type="hidden" name="op" value="regen">'
                      '<input type="hidden" name="id" value="%s">'
                      '<button class="btn gray" type="submit">换验证码</button></form>'
                      '<form method="post" action="/admin/account" style="margin:0">'
                      '<input type="hidden" name="op" value="reject">'
                      '<input type="hidden" name="id" value="%s">'
                      '<button class="btn gray" type="submit">撤回</button></form></div>'
                      % (html.escape(a["name"]), html.escape(a["created"]),
                         html.escape(a["code"]), remark_line,
                         html.escape(a["id"]), html.escape(a["id"])))
    if not pass_html:
        pass_html = '<div class="empty">暂无等待申请人设置密码的申请</div>'
    user_html = ""
    for u in users:
        user_html += ('<div class="acct"><span class="nm">%s</span>'
                      '<span class="meta">开通于 %s%s</span>'
                      '<form method="post" action="/admin/account" style="margin:0">'
                      '<input type="hidden" name="op" value="del_user">'
                      '<input type="hidden" name="name" value="%s">'
                      '<button class="btn gray" type="submit" '
                      'onclick="return confirm(\'确认彻底删除「%s」？将同时删除其云空间目录中的全部文件、头像和开通记录，且不可恢复。\')">彻底删除</button>'
                      '</form></div>'
                      % (html.escape(u["name"]), html.escape(u["created"]),
                         " · 有自定义头像" if u["avatar"] else "",
                         html.escape(u["name"]), html.escape(u["name"])))
    if not user_html:
        user_html = '<div class="empty">暂无已开通的云空间账号</div>'
    root = html.escape(accounts.cloud_root())
    return """
<div class="card"><h2>云空间账号<span class="tip">通过 / 更换验证码 / 撤回 / 彻底删除 即时生效</span></h2>
 <div class="body">
  <div class="note">每位用户拥有一个独立目录，位于 <b>%(root)s</b> 之下，相互不可见。
   密码仅保存哈希摘要，管理端无法查看明文；权限固定为「全部权限」；
   用户可自行修改头像，未修改者使用默认头像。
   <br>开通流程：申请人填写姓名 → 管理员点击「通过」（系统生成 4 位验证码，<b>须由管理员告知申请人</b>）
   → 申请人凭「姓名 + 验证码」自行设置密码，账号方可启用。设置密码前，该姓名不可用于登录。
   <br><b>「彻底删除」</b>会同时清除该账号、开通记录、头像及其云空间目录中的全部文件，操作不可恢复。</div>
  <div class="sub">待审核申请（%(ac)d 条）</div>
  %(apps)s
  <div class="sub">已通过、等待申请人设置密码（%(pc)d 条）</div>
  %(pass)s
  <div class="sub">已开通（%(uc)d 个）</div>
  %(users)s
  <form method="post" action="/admin/account" class="mini" style="margin-top:10px">
   <input type="hidden" name="op" value="add_user">
   <input type="text" name="name" placeholder="姓名" maxlength="24">
   <input type="text" name="pw" placeholder="初始密码（至少 8 位）" maxlength="64">
   <br><span class="hint">密码区分大小写；请把初始密码线下告知本人。</span>
   <button type="submit" class="btn">手动开通</button>
  </form>
 </div>
</div>
""" % {"root": root, "ac": len(apps), "pc": len(passed), "uc": len(users),
       "apps": app_html, "pass": pass_html, "users": user_html}


def do_account(op, form):
    """处理 /admin/account 上的操作，返回提示文字"""
    from . import accounts
    op = (op or "").strip()
    if op == "approve":
        ok, msg = accounts.approve((form.get("id") or "").strip())
        return msg
    if op == "reject":
        ok, msg = accounts.reject((form.get("id") or "").strip())
        return msg
    if op == "regen":
        ok, msg = accounts.regenerate((form.get("id") or "").strip())
        return msg
    if op == "del_user":
        ok, msg = accounts.delete_user((form.get("name") or "").strip())
        return msg
    if op == "add_user":
        ok, msg = accounts.create((form.get("name") or "").strip(),
                                  (form.get("pw") or "").strip())
        return msg
    return "无法识别的操作"


def _preflight_compile():
    """重启前先做一次语法检查：新代码有语法错误就不动正在跑的服务。"""
    import py_compile
    targets = [os.path.join(settings.PROJECT_DIR, "app.py")]
    srv = os.path.join(settings.PROJECT_DIR, "server")
    for name in os.listdir(srv):
        if name.endswith(".py"):
            targets.append(os.path.join(srv, name))
    for path in targets:
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:  # noqa: BLE001
            try:
                with open(os.path.join(settings.PROJECT_DIR, "runtime", "logs", "_restart_preflight.txt"),
                          "a", encoding="utf-8") as fh:
                    fh.write("%s  %s\n" % (path, exc))
            except OSError:
                pass
            return False
    return True


def restart_service():
    """重启服务：先语法检查，再由分离的小守护进程等端口释放、拉起 app.py，
    并用 /healthz 轮询确认真的起来了；失败会写日志，不会假装成功。"""
    if not _preflight_compile():
        return False
    project = settings.PROJECT_DIR
    try:
        port = int((settings._read_ini(settings.CONFIG_FILE).get("port") or settings.DEFAULT_PORT))
    except Exception:  # noqa: BLE001
        port = settings.DEFAULT_PORT
    logdir = os.path.join(project, "runtime", "logs")
    try:
        os.makedirs(logdir, exist_ok=True)
    except OSError:
        pass
    out_path = os.path.join(logdir, "_stdout.log")
    err_path = os.path.join(logdir, "_stderr.log")
    restart_log = os.path.join(logdir, "_restart.log")
    code = (
        "import os, socket, subprocess, sys, time, urllib.request\n"
        "project = %r\n"
        "port = %d\n"
        "python = sys.executable\n"
        "out_path = %r\n"
        "err_path = %r\n"
        "restart_log = %r\n"
        "flags = 0x00000008 | 0x00000200 | 0x08000000\n"
        "def note(msg):\n"
        "    try:\n"
        "        with open(restart_log, 'a', encoding='utf-8') as fh:\n"
        "            fh.write(time.strftime('%%Y-%%m-%%d %%H:%%M:%%S ') + msg + '\\n')\n"
        "    except OSError:\n"
        "        pass\n"
        "def free():\n"
        "    try:\n"
        "        s = socket.create_connection(('127.0.0.1', port), timeout=0.4)\n"
        "        s.close()\n"
        "        return False\n"
        "    except OSError:\n"
        "        return True\n"
        "def healthy():\n"
        "    try:\n"
        "        req = urllib.request.Request('http://127.0.0.1:%%d/healthz' %% port)\n"
        "        with urllib.request.urlopen(req, timeout=2) as r:\n"
        "            body = r.read(200).decode('utf-8', 'replace')\n"
        "        return r.status == 200 and 'ok' in body.lower()\n"
        "    except Exception:\n"
        "        return False\n"
        "for _ in range(80):\n"
        "    if free():\n"
        "        break\n"
        "    time.sleep(0.25)\n"
        "else:\n"
        "    note('端口 %%d 一直没释放，放弃重启' %% port)\n"
        "    raise SystemExit(1)\n"
        "time.sleep(0.5)\n"
        "for attempt in range(1, 4):\n"
        "    out = open(out_path, 'ab')\n"
        "    err = open(err_path, 'ab')\n"
        "    p = subprocess.Popen([python, 'app.py'], cwd=project, creationflags=flags,\n"
        "                         stdout=out, stderr=err, close_fds=True)\n"
        "    out.close(); err.close()\n"
        "    note('第 %%d 次拉取 app.py，pid=%%s' %% (attempt, p.pid))\n"
        "    for _ in range(30):\n"
        "        time.sleep(1)\n"
        "        if healthy():\n"
        "            note('健康检查通过，服务已在端口 %%d' %% port)\n"
        "            raise SystemExit(0)\n"
        "        if p.poll() is not None:\n"
        "            note('进程提前退出，returncode=%%s' %% p.returncode)\n"
        "            break\n"
        "    if p.poll() is None:\n"
        "        p.terminate()\n"
        "        try:\n"
        "            p.wait(3)\n"
        "        except Exception:\n"
        "            p.kill()\n"
        "    note('第 %%d 次启动未通过健康检查' %% attempt)\n"
        "    time.sleep(1.5)\n"
        "note('重启失败：请手动运行 launcher.bat，并查看 runtime/logs/_stderr.log')\n"
        "raise SystemExit(2)\n"
    ) % (project, port, out_path, err_path, restart_log)
    try:
        subprocess.Popen([sys.executable, "-c", code], cwd=project,
                         creationflags=0x00000008 | 0x00000200 | 0x08000000,
                         close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        return False
    return True


# --------------------------------------------------------------------------- #
# 页面
# --------------------------------------------------------------------------- #
CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:#eef2f6;color:#26323d}
header{background:linear-gradient(135deg,#0f6fbd,#0b5796);color:#fff;padding:13px 16px;
  display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:9;
  box-shadow:0 2px 10px rgba(15,60,100,.18)}
header h1{margin:0;font-size:16px;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
header a,header button{background:rgba(255,255,255,.16);border:0;color:#fff;border-radius:8px;
  padding:6px 12px;font-size:13px;cursor:pointer;text-decoration:none}
.wrap{max-width:900px;margin:0 auto;padding:14px 12px 40px}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(20,40,70,.07);
  margin:0 0 14px;overflow:hidden}
.card>h2{margin:0;padding:12px 16px;font-size:14.5px;background:#f7fafd;border-bottom:1px solid #e8eef4;
  color:#0f6fbd}
.card>h2 .tip{float:right;font-weight:400;color:#8d9aa6;font-size:12px}
.body{padding:12px 16px}
.row{display:flex;gap:10px;align-items:center;padding:6px 0;flex-wrap:wrap;border-bottom:1px dashed #eef2f6}
.row:last-child{border-bottom:0}
.row label{flex:0 0 150px;color:#4a5a68;font-size:13px}
.row input[type=text],.row input[type=password]{flex:1;min-width:150px;padding:7px 10px;border:1px solid #d7e0e8;
  border-radius:8px;font-size:13.5px;background:#fff}
.row .hint{flex:1 0 100%;color:#93a1ae;font-size:12px;padding-left:160px;margin-top:-2px}
.rules .r{border:1px solid #e6ecf1;border-radius:10px;padding:10px;margin-bottom:10px;background:#fbfdff}
.rules .r .line{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.rules input[type=text],.rules input[type=password]{padding:6px 9px;border:1px solid #d7e0e8;border-radius:7px;
  font-size:13px;background:#fff;min-width:0}
.rules .nm{flex:1 1 130px}.rules .pw{flex:1 1 150px}.rules .rt{flex:1 1 150px}
.rules .perms{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px;font-size:12.5px;color:#4a5a68}
.rules .perms label{display:inline-flex;align-items:center;gap:4px;flex:0 0 auto}
.rules .del{background:#fdecec;color:#c62828;border:1px solid #f6c7c7;border-radius:7px;
  padding:5px 10px;font-size:12.5px;cursor:pointer}
.acts{display:flex;gap:10px;flex-wrap:wrap;padding-top:6px}
.btn{border:0;border-radius:9px;padding:9px 18px;font-size:13.5px;cursor:pointer;background:#0f6fbd;color:#fff}
.btn.gray{background:#e7eef5;color:#3d5162}
.btn.red{background:#c62828}
.flash{margin:0 0 12px;padding:10px 14px;border-radius:10px;background:#e8f5e9;color:#1b5e20;font-size:13px}
.flash.warn{background:#fff8e1;color:#7a5c00}
textarea{width:100%;min-height:120px;padding:9px 11px;border:1px solid #d7e0e8;border-radius:9px;
  font:13px/1.55 ui-monospace,Consolas,monospace;background:#fff}
.foot{padding:16px 6px;text-align:center;color:#8d9aa6;font-size:12px}
.note{color:#5d6c7a;font-size:12.5px;line-height:1.7;margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}
.chip{display:inline-flex;align-items:center;gap:6px;background:#f2f7fc;border:1px solid #dbe7f2;
  border-radius:999px;padding:3px 6px 3px 12px;font-size:13px;color:#20313f;margin:0}
.chip i{font-style:normal;color:#93a1ae;font-size:11.5px;margin-left:4px}
.chip .x{background:#fff;border:1px solid #e0e8f0;color:#c62828;border-radius:999px;
  padding:2px 9px;font-size:12px;cursor:pointer}
.mini{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.mini input[type=text]{flex:1 1 200px;min-width:140px;padding:8px 10px;border:1px solid #d7e0e8;
  border-radius:8px;font-size:13.5px}
.empty{color:#93a1ae;font-size:12.5px}
.online{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}
.ouser{display:flex;align-items:center;gap:9px;background:#fbfdff;border:1px solid #e6eef5;
  border-radius:10px;padding:8px 10px;min-width:0}
.oav{width:30px;height:30px;border-radius:50%;background:#e8f2fb;color:#0f6fbd;flex:0 0 30px;
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.ouser .nm{min-width:0;flex:1}
.ouser b{display:block;font-size:13.5px;color:#1b2b3a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ouser span{display:block;margin-top:2px;font-size:11.5px;color:#8d9aa6}
.disabled-note code{font-size:11.5px;background:#f2f5f8;padding:1px 5px;border-radius:4px;color:#5d6c7a}
.chips.fold{max-height:104px;overflow:hidden;position:relative;padding-bottom:18px}
.chips.fold:after{content:"";position:absolute;left:0;right:0;bottom:0;height:34px;
  background:linear-gradient(rgba(255,255,255,0),#fff)}
.chips.fold.open{max-height:none;overflow:visible;padding-bottom:0}
.chips.fold.open:after{display:none}
.more{display:inline-block;margin:-4px 0 12px;background:#eef4fa;border:1px solid #d7e0e8;
  border-radius:8px;padding:5px 12px;font-size:12.5px;color:#2b5f8c;cursor:pointer}
.more:hover{background:#e3edf7}
.acct{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:7px 0;border-bottom:1px dashed #eef2f6}
.acct .nm{font-size:13.5px;color:#20313f;min-width:90px}
.acct .meta{color:#93a1ae;font-size:12px;flex:1}
.acct .btn{padding:5px 12px;font-size:12.5px}
.sub{color:#8d9aa6;font-size:12px;margin:8px 0 4px}
@media (max-width:640px){
  .row label{flex:1 0 100%}.row .hint{padding-left:0}
  .rules .nm,.rules .pw,.rules .rt{flex:1 1 100%}
}
"""


def _field_html(sec, key, label, kind, hint):
    val = settings.raw(key) if key in settings.DEFAULTS else ""
    name = html.escape("cfg|%s|%s" % (sec, key), quote=True)
    if kind == "pw":
        inp = ('<input type="password" name="%s" value="%s" autocomplete="new-password">'
               % (name, html.escape(val, quote=True)))
    else:
        inp = ('<input type="text" name="%s" value="%s">'
               % (name, html.escape(val, quote=True)))
    h = ('<div class="hint">%s</div>' % html.escape(hint)) if hint else ""
    return ('<div class="row"><label>%s</label>%s%s</div>'
            % (html.escape(label), inp, h))


def _rule_html(i, r):
    perms = set(r.get("_perms_set") or [])
    boxes = "".join(
        '<label><input type="checkbox" name="rperm_%d_%s"%s>%s</label>'
        % (i, p, " checked" if p in perms else "", PERM_LABEL[p])
        for p in PERM_KEYS)
    return ('<div class="r">'
            '<div class="line">'
            '<input class="nm" type="text" name="rule_name_%d" placeholder="姓名（* = 全部访问者，!姓名 = 排除该访问者）" value="%s">'
            '<input class="pw" type="password" autocomplete="off" name="rule_pw_%d" placeholder="密码" value="%s">'
            '<input class="rt" type="text" name="rule_root_%d" placeholder="目录（空 = 全部；如 文件/学习资料）" value="%s">'
            '<button type="button" class="del" onclick="this.closest(\'.r\').remove()">删除</button>'
            '</div>'
            '<div class="line" style="margin-top:8px">'
            '<input type="text" style="flex:1" name="rule_note_%d" placeholder="备注（仅管理员可见）" value="%s">'
            '</div>'
            '<div class="perms">%s</div>'
            '</div>'
            % (i, html.escape(r.get("name", ""), quote=True),
               i, html.escape(r.get("password", ""), quote=True),
               i, html.escape(r.get("root", ""), quote=True),
               i, html.escape(r.get("note", ""), quote=True), boxes))


def build_admin_page(grant=None, saved=0, warn=""):
    rlist = rules.load()
    groups = []
    seen = []
    for sec, key, label, kind, hint in FIELDS:
        if sec not in seen:
            seen.append(sec)
            groups.append((sec, []))
        groups[-1][1].append((sec, key, label, kind, hint))
    cards = []
    for sec, items in groups:
        tip = ""
        if any(k in REQUIRE_RESTART for (_s, k, _l, _kind, _h) in items):
            tip = '<span class="tip">修改后需重启服务</span>'
        body = "".join(_field_html(*it) for it in items)
        cards.append('<div class="card"><h2>%s%s</h2><div class="body">%s</div></div>'
                     % (html.escape(sec), tip, body))

    rules_block = "".join(_rule_html(i, r) for i, r in enumerate(rlist))
    flash = ""
    if saved:
        flash = '<div class="flash">已保存（共修改 %d 项配置）。%s</div>' % (saved, html.escape(warn))
    elif warn:
        flash = '<div class="flash warn">%s</div>' % html.escape(warn)

    who = html.escape((grant or {}).get("name") or "")
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理控制台 · 文件服务平台</title><style>%(css)s</style></head>
<body>
<header>
  <h1>管理控制台 · 文件服务平台</h1>
  <a href="/browse">返回文件列表</a>
  <button type="button" onclick="doRestart(this)">重启服务</button>
  <a href="/logout">注销</a>
</header>
<div class="wrap">
%(flash)s
%(onlinecard)s
%(wlcard)s
%(accard)s
<div class="card"><h2>登录规则<span class="tip">修改后于下次登录生效，无需重启</span></h2>
 <div class="body rules">
  <div style="color:#8d9aa6;font-size:12.5px;margin:-4px 0 10px">
   按自上而下顺序匹配，首条命中即生效。姓名填写 <b>*</b> 表示全部访问者，填写 <b>!张三</b> 表示排除该访问者。
   目录填写相对存储根的路径（如 <b>文件/学习资料</b>），留空表示全部目录。
  </div>
  <div id="rulesBox">%(rules)s</div>
  <button type="button" class="btn gray" onclick="addRule()">+ 新增规则</button>
 </div>
</div>

<form method="post" action="/admin/save" id="mainForm">
 <input type="hidden" name="rules_present" value="1">
 <div id="rulesHolder" style="display:none"></div>
%(cards)s
<div class="card"><h2>屏蔽路径（文本直接编辑）<span class="tip">保存后立即生效，对所有姓名、密码、权限一律生效</span></h2>
 <div class="body">
  <div class="hint">一行一个路径。相对路径按存储根解析（如 <b>Tools/Script</b>），也可以写绝对路径。屏蔽文件夹会连同其下所有内容一起从列表、搜索、下载、预览、打包中移除；<b>#</b> 开头为注释。</div>
  <textarea name="blocked_paths" spellcheck="false">%(blkpaths)s</textarea>
 </div>
</div>
<div class="card"><h2>黑名单手动文件（文本直接编辑）<span class="tip">点击「保存全部」后生效；上方卡片中的修改即时生效</span></h2>
 <div class="body">
  <div class="hint">这里只编辑 <b>data/lists/blacklist/manual.txt</b>。同目录下的 .csv / .xlsx / .xlsm / .docx 会被自动合并，但不会在这里显示或被覆盖。</div>
  <textarea name="blacklist" spellcheck="false">%(blk)s</textarea>
 </div>
</div>
<div class="acts" style="padding:0 0 20px">
 <button class="btn" type="submit">保存全部</button>
 <button class="btn gray" type="button" onclick="doRestart(this)">保存后重启</button>
</div>
</form>
<div class="foot">当前身份：%(who)s · 规则文件 rules.json · 配置文件 config.ini</div>
</div>
<script>
var seq = %(seq)d;
function addRule(){
  var box = document.getElementById('rulesBox');
  var html = '<div class="r"><div class="line">'
    + '<input class="nm" type="text" name="rule_name_' + seq + '" placeholder="姓名（* = 全部访问者，!姓名 = 排除该访问者）">'
    + '<input class="pw" type="text" name="rule_pw_' + seq + '" placeholder="密码">'
    + '<input class="rt" type="text" name="rule_root_' + seq + '" placeholder="目录（留空 = 全部）">'
    + '<button type="button" class="del" onclick="this.closest(\\'.r\\').remove()">删除</button>'
    + '</div><div class="line" style="margin-top:8px">'
    + '<input type="text" style="flex:1" name="rule_note_' + seq + '" placeholder="备注">'
    + '</div><div class="perms">'
    + ['download','preview','zip','upload','mkdir','rename','delete'].map(function(p){
        var label = {download:'下载',preview:'预览',zip:'打包',upload:'上传',mkdir:'新建目录',rename:'重命名',delete:'删除'}[p];
        return '<label><input type="checkbox" name="rperm_' + seq + '_' + p + '">' + label + '</label>';
      }).join('')
    + '</div></div>';
  box.insertAdjacentHTML('beforeend', html);
  seq++;
}
function collectRules(){
  var holder = document.getElementById('rulesHolder');
  holder.innerHTML = document.getElementById('rulesBox').innerHTML;
  document.getElementById('rulesBox').querySelectorAll('input').forEach(function(el){
    el.disabled = true;
  });
}
function expandChips(btn){
  var id = btn.getAttribute('data-box');
  var box = document.getElementById(id);
  var tpl = document.getElementById(id + 'Rest');
  if (!box) return;
  if (tpl) {
    box.insertAdjacentHTML('beforeend', tpl.innerHTML);
    tpl.remove();
  }
  btn.remove();
}
document.getElementById('mainForm').addEventListener('submit', collectRules);
function doRestart(btn){
  var f = document.getElementById('mainForm');
  collectRules();
  if (!confirm('确认保存并重启？正在上传或下载的任务将中断。')) return;
  btn.disabled = true; btn.textContent = '正在重启服务…';
  var data = new FormData(f);
  data.set('do_restart', '1');
  fetch('/admin/save', {method:'POST', body:data}).then(function(r){ return r.json(); }).then(function(j){
    if (j && j.ok === false) {
      alert('重启前检查未通过，服务没有停：' + ((j.msgs || []).join('；') || '请查看 runtime/logs 目录'));
      btn.disabled = false; btn.textContent = '保存并重启';
      return;
    }
    setTimeout(function(){
      var t0 = Date.now();
      (function poll(){
        fetch('/healthz', {cache:'no-store'}).then(function(r){
          return r.ok ? r.json() : null;
        }).then(function(j){
          if (j && j.ok) { alert('服务已重启'); location.reload(); return; }
          if (Date.now() - t0 < 60000) setTimeout(poll, 800);
          else { alert('60 秒内没有等到服务恢复，请手动运行 launcher.bat 并查看 runtime/logs/_restart.log'); btn.disabled = false; btn.textContent = '保存并重启'; }
        }).catch(function(){
          if (Date.now() - t0 < 60000) setTimeout(poll, 800);
          else { alert('60 秒内没有等到服务恢复，请手动运行 launcher.bat 并查看 runtime/logs/_restart.log'); btn.disabled = false; btn.textContent = '保存并重启'; }
        });
      })();
    }, 1500);
  }).catch(function(){
    btn.disabled = false; btn.textContent = '保存并重启';
    alert('保存请求失败，服务未重启');
  });
  return false;
}
</script>
</body></html>""" % {
        "css": CSS,
        "flash": flash,
        "rules": rules_block,
        "cards": "\n".join(cards),
        "blk": html.escape(read_blacklist()),
        "blkpaths": html.escape(blocked.read_text()),
        "wlcard": roster_cards(),
        "onlinecard": online_card(),
        "accard": accounts_card(),
        "who": who,
        "seq": len(rlist),
    }

