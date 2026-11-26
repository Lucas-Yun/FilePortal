# -*- coding: utf-8 -*-
# 模块说明：Linux 启动器：启动前检查和后台服务拉起
"""Linux launcher/console for FilePortal.

The Linux edition is source-based: data, assets and docs stay in ``app/``.
On first run it rewrites Windows paths in ``app/config.ini`` to Linux paths
(projection folder = the user's Documents folder, cloud folder = ~/FilePortalCloud).
"""
import os
import re
import sys
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG = APP_DIR / "config.ini"
LOG_DIR = APP_DIR / "runtime" / "logs"
STDOUT_LOG = LOG_DIR / "_stdout.log"
PORT = 8000


def _read_config():
    try:
        return CONFIG.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _set_ini_key(text, key, value):
    pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=.*$", re.MULTILINE)
    line = "%s = %s" % (key, value)
    if pattern.search(text):
        return pattern.sub(lambda m: line, text, count=1)
    # key missing: add it right after the [服务器] header if present
    marker = re.search(r"^\[服务器\]\s*$", text, re.MULTILINE)
    if marker:
        pos = marker.end()
        return text[:pos] + "\n" + line + text[pos:]
    return text + "\n" + line + "\n"


def _xdg_documents():
    try:
        out = __import__("subprocess").run(["xdg-user-dir", "DOCUMENTS"],
                                           capture_output=True, text=True, timeout=5).stdout.strip()
        if out and Path(out).is_dir():
            return Path(out).resolve()
    except Exception:
        pass
    cfg = Path.home() / ".config" / "user-dirs.dirs"
    try:
        for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("XDG_DOCUMENTS_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
                raw = raw.replace("$HOME", str(Path.home()))
                p = Path(raw)
                if p.is_dir():
                    return p.resolve()
    except OSError:
        pass
    docs = Path.home() / "Documents"
    if docs.is_dir():
        return docs.resolve()
    share = Path.home() / "FilePortalShare"
    share.mkdir(parents=True, exist_ok=True)
    return share.resolve()


def _is_windows_path(value):
    return bool(re.match(r"^[A-Za-z]:[\\/]", value or "")) or "\\" in (value or "")


def ensure_config():
    text = _read_config()
    if not text:
        text = "[服务器]\nport = 8000\nhost = 0.0.0.0\n"
    docs = _xdg_documents()
    try:
        (docs / "文件" / "学习资料").mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    current = ""
    m = re.search(r"^[ \t]*projection_root[ \t]*=[ \t]*(.*)$", text, re.MULTILINE)
    if m:
        current = m.group(1).strip()
    if (not current) or _is_windows_path(current):
        text = _set_ini_key(text, "projection_root", str(docs))
        # older key: keep it in sync so old code and old docs still work
        text = _set_ini_key(text, "root", str(docs))
    cloud = ""
    cm = re.search(r"^[ \t]*cloud_root[ \t]*=[ \t]*(.*)$", text, re.MULTILINE)
    if cm:
        cloud = cm.group(1).strip()
    if (not cloud) or _is_windows_path(cloud) or not os.path.isabs(cloud):
        cloud_dir = Path.home() / "FilePortalCloud"
        cloud_dir.mkdir(parents=True, exist_ok=True)
        text = _set_ini_key(text, "cloud_root", str(cloud_dir))
    if text != _read_config():
        tmp = CONFIG.with_suffix(".ini.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, CONFIG)
    return docs


def _load_service():
    sys.path.insert(0, str(APP_DIR))
    import linux_service  # noqa: E402
    return linux_service


def _begin():
    os.environ["FILEPORTAL_HOME"] = str(APP_DIR)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _ensure(path, port):
    _begin()
    if path.is_listening(port):
        return True
    return path.start_service(APP_DIR, port, str(STDOUT_LOG))


def _service_pid(path, port):
    return path.pid_on_port(port)


def _browser():
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        webbrowser.open("http://127.0.0.1:%d/" % PORT, new=2)


def main():
    args = [a.lower() for a in sys.argv[1:]]
    mode = args[0].lstrip("-") if args else "run"
    if mode in ("service", "server"):
        ensure_config()
        os.environ["FILEPORTAL_HOME"] = str(APP_DIR)
        sys.path.insert(0, str(APP_DIR))
        import app
        # app.py has its own argparse: drop the launcher-only mode flag.
        sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:]
                                    if a not in ("--service", "--server")]
        app.main()
        return 0

    service = _load_service()
    ensure_config()
    if mode in ("console", "cmd", "terminal"):
        import console
        return console.main()
    if mode in ("ensure", "start", "run"):
        ok = _ensure(service, PORT)
        print("服务已启动: http://127.0.0.1:%d" % PORT if ok else "服务启动失败，请查看 %s" % STDOUT_LOG)
        if mode != "ensure":
            _browser()
        return 0 if ok else 1
    if mode in ("status", "check"):
        pid = _service_pid(service, PORT)
        print("运行中，PID=%s" % pid if pid else "未运行")
        return 0 if pid else 1
    if mode in ("stop", "quit", "exit"):
        ok = service.stop_service(PORT)
        print("已停止" if ok else "停止失败")
        return 0 if ok else 1
    if mode in ("open", "browse"):
        _browser()
        return 0
    if mode in ("help", "--help", "-h"):
        print("用法: ./launcher.sh [run|start|ensure|stop|status|console|open|help]")
        return 0
    print("未知参数: %s" % sys.argv[1:])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
