# -*- coding: utf-8 -*-
# 模块说明：Windows 单文件便携版启动器：部署数据目录并分发各运行模式
"""FilePortal Portable entry.

One executable. First run creates a FilePortalData folder next to the EXE
(like PCL creating .minecraft) and seeds config/data/assets/docs there.
"""
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

DATA_DIR_NAME = "FilePortalData"
WINDOW_TITLE = "FilePortal"


def _app_dir() -> Path:
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    """PyInstaller onefile extraction dir, or the app dir when running source."""
    return Path(getattr(sys, "_MEIPASS", _app_dir()))


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _message(text: str) -> None:
    """Best-effort user-visible error without opening a console."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), WINDOW_TITLE, 0x10)
    except Exception:
        try:
            print(text)
        except Exception:
            pass


def _windows_documents() -> str:
    """Ask Windows for the real Documents known-folder (OneDrive redirect aware)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                         (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                                                 wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ptr = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(ptr))
        if hr == 0 and ptr.value:
            value = ptr.value
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            return value
    except Exception:
        pass

    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return ""


def documents_dir() -> Path:
    if os.name == "nt":
        value = _windows_documents()
        if value:
            p = Path(value)
            if p.is_dir():
                return p
        p = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
        if p.is_dir():
            return p
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "FilePortalShare"

    # Linux/macOS fallback for the shared logic; Linux launcher writes its own config.
    try:
        out = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        if out and Path(out).is_dir():
            return Path(out)
    except Exception:
        pass
    p = Path.home() / "Documents"
    if p.is_dir():
        return p
    return Path.home() / "FilePortalShare"


def _safe_target() -> Path:
    base = _exe_dir() / DATA_DIR_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return base
    except OSError:
        fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / DATA_DIR_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        _message("EXE 所在目录不可写，数据已改放到：\n%s" % fallback)
        return fallback


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        elif not target.exists():
            shutil.copy2(item, target)


def _seed_config(home: Path, docs: Path) -> None:
    cfg = home / "config.ini"
    if cfg.exists():
        return
    bundle = _bundle_dir()
    template = bundle / "config.ini"
    if not template.exists():
        template = _app_dir() / "config.ini"
    try:
        text = template.read_text(encoding="utf-8-sig") if template.exists() else ""
    except OSError:
        text = ""
    if not text:
        text = (
            "[服务器]\nport = 8000\nhost = 0.0.0.0\n"
            "projection_root = \nworkers =\n\n"
            "[密码]\npw_full = \nadmin_password = \n"
        )
    root_line = "projection_root = %s" % str(docs)
    text = re.sub(r"(?m)^\s*projection_root\s*=.*$", lambda _m: root_line, text)
    text = re.sub(r"(?m)^\s*root\s*=.*$", lambda _m: "root = %s" % str(docs), text)
    if not re.search(r"(?m)^\s*projection_root\s*=", text):
        text = text.replace("[服务器]", "[服务器]\n" + root_line, 1)
    cfg.write_text(text, encoding="utf-8")


def prepare_home() -> Path:
    home = _safe_target()
    bundle = _bundle_dir()
    docs = documents_dir()

    # 1) seed data/assets/docs only when missing; never overwrite user files.
    data_src = bundle / "seed_data"
    if not data_src.is_dir():
        data_src = _app_dir() / "data"
    _copy_tree(data_src, home / "data")

    assets_src = bundle / "assets"
    if not assets_src.is_dir():
        assets_src = _app_dir() / "assets"
    _copy_tree(assets_src, home / "assets")

    docs_src = bundle / "docs"
    if not docs_src.is_dir():
        docs_src = _app_dir() / "docs"
    _copy_tree(docs_src, home / "docs")

    (home / "certs").mkdir(parents=True, exist_ok=True)
    (home / "runtime" / "logs").mkdir(parents=True, exist_ok=True)
    (home / "runtime" / "cache").mkdir(parents=True, exist_ok=True)

    # 2) config is generated once, using the real Documents folder of this PC.
    _seed_config(home, docs)
    # 学习资料档默认只看这个子目录；先建好空目录，避免首次登录 404。
    try:
        (docs / "文件" / "学习资料").mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return home


def _set_home(home: Path) -> None:
    os.environ["FILEPORTAL_HOME"] = str(home)
    os.environ.setdefault("FILEPORTAL_PORTABLE", "1")


def _spawn(mode: str) -> None:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, mode]
        cwd = str(_exe_dir())
    else:
        cmd = [sys.executable, str(_app_dir() / "portable.py"), mode]
        cwd = str(_app_dir())
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_GROUP | NO_WINDOW
    subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, creationflags=flags)


def _allocation_console() -> None:
    """A windowed onefile exe has no console; create one for --console mode."""
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            ctypes.windll.kernel32.AllocConsole()
    except Exception:
        pass


def _run_console() -> int:
    _allocation_console()
    try:
        from console import main
        return main() or 0
    except Exception as exc:  # noqa: BLE001
        _message("控制台启动失败：%s" % exc)
        return 1


def main() -> int:
    home = prepare_home()
    _set_home(home)

    raw = list(sys.argv[1:])
    mode = "default"
    for flag in ("--service", "--tray", "--ensure", "--console",
                 "--update-mode", "--maintenance-server"):
        if flag in raw:
            mode = flag[2:]
            break
    # 网页后台重启的新进程：强制走服务模式，但保留 --restart-after-exit 给 app.py。
    if "--restart-after-exit" in raw:
        mode = "service"
    # app.py / tray.py / console.py 不认识的模式参数在这里移除。
    args = [a for a in raw if a not in ("--service", "--tray", "--ensure", "--console",
                                        "--update-mode", "--maintenance-server")]
    sys.argv = [sys.argv[0]] + args

    if mode == "service":
        from app import main as service_main
        return service_main() or 0
    if mode == "tray":
        from tray import main as tray_main
        return tray_main() or 0
    if mode == "ensure":
        from tray import ensure_service
        return ensure_service()
    if mode == "console":
        return _run_console()
    if mode == "update-mode":
        from update_mode import main as update_main
        return update_main(args) or 0
    if mode == "maintenance-server":
        from update_server import main as maintenance_main
        return maintenance_main(args) or 0

    # Default double-click: ensure service, open the browser, then run the tray
    # in this same process. Spawning a separate --tray child would let the
    # onefile main exit immediately and trigger PyInstaller temp-dir cleanup
    # warnings while the tray still uses the extracted files.
    try:
        from tray import ensure_service, service_running, main as tray_main
        if not service_running():
            ok = ensure_service()
            if ok != 0:
                _message("服务启动失败。请查看：\n%s" % (home / "runtime" / "logs" / "_stdout.log"))
                return 1
        try:
            from server import settings
            port = settings.DEFAULT_PORT
        except Exception:
            port = 8000
        time.sleep(0.2)
        webbrowser.open("http://127.0.0.1:%d" % port)
        return tray_main()
    except Exception as exc:  # noqa: BLE001
        _message("FilePortal 启动失败：%s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
