# -*- coding: utf-8 -*-
# 模块说明：Windows 托盘：服务生命周期与后台入口
"""文件服务平台 · 系统托盘管理器（纯标准库，无第三方依赖）

在 Windows 通知区域显示命令行窗口图标：
  · 鼠标悬停：显示服务运行状态与端口
  · 右键菜单：打开控制台 / 重启任务 / 关闭任务
  · 双击图标：打开控制台

由 launcher.bat 通过 pythonw.exe 启动，无控制台窗口。
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import socket
import subprocess
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config.ini")
ICON = os.path.join(BASE, "assets", "images", "console.ico")
LOG = os.path.join(BASE, "runtime", "logs", "_tray.log")

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
iphlpapi.GetExtendedTcpTable.restype = wt.DWORD
iphlpapi.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD),
                                         wt.BOOL, wt.DWORD, wt.DWORD, wt.DWORD]


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wt.DWORD),
        ("dwLocalAddr", wt.DWORD),
        ("dwLocalPort", wt.DWORD),
        ("dwRemoteAddr", wt.DWORD),
        ("dwRemotePort", wt.DWORD),
        ("dwOwningPid", wt.DWORD),
    ]


TCP_TABLE_OWNER_PID_LISTENER = 3
AF_INET = 2

# 64 位下必须声明返回类型，否则句柄会被截断为 32 位
kernel32.GetModuleHandleW.restype = wt.HANDLE
kernel32.CreateMutexW.restype = wt.HANDLE
kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
user32.CreateWindowExW.restype = wt.HWND
user32.LoadImageW.restype = wt.HANDLE
user32.LoadIconW.restype = wt.HANDLE
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = ctypes.c_longlong
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
shell32.Shell_NotifyIconW.restype = wt.BOOL

gdi32.CreateFontW.restype = ctypes.c_void_p
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreateSolidBrush.argtypes = [wt.DWORD]
gdi32.SelectObject.argtypes = [wt.HDC, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
gdi32.GetDeviceCaps.restype = ctypes.c_int
gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
gdi32.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT]
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.BeginPaint.restype = wt.HDC
user32.BeginPaint.argtypes = [wt.HWND, ctypes.c_void_p]
user32.EndPaint.argtypes = [wt.HWND, ctypes.c_void_p]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.UpdateWindow.argtypes = [wt.HWND]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.SetCapture.restype = wt.HWND
user32.SetCapture.argtypes = [wt.HWND]
user32.ReleaseCapture.argtypes = []
user32.GetCapture.restype = wt.HWND
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.SetFocus.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetTimer.argtypes = [wt.HWND, wt.UINT, wt.UINT, ctypes.c_void_p]
user32.SetTimer.restype = wt.UINT
user32.KillTimer.argtypes = [wt.HWND, wt.UINT]
user32.SetProcessDPIAware.restype = wt.BOOL

WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_DESTROY = 0x0002
WM_CONTEXTMENU = 0x007B
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04

DT_LEFT = 0x0000
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020

WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_KEYDOWN = 0x0100
WM_KILLFOCUS = 0x0008
WM_ACTIVATE = 0x0006
VK_ESCAPE = 0x1B
WS_POPUP = 0x80000000
WS_BORDER = 0x00800000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
SW_HIDE = 0
SW_SHOW = 5
SM_CXSCREEN = 0
SM_CYSCREEN = 1

MENU_ITEMS = ((1, "打开控制台"), (2, "重启任务"), (3, "关闭任务"))

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
IDI_APPLICATION = 32512

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wt.HDC),
        ("fErase", wt.BOOL),
        ("rcPaint", wt.RECT),
        ("fRestore", wt.BOOL),
        ("fIncUpdate", wt.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]


def read_port():
    try:
        with open(CONFIG, "r", encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"\s*port\s*=\s*(\d+)", line)
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return 8000


PORT = read_port()


def python_exe():
    """优先返回 python.exe（用于打开控制台），pythonw 仅用于本脚本自身。"""
    exe = sys.executable or ""
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            return cand
    if exe and os.path.exists(exe):
        return exe
    return "python"


PY = python_exe()


def service_running():
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=0.4)
        s.close()
        return True
    except OSError:
        return False


def pid_on_port():
    """通过 IP Helper API 读取监听端口的进程 PID（不依赖外部命令）。"""
    size = wt.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, AF_INET,
                                 TCP_TABLE_OWNER_PID_LISTENER, 0)
    if not size.value:
        return None
    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, AF_INET,
                                       TCP_TABLE_OWNER_PID_LISTENER, 0)
    if ret != 0:
        return None
    count = ctypes.cast(buf, ctypes.POINTER(wt.DWORD)).contents.value
    rows = ctypes.cast(ctypes.byref(buf, ctypes.sizeof(wt.DWORD)),
                       ctypes.POINTER(MIB_TCPROW_OWNER_PID))
    for i in range(count):
        row = rows[i]
        local_port = ((row.dwLocalPort & 0xFF) << 8) | ((row.dwLocalPort >> 8) & 0xFF)
        if local_port == PORT:
            return int(row.dwOwningPid)
    return None


def stop_service():
    pid = pid_on_port()
    if not pid:
        return not service_running()
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        log_error()
        return False
    import time
    for _ in range(20):
        time.sleep(0.25)
        if not service_running():
            break
    return True


def start_service():
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        logf = open(os.path.join(BASE, "runtime", "logs", "_stdout.log"), "a",
                    encoding="utf-8", errors="ignore")
    except OSError:
        logf = subprocess.DEVNULL
    try:
        subprocess.Popen([PY, os.path.join(BASE, "app.py")], cwd=BASE,
                         stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                         close_fds=True,
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        log_error()
        return False
    finally:
        try:
            if logf is not subprocess.DEVNULL:
                logf.close()
        except Exception:  # noqa: BLE001
            pass
    import time
    for _ in range(40):
        time.sleep(0.25)
        if service_running():
            return True
    return False


def restart_service():
    stop_service()
    import time
    time.sleep(1)
    return start_service()


def open_console():
    line = 'cd /d "%s" && "%s" console.py' % (BASE, PY)
    try:
        subprocess.Popen('cmd.exe /k "%s"' % line, cwd=BASE,
                         creationflags=CREATE_NEW_CONSOLE)
    except Exception:  # noqa: BLE001
        log_error()


def log_error():
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")
    except OSError:
        pass


def tip_text():
    if service_running():
        return "文件服务平台 · 运行中（端口 %d）" % PORT
    return "文件服务平台 · 未运行（双击打开控制台）"


class TrayApp:
    def __init__(self):
        self.hwnd = None
        self.hicon = None
        self.nid = None
        self.port = PORT
        try:
            user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass
        self._wndproc_ref = WNDPROC(self._wndproc)
        self.menu_hwnd = None
        self.menu_hover = -1
        self._menu_wndproc_ref = WNDPROC(self._menu_wndproc)
        self._init_menu_resources()

    def _init_menu_resources(self):
        """自绘菜单所需的字体、画笔与尺寸（按系统 DPI 缩放）。"""
        hdc = user32.GetDC(None)
        self.dpi = gdi32.GetDeviceCaps(hdc, 88) or 96
        font_height = -int(round(9.0 * self.dpi / 72.0))
        self.menu_font = gdi32.CreateFontW(font_height, 0, 0, 0, 400, 0, 0, 0,
                                           1, 0, 0, 5, 0, "Microsoft YaHei UI")
        old = gdi32.SelectObject(hdc, self.menu_font)
        max_width = 0
        for _, label in MENU_ITEMS:
            size = wt.SIZE()
            gdi32.GetTextExtentPoint32W(hdc, label, len(label), ctypes.byref(size))
            max_width = max(max_width, size.cx)
        gdi32.SelectObject(hdc, old)
        user32.ReleaseDC(None, hdc)
        self.menu_item_w = max_width + int(round(48 * self.dpi / 96.0))
        self.menu_item_h = int(round(30 * self.dpi / 96.0))
        self.menu_bg_brush = gdi32.CreateSolidBrush(0x00FFFFFF)
        self.menu_sel_brush = gdi32.CreateSolidBrush(0x00F5E8D8)

    # ------------------------------------------------------------------ #
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                low = lparam & 0xFFFF
                if low in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self.show_menu(hwnd)
                    return 0
                if low == WM_LBUTTONDBLCLK:
                    open_console()
                    return 0
            elif msg == WM_COMMAND:
                cmd = wparam & 0xFFFF
                if cmd == 1:
                    open_console()
                elif cmd == 2:
                    restart_service()
                    self.refresh()
                elif cmd == 3:
                    stop_service()
                    self.quit()
                return 0
            elif msg == WM_TIMER:
                self.refresh()
                return 0
            elif msg == WM_DESTROY:
                user32.KillTimer(hwnd, 1)
                user32.PostQuitMessage(0)
                return 0
        except Exception:  # noqa: BLE001
            log_error()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------------ #
    def create_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW()
        cls.style = 0
        cls.lpfnWndProc = self._wndproc_ref
        cls.hInstance = hinst
        cls.lpszClassName = "FilePortalTrayWnd"
        if not user32.RegisterClassW(ctypes.byref(cls)):
            err = ctypes.get_last_error()
            if err != 1410:  # 类已注册
                raise OSError("RegisterClassW failed: %d" % err)
        self.hwnd = user32.CreateWindowExW(
            0, "FilePortalTrayWnd", "FilePortalTray", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW failed: %d" % ctypes.get_last_error())

        menu_cls = WNDCLASSW()
        menu_cls.style = 0
        menu_cls.lpfnWndProc = self._menu_wndproc_ref
        menu_cls.hInstance = hinst
        menu_cls.hbrBackground = self.menu_bg_brush
        menu_cls.lpszClassName = "FilePortalMenuWnd"
        if not user32.RegisterClassW(ctypes.byref(menu_cls)):
            err = ctypes.get_last_error()
            if err != 1410:
                raise OSError("RegisterClassW(menu) failed: %d" % err)
        self.menu_pad = int(round(6 * self.dpi / 96.0))
        menu_h = len(MENU_ITEMS) * self.menu_item_h + self.menu_pad * 2
        self.menu_hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW | WS_EX_TOPMOST, "FilePortalMenuWnd", "FilePortalMenu",
            WS_POPUP | WS_BORDER, 0, 0, self.menu_item_w, menu_h,
            None, None, hinst, None)
        if not self.menu_hwnd:
            raise OSError("CreateWindowExW(menu) failed: %d" % ctypes.get_last_error())

        if os.path.exists(ICON):
            self.hicon = user32.LoadImageW(None, ICON, IMAGE_ICON, 0, 0,
                                           LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not self.hicon:
            self.hicon = user32.LoadIconW(None, wt.LPARAM(IDI_APPLICATION))

    def add_icon(self):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.hicon
        nid.szTip = tip_text()[:127]
        self.nid = nid
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            raise OSError("Shell_NotifyIconW(NIM_ADD) failed")

    def refresh(self):
        if not self.nid:
            return
        self.nid.uFlags = NIF_TIP
        self.nid.szTip = tip_text()[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    # -------------------------- 自绘弹出菜单 -------------------------- #
    def _menu_point(self, lparam):
        return (ctypes.c_short(lparam & 0xFFFF).value,
                ctypes.c_short((lparam >> 16) & 0xFFFF).value)

    def _menu_index(self, x, y):
        if self.menu_pad <= y < self.menu_pad + len(MENU_ITEMS) * self.menu_item_h:
            if 0 <= x < self.menu_item_w:
                return (y - self.menu_pad) // self.menu_item_h
        return -1

    def _draw_menu(self, hdc):
        rc = wt.RECT()
        user32.GetClientRect(self.menu_hwnd, ctypes.byref(rc))
        user32.FillRect(hdc, ctypes.byref(rc), self.menu_bg_brush)
        old = gdi32.SelectObject(hdc, self.menu_font)
        gdi32.SetBkMode(hdc, 1)
        gdi32.SetTextColor(hdc, 0x001A1A1A)
        for idx, (_cmd, label) in enumerate(MENU_ITEMS):
            top = self.menu_pad + idx * self.menu_item_h
            item = wt.RECT(0, top, rc.right, top + self.menu_item_h)
            if idx == self.menu_hover:
                user32.FillRect(hdc, ctypes.byref(item), self.menu_sel_brush)
            text_rect = wt.RECT(item.left + int(round(20 * self.dpi / 96.0)),
                                item.top, item.right, item.bottom)
            user32.DrawTextW(hdc, label, -1, ctypes.byref(text_rect),
                             DT_SINGLELINE | DT_VCENTER | DT_LEFT)
        if old:
            gdi32.SelectObject(hdc, old)

    def _paint_menu(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        self._draw_menu(hdc)
        user32.EndPaint(hwnd, ctypes.byref(ps))

    def hide_menu(self):
        if not self.menu_hwnd:
            return
        user32.KillTimer(self.menu_hwnd, 7)
        if user32.GetCapture() == self.menu_hwnd:
            user32.ReleaseCapture()
        user32.ShowWindow(self.menu_hwnd, SW_HIDE)

    def _menu_wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_PAINT:
                self._paint_menu(hwnd)
                return 0
            if msg == WM_ERASEBKGND:
                return 1
            if msg == WM_MOUSEMOVE:
                x, y = self._menu_point(lparam)
                idx = self._menu_index(x, y)
                if idx != self.menu_hover:
                    self.menu_hover = idx
                    user32.InvalidateRect(hwnd, None, True)
                    user32.UpdateWindow(hwnd)
                return 0
            if msg == WM_LBUTTONDOWN:
                x, y = self._menu_point(lparam)
                if self._menu_index(x, y) < 0:
                    self.hide_menu()
                return 0
            if msg == WM_LBUTTONUP:
                x, y = self._menu_point(lparam)
                idx = self._menu_index(x, y)
                self.hide_menu()
                if idx >= 0 and self.hwnd:
                    user32.PostMessageW(self.hwnd, WM_COMMAND, MENU_ITEMS[idx][0], 0)
                return 0
            if msg == WM_RBUTTONDOWN:
                self.hide_menu()
                return 0
            if msg == WM_KEYDOWN and wparam == VK_ESCAPE:
                self.hide_menu()
                return 0
            if msg == WM_TIMER and wparam == 7:
                pos = wt.POINT()
                user32.GetCursorPos(ctypes.byref(pos))
                rc = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                inside = rc.left <= pos.x < rc.right and rc.top <= pos.y < rc.bottom
                pressed = user32.GetAsyncKeyState(0x01) & 0x8000 or user32.GetAsyncKeyState(0x02) & 0x8000
                if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                    self.hide_menu()
                    return 0
                if pressed and not inside:
                    self.hide_menu()
                    return 0
                return 0
        except Exception:  # noqa: BLE001
            log_error()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def show_menu(self, hwnd):
        if not self.menu_hwnd:
            return
        pos = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
        rc = wt.RECT()
        user32.GetClientRect(self.menu_hwnd, ctypes.byref(rc))
        w, h = rc.right, rc.bottom
        sw = user32.GetSystemMetrics(SM_CXSCREEN)
        sh = user32.GetSystemMetrics(SM_CYSCREEN)
        x = max(0, min(pos.x, sw - w))
        y = max(0, min(pos.y, sh - h))
        self.menu_hover = -1
        user32.SetWindowPos(self.menu_hwnd, ctypes.c_void_p(-1), x, y, w, h,
                            0x0040)  # HWND_TOPMOST | SWP_SHOWWINDOW
        user32.ShowWindow(self.menu_hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.menu_hwnd)
        user32.SetFocus(self.menu_hwnd)
        user32.SetCapture(self.menu_hwnd)
        user32.InvalidateRect(self.menu_hwnd, None, True)
        user32.UpdateWindow(self.menu_hwnd)
        user32.SetTimer(self.menu_hwnd, 7, 100, None)

    def quit(self):
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None
        if self.menu_hwnd:
            user32.DestroyWindow(self.menu_hwnd)
            self.menu_hwnd = None
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        for obj in (getattr(self, "menu_font", None),
                    getattr(self, "menu_bg_brush", None),
                    getattr(self, "menu_sel_brush", None)):
            if obj:
                gdi32.DeleteObject(obj)


def ensure_service():
    """--ensure 模式：确保服务在运行，供启动批处理调用。"""
    if service_running():
        print("  [INFO] File Service Platform is already running on port %d." % PORT)
        return 0
    print("  [INFO] Starting File Service Platform on port %d..." % PORT)
    if start_service():
        print("  [INFO] Service started: http://127.0.0.1:%d" % PORT)
        return 0
    print("  [ERROR] Service failed to start. See runtime/logs/_stdout.log for details.")
    return 1


def main():
    if "--ensure" in sys.argv:
        return ensure_service()
    mutex = kernel32.CreateMutexW(None, False, "Local\\FilePortalTrayPy")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return 0
    app = TrayApp()
    app.create_window()
    app.add_icon()
    user32.SetTimer(app.hwnd, 1, 2000, None)
    app.refresh()
    msg = wt.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    app.quit()
    kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        log_error()
        sys.exit(1)
