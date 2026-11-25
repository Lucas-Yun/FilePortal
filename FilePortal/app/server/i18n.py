# -*- coding: utf-8 -*-
"""FilePortal 轻量双语层（仅 zh / en）。

不修改业务逻辑，只在输出 HTML 前翻译“界面标签类”元素，避免误改文件名、
目录名、用户姓名等真实数据。语言选择用 Cookie 记忆，页面右下角切换。
"""

import re

COOKIE_NAME = "fp_lang"
SUPPORTED = ("zh", "en")

# 只翻译这些标签的文本，文件列表里的文件名/路径不会被触碰。
_TEXT_TAGS = ("title", "h1", "h2", "h3", "label", "button", "th", "option")
_TEXT_CLASSES = ("sub", "hint", "tip", "empty", "cTitle", "reghint", "foot",
                 "notice", "msg", "err", "okmsg", "stat", "cardtitle", "muted",
                 "advhint", "advfoot", "favempty",
                 "pgbtn", "backbtn", "regbtn", "ghostbtn", "back", "crumb",
                 "regbadge", "regaskt", "regasks", "applylink", "noticepill")

_MAP = {
    # 登录 / 注册 / 须知
    "文件服务平台": "FilePortal",
    "请输入访问者姓名与访问密码，验证通过后进入文件存储区域":
        "Enter your name and access password to open the file workspace.",
    "访问者姓名": "Name",
    "请输入您的真实姓名": "Enter your name",
    "访问密码": "Password",
    "请输入访问密码": "Enter your password",
    "登 录": "Sign in",
    "登录": "Sign in",
    "用户须知": "User notice",
    "本服务必须获得授权后方可使用。": "This service requires authorization before use.",
    "使用前请先向开发者确认是否已授权；如尚未授权，请先联系开发者完成授权，再使用本服务。":
        "Confirm authorization with the developer before use. If you are not authorized, contact the developer first.",
    "开发者联系方式": "Developer contact",
    "微信": "WeChat",
    "电话": "Phone",
    "邮箱": "Email",
    "如需独立存储空间，可提交开通申请": "Need a private workspace? Submit an access request.",
    "开通申请": "Request access",
    "返回申请页": "Back to application",
    "云空间开通须知": "Workspace access notice",
    "取消并返回登录": "Cancel and return to sign in",
    "同意并继续申请": "Agree and continue",
    "凭验证码设置密码": "Set password with verification code",
    "注册": "Register",
    "还没有云空间账号？": "No workspace account yet?",
    "注册云空间账号": "Create workspace account",
    "已通过管理员审批": "Approved by administrator",
    "请填写申请时的姓名、管理员发放的 4 位验证码，并设置本人密码。三项校验一致后，云空间账号才会创建。":
        "Enter the name used in your request, the 4-digit code from the administrator, and choose a password. The account is created only when all three match.",
    "4 位验证码": "4-digit verification code",
    "设置密码（至少 8 位）": "Password (at least 8 characters)",
    "至少 8 位，建议字母和数字组合": "At least 8 characters; letters and numbers recommended",
    "再次输入密码": "Enter password again",
    "完成注册": "Create account",
    "还没有提交过云空间申请？": "Haven't submitted a workspace request?",
    "只有管理员审批通过并发放验证码后，才能在这一页直接设置密码。":
        "You can set a password here only after an administrator approves your request and issues a verification code.",
    "未获得管理员审批？点击这里申请 →": "Not approved by the administrator? Apply here →",
    "返回登录": "Back to sign in",
    "开通须知": "Access notice",
    "第 1 步 · 提交申请": "Step 1 · Submit request",
    "填写申请人姓名和备注。提交后管理员会在管理控制台收到申请；审批通过后会生成 4 位验证码。":
        "Enter the applicant name and an optional note. The administrator receives the request in the console; approval generates a 4-digit code.",
    "已有审批？返回注册 · 凭验证码设密":
        "Already approved? Return to registration · Set password with code",
    "重新阅读开通须知": "Read the access notice again",
    "确认提交": "Submit",
    "请先完整阅读以下 5 项说明。停留 5 秒后可点击「同意」，再进入申请页。":
        "Read all five notes below. After 5 seconds you can click Agree to continue to the request form.",
    "提交云空间开通申请": "Submit workspace request",
    "第一步：阅读须知并点击同意": "Step 1: Read the notice and agree",
    "第二步：填写申请人姓名（必填）与备注（选填）并提交申请":
        "Step 2: Enter your name and an optional note, then submit",
    "第三步：凭 4 位验证码设置密码并完成注册":
        "Step 3: Set a password with the 4-digit verification code",
    "申请人姓名": "Applicant name",
    "备注（选填）": "Note (optional)",
    "备注": "Note",
    "验证码": "Verification code",
    "确认密码": "Confirm password",
    "设置密码": "Set password",
    "姓名不能为空": "Name is required.",
    "两次输入的密码不一致": "Passwords do not match.",
    "注册功能当前未开放": "Registration is currently disabled.",
    "禁止访问": "Access denied.",
    "密码错误次数过多，请于 %d 秒后重试": "Too many failed attempts. Try again in %d seconds.",
    "登录请求过于频繁，请于 %d 秒后重试": "Too many login requests. Try again in %d seconds.",
    "登录已过期，请重新登录。": "Your session has expired. Please sign in again.",
    "登录状态已失效，请重新登录。": "Your session is no longer valid. Please sign in again.",
    "该账号已被禁止访问。": "This account has been blocked.",
    "该账号已不存在，请重新登录。": "This account no longer exists. Please sign in again.",
    "该账号已在其他设备登录，当前设备已自动退出。":
        "This account signed in on another device. This device has been signed out.",

    # 文件浏览 / 工具栏
    "根目录": "Root",
    "上级": "Up",
    "上传文件": "Upload files",
    "上传目录": "Upload folder",
    "新建目录": "New folder",
    "批量操作": "Batch actions",
    "回收站": "Recycle bin",
    "常用目录": "Favorites",
    "收藏当前目录": "Favorite this folder",
    "粘贴到当前": "Paste here",
    "刷新": "Refresh",
    "搜索": "Search",
    "全选": "Select all",
    "文件名": "Name",
    "名称": "Name",
    "大小": "Size",
    "修改时间": "Modified",
    "类型": "Type",
    "操作": "Actions",
    "下载": "Download",
    "预览": "Preview",
    "详情": "Details",
    "重命名": "Rename",
    "删除": "Delete",
    "彻底删除": "Delete permanently",
    "还原": "Restore",
    "清空": "Empty",
    "复制": "Copy",
    "移动": "Move",
    "剪切": "Cut",
    "粘贴": "Paste",
    "复制下载链接": "Copy download link",
    "复制打包链接": "Copy ZIP link",
    "收藏此目录": "Favorite this folder",
    "剪切，去目标目录粘贴": "Cut and paste in another folder",
    "删除（移入回收站）": "Delete (move to recycle bin)",
    "打包下载": "Download ZIP",
    "上一页": "Previous",
    "下一页": "Next",
    "共 %d 项 · %s": "%d items · %s",
    "第 %d/%d 页": "Page %d/%d",
    "· 第 %d/%d 页": "· Page %d/%d",
    "· 存储可用空间 %s": "· Storage free %s",
    "%s（可用 %d%%）": "%s (%d%% free)",
    "目录不存在或已被移动": "The folder does not exist or has been moved.",
    "当前身份无权访问该目录": "You do not have access to this folder.",
    "这个该目录为空": "This folder is empty.",
    "无法读取该目录（%s）": "Cannot read this folder (%s)",
    "未找到与「%s」的文件或文件夹（已搜索当前文件夹和它下面全部子目录）":
        "No files or folders matching %s were found, including all subfolders.",
    "搜索「%s」（含全部子目录）· %s": "Search %s (all subfolders) · %s",
    "确认": "Confirm",
    "设置": "Settings",
    "高级设置": "Advanced settings",
    "注销": "Sign out",
    "退出登录": "Sign out",
    "名称 升序": "Name ascending",
    "名称 降序": "Name descending",
    "修改时间 升序": "Modified ascending",
    "修改时间 降序": "Modified descending",
    "大小 升序": "Size ascending",
    "大小 降序": "Size descending",
    "并发下载（多连接，速度快）": "Concurrent download (multi-connection, faster)",
    "单连接下载（兼容老设备）": "Single-connection download (legacy devices)",
    "并发下载会把文件切成多段同时取；网络不稳或老设备容易出错时改用单连接。":
        "Concurrent download splits a file into ranges. Use single-connection mode on unstable networks or older devices.",
    "标准模式（推荐）": "Standard mode (recommended)",
    "兼容模式（系统下载器）": "Compatibility mode (system downloader)",
    "兼容模式交给系统自带下载器直接存盘，没有进度条，但老旧浏览器和学习机最不容易失败。":
        "Compatibility mode hands the file to the system downloader. There is no progress bar, but it works best on legacy browsers and study devices.",
    "保留中文（推荐）": "Keep Chinese names (recommended)",
    "仅英文和数字（兼容老旧设备）": "ASCII only (legacy devices)",
    "部分安卓 WebView 处理中文文件名会出错，下载后名字异常或后缀变错时，改成“仅英文和数字”。":
        "Some Android WebViews mishandle Chinese filenames. Switch to ASCII only if the saved name or extension is wrong.",
    "完成后自动收起下载进度面板": "Auto-hide the download panel when finished",
    "开启后单个文件下载完成约 1.5 秒自动收起；批量下载会等全部结束后再收起。":
        "A single file hides about 1.5 seconds after completion. Batch downloads hide after all files finish.",
    "设置只保存在当前设备，换设备需要重新选择。":
        "Settings are stored only on this device and must be selected again on another device.",
    "暂无收藏项。进入常用目录后点击「收藏当前目录」即可添加。":
        "No favorites yet. Open a folder and click Favorite this folder to add one.",
    "暂无收藏项": "No favorites yet",
    "确定": "OK",
    "取消": "Cancel",
    "关闭": "Close",
    "保存": "Save",
    "上传中": "Uploading",
    "处理中": "Working",
    "已完成": "Done",
    "失败": "Failed",
    "成功": "Success",
    "当前目录": "Current folder",
    "目标目录": "Destination folder",
    "新建文件夹": "New folder",
    "文件夹": "Folder",
    "文件": "File",
    "选择文件": "Choose files",

    # 管理后台
    "管理控制台 · 文件服务平台": "Admin Console · FilePortal",
    "管理控制台": "Admin Console",
    "重启服务": "Restart service",
    "当前在线用户": "Online users",
    "白名单": "Allowlist",
    "黑名单": "Blocklist",
    "云空间账号": "Cloud accounts",
    "登录规则": "Login rules",
    "屏蔽路径（文本直接编辑）": "Blocked paths (plain text)",
    "黑名单手动文件（文本直接编辑）": "Blocklist manual file (plain text)",
    "保存全部": "Save all",
    "保存后重启": "Save and restart",
    "添加": "Add",
    "加入黑名单": "Add to blocklist",
    "通过": "Approve",
    "拒绝": "Reject",
    "换验证码": "New code",
    "撤回": "Revoke",
    "手动开通": "Create account",
    "主人姓名": "Full-access name",
    "后台姓名": "Admin name",
    "只读密码": "Read-only password",
    "后台专用密码": "Admin password",
    "最高权限密码": "Full-access password",
    "学习资料密码": "Study password",
    "旧密码": "Legacy password",
    "开放注册": "Enable registration",
    "显示页脚": "Show footer",
    "普通访问": "Normal access",
    "每页条数": "Items per page",
    "监听地址": "Listen address",
    "站点编号": "Site code",
    "联系微信": "Contact WeChat",
    "联系电话": "Contact phone",
    "联系邮箱": "Contact email",
    "公安备案号": "Police record number",
    "公安备案链接": "Police record link",
    "ICP 备案号": "ICP number",
    "ICP 链接": "ICP link",
    "云空间根目录": "Cloud storage root",
    "列表缓存秒数": "List cache seconds",
    "文件下载并发": "File download concurrency",
    "打包下载并发": "ZIP download concurrency",
    "最高权限包含": "Full-access permissions",
    "只读权限包含": "Read-only permissions",
    "学习资料权限包含": "Study permissions",
    "登录保持天数": "Session lifetime (days)",
    "白名单文件夹": "Allowlist folder",
    "黑名单文件夹": "Blocklist folder",
    "白名单生效": "Enforce allowlist",
    "请求超时秒数": "Request timeout (seconds)",
    "同时处理请求数": "Request workers",
    "头像上限 KB": "Avatar limit (KB)",
    "学习资料子目录": "Study subfolder",
    "无法识别的操作": "Unknown operation",
    "0 表示关闭该功能": "0 disables this feature",
    "1 表示仅名单内人员可访问；0 表示白名单不生效":
        "1 allows only listed names; 0 disables the allowlist",
    "1 表示通过“另存为”直写绕开浏览器下载拦截（推荐）":
        "1 uses Save As direct write to avoid browser download warnings (recommended)",
    "0.0.0.0 表示监听全部网卡，通常无需修改":
        "0.0.0.0 listens on all interfaces; normally no change is needed",
    "留空表示仅提供 HTTP 服务": "Leave blank to serve HTTP only",
    "留空表示按 CPU 核数自动计算": "Leave blank to size workers from CPU count",
    "留空表示沿用上面的 PW_FULL": "Leave blank to reuse PW_FULL",
    "修改后需重启服务；内网穿透映射的目标端口须同步调整":
        "Restart after changing this; update the tunnel target port too",
    "超过该上限时改为边压缩边传输": "Above this size, files are compressed while streaming",
    "按设备与姓名分别计数，防止重复提交申请":
        "Counted separately by device and name to prevent duplicate requests",
    "以英文逗号分隔；规则文件中的规则优先级更高":
        "Comma-separated; login rules take priority",
    "用这个名字 + 最高权限密码登录就能进本页":
        "Sign in with this name and the full-access password to open this page",
    "仅当访问者姓名等于「主人姓名」时可用":
        "Available only when the visitor name equals the full-access name",
    "任意姓名配合该密码仅可访问学习资料目录":
        "Any name with this password can access only the study folder",
    "只删除 manual.txt 中的记录": "Removes records from manual.txt only",
    "规则未发生变化（共 %d 条）": "No rule changes (%d rules)",
    "规则已保存（共 %d 条），此前登录的会话需重新登录":
        "Rules saved (%d rules). Existing sessions must sign in again.",
    "存在未填写密码的规则，已跳过": "A rule without a password was skipped.",
    "以下改动需要重启服务才生效：%s": "These changes take effect after a restart: %s",
    "白名单已保存": "Allowlist saved",
    "黑名单已保存": "Blocklist saved",
    "待审核申请": "Pending applications",
    "暂无待审核申请": "No pending applications.",
    "已通过、等待申请人设置密码": "Approved, waiting for applicant to set a password",
    "暂无等待申请人设置密码的申请": "No applications are waiting for password setup.",
    "已开通": "Active accounts",
    "暂无已开通的账号": "No active accounts.",
    "暂无已开通的云空间账号": "No active cloud accounts.",
    "云空间账号": "cloud account",
    "密码区分大小写": "Passwords are case-sensitive",
    "请把初始密码线下告知本人。": "Tell the user the initial password offline.",
    "+ 新增规则": "+ Add rule",
    "当前身份": "Current identity",
    "规则文件": "rules file",
    "配置文件": "config file",
    "新增规则": "Add rule",
    "已通过": "Approved",
    "审核": "Review",
    "已从白名单移出：%s": "Removed from allowlist: %s",
    "已从黑名单移除：%s": "Removed from blocklist: %s",
    "黑名单中不存在「%s」": "%s is not in the blocklist",
    "屏蔽路径已保存（共 %d 条），列表缓存已刷新":
        "Blocked paths saved (%d). List cache refreshed.",
    "屏蔽路径保存失败：%s": "Could not save blocked paths: %s",
    "规则未保存：%s": "Rules were not saved: %s",
    "当前 %d 个姓名 · 修改即时生效": "%d names · changes apply immediately",
    "共 %d 人 · %d 台设备 · 最近 30 分钟活跃":
        "%d users · %d devices · active in the last 30 minutes",
    "最近 30 分钟活跃": "active in the last 30 minutes",
    "当前在线用户": "Online users",
    "在线用户": "Online users",

    # 页脚 / 通用
    "文件服务平台 · @TITLE@": "FilePortal · @TITLE@",
    "FilePortal 文件映射服务": "FilePortal · Self-hosted file workspace",
    "本文件映射服务知识产权归Admin所有": "FilePortal · Self-hosted file workspace",
    "京ICP备0000000号": "",
    "京公网安备00000000000000号": "",
}

# 带动态数字的短句，优先用正则处理。
_PATTERNS = [
    (re.compile(r"(\d+)\s*人\s*·\s*(\d+)\s*台设备\s*·\s*最近\s*30\s*分钟活跃"),
     r"\1 users · \2 devices · active in the last 30 minutes"),
    (re.compile(r"当前\s*(\d+)\s*个姓名\s*·\s*修改即时生效"),
     r"\1 names · changes apply immediately"),
    (re.compile(r"同意（\s*(\d+)\s*秒）"), r"Agree (\1s)"),
    (re.compile(r"共\s*(\d+)\s*项\s*·\s*"), r"\1 items · "),
    (re.compile(r"第\s*(\d+)\s*/\s*(\d+)\s*页"), r"Page \1/\2"),
    (re.compile(r"(\d+)\s*分钟前"), r"\1 min ago"),
    (re.compile(r"(\d+)\s*小时前"), r"\1 hr ago"),
    (re.compile(r"(\d+)\s*天前"), r"\1 days ago"),
    (re.compile(r"(\d+)\s*秒前"), r"\1 sec ago"),
    (re.compile(r"（\s*(\d+)\s*条）"), r" (\1)"),
    (re.compile(r"（\s*(\d+)\s*个）"), r" (\1)"),
    (re.compile(r"未找到与「(.+?)」的文件或文件夹（已搜索当前文件夹和它下面全部子目录）"),
     r'No files or folders matching "\1" were found, including all subfolders.'),
    (re.compile(r"无法读取该目录（(.+?)）"), r"Cannot read this folder (\1)"),
    (re.compile(r"搜索「(.+?)」（含全部子目录）·\s*"), r'Search "\1" (all subfolders) · '),
    (re.compile(r"(.+?)（可用\s*(\d+)%）"), r"\1 (\2% free)"),
]


def current_lang(cookie_header):
    raw = cookie_header or ""
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == COOKIE_NAME:
                v = v.strip().lower()
                return v if v in SUPPORTED else "zh"
    return "zh"


def _tr(text):
    if not text:
        return text
    for zh, en in _REPLACEMENTS:
        if zh and zh in text:
            text = text.replace(zh, en)
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


_REPLACEMENTS = sorted(_MAP.items(), key=lambda kv: -len(kv[0]))

_TAG_RE = {
    tag: re.compile(r"(<%s(?=[\s>])[^>]*>)(.*?)(</%s>)" % (tag, tag), re.I | re.S)
    for tag in _TEXT_TAGS
}

_CLASS_RE = re.compile(
    r'(<(?:p|span|div|a)[^>]*\bclass="[^"]*\b(?:%s)\b[^"]*"[^>]*>)(.*?)(</(?:p|span|div|a)>)'
    % "|".join(_TEXT_CLASSES), re.I | re.S)


_JS_MAP = {
    "新建目录的名称：": "New folder name: ",
    "请输入新的名称：": "Enter a new name: ",
    "重命名失败：": "Rename failed: ",
    "确认删除「": "Delete ",
    "」吗？\\n删除后该项目将移入回收站，可在回收站中还原。":
        "?\\nThe item will be moved to the recycle bin and can be restored.",
    "删除失败：": "Delete failed: ",
    "已选 ": "Selected ",
    " 项": " items",
    "确认删除所选 ": "Delete the selected ",
    " 项？\\n删除后各项将移入回收站，可在回收站中还原。":
        " items?\\nThey will be moved to the recycle bin and can be restored.",
    "」删除失败：": " failed to delete: ",
    "当前身份没有下载权限": "Your current role cannot download files.",
    "批量下载.zip": "Batch download.zip",
    "请输入目标目录路径（留空表示当前目录）：": "Target folder path (leave empty for current folder): ",
    "有 ": "There are ",
    " 项移动未成功（可能目标已存在同名项目，或目标位于其自身内部）":
        " items that could not be moved. The target may already contain the same name, or be inside the source.",
    "已标记移动「": "Move marked: ",
    "」，请进入目标目录后点击「粘贴到当前」": ". Open the target folder and click Paste here.",
    "粘贴「": "Paste ",
    "」到当前": " here",
    "粘贴到当前": "Paste here",
    "已移动「": "Moved ",
    "」至当前目录": " to this folder",
    "移动失败：": "Move failed: ",
    "正在加载": "Loading...",
    "回收站当前为空": "The recycle bin is empty.",
    "回收站数据读取失败": "Could not read the recycle bin.",
    "还原": "Restore",
    "彻底删除": "Delete permanently",
    "文件夹": "Folder",
    " · 原位置 ": " · Original location ",
    "彻底删除「": "Delete permanently ",
    "」？该操作不可撤销": "? This cannot be undone.",
    "已还原": "Restored",
    "已删除": "Deleted",
    "操作失败：": "Operation failed: ",
    "确认清空回收站？其中全部项目将被永久删除且无法还原。":
        "Empty the recycle bin? Everything in it will be permanently deleted.",
    "回收站已清空": "The recycle bin is empty.",
    "清空失败：": "Empty failed: ",
    "无法读取该文件": "Cannot read this file.",
    "名称": "Name",
    "位置": "Location",
    "类型": "Type",
    "大小": "Size",
    "修改时间": "Modified",
    "直链": "Direct link",
    "打开": "Open",
    "根目录": "Root",
    "请点击下方「统计占用空间」": "Click Calculate total size below.",
    "计算总大小（含全部子目录）": "Calculate total size (all subfolders)",
    "正在统计": "Calculating...",
    " 个文件": " files",
    "，统计结果已截断": ", results truncated",
    "统计失败": "Calculation failed",
    "」已在常用目录列表中": " is already in favorites.",
    "已加入常用目录：「": "Added to favorites: ",
    "暂无收藏项。进入常用目录后点击「收藏当前目录」即可添加。":
        "No favorites yet. Open a folder and click Favorite this folder to add one.",
    "等待": "Waiting",
    "完成": "Done",
    "网络错误": "Network error",
    "失败：": "Failed: ",
    "失败 ": "Failed ",
    "上传中 ": "Uploading ",
    "上传结束：成功 ": "Upload finished: ",
    " 个，失败 ": " succeeded, ",
    " 个（重新上传将覆盖同名文件）": " failed. Uploading again overwrites same-name files.",
    "上传完成（": "Upload complete (",
    " 个文件）": " files)",
    " 个文件未能完成上传，可重新选择后上传": " files could not be uploaded. Select them again to retry.",
    "正在上传头像": "Uploading avatar...",
    "头像已更新": "Avatar updated.",
    "头像上传失败": "Avatar upload failed.",
    "头像上传失败（网络问题）": "Avatar upload failed (network error).",
    "图片超出 12 MB，请压缩后再上传": "The image is larger than 12 MB. Compress it before uploading.",
    "该类型无法在线预览，请点击右上角「下载」查看。":
        "This file type cannot be previewed. Click Download in the top right.",

    "打包": "Archive",
    "<span class=\"nm\"></span><span class=\"x\">删除</span>":
        "<span class=\"nm\"></span><span class=\"x\">Delete</span>",
    "失败": "Failed",
    "另存为": "Save As",
    "准备中…": "Preparing...",
    "取消": "Cancel",
    "已转交浏览器原生下载（如提示“不安全/是否保留”，请选择“保留”）":
        "Handed off to the browser downloader. If prompted, choose Keep.",
    " 个分段连接": " connections",
    "长度对不上": "Length mismatch",
    "已保存 · ": "Saved · ",
    "已取消（文件可能不完整）": "Canceled (the file may be incomplete)",
    "保存失败（": "Save failed (",
    "），已切换为常规下载": "). Switched to regular download.",
    " · 单连接下载": " · Single connection",
    "已写入 ": "Written ",
    "已取消": "Canceled",
    "并发下载失败（": "Concurrent download failed (",
    "打开": "Open",
    "· 并发下载：将文件分段并行获取，可缩短大文件传输耗时；系统配置值为全站并发上限，":
        "· Concurrent download fetches file ranges in parallel to shorten large transfers. The system value is the site-wide limit, ",
    "· 单连接下载：以单条连接顺序获取，传输稳定性最佳，适用于老旧设备、弱网环境，":
        "· Single-connection download reads sequentially. It is the most stable option for older devices and weak networks, ",
    "或并发分片校验失败的情形。": "or when range verification fails.",
    "「兼容模式」不经过网页下载流程，将地址交由系统下载器处理：无进度显示、单连接，":
        "Compatibility mode bypasses the page download flow and hands the URL to the system downloader: no progress bar, single connection, ",
    "如浏览器提示「不安全 / 是否保留」：标准模式下请选择「保留」；":
        "If the browser asks whether to keep an unsafe download, choose Keep in standard mode; ",
    "如需彻底消除该提示，请通过 HTTPS 地址访问，或切换至兼容模式。":
        "to remove the prompt entirely, use an HTTPS address or switch to compatibility mode.",
}

_JS_REPLACEMENTS = sorted(_JS_MAP.items(), key=lambda kv: -len(kv[0]))

def _js_tr(chunk):
    for zh, en in _JS_REPLACEMENTS:
        chunk = chunk.replace(zh, en)
    return chunk
_ATTR_RE = re.compile(r'(\b(?:title|placeholder|aria-label)=")([^"]*)(")', re.I)


def _apply_fragment(fragment):
    for tag, rx in _TAG_RE.items():
        fragment = rx.sub(lambda m: m.group(1) + _tr(m.group(2)) + m.group(3), fragment)
    fragment = _CLASS_RE.sub(lambda m: m.group(1) + _tr(m.group(2)) + m.group(3), fragment)
    fragment = _ATTR_RE.sub(lambda m: m.group(1) + _tr(m.group(2)) + m.group(3), fragment)
    return fragment


def _lang_switch(lang):
    active_zh = " active" if lang == "zh" else ""
    active_en = " active" if lang == "en" else ""
    return (
        '<div class="fpLang" role="group" aria-label="Language">'
        '<span>Language</span>'
        '<button type="button" class="zh%s" data-fp-lang="zh">中文</button>'
        '<button type="button" class="en%s" data-fp-lang="en">English</button>'
        '</div>'
        '<style>.fpLang{position:fixed;right:14px;bottom:14px;z-index:9999;'
        'display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:10px;'
        'background:rgba(10,45,75,.88);color:#fff;font:12px/1.2 -apple-system,'
        'BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;'
        'box-shadow:0 4px 14px rgba(0,0,0,.18)}'
        '.fpLang span{opacity:.78;margin-right:2px}'
        '.fpLang button{border:0;border-radius:7px;padding:4px 8px;font:inherit;'
        'color:#dceeff;background:transparent;cursor:pointer}'
        '.fpLang button.active{color:#fff;background:#0f6fbd}'
        '</style>'
        '<script>(function(){var b=document.querySelectorAll(".fpLang button");'
        'for(var i=0;i<b.length;i++){b[i].onclick=function(){var l=this.getAttribute("data-fp-lang");'
        'document.cookie="fp_lang="+l+"; Path=/; Max-Age=31536000; SameSite=Lax";'
        'location.reload();};}})();</script>'
    ) % (active_zh, active_en)


_OPEN_TAG_RE = re.compile(r"<(script|style)\b[^>]*>", re.I)


def _split_markup(body):
    """Split script/style blocks without a backtracking regular expression."""
    parts = []
    pos = 0
    lower = body.lower()
    while True:
        m = _OPEN_TAG_RE.search(body, pos)
        if not m:
            parts.append(body[pos:])
            return parts
        tag = m.group(1).lower()
        close_start = lower.find("</" + tag, m.end())
        if close_start < 0:
            parts.append(body[pos:])
            return parts
        close_end = body.find(">", close_start)
        if close_end < 0:
            parts.append(body[pos:])
            return parts
        parts.append(body[pos:close_end + 1])
        pos = close_end + 1


def render(body, lang):
    """把 HTML 中的界面文字翻成目标语言，并在页面底部加入语言切换。"""
    if not isinstance(body, str):
        return body
    if lang == "en":
        # 保留 script/style 内部原样，避免改坏 JS/CSS
        chunks = _split_markup(body)
        out = []
        for chunk in chunks:
            if chunk[:1] == "<" and re.match(r"<(?:script|style)[\s>]", chunk, re.I):
                chunk = _js_tr(chunk) if chunk.lstrip().lower().startswith("<script") else chunk
                out.append(chunk)
            else:
                out.append(_apply_fragment(chunk))
        body = "".join(out)
        body = re.sub(r'(<html\s+lang=")([^"]*)(")', r'\1en\3', body, count=1, flags=re.I)
    body = re.sub(r"</body>", _lang_switch(lang) + "</body>", body, count=1, flags=re.I)
    return body
