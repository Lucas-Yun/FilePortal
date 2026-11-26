# -*- coding: utf-8 -*-
# 模块说明：config.ini 读取、默认值、路径解析和整数范围
"""配置读取：所有可调参数都在程序目录的 config.ini 里，黑名单在 data/lists/blacklist/ 里。

这个文件只负责「读 + 兜底」，日常改配置请直接改 config.ini，不用碰这里。
config.ini 写错了或者删了，程序会退回下面 DEFAULTS 里的出厂值，不会启动失败。
"""

import configparser
import os
import secrets
import sys

# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
_SOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _base_dir():
    """运行数据根目录。

    · 普通源码版：就是 app 目录；
    · 单文件 exe：启动器会提前设置 FILEPORTAL_HOME 指向 exe 旁边的
      FilePortalData，配置、数据、日志都放那里，不依赖临时解压目录。
    """
    env = os.environ.get("FILEPORTAL_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _SOURCE_DIR


PROJECT_DIR = _base_dir()
SOURCE_DIR = _SOURCE_DIR
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
DOCS_DIR = os.path.join(PROJECT_DIR, "docs")
CERTS_DIR = os.path.join(PROJECT_DIR, "certs")
DATA_DIR = os.path.join(PROJECT_DIR, "data")
RUN_DIR = os.path.join(PROJECT_DIR, "runtime")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config.ini")
BLACKLIST_DIR = os.path.join(DATA_DIR, "lists", "blacklist")
RULES_FILE = os.path.join(DATA_DIR, "rules.json")   # 登录规则（谁 + 什么密码 → 什么权限 / 哪一层目录）
SESSION_SECRET_FILE = os.path.join(DATA_DIR, ".session_secret")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    pass

SERVER_VERSION = "FilePortal/1.0.2"


def _load_session_secret():
    """会话签名密钥：持久化在数据目录，重启后已登录用户不会被全部踢掉。"""
    path = SESSION_SECRET_FILE
    try:
        with open(path, "r", encoding="ascii") as fh:
            raw = fh.read().strip()
        if len(raw) >= 64:
            return bytes.fromhex(raw[:64])
    except (OSError, ValueError):
        pass
    value = secrets.token_hex(32)
    try:
        with open(path, "w", encoding="ascii") as fh:
            fh.write(value + "\n")
    except OSError:
        pass
    return bytes.fromhex(value)


SESSION_SECRET = _load_session_secret()      # 首次生成后持久化；重启不再清空登录
CHUNK = 512 * 1024                         # 文件收发分块（越大系统调用越少，穿透下更划算）
MAX_TEXT_PREVIEW = 1024 * 1024             # 文本预览最多读 1MB
HIDDEN_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "folder.ini", ".trash", ".cloudmeta",
                "blocked_paths.txt", ".session_secret", "sessions.json", "cache"}

# --------------------------------------------------------------------------- #
# 出厂默认值（config.ini 里没写、写空、写坏了都走这里）
# --------------------------------------------------------------------------- #
DEFAULTS = {
    # [服务器]
    "port": "8000",
    "host": "0.0.0.0",
    # 新的正式名称；旧的 root 继续兼容（projection_root 优先）
    "projection_root": "",
    "root": os.path.join(os.path.expanduser("~"), "Documents"),
    "workers": "",
    "zip_slots": "2",
    "upload_slots": "4",
    "list_cache_seconds": "3",
    "per_page": "60",
    "request_timeout": "60",
    # 回收站：删除的文件先挪进 <投射目录>\.trash，多少天以后才真正清掉
    "trash_days": "30",
    # HTTPS（留空 = 普通 HTTP；填了证书路径就用 https:// 提供服务）
    "certfile": "",
    "keyfile": "",
    "https_port": "0",
    # [密码]
    "pw_full": "",
    "admin_password": "",            # 后台专用密码；留空=沿用 pw_full，旧密码不再能进后台
    "pw_study": "",
    "pw_read": "",
    "legacy_password": "",          # 留空=停用；不再内置任何已知默认密码
    "full_name": "管理员",
    "admin_name": "Admin",
    "study_subpath": "文件/学习资料",
    "session_days": "7",
    # —— 白名单 / 黑名单 ——
    "whitelist_dir": "data/lists/whitelist",       # 白名单文件夹（相对项目目录）；里面的 txt/csv/xlsx/docx 都会被读
    "blacklist_dir": "data/lists/blacklist",       # 黑名单文件夹，规则与白名单相同
    "whitelist_enforce": "1",        # 1=名单里有名字就只管这些人；0=白名单不生效（不推荐）
    # —— 防密码暴力破解（不按 IP 封，走端口映射时 IP 全是 127.0.0.1）——
    "login_max_fails": "8",            # 同一个访问人姓名连续错几次开始锁
    "login_lock_seconds": "90",        # 第一次锁多久（秒）
    "login_lock_max_seconds": "900",   # 反复出错时最多锁到多久（秒）
    "login_rate_per_minute": "12",     # 全站每分钟最多几次登录尝试（所有设备合起来算）
    "login_burst": "24",               # 允许一次突发多少下（填大了手机连点也不会误伤）
    "login_fail_delay_ms": "200",      # 每次密码错误额外拖延多久再回话（毫秒，越错越久）
    "login_fail_delay_max_ms": "1500",  # 拖延上限（毫秒）
    # [下载]
    "file_threads": "24",           # 普通文件下载：全站同时最多几条连接（也等于单个任务最多开几条）
    "zip_threads": "16",            # 打包下载：全站同时最多几条连接
    "threaded_max_mb": "64",        # 多大的文件才走浏览器多线程（再大就交给浏览器原生下载直接写盘）
    "zip_cache_max_mb": "256",      # 多大的文件夹允许"先打包成临时文件"（只有这样才能多线程；再大就边压边发）
    "zip_cache_minutes": "30",      # 打包缓存保留多少分钟
    "save_picker": "1",             # 1=点下载先弹「另存为」再直写（绕开浏览器拦截）；0=老式下载
    "dl_token_hours": "12",         # 带签名的下载直链（/d?t=…）有效期，给不带 Cookie 的老设备用
    # [权限]
    "full_perms": "download, preview, zip, upload, mkdir, rename, delete",
    "study_perms": "download, preview, zip, upload, mkdir",
    "read_perms": "download, preview, zip",
    # [页脚]
    "show_footer": "false",
    "site_code": "",
    "icp_no": "",
    "icp_url": "https://beian.miit.gov.cn/",
    "police_no": "",
    "police_url": "https://beian.mps.gov.cn/#/query/webSearch?code=00000000000000",
    # [云盘] 自建多用户云盘（注册要管理员审核）
    "cloud_root": r"D:\CLOUDPAN",     # 每人一个文件夹，建在这个目录下面
    "register_enabled": "1",          # 1=登录页显示「注册」按钮；0=关闭注册入口
    "register_notice_seconds": "5",   # 注册须知必须停留几秒才能点「同意」（0=立刻可点）
    "contact_wechat": "",             # 开通须知页展示的联系方式（留空不显示）
    "contact_phone": "",
    "contact_email": "",
    "register_daily_limit": "1",      # 同一台设备 / 同一个名字，一天最多提交几次申请
    "avatar_max_kb": "2048",          # 头像上传上限（KB）
    "upload_parallel": "3",           # 一次选很多文件时，前端同时传几个（1=一个一个来）
    "upload_max_mb": "4096",          # 单个文件上限（MB）；0 = 不限制
    "user_quota_mb": "10240",         # 每个云空间账号容量上限（MB）；0 = 不限制
    "thumb_source_max_mb": "20",      # 服务端生成缩略图时，原图最大读取大小（MB）
    "thumb_max_px": "320",            # 缩略图最长边像素
    "log_days": "90",                 # 操作日志按天保留多少天，超期自动清理
}


def _read_ini(path):
    """把 config.ini 所有分节里的键值摊平成一张表（键一律小写）"""
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read(path, encoding="utf-8-sig")
    except Exception:  # noqa: BLE001  —— 文件写坏了就当没有
        return {}
    out = {}
    for sec in cfg.sections():
        for key, val in cfg.items(sec):
            out[key.strip().lower()] = val.strip()
    return out


_RAW = _read_ini(CONFIG_FILE)
CONFIG_LOADED = bool(_RAW)


def raw(key):
    """原始字符串。config.ini 里没写或写成空值 → 用出厂默认值"""
    key = key.lower()
    val = _RAW.get(key)
    if val is None or val == "":
        return DEFAULTS[key]
    return val


def text(key):
    """字符串（不做小写处理，密码、姓名用它）"""
    return raw(key)


def integer(key, low=1, high=None):
    try:
        n = int(str(raw(key)).strip())
    except (TypeError, ValueError):
        try:
            n = int(DEFAULTS[key])
        except (KeyError, ValueError):
            n = low
    if n < low:
        n = low
    if high is not None and n > high:
        n = high
    return n


def flag(key):
    """布尔：true/1/yes/on/开 等都算真"""
    val = str(raw(key)).strip().lower()
    return val not in ("0", "false", "no", "off", "否", "关", "n", "f")


# --------------------------------------------------------------------------- #
# 服务器
# --------------------------------------------------------------------------- #
DEFAULT_PORT = integer("port", 1, 65535)
DEFAULT_HOST = text("host")
# 投射目录：新键优先；为了兼容旧配置，没写 projection_root 时继续读 root。
DEFAULT_ROOT = text("projection_root") or text("root")
WORKERS = integer("workers", 1, 64) if str(raw("workers")).strip().isdigit() else 0
ZIP_SLOTS = integer("zip_slots", 1, 16)
UPLOAD_SLOTS = integer("upload_slots", 1, 32)
try:
    LIST_CACHE_SECONDS = max(0.0, float(str(raw("list_cache_seconds")).replace(",", ".")))
except ValueError:
    LIST_CACHE_SECONDS = 3.0
LIST_CACHE_MAX = 96
PER_PAGE = integer("per_page", 10, 1000)
REQUEST_TIMEOUT = integer("request_timeout", 1, 600)
CERTFILE = text("certfile")        # 证书路径（PEM）；留空就是 HTTP
KEYFILE = text("keyfile")          # 私钥路径；证书里已包含私钥时可留空
HTTPS_PORT = integer("https_port", 0, 65535)   # 0=不开额外 HTTPS 口；填了就 HTTP+HTTPS 双口并存

# --------------------------------------------------------------------------- #
# 下载（多线程 / 打包缓存）
# --------------------------------------------------------------------------- #
FILE_THREADS = integer("file_threads", 1, 64)      # 全站文件下载并发上限
ZIP_THREADS = integer("zip_threads", 1, 64)        # 全站打包下载并发上限
THREADED_MAX_MB = integer("threaded_max_mb", 1, 4096)   # 超过这个大小就不在浏览器里拼了
ZIP_CACHE_MAX_MB = integer("zip_cache_max_mb", 1, 8192)
ZIP_CACHE_MINUTES = integer("zip_cache_minutes", 1, 1440)
# 1 = 点下载先弹「另存为」再直接写盘（数据不经过浏览器下载管理器，因此不会被判"不安全"）
# 0 = 老办法：浏览器原生下载 / 网页内拼好再存（可能触发"此文件可能有害，是否保留"）
SAVE_PICKER = flag("save_picker")

# 上传限制 / 缩略图
UPLOAD_MAX_MB = integer("upload_max_mb", 0, 1024 * 1024)
USER_QUOTA_MB = integer("user_quota_mb", 0, 1024 * 1024)
THUMB_SOURCE_MAX_MB = integer("thumb_source_max_mb", 1, 512)
THUMB_MAX_PX = integer("thumb_max_px", 64, 2000)

# --------------------------------------------------------------------------- #
# 密码 / 登录
# --------------------------------------------------------------------------- #
ROLE_FULL = "full"
ROLE_STUDY = "study"
ROLE_READ = "read"

PW_FULL = text("pw_full")
PW_ADMIN = text("admin_password")
PW_STUDY = text("pw_study")
PW_READ = text("pw_read")
DEFAULT_PASSWORD = text("legacy_password")
NAME_FULL = text("full_name")
ADMIN_NAME = text("admin_name") or "Admin"      # 网页后台（配置界面）专用姓名
STUDY_SUBPATH = text("study_subpath")

SESSION_TTL = integer("session_days", 1, 365) * 24 * 3600

# 防暴力破解（全部按「访问人姓名 / 全站总量」限制，绝不按 IP 限制）
LOGIN_MAX_FAILS = integer("login_max_fails", 1, 100)
LOGIN_LOCK_SECONDS = integer("login_lock_seconds", 1, 86400)
LOGIN_LOCK_MAX_SECONDS = integer("login_lock_max_seconds", 1, 86400)
LOGIN_RATE_PER_MINUTE = integer("login_rate_per_minute", 1, 600)
LOGIN_BURST = integer("login_burst", 1, 600)
LOGIN_FAIL_DELAY_MS = integer("login_fail_delay_ms", 0, 5000)
LOGIN_FAIL_DELAY_MAX_MS = integer("login_fail_delay_max_ms", 0, 5000)
if LOGIN_LOCK_MAX_SECONDS < LOGIN_LOCK_SECONDS:
    LOGIN_LOCK_MAX_SECONDS = LOGIN_LOCK_SECONDS
if LOGIN_FAIL_DELAY_MAX_MS < LOGIN_FAIL_DELAY_MS:
    LOGIN_FAIL_DELAY_MAX_MS = LOGIN_FAIL_DELAY_MS

# --------------------------------------------------------------------------- #
# 权限表
# --------------------------------------------------------------------------- #
_CAP_ALIAS = {
    "download": "download", "下载": "download",
    "preview": "preview", "预览": "preview",
    "zip": "zip", "打包": "zip", "打包下载": "zip",
    "upload": "upload", "上传": "upload",
    "mkdir": "mkdir", "新建": "mkdir", "新建文件夹": "mkdir",
    "rename": "rename", "重命名": "rename", "改名": "rename",
    "delete": "delete", "删除": "delete",
}


def _parse_perms(key):
    items = []
    for part in str(raw(key)).replace("，", ",").replace(";", ",").split(","):
        cap = _CAP_ALIAS.get(part.strip().lower())
        if cap and cap not in items:
            items.append(cap)
    return set(items) or set(_parse_perms_default(key))


def parse_perms(text_value):
    """把 "download, upload, delete" 这类文本解析成权限集合（规则文件 / 后台页面都用它）"""
    items = []
    for part in str(text_value or "").replace("，", ",").replace(";", ",").split(","):
        cap = _CAP_ALIAS.get(part.strip().lower())
        if cap and cap not in items:
            items.append(cap)
    return set(items)


ALL_PERMS = ("download", "preview", "zip", "upload", "mkdir", "rename", "delete")


def _parse_perms_default(key):
    return [p.strip().lower() for p in DEFAULTS[key].split(",") if p.strip()]


ROLE_PERMS = {
    ROLE_FULL: _parse_perms("full_perms"),
    ROLE_STUDY: _parse_perms("study_perms"),
    ROLE_READ: _parse_perms("read_perms"),
}

# --------------------------------------------------------------------------- #
# 页脚备案
# --------------------------------------------------------------------------- #
SHOW_FOOTER = flag("show_footer")
SITE_CODE = text("site_code")
ICP_NO = text("icp_no")
ICP_URL = text("icp_url")
POLICE_NO = text("police_no")
POLICE_URL = text("police_url")

# --------------------------------------------------------------------------- #
# 黑名单（由 denylist 模块动态读取目录，这里只保留兼容入口）
# --------------------------------------------------------------------------- #
def is_blocked(name):
    """这个姓名是否在黑名单里（目录内所有名单文件合并，不分大小写）。"""
    from . import denylist
    return denylist.is_blocked(name)


# --------------------------------------------------------------------------- #
# 角色 → 目录 / 权限
# --------------------------------------------------------------------------- #
def role_root(role, base_root=None):
    """某个角色能访问的根目录"""
    base = os.path.abspath(base_root or DEFAULT_ROOT)
    if role == ROLE_STUDY:
        sub = (STUDY_SUBPATH or "").replace("\\", "/").strip("/")
        if sub:
            return os.path.join(base, *sub.split("/"))
    return base


def role_perms(role):
    return ROLE_PERMS.get(role, ROLE_PERMS[ROLE_READ])


# --------------------------------------------------------------------------- #
# 投射目录安全校验
# --------------------------------------------------------------------------- #
def validate_projection_root(path):
    """检查投射目录是否安全。

    允许投射普通用户目录下的具体文件夹（例如 .../Documents 或
    D:\\Users\\Documents），但拒绝整盘、系统目录、用户主目录本身，
    避免把整台电脑的文件通过网页暴露出去。
    返回 (是否安全, 给用户的提示, 规范化后的绝对路径)。
    """
    raw_path = str(path or "").strip()
    if not raw_path:
        return False, "投射目录为空。请在 config.ini 的 [服务器] 里填写 projection_root。", ""
    expanded = os.path.expanduser(raw_path)
    if not os.path.isabs(expanded):
        return False, "投射目录必须是绝对路径：%s" % raw_path, os.path.abspath(expanded)
    real = os.path.realpath(os.path.abspath(expanded))
    if os.name == "nt":
        drive, tail = os.path.splitdrive(real)
        parts = [p for p in tail.replace("/", "\\").split("\\") if p]
        if not parts:
            return False, "不能把整个磁盘作为投射目录：%s" % real, real
        first = parts[0].lower()
        if first == "windows":
            return False, "不能投射 Windows 系统目录：%s" % real, real
        if first in ("program files", "program files (x86)", "programdata"):
            return False, "不能投射系统程序目录：%s" % real, real
        if first == "users" and len(parts) <= 1:
            return False, "不能投射整个用户目录，请选择它下面的具体文件夹：%s" % real, real
        home = os.path.realpath(os.path.expanduser("~"))
        if real == home:
            return False, "不能投射用户主目录本身，请选择它下面的具体文件夹：%s" % real, real
    else:
        home = os.path.realpath(os.path.expanduser("~"))
        if real == "/" or real == home:
            return False, "不能投射根目录或用户主目录本身：%s" % real, real
        if real in ("/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc",
                    "/sys", "/root", "/home", "/opt", "/srv", "/var", "/tmp"):
            return False, "不能投射 Linux 系统目录：%s" % real, real
    return True, "", real


class Config:
    root = DEFAULT_ROOT
    password = DEFAULT_PASSWORD
    port = DEFAULT_PORT
    host = DEFAULT_HOST
