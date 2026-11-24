# -*- coding: utf-8 -*-
"""HTML 页面：登录页 / 文件列表 / 错误页，以及列表渲染与分页。"""

import html
import os
import re
import shutil
import urllib.parse

from .icons import get_sprite, icon_for, EXT_ICON
from .fsutil import human_size, fmt_time, ext_of, preview_kind, q, scan_entries, search_entries
from . import settings
from .settings import (Config, PER_PAGE, ROLE_FULL, ROLE_STUDY, ROLE_READ,
                       role_perms, role_root)


# --------------------------------------------------------------------------- #
# 页脚：备案号（登录页 / 列表页 / 错误页 底部都显示）
# 具体号码在 server/settings.py 里改。
# --------------------------------------------------------------------------- #
FOOTER_CSS = """
.foot{margin:26px 6px 26px;padding-top:13px;border-top:1px solid #e6ecf1;
  font-size:12px;line-height:2;color:#8d9aa6;text-align:center;word-break:break-all}
.foot a{color:#8d9aa6;text-decoration:none;padding:0 6px;display:inline-block}
.foot a:hover{color:#0f6fbd;text-decoration:underline}
.foot .badge{width:14px;height:14px;vertical-align:-2.5px;margin-right:4px}
@media (max-width:640px){.foot{font-size:11.5px;line-height:1.9;margin:20px 4px}}
"""

# 备案号前面的徽记：优先用 assets/images/guohui.png（真国徽图，换成别的图直接覆盖那个文件即可）；
# 那个文件被删掉时退回一个简笔 svg，不至于空一块。
_BADGE_SVG = ('<svg class="badge" viewBox="0 0 24 24" fill="none">'
              '<circle cx="12" cy="12" r="9.2" fill="#d81e06" stroke="#f8d569" stroke-width="1.6"/>'
              '<path d="m12 4.6 1.35 2.9 3.1.35-2.3 2.1.6 3.1-2.8-1.6-2.9 1.6.6-3.1-2.3-2.1-3.1-.35z" '
              'fill="#f8d569"/>'
              '<path d="M7.6 15.4h8.8v1.6H7.6zM9.2 13.4h5.6v1.4H9.2z" fill="#f8d569"/></svg>')


def _badge_html():
    """assets/images/guohui.png 存在就用真国徽，否则用内置简笔徽记"""
    from .icons import IMG_DIR
    if os.path.isfile(os.path.join(IMG_DIR, "guohui.png")):
        return '<img class="badge" src="/img/guohui.png" alt="" width="14" height="14">'
    return _BADGE_SVG


def build_footer():
    if not getattr(settings, "SHOW_FOOTER", True):
        return ""
    site = html.escape(getattr(settings, "SITE_CODE", "") or "")
    icp = html.escape(getattr(settings, "ICP_NO", "") or "")
    icp_url = html.escape(getattr(settings, "ICP_URL", "") or "")
    pol = html.escape(getattr(settings, "POLICE_NO", "") or "")
    pol_url = html.escape(getattr(settings, "POLICE_URL", "") or "")
    parts = []
    if site:
        parts.append('<span>网站标识码 %s</span>' % site)
    if icp:
        parts.append('<a href="%s" target="_blank" rel="noopener">%s</a>' % (icp_url, icp))
    if pol:
        parts.append('<a href="%s" target="_blank" rel="noopener">%s%s</a>' % (pol_url, _badge_html(), pol))
    if not parts:
        return ""
    return '<footer class="foot">%s</footer>' % "".join(parts)


def _contact_values():
    """config.ini 里配置的开发者联系方式；留空的项直接跳过。"""
    out = []
    for label, key in (("微信", "contact_wechat"), ("电话", "contact_phone"),
                       ("邮箱", "contact_email")):
        val = (settings.raw(key) or "").strip()
        if val:
            out.append((label, val))
    return out


def _login_contact_html():
    rows = _contact_values()
    if not rows:
        return ""
    return ('<div class="cTitle">开发者联系方式</div>' +
            "".join('<div class="cRow"><span>%s</span><b>%s</b></div>'
                    % (html.escape(label), html.escape(val)) for label, val in rows))


ERROR_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>文件服务平台</title>
<style>
*{box-sizing:border-box}
html,body{height:100%;margin:0}
html{background:#f2f5f8;overscroll-behavior-y:contain}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:#f2f5f8;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px}
.card{background:#fff;border-radius:16px;padding:34px 28px;max-width:380px;width:100%;text-align:center;
  box-shadow:0 10px 30px rgba(12,45,70,.08)}
.ic{width:52px;height:52px;border-radius:14px;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;
  background:#eef5fb;color:#3b82b8}
.ic svg{width:26px;height:26px}
h2{margin:0 0 8px;font-size:17px;color:#12293f}
p{margin:0 0 22px;font-size:13.5px;color:#7b8a99;line-height:1.6;word-break:break-word}
a.btn{display:inline-block;padding:11px 22px;border-radius:10px;color:#fff;text-decoration:none;font-size:14px;
  background:linear-gradient(135deg,#0f6fbd,#0e8fae)}
@media (max-width:560px), (max-height:700px){
  .fpLang{position:static !important;right:auto !important;bottom:auto !important;
    margin:10px auto 0 !important;align-self:center}
}
</style>
</head>
<body>
<div class="card">
  <div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5"/><circle cx="12" cy="16.6" r=".9" fill="currentColor"/>
  </svg></div>
  <h2>@TITLE@</h2>
  <p>@MSG@</p>
  <a class="btn" href="/browse">返回根目录</a>
</div>
</body>
</html>
"""


def build_error(title, msg):
    return (ERROR_PAGE
            .replace("@TITLE@", html.escape(title))
            .replace("@MSG@", html.escape(msg))
            .replace("@FOOTER@", build_footer()))


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f6fbd">
<title>文件服务平台</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;min-height:100%}
html{
  background-color:#0b4f86;
  background-image:linear-gradient(160deg,#0b4f86 0%,#1279b8 45%,#0d95a6 100%);
  background-repeat:no-repeat;background-size:cover;background-attachment:fixed;
  overscroll-behavior-y:contain;
}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(160deg,#0b4f86 0%,#1279b8 45%,#0d95a6 100%);
  background-attachment:fixed;
  display:flex;flex-direction:column;align-items:center;
  min-height:100vh;min-height:100dvh;
  padding:24px;overflow-x:hidden;overscroll-behavior-y:contain;
}
.loginShell{display:flex;align-items:center;justify-content:center;gap:18px;width:100%;max-width:820px;margin:auto}
.card{
  width:100%;max-width:380px;flex:0 1 380px;background:#fff;border-radius:18px;
  box-shadow:0 18px 50px rgba(6,34,58,.28);padding:30px 26px 26px;
  animation:pop .35s ease both;
}
.noticeCard{
  width:100%;max-width:360px;flex:0 1 360px;background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.28);border-radius:18px;padding:24px 22px;
  color:#f4fbff;box-shadow:0 12px 34px rgba(6,34,58,.18);backdrop-filter:blur(6px);
}
.noticeCard h2{margin:0 0 10px;font-size:18px;color:#fff;letter-spacing:1px}
.noticeCard p{margin:0;font-size:13.5px;line-height:1.8;color:#f1faff}
.noticeCard p b{color:#fff}
.noticeCard .cTitle{margin-top:18px;font-size:12.5px;color:#d8efff;letter-spacing:.08em}
.noticeCard .cRow{display:flex;gap:10px;margin-top:7px;font-size:13px;line-height:1.5}
.noticeCard .cRow span{flex:0 0 38px;color:#d8efff}
.noticeCard .cRow b{font-weight:500;color:#fff;word-break:break-all}
@media (max-width:760px){
  body{padding:16px 12px}
  .loginShell{flex-direction:column;gap:10px}
  .card{max-width:100%;flex:none;padding:24px 20px 22px}
  .noticeCard{max-width:100%;flex:none;padding:16px 18px}
  .noticeCard h2{font-size:16px;margin-bottom:8px}
  .noticeCard p{font-size:12.5px;line-height:1.75}
}
@media (max-width:430px){
  body{padding:10px}
  .card{padding:20px 16px 18px;border-radius:14px}
  .noticeCard{padding:14px 15px;border-radius:14px}
  h1{font-size:19px}
  .sub{font-size:12.5px;margin:6px 0 16px}
  .hint{font-size:11.5px;margin-top:14px}
}
@media (max-width:760px), (max-height:700px){
  .fpLang{position:static !important;right:auto !important;bottom:auto !important;
    margin:10px auto 0 !important;align-self:center}
}
@keyframes pop{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.logo{
  width:46px;height:46px;border-radius:50%;flex:0 0 46px;
  background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;
}
.logo img{width:100%;height:100%;display:block}
h1{font-size:21px;margin:0;color:#12293f;letter-spacing:.5px}
.sub{font-size:13px;color:#7b8a99;margin:8px 0 22px}
label{display:block;font-size:13px;color:#41586d;margin-bottom:7px}
.field{position:relative}
.field svg{position:absolute;left:12px;top:50%;transform:translateY(-50%);width:17px;height:17px;color:#9aa8b5}
input[type=password],input[type=text]{
  width:100%;height:48px;border:1px solid #dbe3ea;border-radius:11px;
  padding:0 14px 0 38px;font-size:16px;color:#12293f;background:#f8fafc;
  outline:none;transition:.18s;
}
input[type=password]:focus,input[type=text]:focus{border-color:#0f6fbd;background:#fff;box-shadow:0 0 0 3px rgba(15,111,189,.13)}
button{
  width:100%;height:48px;margin-top:16px;border:0;border-radius:11px;cursor:pointer;
  background:linear-gradient(135deg,#0f6fbd,#0e8fae);color:#fff;font-size:16px;
  font-weight:600;letter-spacing:2px;transition:.18s;
}
button:hover{filter:brightness(1.06)}
button:active{transform:scale(.985)}
.err{
  background:#fdecec;color:#c0392b;font-size:13px;border-radius:9px;
  padding:9px 12px;margin-bottom:14px;display:flex;gap:8px;align-items:center;
}
.okmsg{
  background:#eafaf0;color:#1e8449;font-size:13px;border-radius:9px;
  padding:9px 12px;margin-bottom:14px;line-height:1.6;
}
.hint{font-size:12px;color:#9aa8b5;text-align:center;margin-top:18px;line-height:1.6}
.reghint{font-size:12.5px;color:#8b9aa8;text-align:center;margin:16px 0 0}
.regbtn{
  display:block;width:132px;height:40px;line-height:38px;margin:10px auto 0;
  border:1px solid #b9d5ea;border-radius:10px;background:#f6fbfe;
  text-align:center;font-size:14px;color:#0f6fbd;letter-spacing:2px;
}
.regbtn:hover{background:#eaf5fd;border-color:#8fc0e0}
</style>
</head>
<body>
<div class="loginShell">
<div class="card">
  <div class="brand">
    <div class="logo"><img src="/img/lock.svg" alt=""></div>
    <h1>文件服务平台</h1>
  </div>
  <p class="sub">请输入访问者姓名与访问密码，验证通过后进入文件存储区域</p>
  @ERROR@
  @OKMSG@
  <form method="post" action="/login" autocomplete="off">
    <label for="who">访问者姓名</label>
    <div class="field">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="8.2" r="3.6"/><path d="M4.8 20c0-3.7 3.2-6 7.2-6s7.2 2.3 7.2 6"/>
      </svg>
      <input id="who" name="who" type="text" placeholder="请输入您的真实姓名" maxlength="24" required value="@WHO@" autofocus>
    </div>
    <label for="pw" style="margin-top:14px">访问密码</label>
    <div class="field">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>
      </svg>
      <input id="pw" name="pw" type="password" placeholder="请输入访问密码" required>
    </div>
    <button type="submit">登 录</button>
  </form>
  @REGISTER@
  <p class="hint">FilePortal · Self-hosted file workspace</p>
</div>
<aside class="noticeCard" aria-label="用户须知">
  <h2>用户须知</h2>
  <p><b>本服务必须获得授权后方可使用。</b>使用前请先向开发者确认是否已授权；如尚未授权，请先联系开发者完成授权，再使用本服务。</p>
  @CONTACT@
</aside>
</div>
</body>
</html>
"""


REG_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f6fbd">
<title>@TITLE@</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;min-height:100%}
html{
  background-color:#0b4f86;
  background-image:linear-gradient(160deg,#0b4f86 0%,#1279b8 45%,#0d95a6 100%);
  background-repeat:no-repeat;background-size:cover;background-attachment:fixed;
  overscroll-behavior-y:contain;
}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(160deg,#0b4f86 0%,#1279b8 45%,#0d95a6 100%);
  background-attachment:fixed;
  display:flex;flex-direction:column;align-items:center;
  min-height:100vh;min-height:100dvh;
  padding:24px;overflow-x:hidden;overscroll-behavior-y:contain;
}
.card{width:100%;max-width:410px;background:#fff;border-radius:18px;box-shadow:0 18px 50px rgba(6,34,58,.28);
  padding:28px 26px 24px;margin:auto}
.brand{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.logo{width:42px;height:42px;border-radius:50%;flex:0 0 42px;background:#fff;border:1px solid #e6eef5;
  display:flex;align-items:center;justify-content:center;overflow:hidden}
.logo img{width:25px;height:25px;display:block}
h1{font-size:19px;margin:0;color:#12293f}
.sub{font-size:12.5px;color:#7b8a99;margin:10px 0 16px;line-height:1.65}
.notice{background:#f7fafd;border:1px solid #e4edf5;border-radius:12px;padding:14px 14px 3px;margin:4px 0 14px}
.notice p{margin:0 0 11px;font-size:13px;color:#41586d;line-height:1.75}
.notice p b{color:#12293f}
label{display:block;font-size:13px;color:#41586d;margin:12px 0 7px}
input{width:100%;height:46px;border:1px solid #dbe3ea;border-radius:11px;padding:0 14px;font-size:16px;
  color:#12293f;background:#f8fafc;outline:none}
input:focus{border-color:#0f6fbd;background:#fff;box-shadow:0 0 0 3px rgba(15,111,189,.13)}
button{width:100%;height:48px;margin-top:18px;border:0;border-radius:11px;cursor:pointer;
  background:linear-gradient(135deg,#0f6fbd,#0e8fae);color:#fff;font-size:16px;font-weight:600;letter-spacing:2px}
button:hover{filter:brightness(1.06)}
button[disabled]{background:#c9d6e1;cursor:not-allowed;filter:none}
.msg{font-size:13px;border-radius:9px;padding:10px 12px;margin-bottom:6px;line-height:1.6}
.ok{background:#eafaf0;color:#1e8449}
.err{background:#fdecec;color:#c0392b}
.ghostbtn{display:block;text-align:center;margin-top:10px;height:46px;line-height:44px;border:1px solid #cfe0ef;
  border-radius:11px;color:#0f6fbd;font-size:14px;background:#f8fbfe}
.ghostbtn:hover{background:#eef7fd}
.back{display:block;text-align:center;margin-top:16px;font-size:13px;color:#0f6fbd;text-decoration:none}
.back:hover{text-decoration:underline}
@media (max-width:560px){
  body{padding:14px 12px}
  .card{padding:22px 18px 20px;border-radius:14px}
  h1{font-size:18px}
  .sub{font-size:12.5px}
  .notice{padding:12px 12px 1px}
  .notice p{font-size:12.5px;line-height:1.7;word-break:break-word}
  button,.ghostbtn{font-size:15px}
}
@media (max-width:560px), (max-height:700px){
  .fpLang{position:static !important;right:auto !important;bottom:auto !important;
    margin:10px auto 0 !important;align-self:center}
}
</style>
</head>
<body>
<div class="card">
  <div class="brand"><div class="logo"><img src="/img/lock.svg" alt=""></div><h1>@TITLE@</h1></div>
  @BODY@
</div>
</body>
</html>
"""


MAIN_PAGE = """<!DOCTYPE html><html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0f6fbd">
<title>文件服务平台 · @TITLE@</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;padding:0}
html{background:#f2f5f8;overscroll-behavior-y:contain}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:#f2f5f8;color:#1b2b3a;font-size:15px;
  min-height:100vh;
}
a{text-decoration:none;color:inherit}
/* ---------- 顶栏 ---------- */
header{
  position:sticky;top:0;z-index:30;
  background:linear-gradient(120deg,#0b4f86,#1279b8 55%,#0d95a6);
  color:#fff;padding:12px 16px 12px;
  box-shadow:0 2px 12px rgba(10,50,80,.16);
}
.hrow{display:flex;align-items:center;gap:10px;max-width:1180px;margin:0 auto}
.brand{display:flex;align-items:center;gap:9px;min-width:0}
.brand .lg{width:30px;height:30px;border-radius:50%;background:#fff;overflow:hidden;
  display:flex;align-items:center;justify-content:center;flex:0 0 30px}
.brand .lg img{width:100%;height:100%;display:block}
.brand .lg svg{width:16px;height:16px}
.brand b{font-size:16px;font-weight:600;letter-spacing:.5px;white-space:nowrap}
.whoTag{font-size:12px;color:rgba(255,255,255,.82);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.spacer{flex:1}
.logout{
  color:#eaf5ff;border:1px solid rgba(255,255,255,.42);background:rgba(255,255,255,.12);
  padding:6px 12px;border-radius:9px;font-size:13px;cursor:pointer;
}
.logout:hover{background:rgba(255,255,255,.22)}
/* ---------- 路径条 ---------- */
.pathbar{
  background:#fff;border-bottom:1px solid #e3eaf0;padding:9px 16px;
  position:sticky;top:52px;z-index:25;
}
.pathbar .inner{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:8px;overflow-x:auto;white-space:nowrap;scrollbar-width:none}
.pathbar .inner::-webkit-scrollbar{display:none}
.crumb{color:#0f6fbd;font-size:13.5px;padding:3px 2px}
.crumb:hover{text-decoration:underline}
.sep{color:#b8c4cf;font-size:13px}
.here{color:#1b2b3a;font-weight:600;font-size:13.5px}
.backbtn{display:flex;align-items:center;gap:5px;color:#5b6b7b;font-size:13px;padding:4px 9px;border-radius:7px;background:#f2f5f8}
.backbtn:hover{background:#e7edf3}
.backbtn svg{width:14px;height:14px}
/* ---------- 工具条 ---------- */
.wrap{max-width:1180px;margin:0 auto;padding:14px 16px 90px}
.tools{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-bottom:12px}
.btn{
  display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 13px;
  border-radius:9px;border:1px solid #dbe4ec;background:#fff;color:#26455f;
  font-size:13.5px;cursor:pointer;transition:.15s;white-space:nowrap;
}
.btn:hover{border-color:#b9cddd;background:#f7fafc}
.btn svg{width:15px;height:15px}
.btn.primary{background:linear-gradient(135deg,#0f6fbd,#0e8fae);border:0;color:#fff}
.btn.primary:hover{filter:brightness(1.06)}
.search{position:relative;flex:1;min-width:150px;max-width:320px}
.search svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:15px;height:15px;color:#a2b0bd}
.search input{
  width:100%;height:36px;border:1px solid #dbe4ec;border-radius:9px;background:#fff;
  padding:0 12px 0 32px;font-size:13.5px;outline:none;
}
.search input:focus{border-color:#0f6fbd;box-shadow:0 0 0 3px rgba(15,111,189,.1)}
select.sort{height:36px;border:1px solid #dbe4ec;border-radius:9px;background:#fff;color:#26455f;
  font-size:13.5px;padding:0 8px;outline:none}
/* ---------- 列表 ---------- */
.list{background:#fff;border:1px solid #e3eaf0;border-radius:12px;overflow:hidden}
.row{
  display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid #f0f4f7;
  transition:background .12s;
}
.row:last-child{border-bottom:0}
.row:hover{background:#f8fbfd}
.row-main{display:flex;align-items:center;gap:11px;flex:1;min-width:0;cursor:pointer}
.ico{width:34px;height:34px;flex:0 0 34px;display:flex;align-items:center;justify-content:center;border-radius:9px;background:rgba(0,0,0,.035)}
.ico svg{width:21px;height:21px}
.nm{min-width:0;flex:1;display:flex;flex-direction:column;justify-content:center;overflow:hidden}
.nm .n{display:block;font-size:14px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nm .tag{display:none;font-size:11.5px;color:#a2b0bd;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.col-size{width:92px;flex:0 0 92px;text-align:right;color:#7b8a99;font-size:12.5px;font-variant-numeric:tabular-nums}
.col-time{width:128px;flex:0 0 128px;text-align:right;color:#9aa8b5;font-size:12.5px;font-variant-numeric:tabular-nums}
.acts{display:flex;gap:4px;flex:0 0 auto}
#tip{
  position:fixed;left:50%;bottom:22px;transform:translateX(-50%) translateY(8px);
  max-width:88vw;padding:9px 14px;border-radius:10px;background:rgba(26,40,54,.94);color:#fff;
  font-size:13px;line-height:1.5;word-break:break-all;box-shadow:0 6px 20px rgba(0,0,0,.22);
  opacity:0;pointer-events:none;transition:.18s;z-index:99
}
#tip.on{opacity:1;transform:translateX(-50%) translateY(0)}
.act{
  width:32px;height:32px;border-radius:8px;border:0;background:transparent;color:#8a99a8;
  display:flex;align-items:center;justify-content:center;cursor:pointer;transition:.14s;
}
.act svg{width:15px;height:15px}
.act:hover{background:#eaf2f9;color:#0f6fbd}
.act.del:hover{background:#fdeaea;color:#d43b3b}
.empty{padding:48px 20px;text-align:center;color:#9aa8b5;font-size:14px}
.empty svg{width:46px;height:46px;color:#cdd8e1;display:block;margin:0 auto 12px}
/* ---------- 分页 ---------- */
.pager{display:flex;flex-wrap:wrap;gap:6px;align-items:center;justify-content:center;margin-top:14px}
.pgbtn{min-width:34px;height:32px;padding:0 10px;border-radius:8px;border:1px solid #dbe4ec;
  background:#fff;color:#26455f;font-size:13px;display:flex;align-items:center;justify-content:center}
.pgbtn:hover{border-color:#b9cddd;background:#f7fafc}
.pgbtn.now{background:linear-gradient(135deg,#0f6fbd,#0e8fae);border-color:transparent;color:#fff;font-weight:600}
.pgbtn.off{color:#c3ced8;background:#f5f8fa;pointer-events:none}
.pgdots{color:#a2b0bd;font-size:13px;padding:0 2px}
/* ---------- 上传面板 ---------- */
.upbox{
  position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:60;
  width:min(560px,calc(100% - 24px));background:#fff;border-radius:13px;
  box-shadow:0 12px 34px rgba(12,45,70,.22);border:1px solid #e3eaf0;
  display:none;overflow:hidden;
}
.upbox.on{display:block}
.uphead{display:flex;align-items:center;gap:8px;padding:11px 14px;border-bottom:1px solid #eef3f7;
  font-size:13.5px;font-weight:600;color:#26455f}
.uphead .spacer{flex:1}
.uphead button{background:transparent;border:0;color:#8a99a8;cursor:pointer;width:26px;height:26px;border-radius:6px}
.uphead button:hover{background:#f1f5f8}
.uphead svg{width:14px;height:14px}
.uplist{max-height:210px;overflow:auto}
.upitem{padding:7px 14px;border-bottom:1px solid #f5f8fa}
.upitem:last-child{border-bottom:0}
.uptop{display:flex;gap:8px;align-items:baseline;font-size:12.5px;color:#41586d}
.uptop .fn{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.uptop .st{font-size:11.5px;color:#9aa8b5;flex:0 0 auto}
.uptop .st.done{color:#1e8449}
.uptop .st.err{color:#d43b3b}
.ubar{height:4px;border-radius:3px;background:#eef3f7;margin-top:5px;overflow:hidden}
.ubar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#0f6fbd,#0d95a6);transition:width .2s}
/* 下载面板：跟上传面板错开位置，两边同时有任务也看得见 */
#dlbox{left:auto;right:18px;transform:none;width:min(420px,calc(100% - 24px));bottom:18px}
#dlbox .ubar i{background:linear-gradient(90deg,#1e8449,#0d95a6)}
#dlbox .upitem .cancel{background:transparent;border:0;color:#8a99a8;cursor:pointer;font-size:11.5px;padding:0 2px}
#dlbox .upitem .cancel:hover{color:#d43b3b}
/* ---------- 拖拽遮罩 ---------- */
.dropmask{
  position:fixed;inset:0;z-index:70;display:none;align-items:center;justify-content:center;
  background:rgba(10,60,95,.42);backdrop-filter:blur(2px);
}
.dropmask.on{display:flex}
.dropmask .box{
  border:2px dashed rgba(255,255,255,.75);border-radius:16px;padding:34px 44px;color:#fff;
  text-align:center;font-size:15px;background:rgba(255,255,255,.1);
}
.dropmask svg{width:42px;height:42px;display:block;margin:0 auto 10px}
/* ---------- 预览弹窗 ---------- */
.modal{position:fixed;inset:0;z-index:80;background:rgba(9,26,40,.78);display:none;
  align-items:center;justify-content:center;padding:18px}
.modal.on{display:flex}
.mbox{background:#0f1b26;border-radius:14px;overflow:hidden;max-width:min(1000px,100%);max-height:92vh;
  display:flex;flex-direction:column;width:100%}
.mhead{display:flex;align-items:center;gap:10px;padding:11px 14px;background:#16232f;color:#dbe8f2}
.mhead .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13.5px}
.mhead a,.mhead button{background:rgba(255,255,255,.12);border:0;color:#dbe8f2;border-radius:8px;
  padding:6px 11px;font-size:12.5px;cursor:pointer}
.mhead button svg{width:14px;height:14px;display:block}
.mbody{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;background:#0b141c;min-height:120px}
.mbody img,.mbody video{max-width:100%;max-height:calc(92vh - 60px);display:block}
.mbody audio{width:min(520px,90vw)}
.mbody iframe{width:min(900px,92vw);height:80vh;border:0;background:#fff}
.mbody pre{margin:0;padding:16px;color:#cfe3f2;font-size:13px;line-height:1.6;white-space:pre-wrap;
  word-break:break-word;width:100%;height:100%;overflow:auto;font-family:Consolas,Menlo,monospace}
.mnote{color:#93a6b6;font-size:13.5px;padding:28px}
/* ---------- 手机端 ---------- */
@media (max-width:640px){
  header{padding:10px 12px}
  .pathbar{padding:8px 12px;top:48px}
  .wrap{padding:10px 10px 96px}
  .col-time{display:none}
  .col-size{display:none}
  .acts{gap:2px}
  .acts .act[data-txt="重命名"]{display:none}
  .row{padding:9px 10px;gap:7px}
  .ico{width:32px;height:32px;flex:0 0 32px}
  .search{max-width:none;order:5;flex:1 0 100%}
  .tools{gap:7px}
  .tools .spacer{display:none}
  .btn{padding:0 10px;font-size:13px}
  .nm .tag{display:block}
}
@media (prefers-color-scheme:dark){}
</style>
</head>
<body>
@SPRITE@
<header>
  <div class="hrow">
    <div class="brand">
      <div class="lg" id="meAvBox"><img id="meAvatar" src="@AVATAR@" alt=""></div>
      <b>文件服务平台</b><span class="whoTag">@WHO@</span>
    </div>
    <div class="spacer"></div>
    @ADMINLINK@<button class="logout" onclick="location.href='/logout'">注销</button>
  </div>
</header>
<div class="pathbar"><div class="inner">@CRUMB@</div></div>
<div class="wrap">
  <div class="tools">
    @TOOLS@<button class="btn" id="btnRefresh"><svg viewBox="0 0 24 24"><use href="#i-refresh"/></svg>刷新</button>
    <button class="btn" id="btnAdv"><svg viewBox="0 0 24 24"><use href="#i-edit"/></svg>高级设置</button>
    @BULKBTN@
    <div class="spacer"></div>
    <div class="search">
      <svg viewBox="0 0 24 24"><use href="#i-search"/></svg>
      <input id="search" type="search" placeholder="检索当前目录及其全部子目录" value="@KWVALUE@">
    </div>
    <select class="sort" id="sort">
      <option value="name|1">名称 升序</option>
      <option value="name|0">名称 降序</option>
      <option value="mtime|0">修改时间 降序</option>
      <option value="mtime|1">修改时间 升序</option>
      <option value="size|0">大小 降序</option>
      <option value="size|1">大小 升序</option>
      <option value="type|1">类型</option>
    </select>
  </div>
  <div class="bulkbar" id="bulkbar">
    <span id="bulkCount">已选 0 项</span>
    <button class="btn" id="bulkDown">批量下载</button>
    <button class="btn" id="bulkMove">批量移动</button>
    <button class="btn" id="bulkDel">批量删除</button>
    <button class="btn" id="bulkClear">取消选择</button>
  </div>
  <div class="list" id="list">
    @ROWS@
  </div>
  @PAGER@
  <p id="stat" style="font-size:12.5px;color:#9aa8b5;margin:10px 4px 0">@STAT@</p>
</div>

<div class="upbox" id="upbox">
  <div class="uphead"><span id="upTitle">上传进行中</span><div class="spacer"></div>
    <button onclick="hideUp()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button></div>
  <div class="uplist" id="uplist"></div>
</div>

<div class="upbox" id="dlbox">
  <div class="uphead"><span id="dlTitle">下载进行中</span><div class="spacer"></div>
    <button onclick="hideDl()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button></div>
  <div class="uplist" id="dllist"></div>
</div>

@DROPMASK@
<div class="modal" id="modal">
  <div class="mbox">
    <div class="mhead">
      <span class="t" id="mTitle"></span>
      <a id="mDown" href="#" download>下载</a>
      <button onclick="closeModal()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button>
    </div>
    <div class="mbody" id="mBody"></div>
  </div>
</div>

<div class="modal" id="infoModal">
  <div class="mbox light">
    <div class="mhead2"><span class="t" id="iTitle">详细信息</span>
      <button onclick="closeInfo()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button></div>
    <div class="ibody" id="iBody"></div>
  </div>
</div>

<div class="modal" id="trashModal">
  <div class="mbox light">
    <div class="mhead2"><span class="t">回收站</span>
      <button class="mini" onclick="emptyTrash()">清空</button>
      <button onclick="closeTrash()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button></div>
    <div class="ibody" id="trashBody"><div class="mnote2">正在加载</div></div>
  </div>
</div>

<div class="modal" id="advModal">
  <div class="mbox light" style="max-width:min(560px,100%)">
    <div class="mhead2"><span class="t">高级设置</span>
      <button onclick="closeAdv()"><svg viewBox="0 0 24 24"><use href="#i-close"/></svg></button></div>
    <div class="ibody" id="advBody">
      <div class="advsec">下载</div>
      <div class="advrow">
        <div class="advlab">下载连接方式</div>
        <select class="advsel" id="advDlMode">
          <option value="multi">并发下载（多连接，速度快）</option>
          <option value="single">单连接下载（兼容老设备）</option>
        </select>
        <div class="advhint">并发下载会把文件切成多段同时取；网络不稳或老设备容易出错时改用单连接。</div>
      </div>
      <div class="advrow">
        <div class="advlab">传输通道</div>
        <select class="advsel" id="advCompat">
          <option value="0">标准模式（推荐）</option>
          <option value="1">兼容模式（系统下载器）</option>
        </select>
        <div class="advhint">兼容模式交给系统自带下载器直接存盘，没有进度条，但老旧浏览器和学习机最不容易失败。</div>
      </div>
      <div class="advrow">
        <div class="advlab">下载文件名</div>
        <select class="advsel" id="advNameZh">
          <option value="zh">保留中文（推荐）</option>
          <option value="ascii">仅英文和数字（兼容老旧设备）</option>
        </select>
        <div class="advhint">部分安卓 WebView 处理中文文件名会出错，下载后名字异常或后缀变错时，改成“仅英文和数字”。</div>
      </div>
      <div class="advrow">
        <div class="advlab">下载完成</div>
        <label class="advcheck"><input type="checkbox" id="advAutoHide"> 完成后自动收起下载进度面板</label>
        <div class="advhint">开启后单个文件下载完成约 1.5 秒自动收起；批量下载会等全部结束后再收起。</div>
      </div>
      <div class="advfoot">设置只保存在当前设备，换设备需要重新选择。</div>
    </div>
  </div>
</div>

<div class="pop" id="pop"></div>
<input type="file" id="avatarInput" accept="image/*,.png,.jpg,.jpeg,.webp,.gif,.bmp,.ico,.svg,.avif" hidden>
<input type="file" id="fileInput" multiple hidden>
<input type="file" id="dirInput" webkitdirectory directory multiple hidden>

<script>
var DIR = "@DIRJSON@";
var CAN_UPLOAD = @CAN_UPLOAD@;
var CAN_MKDIR = @CAN_MKDIR@;
var CAN_AVATAR = @CAN_AVATAR@;
var DLC = @DLCFG@;          /* 并发下载参数：file / zip / maxMB / up */

function $(id){ return document.getElementById(id); }
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ---------- 跳转（排序 / 搜索 / 翻页都交给服务端处理） ---------- */
function goBrowse(pageNo){
  var params = new URLSearchParams();
  if (DIR) params.set('p', DIR);
  var s = $('sort').value.split('|');
  if (!(s[0] === 'name' && s[1] === '1')){
    params.set('sort', s[0]);
    params.set('order', s[1] === '1' ? 'asc' : 'desc');
  }
  var kw = $('search') ? $('search').value.trim() : '';
  if (kw) params.set('q', kw);
  if (pageNo && pageNo > 1) params.set('page', String(pageNo));
  var qs = params.toString();
  location.href = '/browse' + (qs ? '?' + qs : '');
}

var searchTimer = null;
if ($('search')){
  $('search').addEventListener('input', function(){
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function(){ goBrowse(1); }, 450);
  });
  $('search').addEventListener('keydown', function(e){
    if (e.key === 'Enter'){ clearTimeout(searchTimer); goBrowse(1); }
  });
}

/* ---------- 上传（多个文件同时传，速度比一个一个快很多；并发数在 config.ini 里改） ---------- */
var queue = [], busy = false, totalFiles = 0, doneFiles = 0;

function hideUp(){
  if (busy) return;
  $('upbox').classList.remove('on');
  $('uplist').innerHTML = '';
}
function showUp(title){
  $('upTitle').textContent = title;
  $('upbox').classList.add('on');
}
function addUpItem(name){
  var el = document.createElement('div');
  el.className = 'upitem';
  el.innerHTML = '<div class="uptop"><span class="fn"></span><span class="st">等待</span></div>' +
                 '<div class="ubar"><i></i></div>';
  el.querySelector('.fn').textContent = name;
  $('uplist').appendChild(el);
  return el;
}
function uploadFile(file, relName){
  return new Promise(function(resolve){
    var item = addUpItem(relName);
    var st = item.querySelector('.st'), bar = item.querySelector('.ubar i');
    var url = '/api/upload?p=' + encodeURIComponent(DIR) + '&name=' + encodeURIComponent(relName);
    var xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.upload.onprogress = function(e){
      if (e.lengthComputable){
        var p = e.loaded / e.total * 100;
        bar.style.width = p.toFixed(1) + '%';
        st.textContent = humanSize(e.loaded) + ' / ' + humanSize(e.total);
      }
    };
    xhr.onload = function(){
      if (xhr.status === 200){
        bar.style.width = '100%'; st.textContent = '完成'; st.className = 'st done';
        resolve(true);
      } else {
        st.textContent = '失败 ' + xhr.status; st.className = 'st err';
        try { st.textContent = '失败：' + JSON.parse(xhr.responseText).error; } catch(e){}
        st.className = 'st err';
        resolve(false);
      }
    };
    xhr.onerror = function(){ st.textContent = '网络错误'; st.className = 'st err'; resolve(false); };
    xhr.send(file);
  });
}
function humanSize(n){
  if (!n) return '0 B';
  var u = ['B','KB','MB','GB','TB'], i = 0;
  while (n >= 1024 && i < u.length-1){ n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(1)) + ' ' + u[i];
}
async function runQueue(){
  if (busy) return;
  busy = true;
  totalFiles = doneFiles + queue.length;
  var failures = 0;
  showUp('上传中 0/' + totalFiles);
  var w = Math.max(1, Math.min(8, (DLC && DLC.up) || 1));
  var pool = [];
  for (var k = 0; k < w; k++){
    pool.push((async function(){
      while (queue.length){
        var it = queue.shift();
        var ok = await uploadFile(it.file, it.name);
        if (!ok) failures++;
        doneFiles++;
        $('upTitle').textContent = '上传中 ' + doneFiles + '/' + totalFiles;
      }
    })());
  }
  await Promise.all(pool);
  busy = false;
  $('upTitle').textContent = failures
      ? ('上传结束：成功 ' + (totalFiles - failures) + ' 个，失败 ' + failures + ' 个（重新上传将覆盖同名文件）')
      : ('上传完成（' + totalFiles + ' 个文件）');
  if (!failures) setTimeout(function(){ location.reload(); }, 700);
  else tip('有 ' + failures + ' 个文件未能完成上传，可重新选择后上传', 5000);
}
function enqueue(files, withPath){
  if (!files || !files.length) return;
  totalFiles += files.length;
  for (var i = 0; i < files.length; i++){
    var f = files[i];
    var name = withPath && f.webkitRelativePath ? f.webkitRelativePath : f.name;
    queue.push({file: f, name: name});
  }
  runQueue();
}
if ($('btnUp')) $('btnUp').onclick = function(){ $('fileInput').click(); };
if ($('btnUpDir')) $('btnUpDir').onclick = function(){ $('dirInput').click(); };
if ($('fileInput')) $('fileInput').onchange = function(){ enqueue(this.files, false); this.value = ''; };
if ($('dirInput')) $('dirInput').onchange = function(){ enqueue(this.files, true); this.value = ''; };
$('btnRefresh').onclick = function(){ location.reload(); };
if ($('btnMk')) $('btnMk').onclick = function(){
  var name = prompt('新建目录的名称：');
  if (!name) return;
  post('/api/mkdir', {p: DIR, name: name}).then(function(){ location.reload(); });
};

/* ---------- 拖拽上传 ---------- */
var dragDepth = 0;
window.addEventListener('dragenter', function(e){
  if (!CAN_UPLOAD) return;
  if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types||[], 'Files') >= 0){
    dragDepth++; $('dropmask').classList.add('on');
  }
});
window.addEventListener('dragleave', function(){ dragDepth--; if (dragDepth <= 0){ dragDepth = 0; $('dropmask').classList.remove('on'); } });
window.addEventListener('dragover', function(e){ e.preventDefault(); });
window.addEventListener('drop', function(e){
  e.preventDefault(); dragDepth = 0; $('dropmask').classList.remove('on');
  if (CAN_UPLOAD && e.dataTransfer && e.dataTransfer.files) enqueue(e.dataTransfer.files, false);
});

/* ---------- 行操作 ---------- */
function post(url, data){
  return fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
    body: new URLSearchParams(data).toString()
  }).then(function(r){
    if (!r.ok) return r.text().then(function(t){ throw new Error(t || ('HTTP ' + r.status)); });
    return r.json().catch(function(){ return {}; });
  });
}

$('list').addEventListener('click', function(e){
  var btn = e.target.closest('.act');
  if (!btn) return;
  var p = btn.dataset.p, nm = btn.dataset.name, dir = btn.dataset.dir === '1';
  var kind = btn.dataset.kind, act = btn.dataset.act;
  // 下载 / 打包 是真正的 <a href> 链接（没有 data-act）。以前这里一律 preventDefault，
  // 结果点了完全没反应；现在改成：能并发下载就走并发下载，走不了就让浏览器自己下。
  if (!act){
    e.stopPropagation();
    var href = btn.getAttribute('href') || '';
    var rel = '';
    if (href.indexOf('p=') >= 0){
      try { rel = decodeURIComponent(href.split('p=')[1]); } catch (_) { rel = ''; }
    }
    var base = rel ? rel.split('/').pop() : '';
    var rowEl = btn.closest ? btn.closest('.row') : null;
    var sz = rowEl ? parseInt(rowEl.getAttribute('data-size') || '0', 10) : 0;
    if (href.indexOf('/download?') === 0){
      e.preventDefault();
      startDl(href, base || nm || 'download', 'file', sz);
    } else if (href.indexOf('/zip?') === 0){
      e.preventDefault();
      startDl(href, ((base || nm || '打包') + '.zip'), 'zip');
    }
    return;
  }
  e.preventDefault(); e.stopPropagation();
  if (act === 'down'){
    if (dir) location.href = '/zip?p=' + encodeURIComponent(p);
    else location.href = '/download?p=' + encodeURIComponent(p);
  } else if (act === 'prev'){
    preview(p, nm, kind);
  } else if (act === 'info'){
    showInfo(p, nm, dir);
  } else if (act === 'fav'){
    addFav(p, nm);
  } else if (act === 'cut'){
    setCut(p, nm, dir);
  } else if (act === 'ren'){
    var nn = prompt('请输入新的名称：', nm);
    if (!nn || nn === nm) return;
    post('/api/rename', {p: p, name: nn}).then(function(){ location.reload(); })
      .catch(function(err){ alert('重命名失败：' + err.message); });
  } else if (act === 'del'){
    if (!confirm('确认删除「' + nm + '」吗？\\n删除后该项目将移入回收站，可在回收站中还原。')) return;
    post('/api/delete', {p: p}).then(function(){ location.reload(); })
      .catch(function(err){ alert('删除失败：' + err.message); });
  } else if (act === 'copy'){
    copyLink(location.origin + btn.dataset.link);
  }
});

/* ---------- 多选 + 批量操作 ---------- */
var BULK = {};
function selCount(){ return Object.keys(BULK).length; }
function refreshBulk(){
  var n = selCount();
  if ($('bulkCount')) $('bulkCount').textContent = '已选 ' + n + ' 项';
  if ($('bulkbar')) $('bulkbar').classList.toggle('on', n > 0);
}
if ($('btnBulk')) $('btnBulk').onclick = function(){
  if (selCount()){ BULK = {}; syncCbx(); refreshBulk(); return; }
  $('bulkbar').classList.add('on');
};
$('list').addEventListener('change', function(e){
  if (!e.target.classList || !e.target.classList.contains('cbx')) return;
  var cb = e.target, p = cb.dataset.p;
  if (cb.checked) BULK[p] = {name: cb.dataset.name, dir: cb.dataset.dir === '1'};
  else delete BULK[p];
  var row = cb.closest('.row'); if (row) row.classList.toggle('sel', cb.checked);
  refreshBulk();
});
function syncCbx(){
  var list = $('list').querySelectorAll('.cbx');
  for (var i = 0; i < list.length; i++){
    var p = list[i].dataset.p;
    list[i].checked = !!BULK[p];
    var row = list[i].closest('.row'); if (row) row.classList.toggle('sel', list[i].checked);
  }
}
if ($('bulkClear')) $('bulkClear').onclick = function(){ BULK = {}; syncCbx(); refreshBulk(); };
if ($('bulkDel')) $('bulkDel').onclick = function(){
  var keys = Object.keys(BULK);
  if (!keys.length) return;
  if (!confirm('确认删除所选 ' + keys.length + ' 项？\\n删除后各项将移入回收站，可在回收站中还原。')) return;
  (async function(){
    for (var i = 0; i < keys.length; i++){
      try { await post('/api/delete', {p: keys[i]}); } catch (e) { alert('「' + BULK[keys[i]].name + '」删除失败：' + e.message); }
    }
    location.reload();
  })();
};
if ($('bulkDown')) $('bulkDown').onclick = function(){
  var keys = Object.keys(BULK);
  if (!keys.length) return;
  if (DLC && DLC.can === 0){ tip('当前身份没有下载权限', 3000); return; }
  var qs = keys.map(function(p){ return 'p=' + encodeURIComponent(p); }).join('&');
  startDl('/zipmulti?' + qs, '批量下载.zip', 'zip');
  BULK = {}; syncCbx(); refreshBulk();
};
if ($('bulkMove')) $('bulkMove').onclick = function(){
  var keys = Object.keys(BULK);
  if (!keys.length) return;
  var dst = prompt('请输入目标目录路径（留空表示当前目录）：', DIR);
  if (dst === null) return;
  (async function(){
    var bad = 0;
    for (var i = 0; i < keys.length; i++){
      try { await post('/api/move', {src: keys[i], dst: dst}); } catch (e) { bad++; }
    }
    BULK = {};
    if (bad) alert('有 ' + bad + ' 项移动未成功（可能目标已存在同名项目，或目标位于其自身内部）');
    location.reload();
  })();
};

/* ---------- 剪切 / 粘贴 ---------- */
var CUT = null;
try { CUT = JSON.parse(localStorage.getItem('fs_cut') || 'null'); } catch (_) { CUT = null; }
function setCut(p, nm, dir){
  CUT = {p: p, name: nm, dir: dir};
  try { localStorage.setItem('fs_cut', JSON.stringify(CUT)); } catch (_) {}
  tip('已标记移动「' + nm + '」，请进入目标目录后点击「粘贴到当前」', 4200);
  applyCutBtn();
}
function applyCutBtn(){
  var b = $('btnPaste');
  if (!b) return;
  b.style.display = CUT ? '' : 'none';
  b.textContent = CUT ? ('粘贴「' + (CUT.name || '') + '」到当前') : '粘贴到当前';
}
if ($('btnPaste')) $('btnPaste').onclick = function(){
  if (!CUT) return;
  post('/api/move', {src: CUT.p, dst: DIR}).then(function(){
    var n = CUT.name; CUT = null;
    try { localStorage.removeItem('fs_cut'); } catch (_) {}
    tip('已移动「' + n + '」至当前目录', 3000);
    setTimeout(function(){ location.reload(); }, 600);
  }).catch(function(err){ alert('移动失败：' + err.message); });
};
applyCutBtn();

/* ---------- 回收站 ---------- */
function closeTrash(){ $('trashModal').classList.remove('on'); }
$('trashModal').addEventListener('click', function(e){ if (e.target === this) closeTrash(); });
function loadTrash(){
  var body = $('trashBody');
  body.innerHTML = '<div class="mnote2">正在加载</div>';
  fetch('/api/trash?op=list').then(function(r){ return r.json(); }).then(function(j){
    if (!j.items || !j.items.length){ body.innerHTML = '<div class="mnote2">回收站当前为空</div>'; return; }
    body.innerHTML = '';
    j.items.forEach(function(it){
      var el = document.createElement('div');
      el.className = 'trow';
      el.innerHTML = '<span class="nm"><b></b><span></span></span>' +
                     '<button data-t="restore">还原</button><button class="del" data-t="purge">彻底删除</button>';
      el.querySelector('b').textContent = it.name;
      el.querySelector('span span').textContent = (it.dir ? '文件夹' : humanSize(it.size)) +
          ' · 原位置 ' + (it.rel || '') + ' · ' + (it.deleted || '');
      el.querySelectorAll('button').forEach(function(b){
        b.onclick = function(){
          var op = b.dataset.t;
          if (op === 'purge' && !confirm('彻底删除「' + it.name + '」？该操作不可撤销')) return;
          post('/api/trash', {op: op, id: it.id}).then(function(res){
            tip(res.msg || (op === 'restore' ? '已还原' : '已删除'), 3000);
            loadTrash();
            if (op === 'restore') setTimeout(function(){ location.reload(); }, 1200);
          }).catch(function(e){ alert('操作失败：' + e.message); });
        };
      });
      body.appendChild(el);
    });
  }).catch(function(){ body.innerHTML = '<div class="mnote2">回收站数据读取失败</div>'; });
}
if ($('btnTrash')) $('btnTrash').onclick = function(){
  $('trashModal').classList.add('on');
  loadTrash();
};
function emptyTrash(){
  if (!confirm('确认清空回收站？其中全部项目将被永久删除且无法还原。')) return;
  post('/api/trash', {op: 'empty'}).then(function(){ tip('回收站已清空', 2500); loadTrash(); })
    .catch(function(e){ alert('清空失败：' + e.message); });
}

/* ---------- 详情（大小 / 时间 / 直链；文件夹还能算总大小） ---------- */
function closeInfo(){ $('infoModal').classList.remove('on'); }
$('infoModal').addEventListener('click', function(e){ if (e.target === this) closeInfo(); });
function showInfo(p, name, isDir){
  $('iTitle').textContent = name;
  var body = $('iBody');
  body.innerHTML = '<div class="mnote2">正在加载</div>';
  $('infoModal').classList.add('on');
  fetch('/api/info?p=' + encodeURIComponent(p)).then(function(r){ return r.json(); }).then(function(j){
    if (!j.ok){ body.innerHTML = '<div class="mnote2">' + (j.error || '无法读取该文件') + '</div>'; return; }
    var rows = [
      ['名称', esc(j.name)],
      ['位置', esc(j.rel || '根目录')],
      ['类型', esc(j.type || '')],
      ['大小', isDir ? '<span id="duTxt">请点击下方「统计占用空间」</span>' : esc(j.size_text)],
      ['修改时间', esc(j.mtime || '')]
    ];
    if (!isDir) rows.push(['直链', j.link ? ('<a href="' + esc(j.link) + '" target="_blank">打开</a>') : '—']);
    body.innerHTML = rows.map(function(r){
      return '<div class="kv"><span class="k">' + r[0] + '</span><span class="v">' + r[1] + '</span></div>';
    }).join('') +
    (isDir ? '<div class="kv"><span class="k"></span><span class="v">' +
             '<button class="btn" id="btnDu" style="height:30px;font-size:12.5px">计算总大小（含全部子目录）</button></span></div>' : '');
    if (isDir && $('btnDu')){
      $('btnDu').onclick = function(){
        $('duTxt').textContent = '正在统计';
        fetch('/api/du?p=' + encodeURIComponent(p)).then(function(r){ return r.json(); }).then(function(d){
          $('duTxt').textContent = d.ok ? (d.size_text + '（' + d.count + ' 个文件' + (d.truncated ? '，统计结果已截断' : '') + '）') : '统计失败';
        }).catch(function(){ $('duTxt').textContent = '统计失败'; });
      };
    }
  }).catch(function(){ body.innerHTML = '<div class="mnote2">无法读取该文件</div>'; });
}

/* ---------- 常用目录（存在本机浏览器里，不上传服务器） ---------- */
function favs(){
  try { return JSON.parse(localStorage.getItem('fs_favs') || '[]'); } catch (_) { return []; }
}
function saveFavs(a){ try { localStorage.setItem('fs_favs', JSON.stringify(a)); } catch (_) {} }
function addFav(p, name){
  var a = favs();
  if (a.some(function(x){ return x.p === p; })){ tip('「' + name + '」已在常用目录列表中', 2200); return; }
  a.push({p: p, name: name, t: Date.now()});
  saveFavs(a); tip('已加入常用目录：「' + name + '」', 2200); renderFav();
}
function delFav(p){
  saveFavs(favs().filter(function(x){ return x.p !== p; }));
  renderFav();
}
function renderFav(){
  var box = $('favdrop');
  if (!box) return;
  var a = favs();
  if (!a.length){ box.innerHTML = '<div class="favempty">暂无收藏项。进入常用目录后点击「收藏当前目录」即可添加。</div>'; return; }
  box.innerHTML = '';
  a.forEach(function(x){
    var el = document.createElement('div');
    el.className = 'favit';
    el.innerHTML = '<span class="nm"></span><span class="x">删除</span>';
    el.querySelector('.nm').textContent = x.name || x.p || '根目录';
    el.querySelector('.nm').onclick = function(){ location.href = '/browse' + (x.p ? ('?p=' + encodeURIComponent(x.p)) : ''); };
    el.querySelector('.x').onclick = function(){ delFav(x.p); };
    box.appendChild(el);
  });
}
if ($('btnFavList')) $('btnFavList').onclick = function(e){
  e.stopPropagation(); renderFav(); $('favdrop').classList.toggle('on');
};
document.addEventListener('click', function(e){
  var box = $('favdrop');
  if (box && box.classList.contains('on') && !e.target.closest('.favbox')) box.classList.remove('on');
});
if ($('btnFavAdd')) $('btnFavAdd').onclick = function(){
  var nm = DIR ? DIR.split('/').pop() : '根目录';
  addFav(DIR, nm);
};

/* ---------- 备注气泡（替代以前遮住界面的底部提示条） ---------- */
var NOTES = {
  mode: '「并发下载 / 单连接下载」为各访问终端独立记录的下载策略。\\n' +
        '· 并发下载：将文件分段并行获取，可缩短大文件传输耗时；系统配置值为全站并发上限，' +
        '多个终端同时下载时按连接数分配。\\n' +
        '· 单连接下载：以单条连接顺序获取，传输稳定性最佳，适用于老旧设备、弱网环境，' +
        '或并发分片校验失败的情形。',
  compat: '「标准模式」通过网页分片下载与“另存为”直写实现，具备进度显示与较高吞吐能力。\\n' +
          '「兼容模式」不经过网页下载流程，将地址交由系统下载器处理：无进度显示、单连接，' +
          '但对学习机、功能机及旧版浏览器具有最佳兼容性。\\n' +
          '如浏览器提示「不安全 / 是否保留」：标准模式下请选择「保留」；' +
          '如需彻底消除该提示，请通过 HTTPS 地址访问，或切换至兼容模式。'
};
function showNote(anchor, key){
  var el = $('pop');
  if (!el) return;
  el.innerHTML = (NOTES[key] || '').replace(/\\n/g, '<br>');
  el.classList.add('on');
  var r = anchor.getBoundingClientRect();
  var w = el.offsetWidth, h = el.offsetHeight;
  var left = Math.min(window.innerWidth - w - 10, Math.max(8, r.left));
  var top = r.top - h - 8;
  if (top < 8) top = r.bottom + 8;
  el.style.left = left + 'px';
  el.style.top = top + 'px';
}
document.querySelectorAll('.noteq').forEach(function(b){
  b.onclick = function(e){ e.stopPropagation(); showNote(b, b.dataset.note); };
});
document.addEventListener('click', function(){ var el = $('pop'); if (el) el.classList.remove('on'); });

/* ---------- 拖到桌面即下载：Chrome / Edge 认 DownloadURL 这种拖拽数据 ---------- */
$('list').addEventListener('dragstart', function(e){
  var row = e.target.closest('.row');
  if (!row || !row.dataset.link) return;
  var isDir = row.dataset.dir === '1';
  var name = row.dataset.name || 'download';
  var fname = isDir ? (name + '.zip') : name;
  var mime = isDir ? 'application/zip' : 'application/octet-stream';
  var url = location.origin + row.dataset.link;
  try {
    e.dataTransfer.setData('DownloadURL', mime + ':' + fname + ':' + url);
    e.dataTransfer.setData('text/uri-list', url);
    e.dataTransfer.setData('text/plain', url);
    e.dataTransfer.effectAllowed = 'copy';
  } catch (_) {}
});

/* ---------- 并发下载 ----------
   普通文件：服务端支持 Range，前端开 N 条连接各扒一段，收齐后拼成一个文件存下来。
   打包下载：先让服务端把文件夹落成缓存 zip（有固定长度），再同样分片并行。
   文件夹太大 / 文件太大 / 家里是老浏览器 → 自动退回浏览器原生下载（直接写盘，不占内存）。
   服务端另有全站闸门（FILE_STREAMS / ZIP_STREAMS）：两台设备同时下、配置 32 时各摊一半。 */
var DLDONE = 0;
function showDl(){ $('dlbox').classList.add('on'); }
function hideDl(){ $('dlbox').classList.remove('on'); }
function dlDone(){
  DLDONE++;
  if (!DL_AUTOHIDE) return;
  setTimeout(function(){
    var busy = false;
    document.querySelectorAll('#dllist .upitem .st').forEach(function(s){
      if (!/完成|失败|取消|已取消/.test(s.textContent)) busy = true;
    });
    if (!busy) hideDl();
  }, 1500);
}
function dlItem(name){
  var el = document.createElement('div');
  el.className = 'upitem';
  el.innerHTML = '<div class="uptop"><span class="fn"></span><span class="st">准备中…</span>' +
                 '<button class="cancel">取消</button></div><div class="ubar"><i></i></div>';
  el.querySelector('.fn').textContent = name;
  $('dllist').appendChild(el);
  return el;
}
function saveBlob(blob, name){
  name = dlName(name);
  if (!blob.type){
    try { blob = new Blob([blob], {type: mimeOfName(name)}); } catch (_) {}
  }
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 5000);
}
function dlFallback(url, item){
  if (item){
    var st = item.querySelector('.st');
    st.textContent = '已转交浏览器原生下载（如提示“不安全/是否保留”，请选择“保留”）';
  }
  location.href = url;      /* 原生下载：单连接、直接写盘，但会经过浏览器的下载安全检查 */
}

/* ---------- 存盘：绕开浏览器的下载安全检查 ----------
   浏览器（Chrome/Edge 尤其 Windows 上）对"网页触发的下载"会做安全判定，
   轻则弹「是否保留」，重则直接「已拦截不安全下载」，把什么文件都拦一遍。
   办法是换成 File System Access API：点下载 → 直接弹「另存为」→ 本页面把字节
   写进你选的那个文件。数据根本不经过下载管理器，也就不存在拦截提示。
   手机浏览器多数没有这套接口 → 自动退回 dlFallback（原生下载 + 提示）。 */

var DL_CHUNK = 4 * 1024 * 1024;    /* 分片 4 MB：内存占用 = 并发数 × 4MB，所以再大的文件也不吃内存 */

function pickSave(name){
  if (!window.showSaveFilePicker) return null;
  try {
    return window.showSaveFilePicker({ suggestedName: name });
  } catch (e) {
    return null;
  }
}

function fetchChunk(url, start, end, signal){
  var opt = { headers: { 'Range': 'bytes=' + start + '-' + end }, cache: 'no-store' };
  if (signal) opt.signal = signal;
  return fetch(url, opt).then(function(r){
    if (r.status !== 206 && r.status !== 200) throw new Error('HTTP ' + r.status);
    return r.arrayBuffer();
  });
}

/* 已知总长度：按 4MB 切片并行取，按顺序写盘（有并发、内存有上限） */
function saveWithPicker(handle, url, total, threads, item){
  var bar = item.querySelector('.ubar i'), st = item.querySelector('.st');
  var cancelBtn = item.querySelector('.cancel');
  var ctl = ('AbortController' in window) ? new AbortController() : null;
  var killed = false, written = 0, t0 = Date.now(), writable = null, n = 0;
  cancelBtn.onclick = function(){ killed = true; if (ctl) ctl.abort(); };
  function tick(){
    var pct = total ? Math.min(100, written / total * 100) : 0;
    var secs = (Date.now() - t0) / 1000;
    var speed = secs > 0.4 ? written / secs : 0;
    bar.style.width = pct.toFixed(1) + '%';
    st.textContent = pct.toFixed(1) + '% · ' + humanSize(written) + ' / ' + humanSize(total) +
                     ' · ' + humanSize(speed) + '/s · ' + n + ' 个分段连接';
  }
  return (async function(){
    try {
      writable = await handle.createWritable();
      var nch = Math.max(1, Math.ceil(total / DL_CHUNK));
      n = Math.max(1, Math.min(threads, 12, nch));
      var pend = {}, nextFetch = 0, nextWrite = 0, inflight = 0;
      tick();
      while (nextWrite < nch){
        if (killed) throw new Error('CANCEL');
        while (nextFetch < nch && inflight < n){
          var s = nextFetch * DL_CHUNK;
          var e = Math.min(total - 1, s + DL_CHUNK - 1);
          pend[nextFetch] = fetchChunk(url, s, e, ctl && ctl.signal);
          nextFetch++; inflight++;
        }
        var buf = await pend[nextWrite];
        delete pend[nextWrite]; inflight--;
        if (killed) throw new Error('CANCEL');
        await writable.write(buf);
        written += buf.byteLength;
        nextWrite++;
        tick();
      }
      await writable.close();
      writable = null;
      if (written !== total) throw new Error('长度对不上');
      bar.style.width = '100%';
      cancelBtn.style.display = 'none';
      dlDone();
      st.textContent = '已保存 · ' + humanSize(written) + ' · ' + ((Date.now() - t0) / 1000).toFixed(1) + 's';
      return 'ok';
    } catch (err) {
      if (writable){ try { await writable.abort(); } catch (_) {} }
      cancelBtn.style.display = 'none';
      if (killed || (err && err.message === 'CANCEL')){ st.textContent = '已取消（文件可能不完整）'; return 'cancel'; }
      st.textContent = '保存失败（' + err.message + '），已切换为常规下载';
      return 'fail';
    }
  })();
}

/* 不知道总长度（边压边发的 zip）：单连接顺流写盘。传了 total 就显示百分比。 */
function saveStreamToPicker(handle, url, item, total){
  var bar = item.querySelector('.ubar i'), st = item.querySelector('.st');
  var cancelBtn = item.querySelector('.cancel');
  var ctl = ('AbortController' in window) ? new AbortController() : null;
  var killed = false, written = 0, t0 = Date.now(), writable = null;
  cancelBtn.onclick = function(){ killed = true; if (ctl) ctl.abort(); };
  return (async function(){
    try {
      var r = await fetch(url, ctl ? { signal: ctl.signal } : {});
      if (r.status !== 200 && r.status !== 206) throw new Error('HTTP ' + r.status);
      writable = await handle.createWritable();
      var reader = r.body.getReader();
      while (true){
        var o = await reader.read();
        if (o.done) break;
        if (killed) throw new Error('CANCEL');
        await writable.write(o.value);
        written += o.value.byteLength;
        var secs = (Date.now() - t0) / 1000;
        var speed = humanSize(secs > 0.4 ? written / secs : 0) + '/s';
        if (total){
          var pct = Math.min(100, written / total * 100);
          bar.style.width = pct.toFixed(1) + '%';
          st.textContent = pct.toFixed(1) + '% · ' + humanSize(written) + ' / ' + humanSize(total) +
                           ' · ' + speed + ' · 单连接下载';
        } else {
          bar.style.width = '100%';
          st.textContent = '已写入 ' + humanSize(written) + ' · ' + speed + ' · 单连接下载';
        }
      }
      await writable.close();
      writable = null;
      cancelBtn.style.display = 'none';
      dlDone();
      st.textContent = '已保存 · ' + humanSize(written) + ' · ' + ((Date.now() - t0) / 1000).toFixed(1) + 's';
      return 'ok';
    } catch (err) {
      if (writable){ try { await writable.abort(); } catch (_) {} }
      cancelBtn.style.display = 'none';
      if (killed || (err && err.message === 'CANCEL')){ st.textContent = '已取消（文件可能不完整）'; return 'cancel'; }
      st.textContent = '保存失败（' + err.message + '），已切换为常规下载';
      return 'fail';
    }
  })();
}
function dlParallel(rangeUrl, total, threads, name, item, plainUrl){
  var bar = item.querySelector('.ubar i'), st = item.querySelector('.st');
  var n = Math.max(1, Math.min(threads, Math.ceil(total / (512 * 1024))));
  var seg = Math.ceil(total / n);
  var parts = new Array(n), loaded = 0, t0 = Date.now(), killed = false;
  var aborter = ('AbortController' in window) ? new AbortController() : null;
  item.querySelector('.cancel').onclick = function(){
    killed = true;
    if (aborter) aborter.abort();
  };
  function tick(){
    var pct = total ? Math.min(100, loaded / total * 100) : 0;
    bar.style.width = pct.toFixed(1) + '%';
    var secs = (Date.now() - t0) / 1000;
    var speed = secs > 0.4 ? loaded / secs : 0;
    st.textContent = pct.toFixed(1) + '% · ' + humanSize(loaded) + ' / ' + humanSize(total) +
                     ' · ' + humanSize(speed) + '/s · ' + n + ' 个分段连接';
  }
  function readPart(resp, idx){
    return new Promise(function(resolve, reject){
      var chunks = [], size = 0;
      if (!resp.body || !resp.body.getReader){
        return resp.arrayBuffer().then(function(buf){
          parts[idx] = new Blob([buf]);
          loaded += buf.byteLength; tick(); resolve();
        }).catch(reject);
      }
      var reader = resp.body.getReader();
      (function pump(){
        reader.read().then(function(o){
          if (o.done){
            parts[idx] = new Blob(chunks);
            resolve();
            return;
          }
          chunks.push(o.value);
          loaded += o.value.byteLength;
          tick();
          pump();
        }).catch(reject);
      })();
    });
  }
  var jobs = [];
  for (var i = 0; i < n; i++){
    (function(i){
      var s = i * seg, e = Math.min(total - 1, s + seg - 1);
      var opt = {headers: {'Range': 'bytes=' + s + '-' + e}};
      if (aborter) opt.signal = aborter.signal;
      jobs.push(fetch(rangeUrl, opt).then(function(r){
        if (r.status !== 206) throw new Error('HTTP ' + r.status);
        return readPart(r, i);
      }));
    })(i);
  }
  tick();
  Promise.all(jobs).then(function(){
    if (killed) return;
    var blob = new Blob(parts, {type: mimeOfName(name)});
    parts = null;
    if (blob.size !== total) throw new Error('长度对不上');
    saveBlob(blob, name);
    bar.style.width = '100%';
    item.querySelector('.cancel').style.display = 'none';
    DLDONE++;
    var secs = (Date.now() - t0) / 1000;
    st.textContent = '完成 · ' + humanSize(total) + ' · ' + secs.toFixed(1) + 's';
  }).catch(function(err){
    if (killed){
      st.textContent = '已取消';
    } else {
      st.textContent = '并发下载失败（' + err.message + '），已切换为常规下载';
      dlFallback(plainUrl);
    }
    item.querySelector('.cancel').style.display = 'none';
  });
}
/* ---------- 下载方式：每个使用者自己选（并发下载 / 单连接下载） ----------
   存在浏览器本地（localStorage），每台设备各记各的，重启浏览器也记得。
   老设备、老浏览器、弱网、或者分片总是失败 → 选单连接下载（一条连接顺序取，最兼容）。 */
var DLMODE = 'multi';
try { DLMODE = (localStorage.getItem('dlmode') === 'single') ? 'single' : 'multi'; } catch (_) {}
/* 文件名是否保留中文：某些安卓 WebView / 老下载器处理中文名会出错（后缀变成 .txt 等） */
var NAME_ZH = true;
try { NAME_ZH = (localStorage.getItem('dlname') !== 'ascii'); } catch (_) {}
/* 下载完成后是否自动收起进度面板 */
var DL_AUTOHIDE = false;
try { DL_AUTOHIDE = (localStorage.getItem('dlautohide') === '1'); } catch (_) {}

var MIME_BY_EXT = {png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', gif:'image/gif',
  bmp:'image/bmp', webp:'image/webp', ico:'image/x-icon', svg:'image/svg+xml', avif:'image/avif',
  pdf:'application/pdf', txt:'text/plain', md:'text/markdown', csv:'text/csv',
  doc:'application/msword', docx:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls:'application/vnd.ms-excel', xlsx:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt:'application/vnd.ms-powerpoint', pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  zip:'application/zip', rar:'application/vnd.rar', '7z':'application/x-7z-compressed',
  mp3:'audio/mpeg', wav:'audio/wav', m4a:'audio/mp4', mp4:'video/mp4', mov:'video/quicktime',
  mkv:'video/x-matroska', avi:'video/x-msvideo', json:'application/json', xml:'application/xml',
  html:'text/html', htm:'text/html', js:'text/javascript', py:'text/plain', cpp:'text/plain', c:'text/plain'};
function mimeOfName(name){
  var m = /\\.([a-z0-9]+)$/i.exec(name || '');
  return (m && MIME_BY_EXT[m[1].toLowerCase()]) || 'application/octet-stream';
}
var KIND_BY_EXT = {png:'image', jpg:'image', jpeg:'image', gif:'image', bmp:'image', webp:'image',
  ico:'image', svg:'image', avif:'image', pdf:'document', doc:'document', docx:'document',
  txt:'document', md:'document', csv:'sheet', xls:'sheet', xlsx:'sheet', ppt:'slides',
  pptx:'slides', zip:'archive', rar:'archive', '7z':'archive', mp3:'audio', wav:'audio',
  mp4:'video', mkv:'video', mov:'video'};
function asciiName(name){
  name = name || 'file';
  var m = /\\.([a-z0-9]+)$/i.exec(name);
  var ext = m ? m[1].toLowerCase() : '';
  var base = m ? name.slice(0, -m[0].length) : name;
  var out = base.replace(/[^\x20-\x7e]/g, '').replace(/[\\/:*?"<>|]+/g, '_')
                .replace(/[\\s_]{2,}/g, '_').replace(/^[ ._-]+|[ ._-]+$/g, '');
  if (!out) out = KIND_BY_EXT[ext] || 'file';
  if (out.length > 90) out = out.slice(0, 90).replace(/[ ._-]+$/g, '') || 'file';
  return out + (ext ? '.' + ext : '');
}
function dlName(name){
  return NAME_ZH ? (name || 'file') : asciiName(name);
}
function withNameMode(url){
  if (!url) return url;
  var p = url.split('?')[0];
  if (p !== '/download' && p !== '/zip' && p !== '/zipmulti') return url;
  url = url.replace(/([?&])nm=[^&]*/g, '').replace(/[?&]$/, '');
  return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'nm=' + (NAME_ZH ? 'zh' : 'ascii');
}
function applyDlMode(){
  var sel = $('advDlMode');
  if (sel) sel.value = (DLMODE === 'single') ? 'single' : 'multi';
  var wrap = $('advDlMode') && $('advDlMode').closest('.advrow');
  if (wrap && DLC.can === 0) wrap.style.display = 'none';
}

/* ---------- 兼容模式（给老设备 / 学习机 / 下载总失败的情况） ----------
   标准模式靠 fetch + 分片 + 另存为直写，很多功能机和定制浏览器（学习机上的“绿色上网”）
   既没有 File System Access，也不认分片拼包，结果就是下载出一堆 "null"、"now"、
   "____.pdf" 并全部失败。兼容模式把这条路全撤掉：直接导航到下载地址，
   由系统自己的下载器去存盘，名字用服务器给的 Content-Disposition。
   代价是没有进度条、单连接，但最不容易失败。 */
var COMPAT = false;
try { COMPAT = (localStorage.getItem('dlcompat') === '1'); } catch (_) {}
/* 下载直链通行证：兼容模式用它生成 /d/… 链接，下载器不带 Cookie 也能下 */
var DLTOKEN = "@DLTOKEN@";
function compatUrl(url, name){
  var qs = url.indexOf('?') >= 0 ? url.slice(url.indexOf('?') + 1) : '';
  return '/d/' + encodeURIComponent(name || 'file') + '?' + qs
       + (DLTOKEN ? ('&t=' + encodeURIComponent(DLTOKEN)) : '');
}
/* 打包下载同样可以带通行证；顺手把"先打缓存再并发下载"的 mt=1 去掉，直接边压边发（老设备更稳） */
function compatZipUrl(url){
  if (!DLTOKEN) return url;
  url = url.replace(/[?&]mt=1/, '');
  return url + (url.indexOf('?') >= 0 ? '&' : '?') + 't=' + encodeURIComponent(DLTOKEN);
}

function applyCompat(){
  var sel = $('advCompat');
  if (sel) sel.value = COMPAT ? '1' : '0';
  var wrap = sel && sel.closest('.advrow');
  if (wrap && DLC.can === 0) wrap.style.display = 'none';
  if (COMPAT){ hideDl(); }
}

/* 单连接下载：一条连接顺序取。有「另存为」就顺流写盘，没有就交给浏览器原生下载。 */
function startDlSingle(url, name, kind, size){
  var h = (DLC.picker === 0) ? null : pickSave(name);
  if (!h){
    dlFallback(url);                 /* 最兼容的路：浏览器自己下，单连接 */
    return;
  }
  h.then(function(handle){
    var item = dlItem(name);
    showDl();
    if (kind === 'zip'){
      tip('正在打包（单连接，边压缩边传输）', 5000);
      saveStreamToPicker(handle, url, item, 0).then(function(res){
        if (res === 'fail') dlFallback(url, item);
      });
    } else if (size && size > 0){
      saveStreamToPicker(handle, url, item, size).then(function(res){
        if (res === 'fail') dlFallback(url, item);
      });
    } else {
      fetch(url, {headers: {'Range': 'bytes=0-0'}}).then(function(r){
        var cr = r.headers.get('Content-Range') || '';
        try { if (r.body) r.body.cancel(); } catch (_) {}
        var slash = cr.lastIndexOf('/');
        var total = (r.status === 206 && slash >= 0) ? parseInt(cr.slice(slash + 1), 10) : 0;
        return saveStreamToPicker(handle, url, item, total);
      }).then(function(res){
        if (res === 'fail') dlFallback(url, item);
      }).catch(function(){ dlFallback(url, item); });
    }
  })['catch'](function(e){
    if (!e || e.name !== 'AbortError') dlFallback(url);
  });
}

/* 老路：浏览器原生下载（浏览器不支持「另存为」接口时才用，可能触发安全提示） */
function startDlLegacy(url, name, kind){
  if (kind === 'zip'){
    tip('正在准备打包（首次生成耗时较长，后续命中缓存可较快完成）', 6000);
    fetch(url + '&mt=1&probe=1').then(function(r){ return r.json(); }).then(function(j){
      if (!j || !j.ok || !j.size){ dlFallback(url); return; }
      showDl();
      var it = dlItem(name);
      dlParallel(url + '&mt=1', j.size, DLC.zip, name, it, url);
    }).catch(function(){ dlFallback(url); });
  } else {
    fetch(url, {headers: {'Range': 'bytes=0-0'}}).then(function(r){
      var cr = r.headers.get('Content-Range') || '';
      try { if (r.body) r.body.cancel(); } catch (_) {}
      if (r.status !== 206){
        dlFallback(url);
        return;
      }
      var slash = cr.lastIndexOf('/');
      var total = slash >= 0 ? parseInt(cr.slice(slash + 1), 10) : 0;
      if (!total || total > DLC.maxMB * 1024 * 1024 || DLC.file <= 1){
        dlFallback(url);        /* 太大：交给浏览器原生下载，免得吃内存 */
        return;
      }
      showDl();
      dlParallel(url, total, DLC.file, name, dlItem(name), url);
    }).catch(function(){ dlFallback(url); });
  }
}

function startDl(url, name, kind, size){
  name = dlName(name);
  url = withNameMode(url);
  if (COMPAT){                      /* 兼容模式：不碰 fetch / blob / 另存为，直接交给系统 */
    tip('兼容模式：已交由系统下载器处理，请在系统下载列表或通知中查看', 4000);
    location.href = (kind === 'file') ? compatUrl(url, name) : compatZipUrl(url);
    return;
  }
  if (DLMODE === 'single'){ startDlSingle(url, name, kind, size); return; }   /* 用户自己选了单连接下载 */
  if (DLC.picker === 0){ startDlLegacy(url, name, kind); return; }   /* config 里关了“另存为直写” */
  var h = pickSave(name);          /* 紧跟点击事件先开「另存为」，否则浏览器不认手势 */
  if (!h){ startDlLegacy(url, name, kind); return; }
  h.then(function(handle){
    var item = dlItem(name);
    showDl();
    if (kind === 'zip'){
      tip('正在准备打包（首次生成耗时较长，后续命中缓存可较快完成）', 6000);
      fetch(url + '&mt=1&probe=1').then(function(r){ return r.json(); }).then(function(j){
        if (j && j.ok && j.size){
          return saveWithPicker(handle, url + '&mt=1', j.size, DLC.zip, item);
        }
        return saveStreamToPicker(handle, url, item);      /* 文件夹太大：边压边发，单连接顺流写盘 */
      }).then(function(res){
        if (res === 'fail') dlFallback(url, item);
      }).catch(function(){
        saveStreamToPicker(handle, url, item).then(function(res){
          if (res === 'fail') dlFallback(url, item);
        });
      });
    } else if (size && size > 0){
      saveWithPicker(handle, url, size, DLC.file, item).then(function(res){
        if (res === 'fail') dlFallback(url, item);
      });
    } else {
      fetch(url, {headers: {'Range': 'bytes=0-0'}}).then(function(r){
        var cr = r.headers.get('Content-Range') || '';
        try { if (r.body) r.body.cancel(); } catch (_) {}
        var slash = cr.lastIndexOf('/');
        var total = (r.status === 206 && slash >= 0) ? parseInt(cr.slice(slash + 1), 10) : 0;
        if (!total){ hideDl(); dlFallback(url); return; }
        saveWithPicker(handle, url, total, DLC.file, item).then(function(res){
          if (res === 'fail') dlFallback(url, item);
        });
      }).catch(function(){ dlFallback(url, item); });
    }
  })['catch'](function(e){
    if (!e || e.name !== 'AbortError') startDlLegacy(url, name, kind);   /* 用户取消了就不管 */
  });
}

/* ---------- 复制直链：发给别人，对方登录后能直接打开/下载 ---------- */
function tip(msg, ms){
  var el = $('tip');
  if (!el){ el = document.createElement('div'); el.id = 'tip'; document.body.appendChild(el); }
  el.textContent = msg; el.classList.add('on');
  clearTimeout(tip._t);
  tip._t = setTimeout(function(){ el.classList.remove('on'); }, ms || 2600);
}
function copyLink(txt){
  function fallback(){
    var ta = document.createElement('textarea');
    ta.value = txt; ta.style.position = 'fixed'; ta.style.top = '-2000px'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    tip(ok ? ('链接已复制：' + txt) : ('复制失败，请手动复制：' + txt), ok ? 2600 : 6000);
  }
  if (navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(txt).then(function(){ tip('链接已复制：' + txt); }, fallback);
  } else {
    fallback();
  }
}

/* ---------- 预览 ---------- */
var PREV_PATH = '', PREV_NAME = '';
function updatePreviewDl(){
  if (!PREV_PATH) return;
  var el = $('mDown');
  if (!el) return;
  el.href = withNameMode('/download?p=' + encodeURIComponent(PREV_PATH));
  el.setAttribute('download', dlName(PREV_NAME));
}
function closeModal(){
  $('modal').classList.remove('on');
  $('mBody').innerHTML = '';
}
$('modal').addEventListener('click', function(e){ if (e.target === this) closeModal(); });
document.addEventListener('keydown', function(e){
  if (e.key !== 'Escape') return;
  closeModal();
  var im = $('infoModal'), tm = $('trashModal'), av = $('advModal');
  if (im) im.classList.remove('on');
  if (tm) tm.classList.remove('on');
  if (av) av.classList.remove('on');
});

function preview(p, name, kind){
  var body = $('mBody');
  $('mTitle').textContent = name;
  PREV_PATH = p; PREV_NAME = name;
  updatePreviewDl();
  body.innerHTML = '';
  var raw = '/raw?p=' + encodeURIComponent(p);
  if (kind === 'image'){
    var img = document.createElement('img'); img.src = raw; body.appendChild(img);
  } else if (kind === 'video'){
    var v = document.createElement('video'); v.src = raw; v.controls = true; v.autoplay = true;
    body.appendChild(v);
  } else if (kind === 'audio'){
    var a = document.createElement('audio'); a.src = raw; a.controls = true; a.autoplay = true;
    body.appendChild(a);
  } else if (kind === 'pdf'){
    var f = document.createElement('iframe'); f.src = raw; body.appendChild(f);
  } else if (kind === 'text'){
    var pre = document.createElement('pre'); pre.textContent = '正在加载'; body.appendChild(pre);
    fetch(raw).then(function(r){ return r.text(); })
      .then(function(t){ pre.textContent = t.length > 400000 ? t.slice(0, 400000) + String.fromCharCode(10, 10) + '…（内容过长，已截断）' : t; })
      .catch(function(){ pre.textContent = '读取失败，请直接下载查看。'; });
  } else {
    body.innerHTML = '<div class="mnote">该类型无法在线预览，请点击右上角「下载」查看。</div>';
  }
  $('modal').classList.add('on');
}

/* ---------- 头像：点顶栏自己的头像就能换（只有云空间用户能换） ---------- */
function avatarTypeByName(name){
  var m = /\\.[a-z0-9]+$/i.exec(name || '');
  var e = m ? m[1].toLowerCase() : '';
  return {png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', webp:'image/webp',
          gif:'image/gif', bmp:'image/bmp', ico:'image/x-icon', svg:'image/svg+xml',
          avif:'image/avif'}[e] || 'application/octet-stream';
}
function postAvatar(blob, ctype){
  tip('正在上传头像', 2500);
  fetch('/api/avatar', {method: 'POST', headers: {'Content-Type': ctype}, body: blob})
    .then(function(r){ return r.json(); })
    .then(function(j){
      if (j && j.ok){
        var el = $('meAvatar');
        if (el) el.src = '/avatar?t=' + Date.now();
        tip('头像已更新', 2500);
      } else {
        tip((j && j.error) || '头像上传失败', 4000);
      }
    }).catch(function(){ tip('头像上传失败（网络问题）', 4000); });
}
function rawAvatar(file){
  if (file.size > 12 * 1024 * 1024){
    tip('图片超出 12 MB，请压缩后再上传', 4000);
    return;
  }
  var t = file.type || avatarTypeByName(file.name);
  if (!t || t === 'application/octet-stream') t = avatarTypeByName(file.name);
  postAvatar(file, t);
}
function uploadAvatar(file){
  if (!file) return;
  var url = URL.createObjectURL(file);
  var img = new Image();
  var done = false;
  function fallback(){
    if (done) return;
    done = true;
    URL.revokeObjectURL(url);
    /* 浏览器解不开的格式（部分 ICO / SVG）按原文件上传，由服务端按文件头识别 */
    rawAvatar(file);
  }
  function normalized(blob){
    if (done) return;
    done = true;
    URL.revokeObjectURL(url);
    if (blob) postAvatar(blob, 'image/png');
    else rawAvatar(file);
  }
  img.onload = function(){
    try {
      var iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
      if (!iw || !ih){ fallback(); return; }
      /* 缩成 256×256 再传：手机拍的原图动辄几 MB，没必要占服务器 */
      var n = Math.min(256, Math.max(iw, ih));
      var cv = document.createElement('canvas');
      cv.width = cv.height = n;
      var cx = cv.getContext('2d');
      var scale = Math.min(n / iw, n / ih);
      var w = iw * scale, h = ih * scale;
      cx.clearRect(0, 0, n, n);
      cx.drawImage(img, (n - w) / 2, (n - h) / 2, w, h);
      cv.toBlob(normalized, 'image/png');
    } catch (e){
      fallback();
    }
  };
  img.onerror = fallback;
  img.src = url;
}
if ($('meAvBox')){
  if (CAN_AVATAR) $('meAvBox').style.cursor = 'pointer';
  $('meAvBox').onclick = function(){
    if (CAN_AVATAR) $('avatarInput').click();
  };
}
if ($('avatarInput')) $('avatarInput').onchange = function(){
  uploadAvatar(this.files && this.files[0]);
  this.value = '';
};

/* 初始化 */
$('sort').value = "@SORTVALUE@";
$('sort').onchange = function(){ goBrowse(1); };
function openAdv(){
  applyDlMode(); applyCompat();
  var nz = $('advNameZh'); if (nz) nz.value = NAME_ZH ? 'zh' : 'ascii';
  var ah = $('advAutoHide'); if (ah) ah.checked = DL_AUTOHIDE;
  $('advModal').classList.add('on');
}
function closeAdv(){ $('advModal').classList.remove('on'); }
if ($('btnAdv')) $('btnAdv').onclick = openAdv;
if ($('advModal')) $('advModal').addEventListener('click', function(e){ if (e.target === this) closeAdv(); });
if ($('advDlMode')) $('advDlMode').onchange = function(){
  DLMODE = (this.value === 'single') ? 'single' : 'multi';
  try { localStorage.setItem('dlmode', DLMODE); } catch (_) {}
  applyDlMode();
};
if ($('advCompat')) $('advCompat').onchange = function(){
  COMPAT = (this.value === '1');
  try { localStorage.setItem('dlcompat', COMPAT ? '1' : '0'); } catch (_) {}
  applyCompat();
};
if ($('advNameZh')) $('advNameZh').onchange = function(){
  NAME_ZH = (this.value !== 'ascii');
  try { localStorage.setItem('dlname', NAME_ZH ? 'zh' : 'ascii'); } catch (_) {}
  updatePreviewDl();
};
if ($('advAutoHide')) $('advAutoHide').onchange = function(){
  DL_AUTOHIDE = !!this.checked;
  try { localStorage.setItem('dlautohide', DL_AUTOHIDE ? '1' : '0'); } catch (_) {}
};
/* 没有下载权限时，把下载相关的三行一起藏掉 */
(function(){
  if (!DLC || DLC.can !== 0) return;
  ['advDlMode', 'advCompat', 'advNameZh'].forEach(function(id){
    var el = $(id), row = el && el.closest('.advrow');
    if (row) row.style.display = 'none';
  });
})();
applyCompat();
applyDlMode();
</script>
</body>
</html>
"""


# 三个页面统一挂页脚：把页脚 CSS 塞进 <style>，并在 </body> 前留 @FOOTER@ 占位
ERROR_PAGE = (ERROR_PAGE
              .replace("</style>", FOOTER_CSS + "</style>", 1)
              .replace("</body>", "@FOOTER@\n</body>", 1))

# 列表页新增的样式（备注气泡、批量条、缩略图、详情/回收站弹窗、常用目录）
MAIN_EXTRA_CSS = """
.noteq{width:22px;height:22px;border-radius:50%;border:1px solid #cfdbe5;background:#fff;color:#7b8a99;
  font-size:12px;line-height:20px;padding:0;cursor:pointer;flex:0 0 22px;margin-left:-4px}
.noteq:hover{border-color:#0f6fbd;color:#0f6fbd}
.pop{position:fixed;z-index:95;max-width:290px;background:#1b2b3a;color:#eaf3fa;font-size:12.5px;
  line-height:1.7;padding:11px 13px;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.24);display:none}
.pop.on{display:block}
.pop::after{content:'';position:absolute;left:14px;bottom:-6px;border:6px solid transparent;
  border-top-color:#1b2b3a;border-bottom:0}
.bulkbar{display:none;align-items:center;gap:8px;flex-wrap:wrap;background:#fff;border:1px solid #dbe4ec;
  border-radius:10px;padding:8px 10px;margin-bottom:10px;font-size:13px;color:#26455f}
.bulkbar.on{display:flex}
.bulkbar .btn{height:30px;font-size:12.5px}
.cbx{width:16px;height:16px;flex:0 0 16px;margin:0;accent-color:#0f6fbd;cursor:pointer}
.thumb{width:34px;height:34px;object-fit:cover;border-radius:8px;display:block;background:#eef3f7}
.row.sel{background:#eef5fb}
.mbox.light{background:#fff;max-width:min(720px,100%)}
.mhead2{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid #eef3f7}
.mhead2 .t{flex:1;min-width:0;font-size:14px;font-weight:600;color:#26455f;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.mhead2 button{background:#f2f6f9;border:0;color:#5b6b7b;border-radius:8px;padding:6px 10px;font-size:12.5px;cursor:pointer}
.mhead2 button svg{width:14px;height:14px;display:block}
.mhead2 button.mini{background:#fdeaea;color:#c0392b}
.ibody{max-height:70vh;overflow:auto;padding:6px 0}
.kv{display:flex;gap:12px;padding:8px 16px;font-size:13px;border-bottom:1px solid #f4f7fa}
.kv .k{width:86px;flex:0 0 86px;color:#8d9aa6}
.kv .v{flex:1;min-width:0;word-break:break-all;color:#26455f}
.kv .v a{color:#0f6fbd}
.mnote2{padding:22px 16px;color:#8d9aa6;font-size:13px;text-align:center}
.advsec{padding:14px 16px 6px;font-size:12px;font-weight:600;color:#8d9aa6;letter-spacing:.04em}
.advrow{padding:11px 16px 13px;border-bottom:1px solid #f1f5f9}
.advlab{font-size:13.5px;color:#26455f;font-weight:500;margin-bottom:7px}
.advsel{width:100%;padding:8px 10px;border:1px solid #dbe5ec;border-radius:9px;background:#fff;
  color:#26455f;font-size:13px;outline:none}
.advhint{margin-top:6px;color:#93a2af;font-size:11.8px;line-height:1.55}
.advcheck{display:flex;align-items:center;gap:7px;font-size:13px;color:#425d74}
.advcheck input{width:15px;height:15px;accent-color:#0f6fbd}
.advfoot{padding:13px 16px 18px;color:#a0adba;font-size:11.5px;line-height:1.6}
.trow{display:flex;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid #f4f7fa;font-size:13px}
.trow .nm{flex:1;min-width:0}
.trow .nm b{display:block;font-weight:500;color:#26455f;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trow .nm span{font-size:11.5px;color:#9aa8b5}
.trow button{background:#eef5fb;border:0;color:#0f6fbd;border-radius:7px;padding:6px 9px;font-size:12px;cursor:pointer}
.trow button.del{background:#fdeaea;color:#c0392b}
.favbox{position:relative;display:inline-flex}
.favdrop{position:absolute;top:38px;left:0;min-width:210px;max-height:300px;overflow:auto;background:#fff;
  border:1px solid #e3eaf0;border-radius:10px;box-shadow:0 10px 28px rgba(12,45,70,.16);padding:6px;display:none;z-index:40}
.favdrop.on{display:block}
.favit{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:7px;font-size:13px;color:#26455f}
.favit:hover{background:#f4f9fd}
.favit .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.favit .x{color:#b0bcc7;font-size:12px;padding:0 3px}
.favit .x:hover{color:#d43b3b}
.favempty{color:#9aa8b5;font-size:12.5px;padding:10px}
@media (max-width:640px){.whoTag{display:none}}
"""

LOGIN_PAGE = (LOGIN_PAGE
              .replace("</style>", FOOTER_CSS + """
.foot{color:rgba(255,255,255,.75);border-top:0;margin:14px 6px 0;padding-top:0;text-shadow:0 1px 2px rgba(0,0,0,.15)}
.foot a{color:rgba(255,255,255,.88)}
.foot a:hover{color:#fff}
</style>""", 1)
              .replace("</body>", "@FOOTER@\n</body>", 1))

MAIN_PAGE = (MAIN_PAGE
             .replace("</style>", MAIN_EXTRA_CSS + "</style>", 1)
             .replace("</style>", FOOTER_CSS + "</style>", 1)
             .replace("</body>", "@FOOTER@\n</body>", 1))

REG_PAGE = (REG_PAGE.replace("</style>", FOOTER_CSS + """
.foot{color:rgba(255,255,255,.75);border-top:0;margin:14px 6px 0;padding-top:0;text-shadow:0 1px 2px rgba(0,0,0,.15)}
.foot a{color:rgba(255,255,255,.88)}
.foot a:hover{color:#fff}
</style>""", 1)
            .replace("</body>", "@FOOTER@\n</body>", 1))


def build_login(error="", who="", note=""):
    block = ""
    if error:
        block = ('<div class="err"><svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
                 'stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/>'
                 '<path d="M12 7v6"/><circle cx="12" cy="16.8" r=".9" fill="currentColor"/></svg>'
                 '%s</div>') % html.escape(error)
    okblock = ('<div class="okmsg">%s</div>' % html.escape(note)) if note else ""
    reg = ('<p class="reghint">如需独立存储空间，可提交开通申请</p>'
           '<a class="regbtn" href="/register">开通申请</a>') if settings.flag("register_enabled") else ""
    return (LOGIN_PAGE.replace("@ERROR@", block)
            .replace("@OKMSG@", okblock)
            .replace("@WHO@", html.escape(who or "", quote=True))
            .replace("@REGISTER@", reg)
            .replace("@CONTACT@", _login_contact_html())
            .replace("@FOOTER@", build_footer()))


def _reg_page(title, body):
    return (REG_PAGE.replace("@TITLE@", html.escape(title))
            .replace("@BODY@", body)
            .replace("@FOOTER@", build_footer()))


def _reg_msg(message, ok):
    if not message:
        return ""
    return '<div class="msg %s">%s</div>' % ("ok" if ok else "err", html.escape(message))


def build_notice(seconds=5, again=False):
    """开通须知：须停留 N 秒方可确认；again=True 表示从申请页重新打开"""
    try:
        sec = max(0, min(60, int(seconds)))
    except (TypeError, ValueError):
        sec = 5
    if again:
        sec = 0          # 从申请页重新打开的须知：只供查阅，不再强制等待
    wait_js = ('var left=0;' if sec <= 0 else 'var left=%d;' % sec)
    btn_label = ("同意并继续申请" if sec <= 0 else "同意（%d 秒）" % sec)
    contact = _contact_values()
    contact_html = ""
    if contact:
        contact_html = ('<p style="margin-top:14px"><b>联系方式（如需咨询）</b></p>'
                        '<ul style="margin:6px 0 0 18px;padding:0;line-height:1.9">%s</ul>'
                        % "".join("<li>%s：%s</li>"
                                  % (html.escape(label), html.escape(val))
                                  for label, val in contact))
    body = """
<p class="sub">提交申请前，请完整阅读以下 5 项说明。阅读完毕并确认同意后，方可进入申请流程。</p>
<div class="notice">
 <p><b>一、主存储空间为主要资料区。</b>绝大部分资料与文件位于主存储空间（即日常登录的文件服务平台），日常查阅与下载均通过主存储空间完成，无需另行开通。</p>
 <p><b>二、本云空间适用于独立存储需求。</b>仅当确需一份仅本人可见的独立存储区域（其他访问者无法查看您的文件，您亦无法查看他人文件）时，方需在此申请开通。</p>
 <p><b>三、开通须经审批，并非提交即生效。</b>流程为：提交申请 → 管理员审批 → 管理员发放 4 位验证码 → 凭「姓名 + 验证码」自行设置密码，账号方可启用。</p>
 <p><b>四、密码仅由本人掌握。</b>服务器仅保存加密摘要，管理员亦无法查看明文；如遗忘密码，须由管理员彻底删除原账号后重新申请。</p>
 <p><b>五、每自然日仅可提交一次申请。</b>重复提交将被拒绝；姓名一经注册即固定，不予变更。</p>
%s
</div>
<form method="post" action="/register" id="agreeForm" autocomplete="off">
 <input type="hidden" name="agree" value="1">
 <button type="submit" id="okBtn" %s>%s</button>
</form>
<a class="back" href="%s">%s</a>
<script>
(function(){
  var btn=document.getElementById('okBtn');
  %s
  if(left<=0){ btn.disabled=false; btn.textContent='同意并继续申请'; return; }
  var t=setInterval(function(){
    left--;
    if(left<=0){ clearInterval(t); btn.disabled=false; btn.textContent='同意并继续申请'; }
    else { btn.textContent='同意（'+left+' 秒）'; }
  },1000);
})();
</script>
""" % (contact_html, "disabled" if sec > 0 else "", btn_label,
       "/register/apply" if again else "/login",
       "返回申请页" if again else "取消并返回登录", wait_js)
    return _reg_page("云空间开通须知", body)


def build_apply(message="", ok=False, who="", remark=""):
    """第二步：填写申请人姓名（必填）与备注（选填）并提交申请"""
    body = """
<a href="/register?again=1" title="重新阅读开通须知" aria-label="重新阅读开通须知"
   style="position:fixed;right:18px;top:18px;z-index:9;width:36px;height:36px;border-radius:50%%;
   background:#eef6fc;color:#0f6fbd;border:1px solid #cfe4f5;display:flex;align-items:center;
   justify-content:center;font-weight:700;text-decoration:none;font-size:16px;
   box-shadow:0 2px 8px rgba(15,111,189,.12)">?</a>
<p class="sub">本步骤需填写申请人姓名，备注为选填项。提交后管理员将在管理控制台收到该申请；审批通过后系统生成 4 位验证码。</p>
%s
<form method="post" action="/register/apply" autocomplete="off">
 <label for="who">申请人姓名</label>
 <input id="who" name="who" type="text" maxlength="24" required value="%s" placeholder="2~24 个字符，不得包含 \\ / : * ? 等符号">
 <label for="remark">备注（选填）</label>
 <textarea id="remark" name="remark" rows="3" maxlength="200" placeholder="如有特殊原因或用途，可在此说明，便于管理员审核；也可不填"
   style="width:100%%;box-sizing:border-box;min-height:86px;border:1px solid #dbe3ea;border-radius:11px;
   padding:12px 14px;font-size:15px;line-height:1.6;color:#12293f;background:#f8fafc;
   outline:none;resize:vertical;font-family:inherit">%s</textarea>
 <button type="submit">确认提交</button>
</form>
<a class="ghostbtn" href="/register/set">已通过审批？凭验证码设置密码</a>
<a class="back" href="/login">返回登录</a>
""" % (_reg_msg(message, ok), html.escape(who or "", quote=True),
       html.escape(remark or ""))
    return _reg_page("提交云空间开通申请", body)


def build_setpw(message="", ok=False, who="", code=""):
    """第三步：凭 4 位验证码设置密码并完成注册"""
    body = """
<p class="sub">请填写申请时使用的姓名、管理员发放的 4 位验证码，以及本人拟使用的密码。三项信息校验一致后，账号方可创建。</p>
%s
<form method="post" action="/register/set" autocomplete="off">
 <label for="who">已通过审批的申请人姓名</label>
 <input id="who" name="who" type="text" maxlength="24" required value="%s" placeholder="申请时填写的姓名">
 <label for="code">4 位验证码</label>
 <input id="code" name="code" type="text" inputmode="numeric" pattern="\\d{4}" maxlength="4" required value="%s" placeholder="管理员提供的 4 位数字">
 <label for="pw">设置密码（至少 8 位）</label>
 <input id="pw" name="pw" type="password" required minlength="4" maxlength="64">
 <label for="pw2">再次输入密码</label>
 <input id="pw2" name="pw2" type="password" required minlength="4" maxlength="64">
 <button type="submit">完成注册</button>
</form>
<a class="back" href="/login">返回登录</a>
""" % (_reg_msg(message, ok), html.escape(who or "", quote=True), html.escape(code or "", quote=True))
    return _reg_page("凭验证码设置密码", body)


def build_crumb(rel):
    parts = rel.split("/") if rel else []
    out = ['<a class="crumb" href="/browse"><svg viewBox="0 0 24 24" width="15" height="15" '
           'fill="currentColor" style="vertical-align:-3px"><use href="#i-home"/></svg> 根目录</a>']
    cur = []
    for i, p in enumerate(parts):
        cur.append(p)
        if i == len(parts) - 1:
            out.append('<span class="sep">›</span><span class="here">%s</span>' % html.escape(p))
        else:
            out.append('<span class="sep">›</span><a class="crumb" href="/browse?p=%s">%s</a>'
                       % (q("/".join(cur)), html.escape(p)))
    # 返回上级
    if parts:
        parent = "/".join(parts[:-1])
        out.insert(0, '<a class="backbtn" href="/browse%s"><svg viewBox="0 0 24 24">'
                      '<use href="#i-back"/></svg>上级</a>'
                      % (("?p=" + q(parent)) if parent else ""))
    return "".join(out)

def _natural_key(text):
    parts = re.split(r"(\d+)", text.lower())
    return [(1, int(p), "") if p.isdigit() else (0, 0, p) for p in parts]


def _sort_key_factory(key):
    if key == "mtime":
        return lambda t: t[2].st_mtime if t[2] else 0
    if key == "size":
        return lambda t: 0 if t[1] else (t[2].st_size if t[2] else 0)
    if key == "type":
        return lambda t: ("0folder" if t[1] else EXT_ICON.get(ext_of(t[0]), "i-file"),
                          _natural_key(t[0]))
    return lambda t: _natural_key(t[0])


def sort_entries(items, key, order):
    reverse = (order == "desc")
    kf = _sort_key_factory(key)
    dirs = sorted([t for t in items if t[1]], key=kf, reverse=reverse)
    files = sorted([t for t in items if not t[1]], key=kf, reverse=reverse)
    return dirs + files


def render_rows(abspath, rel, sort_key="name", order="asc", kw="", page=1, role=ROLE_FULL,
                perms=None, root=None):
    perms = perms if perms is not None else role_perms(role)
    can_select = bool(perms & {"delete", "download"})
    can_move = ("delete" in perms) and bool(perms & {"upload", "mkdir"})
    searching = bool(kw)
    scanned = 0
    truncated = False
    try:
        if searching:
            # 跨子目录搜索：当前文件夹 + 下面所有的层都找一遍（有扫描预算，不会把机器拖死）
            found, scanned, truncated = search_entries(abspath, kw, root=root)
            ordered = found
        else:
            entries = scan_entries(abspath)
            ordered = [(  (rel + "/" + name) if rel else name, name, is_dir, st)
                       for (name, is_dir, st) in sort_entries(entries, sort_key, order)]
    except PermissionError:
        return ('<div class="empty"><svg viewBox="0 0 24 24"><use href="#i-folder"/></svg>'
                '当前身份无权访问该目录</div>', 0, 0, 1, 1)
    except FileNotFoundError:
        return ('<div class="empty">目录不存在或已被移动</div>', 0, 0, 1, 1)
    except OSError as exc:
        return ('<div class="empty">无法读取该目录（%s）</div>'
                % html.escape(str(exc)), 0, 0, 1, 1)

    if searching:
        ordered = list(ordered)     # search_entries 已经按相关度排好，不再重排
    else:
        ordered = list(ordered)

    total = len(ordered)
    total_size = sum(0 if t[2] else (t[3].st_size if t[3] else 0) for t in ordered)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page_no = min(max(1, page), pages)
    page_items = ordered[(page_no - 1) * PER_PAGE: page_no * PER_PAGE]

    rows = []
    for child_rel, name, is_dir, st in page_items:
        size = 0 if is_dir else (st.st_size if st else 0)
        mtime = st.st_mtime if st else 0
        sym, color = icon_for(name, is_dir)
        sub_dir = child_rel[:-len(name)].rstrip("/") if child_rel != name else ""
        href = q(child_rel)                       # 用于 URL
        attr_p = html.escape(child_rel, quote=True)   # 用于 data-p（原始相对路径）
        attr_n = html.escape(name, quote=True)        # 用于 data-name（原始文件名）
        js_p = html.escape(child_rel.replace("\\", "\\\\").replace("'", "\\'"), quote=True)
        js_n = html.escape(name.replace("\\", "\\\\").replace("'", "\\'"), quote=True)
        kind = "" if is_dir else preview_kind(name)
        ext = "" if is_dir else ext_of(name)
        type_key = "0folder" if is_dir else (ext or "zzz")
        where = (" · 在 " + sub_dir) if (searching and sub_dir) else ""

        if is_dir:
            main_open = '<a class="row-main" href="/browse?p=%s">' % href
            main_close = '</a>'
            tag = "文件夹" + where
            acts = ""
            if "zip" in perms:
                acts += ('<a class="act" href="/zip?p=%s" title="打包下载"><svg viewBox="0 0 24 24">'
                         '<use href="#i-zip"/></svg></a>' % href)
                acts += ('<button class="act" data-act="copy" data-link="/zip?p=%s" title="复制打包链接">'
                         '<svg viewBox="0 0 24 24"><use href="#i-share"/></svg></button>' % href)
            acts += ('<button class="act" data-act="info" data-p="%s" data-name="%s" data-dir="1" title="详情">'
                     '<svg viewBox="0 0 24 24"><use href="#i-preview"/></svg></button>' % (attr_p, attr_n))
            acts += ('<button class="act" data-act="fav" data-p="%s" data-name="%s" title="收藏此目录">'
                     '<svg viewBox="0 0 24 24"><use href="#i-link"/></svg></button>' % (attr_p, attr_n))
            if can_move:
                acts += ('<button class="act" data-act="cut" data-p="%s" data-name="%s" title="剪切，去目标目录粘贴">'
                         '<svg viewBox="0 0 24 24"><use href="#i-back"/></svg></button>' % (attr_p, attr_n))
            if "rename" in perms:
                acts += ('<button class="act" data-act="ren" data-p="%s" data-name="%s" data-txt="重命名" title="重命名">'
                         '<svg viewBox="0 0 24 24"><use href="#i-edit"/></svg></button>' % (attr_p, attr_n))
            if "delete" in perms:
                acts += ('<button class="act del" data-act="del" data-p="%s" data-name="%s" title="删除（移入回收站）">'
                         '<svg viewBox="0 0 24 24"><use href="#i-trash"/></svg></button>' % (attr_p, attr_n))
            icon_html = '<span class="ico" style="color:%s"><svg viewBox="0 0 24 24"><use href="#%s"/></svg></span>' % (color, sym)
        else:
            main_open = '<div class="row-main" onclick="preview(\'%s\',\'%s\',\'%s\')">' % (js_p, js_n, kind)
            main_close = '</div>'
            tag = ("%s · %s" % ((ext.upper() + " 文件") if ext else "文件", human_size(size))) + where
            acts = ""
            if "download" in perms:
                acts += ('<a class="act" href="/download?p=%s" title="下载"><svg viewBox="0 0 24 24">'
                         '<use href="#i-down"/></svg></a>' % href)
                acts += ('<button class="act" data-act="copy" data-link="/download?p=%s" title="复制下载链接">'
                         '<svg viewBox="0 0 24 24"><use href="#i-share"/></svg></button>' % href)
            if "preview" in perms:
                acts += ('<button class="act" data-act="prev" data-p="%s" data-name="%s" data-kind="%s" title="预览">'
                         '<svg viewBox="0 0 24 24"><use href="#i-preview"/></svg></button>' % (attr_p, attr_n, kind))
            acts += ('<button class="act" data-act="info" data-p="%s" data-name="%s" data-dir="0" title="详情">'
                     '<svg viewBox="0 0 24 24"><use href="#i-preview"/></svg></button>' % (attr_p, attr_n))
            if can_move:
                acts += ('<button class="act" data-act="cut" data-p="%s" data-name="%s" title="剪切，去目标目录粘贴">'
                         '<svg viewBox="0 0 24 24"><use href="#i-back"/></svg></button>' % (attr_p, attr_n))
            if "rename" in perms:
                acts += ('<button class="act" data-act="ren" data-p="%s" data-name="%s" data-txt="重命名" title="重命名">'
                         '<svg viewBox="0 0 24 24"><use href="#i-edit"/></svg></button>' % (attr_p, attr_n))
            if "delete" in perms:
                acts += ('<button class="act del" data-act="del" data-p="%s" data-name="%s" title="删除（移入回收站）">'
                         '<svg viewBox="0 0 24 24"><use href="#i-trash"/></svg></button>' % (attr_p, attr_n))
            # 图片给一个小缩略图（小于 3MB 才出，避免大图把小水管拖死）
            if kind == "image" and size and size <= 3 * 1024 * 1024:
                icon_html = '<span class="ico" style="padding:0"><img class="thumb" loading="lazy" src="/thumb?p=%s" alt=""></span>' % href
            else:
                icon_html = '<span class="ico" style="color:%s"><svg viewBox="0 0 24 24"><use href="#%s"/></svg></span>' % (color, sym)

        cbx = ('<input type="checkbox" class="cbx" data-p="%s" data-name="%s" data-dir="%d">'
               % (attr_p, attr_n, 1 if is_dir else 0)) if can_select else ""

        rows.append(
            '<div class="row" draggable="true" data-name="%s" data-size="%d" data-mtime="%.0f"'
            ' data-dir="%d" data-type="%s" data-link="%s">%s'
            '%s%s<span class="nm"><span class="n">%s</span><span class="tag">%s</span></span>%s'
            '<span class="col-size">%s</span><span class="col-time">%s</span>'
            '<span class="acts">%s</span></div>'
            % (
                attr_n, size, mtime, 1 if is_dir else 0, type_key,
                ("/zip?p=" if is_dir else "/download?p=") + href,
                cbx, main_open, icon_html,
                attr_n, html.escape(tag, quote=True), main_close,
                "" if is_dir else human_size(size),
                fmt_time(mtime),
                acts,
            )
        )

    if not rows:
        if total == 0 and kw:
            body = '<div class="empty">未找到与「%s」的文件或文件夹（已搜索当前文件夹和它下面全部子目录）</div>' % html.escape(kw)
        else:
            body = ('<div class="empty"><svg viewBox="0 0 24 24"><use href="#i-folder"/></svg>'
                    '这个该目录为空</div>')
        return body, total, total_size, pages, page_no
    return "".join(rows), total, total_size, pages, page_no


def _page_url(rel, sort_key, order, kw, page):
    params = []
    if rel:
        params.append(("p", rel))
    if sort_key != "name" or order != "asc":
        params.append(("sort", sort_key))
        params.append(("order", order))
    if kw:
        params.append(("q", kw))
    if page and page > 1:
        params.append(("page", str(page)))
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return "/browse" + (("?" + qs) if qs else "")


def build_pager(rel, sort_key, order, kw, page, pages):
    if pages <= 1:
        return ""
    out = ['<div class="pager">']
    if page > 1:
        out.append('<a class="pgbtn" href="%s">上一页</a>'
                   % _page_url(rel, sort_key, order, kw, page - 1))
    else:
        out.append('<span class="pgbtn off">上一页</span>')

    lo = max(1, page - 2)
    hi = min(pages, page + 2)
    if lo > 1:
        out.append('<a class="pgbtn" href="%s">1</a>' % _page_url(rel, sort_key, order, kw, 1))
        if lo > 2:
            out.append('<span class="pgdots">…</span>')
    for i in range(lo, hi + 1):
        cls = "pgbtn now" if i == page else "pgbtn"
        out.append('<a class="%s" href="%s">%d</a>'
                   % (cls, _page_url(rel, sort_key, order, kw, i), i))
    if hi < pages:
        if hi < pages - 1:
            out.append('<span class="pgdots">…</span>')
        out.append('<a class="pgbtn" href="%s">%d</a>'
                   % (_page_url(rel, sort_key, order, kw, pages), pages))

    if page < pages:
        out.append('<a class="pgbtn" href="%s">下一页</a>'
                   % _page_url(rel, sort_key, order, kw, page + 1))
    else:
        out.append('<span class="pgbtn off">下一页</span>')
    out.append('</div>')
    return "".join(out)


_DROP_MASK = ('<div class="dropmask" id="dropmask">\n'
              '  <div class="box">\n'
              '    <svg viewBox="0 0 24 24" fill="currentColor"><use href="#i-up"/></svg>\n'
              '    松开即可上传至当前目录\n'
              '  </div>\n'
              '</div>')


def _dl_token_for(who, root, perms):
    """页面里带一张下载通行证：兼容模式把链接换成 /d/…?t=…，下载器不带 Cookie 也能下"""
    if "download" not in perms:
        return ""
    try:
        from . import dltoken
        return dltoken.make({"name": who or "", "root": root or "", "perms": perms})
    except Exception:      # noqa: BLE001  —— 签名出问题也不能把页面弄挂
        return ""


def _dl_cfg_json(perms):
    """给前端的并发下载参数。单个任务开的连接数不能超过服务器线程池，
    否则一堆连接排在门外反而更慢。"""
    workers = settings.WORKERS
    if not workers:      # 没在 config 里写死就是按 CPU 算，跟 app.py 的 default_workers 一致
        workers = max(8, min(24, (os.cpu_count() or 4) * 2))
    file_t = max(1, min(settings.FILE_THREADS, workers))
    zip_t = max(1, min(settings.ZIP_THREADS, workers))
    if "download" not in perms:
        file_t = zip_t = 1
    up = max(1, min(8, settings.integer("upload_parallel", 1, 8)))
    return ('{"file": %d, "zip": %d, "maxMB": %d, "picker": %d, "can": %d, "up": %d}' %
            (file_t, zip_t, settings.THREADED_MAX_MB, 1 if settings.SAVE_PICKER else 0,
             1 if "download" in perms else 0, up))


def _tools_html(perms):
    """工具栏：没有权限的按钮直接不生成，剩下的自然并排（不留空位）"""
    out = []
    if "upload" in perms:
        out.append('<button class="btn primary" id="btnUp"><svg viewBox="0 0 24 24">'
                   '<use href="#i-up"/></svg>上传文件</button>')
        out.append('<button class="btn" id="btnUpDir"><svg viewBox="0 0 24 24">'
                   '<use href="#i-upload-folder"/></svg>上传目录</button>')
    if "mkdir" in perms:
        out.append('<button class="btn" id="btnMk"><svg viewBox="0 0 24 24">'
                   '<use href="#i-newfolder"/></svg>新建目录</button>')
    out.append('<div class="favbox"><button class="btn" id="btnFavList"><svg viewBox="0 0 24 24">'
               '<use href="#i-link"/></svg>常用目录</button>'
               '<div class="favdrop" id="favdrop"></div></div>')
    out.append('<button class="btn" id="btnFavAdd" title="把当前文件夹加进常用目录">收藏当前目录</button>')
    if ("delete" in perms) and bool(perms & {"upload", "mkdir"}):
        out.append('<button class="btn" id="btnPaste" style="display:none">粘贴到当前</button>')
    if "delete" in perms:
        out.append('<button class="btn" id="btnTrash"><svg viewBox="0 0 24 24">'
                   '<use href="#i-trash"/></svg>回收站</button>')
    return "".join(out)


def _disk_free_text(path):
    """存储可用空间空间，取不到就返回空字符串（页面上就不显示这一段）"""
    try:
        usage = shutil.disk_usage(os.path.abspath(path))
    except (OSError, AttributeError):
        return ""
    free = human_size(usage.free)
    try:
        pct = int(round(usage.free * 100.0 / usage.total))
    except ZeroDivisionError:
        return free
    return "%s（可用 %d%%）" % (free, pct)


def build_page(rel, abspath, sort_key="name", order="asc", kw="", page=1,
               root=None, role=ROLE_FULL, perms=None, admin=False, who="", avatar="",
               can_avatar=False):
    perms = perms if perms is not None else role_perms(role)
    rows, count, size, pages, page_no = render_rows(abspath, rel, sort_key, order, kw, page,
                                                    role=role, perms=perms, root=root)
    if rel:
        title = rel.rstrip("/").split("/")[-1]
    else:
        title = os.path.basename(os.path.abspath(root or Config.root))
    stat = "共 %d 项 · %s" % (count, human_size(size))
    if kw:
        stat = "搜索「%s」（含全部子目录）· %s" % (kw, stat)
    if pages > 1:
        stat += " · 第 %d/%d 页" % (page_no, pages)
    # 存储可用空间空间（只看一眼，开销很小），方便你知道还剩多少地方能放东西
    free_txt = _disk_free_text(root or Config.root)
    if free_txt:
        stat += " · 存储可用空间 %s" % free_txt
    sort_value = "%s|%d" % (sort_key, 1 if order == "asc" else 0)
    admin_link = ('<button class="logout" onclick="location.href=\'/admin\'" '
                  'title="管理控制台">设置</button>') if admin else ""
    bulk_btn = ('<button class="btn" id="btnBulk"><svg viewBox="0 0 24 24"><use href="#i-file"/></svg>'
                '批量操作</button>') if perms & {"delete", "download"} else ""
    page_html = (MAIN_PAGE
                 .replace("@SPRITE@", get_sprite())
                 .replace("@CRUMB@", build_crumb(rel))
                 .replace("@TOOLS@", _tools_html(perms))
                 .replace("@BULKBTN@", bulk_btn)
                 .replace("@AVATAR@", html.escape(avatar or "/img/avatar_default.svg", quote=True))
                 .replace("@WHO@", html.escape(who or "", quote=True))
                 .replace("@ADMINLINK@", admin_link)
                 .replace("@DROPMASK@", _DROP_MASK if "upload" in perms else "")
                 .replace("@ROWS@", rows)
                 .replace("@PAGER@", build_pager(rel, sort_key, order, kw, page_no, pages))
                 .replace("@STAT@", html.escape(stat))
                 .replace("@DIRJSON@", rel.replace("\\", "\\\\").replace('"', '\\"'))
                 .replace("@CAN_UPLOAD@", "true" if "upload" in perms else "false")
                 .replace("@CAN_MKDIR@", "true" if "mkdir" in perms else "false")
                 .replace("@CAN_AVATAR@", "true" if can_avatar else "false")
                 .replace("@DLCFG@", _dl_cfg_json(perms))
                 .replace("@KWVALUE@", html.escape(kw, quote=True))
                 .replace("@SORTVALUE@", sort_value)
                 .replace("@DLTOKEN@", _dl_token_for(who, root, perms))
                 .replace("@TITLE@", html.escape(title))
                 .replace("@FOOTER@", build_footer()))
    return page_html
