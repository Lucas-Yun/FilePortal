# 模块说明：白名单/黑名单名单文件的解析与合并
"""白名单（访问人姓名允许名单）。

用法：数据目录下有个「lists/whitelist」文件夹，往里丢任意多个文件，程序自动合并成一个姓名名单：

- .txt / .csv / .md     纯文本：名字之间可以是空格、换行、逗号（中英文都行）、分号、Tab
- .xlsx / .xlsm         Excel：一竖列、一横排、一片表格都能读，空单元格自动跳过
- .docx                 Word：每段 / 每个单元格里的名字都会被读出来（.doc 老格式读不了，另存成 .docx 即可）

规则：
- 以 # 或 // 开头的行是注释，不当作名字；
- 纯数字（学号、序号、日期）不会被当名字；
- 名字大小写、前后空格会被忽略（英文名字 "Li Ming" 和 "li ming" 视为同一个人）；
- 网页后台里"添加/移出"改的是「data/lists/whitelist/manual.txt」这一个文件，别的手工文件只读不改。

白名单一旦有名字就"常开"生效：不在名单里的人，密码再对也进不来（后台身份 Admin 永远除外，
这样万一把自己漏掉了也还能进后台把自己加回去）。名单是空的就等于不限制，后台页会提示。
"""

import os
import re
import threading
import zipfile
import xml.etree.ElementTree as ET

from . import settings

MANUAL_FILE = "manual.txt"
MANUAL_HEAD = """# Names added by the admin "whitelist" card. One name per line.
# This file can be edited by hand and takes effect immediately.
# Other .txt / .csv / .xlsx / .docx files in this folder are merged automatically.
"""

_SPLIT = re.compile(r"[ \t\r\n,，、;；|/]+")
_SEP_IN = re.compile(r"[,，、;；|/]")
_FORBID = re.compile(r"[<>\"'`*\\=%$]")
_NUMERIC = re.compile(r"^-?\d+([.,]\d+)?$")
_NS_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_lock = threading.Lock()
_cache = {"stamp": None, "map": {}}


def dir_path():
    """白名单文件夹的绝对路径（配置里可以换成别的名字）"""
    name = (settings.raw("whitelist_dir") or "data/lists/whitelist").strip() or "data/lists/whitelist"
    p = name if os.path.isabs(name) else os.path.join(settings.PROJECT_DIR, name)
    return p


def manual_path():
    return os.path.join(dir_path(), MANUAL_FILE)


def ensure_dir():
    try:
        os.makedirs(dir_path(), exist_ok=True)
    except OSError:
        return
    mp = manual_path()
    if not os.path.exists(mp):
        try:
            with open(mp, "w", encoding="utf-8") as fh:
                fh.write(MANUAL_HEAD)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# 各种文件 → 一堆"文本片段"（片段再拆成名字）
# --------------------------------------------------------------------------- #
def _read_text(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with open(path, "r", encoding=enc, errors="strict") as fh:
                return fh.read()
        except (UnicodeDecodeError, OSError):
            continue
    try:
        with open(path, "r", encoding="gb18030", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def _pieces_txt(path):
    text = _read_text(path)
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        out.append(s)
    return out


def _pieces_xlsx(path):
    """Excel：把所有单元格的文字取出来（sharedStrings / inlineStr / 普通字符串都认）"""
    out = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root.iter(_NS_X + "si"):
                    shared.append("".join(t.text or "" for t in si.iter(_NS_X + "t")))
            sheets = [n for n in names if re.match(r"^xl/worksheets/sheet\d+\.xml$", n)]
            for sn in sorted(sheets)[:20]:
                root = ET.fromstring(zf.read(sn))
                for cell in root.iter(_NS_X + "c"):
                    kind = cell.get("t")
                    val = None
                    if kind == "s":
                        v = cell.find(_NS_X + "v")
                        if v is not None and v.text and v.text.strip().isdigit():
                            i = int(v.text.strip())
                            val = shared[i] if i < len(shared) else None
                    elif kind == "inlineStr":
                        val = "".join(t.text or "" for t in cell.iter(_NS_X + "t"))
                    elif kind in (None, "str"):
                        v = cell.find(_NS_X + "v")
                        val = v.text if v is not None else None
                        if val and _NUMERIC.match(val.strip()):
                            val = None          # 序号 / 学号 / 日期序列号：不是名字
                    if val:
                        out.append(val.strip())
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError, IndexError):
        pass
    return out


def _pieces_docx(path):
    """Word：段落、表格单元格里的文字都取出来"""
    out = []
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                return out
            root = ET.fromstring(zf.read("word/document.xml"))
        for p in root.iter(_NS_W + "p"):
            txt = "".join(t.text or "" for t in p.iter(_NS_W + "t")).strip()
            if txt:
                out.append(txt)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError):
        pass
    return out


def _pieces(path):
    low = path.lower()
    if low.endswith((".xlsx", ".xlsm")):
        return _pieces_xlsx(path)
    if low.endswith(".docx"):
        return _pieces_docx(path)
    if low.endswith((".txt", ".csv", ".md", ".list", ".names")):
        return _pieces_txt(path)
    if low.endswith(".xls"):
        # 老的二进制 .xls 读不了，先用纯文本方式兜一下（能捞到大部分汉字名）
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
            txt = blob.decode("utf-16-le", errors="ignore")
            return [s for s in re.split(r"[\r\n]+", txt) if s.strip()]
        except OSError:
            return []
    return []


def clean_name(tok):
    """Public wrapper used by the blacklist parser as well."""
    return _clean(tok)


def _clean(tok):
    tok = (tok or "").strip().strip("\"'“”‘’").strip()
    tok = re.sub(r"\s+", " ", tok)
    if not tok or len(tok) > 32:
        return None
    if _FORBID.search(tok) or _SEP_IN.search(tok):
        return None
    if _NUMERIC.match(tok):
        return None
    if tok in ("姓名", "名字", "真实姓名", "name", "Name", "NAME", "人员", "学生"):
        return None
    return tok


def _names_of_piece(piece):
    out = []
    whole = _clean(piece)
    if whole and " " not in whole and len(whole) >= 2:
        out.append(whole)
    for raw in _SPLIT.split(piece):
        c = _clean(raw)
        if c:
            out.append(c)
    return out


def scan_dir(d):
    """Read a directory of list files and return {lowercase: (display, source)}."""
    out = {}
    if not os.path.isdir(d):
        return out
    try:
        entries = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in entries:
        full = os.path.join(d, fn)
        if not os.path.isfile(full) or fn.startswith(".") or fn.startswith("~$"):
            continue
        for piece in _pieces(full):
            for name in _names_of_piece(piece):
                key = name.casefold()
                if key not in out:
                    out[key] = (name, fn)
    return out


def _scan():
    """真正读盘，返回 {小写名: (显示名, 来源文件名)}"""
    return scan_dir(dir_path())


def _stamp():
    d = dir_path()
    try:
        st = os.stat(d)
        base = [st.st_mtime_ns]
        for fn in os.listdir(d):
            try:
                base.append(os.stat(os.path.join(d, fn)).st_mtime_ns)
            except OSError:
                pass
        return tuple(base)
    except OSError:
        return (0,)


def data():
    """带缓存的读取结果：{小写名: (显示名, 来源)}"""
    stamp = _stamp()
    with _lock:
        if _cache["stamp"] != stamp:
            _cache["map"] = _scan()
            _cache["stamp"] = stamp
        return dict(_cache["map"])


def names():
    """按来源文件、名字排好的列表 [(显示名, 来源)]"""
    m = data()
    return sorted(m.values(), key=lambda t: (t[1], t[0]))


def count():
    return len(data())


def has(name):
    if not (name or "").strip():
        return False
    m = data()
    if not m:
        return True                     # 名单是空的 = 不限制
    if "*" in m or "所有人" in m or "任何人" in m:
        return True
    return name.strip().casefold() in m


def enforced():
    """白名单是否真的在起作用（有名字 + 配置没关）"""
    if not settings.flag("whitelist_enforce"):
        return False
    return count() > 0


# --------------------------------------------------------------------------- #
# 后台页用的增删（只动「manual.txt」）
# --------------------------------------------------------------------------- #
def _read_manual_lines():
    p = manual_path()
    if not os.path.exists(p):
        return []
    return _pieces_txt(p)


def _write_manual(lines):
    ensure_dir()
    p = manual_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(MANUAL_HEAD)
        for ln in lines:
            fh.write(ln + "\n")
    os.replace(tmp, p)


def add_manual(name):
    name = _clean(name)
    if not name:
        return False, "这个名字看起来不像人名"
    lines = _read_manual_lines()
    if any(ln.strip().casefold() == name.casefold() for ln in lines):
        return False, "「%s」已经在手动名单里了" % name
    lines.append(name)
    _write_manual(lines)
    return True, "已添加到白名单：%s" % name


def remove_manual(name):
    """从手动文件里删掉；如果这个名字只在别的文件里（Excel/Word 等），删不掉，交给黑名单"""
    name = (name or "").strip()
    lines = _read_manual_lines()
    keep = [ln for ln in lines if ln.strip().casefold() != name.casefold()]
    removed = len(keep) != len(lines)
    if removed:
        _write_manual(keep)
    return removed, len(lines) - len(keep)
