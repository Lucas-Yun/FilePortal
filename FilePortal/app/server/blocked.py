# -*- coding: utf-8 -*-
# 模块说明：屏蔽路径的读写、解析与列表缓存失效
"""屏蔽路径：无论什么姓名、什么密码、什么权限，都不能在网页上看到或取到。

配置文件是数据目录的「blocked_paths.txt」，一行一条：
  · 相对路径按 config.ini 的 root 解析，例如  Tools/Script
  · 也可以写绝对路径，例如  C:\\Users\\Public\\Documents\\Tools\\Script
  · # 开头的行是注释

命中规则：路径本身，或它下面的任何子路径，都算被屏蔽。
所以屏蔽一个文件夹，等于把整个文件夹从列表、搜索、下载、预览、打包里全部拿掉。
"""
import os
import tempfile
import threading
import time

from . import settings

FILE_NAME = "blocked_paths.txt"

# 首次启动时生成的默认值（只生成一次；以后在后台或文件里自己维护）
DEFAULT_TEXT = """# 屏蔽路径：一行一条，命中文件夹会连同下面所有内容一起隐藏。
# 相对路径按 config.ini 的 root 解析；也可以写绝对路径；# 开头为注释。
# 保存后立即生效，不需要重启。

# 服务本体与它的上级
Tools/Script
Services/Private/FilePortal
Services/Private/FilePortal
Services/Private/FilePortal-学习资料

# 个人目录里的磁盘映像文件
private/secret.vhdx
"""

_lock = threading.RLock()
_snapshot = None          # tuple[(normcase path, ...)]
_version = 0
_stamp = None             # (mtime_ns, size)
_last_check = 0.0


def _file_stamp():
    try:
        st = os.stat(path())
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def path():
    return os.path.join(settings.DATA_DIR, FILE_NAME)


def _atomic_write(text):
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".blocked-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def ensure_file():
    """文件不存在时写入默认屏蔽清单；已存在则一个字节都不动。"""
    if os.path.exists(path()):
        return
    try:
        _atomic_write(DEFAULT_TEXT)
    except OSError:
        pass


def read_text():
    ensure_file()
    try:
        with open(path(), "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError:
        return DEFAULT_TEXT


def write_text(text):
    """后台保存用：原样保存用户编辑的文本，随后重新加载屏蔽表。"""
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
    _atomic_write(body)
    reload()


def _to_abs(line):
    line = (line or "").strip()
    if not line or line.startswith("#") or line.startswith("//"):
        return None
    line = line.replace("\\", "/")
    # 允许用户写带引号的路径
    if len(line) >= 2 and line[0] == line[-1] and line[0] in ("'", '"'):
        line = line[1:-1].strip()
    if not line:
        return None
    if os.path.isabs(line):
        p = line
    else:
        p = os.path.join(settings.Config.root, *[x for x in line.split("/") if x not in ("", ".")])
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except (OSError, ValueError):
        return None


def reload():
    """重新读取屏蔽文件。后台保存后、或手工改文件后 2 秒内自动生效。"""
    global _snapshot, _version, _stamp, _last_check
    ensure_file()
    try:
        with open(path(), "r", encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
    except OSError:
        # 文件暂时读不到时按出厂清单“失败关闭”，不能因为读不到就全部放行
        lines = DEFAULT_TEXT.splitlines()
    items = []
    for line in lines:
        p = _to_abs(line)
        if p and p not in items:
            items.append(p)
    stamp = _file_stamp()
    with _lock:
        _snapshot = tuple(items)
        _version += 1
        _stamp = stamp
        _last_check = time.monotonic()
        return len(items)


def _ensure():
    global _stamp, _last_check
    if _snapshot is None:
        reload()
        return
    now = time.monotonic()
    if now - _last_check < 2.0:
        return
    stamp = _file_stamp()
    if stamp == _stamp:
        _last_check = now
        return
    reload()


def version():
    _ensure()
    return _version


def _hit(p):
    with _lock:
        snap = _snapshot or ()
    for b in snap:
        if p == b:
            return True
        if b.endswith(os.sep):
            if p.startswith(b):
                return True
        elif p.startswith(b + os.sep):
            return True
    return False


def is_blocked(abspath):
    """绝对路径是否落在屏蔽清单内（含被屏蔽目录的所有子路径和软链接真身）。"""
    if not abspath:
        return False
    _ensure()
    try:
        p = os.path.normcase(os.path.normpath(os.path.abspath(abspath)))
    except (OSError, ValueError):
        return False
    if _hit(p):
        return True
    try:
        real = os.path.normcase(os.path.realpath(abspath))
    except (OSError, ValueError):
        return False
    return real != p and _hit(real)


def is_blocked_rel(rel, root=None):
    root = os.path.abspath(root or settings.Config.root)
    rel = (rel or "").replace("\\", "/").strip("/")
    parts = [x for x in rel.split("/") if x not in ("", ".")]
    return is_blocked(os.path.join(root, *parts) if parts else root)


# 首次导入时把默认文件落盘（不会覆盖用户已有的文件）
ensure_file()
