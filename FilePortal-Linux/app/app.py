# -*- coding: utf-8 -*-
# 模块说明：服务入口：解析启动参数、做路径校验并启动 HTTP/HTTPS 服务
"""文件服务平台 —— 入口。把本机的一个文件夹投射成网页，手机 / 平板 / 任意电脑都能访问。

    python app.py                       # 用默认配置启动（端口 8000）
    python app.py --port 8001 --root "D:\\别的文件夹"
"""

import argparse
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.settings import (CONFIG_FILE, CONFIG_LOADED, Config,
                             DEFAULT_HOST, DEFAULT_PASSWORD, DEFAULT_PORT,
                             DEFAULT_ROOT, LIST_CACHE_SECONDS, NAME_FULL, PW_FULL,
                             PW_READ, PW_STUDY, STUDY_SUBPATH, UPLOAD_SLOTS,
                             WORKERS, ZIP_SLOTS, LOGIN_MAX_FAILS, LOGIN_LOCK_SECONDS,
                             LOGIN_LOCK_MAX_SECONDS, LOGIN_RATE_PER_MINUTE,
                             LOGIN_FAIL_DELAY_MS, LOGIN_FAIL_DELAY_MAX_MS,
                             CERTFILE, KEYFILE, HTTPS_PORT,
                             validate_projection_root)
from server import denylist
from server.oplog import init_log
from server.handlers import Handler
from server.server import BoundedServer, shutdown


def local_ips():
    """枚举本机可用的局域网 IPv4 地址，用于启动提示和二维码。"""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


def port_available(port):
    """先尝试连接一次本机该端口：能连上说明已有程序在监听。
    （Windows 的 SO_REUSEADDR 允许两个程序抢同一端口，只靠 bind 判断不出来）"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.8):
            return False
    except OSError:
        return True


def wait_port_free(port, timeout=25.0):
    """等待旧服务释放端口；用于网页后台重启后的接替进程。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_available(port):
            return True
        time.sleep(0.25)
    return port_available(port)


def default_workers():
    """按 CPU 核数给出默认并发线程数，限制在 8~24。"""
    cpu = os.cpu_count() or 4
    return max(8, min(24, cpu * 2))


def main():
    """启动文件服务；支持命令行覆盖端口、根目录和密码。"""
    ap = argparse.ArgumentParser(description="网页版文件投射服务")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="要投射的文件夹")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="端口，默认 8000")
    ap.add_argument("--host", default=DEFAULT_HOST, help="监听地址，默认 0.0.0.0")
    ap.add_argument("--password", default=DEFAULT_PASSWORD, help="访问密码")
    ap.add_argument("--workers", type=int, default=WORKERS or default_workers(),
                    help="同时处理的请求数上限（默认按 CPU 自动算，一般 8~32）")
    # 网页后台重启专用：旧进程退出后，这个新进程先等端口释放再启动。
    # 单文件 EXE 也能用，避免依赖 python -c 守护进程。
    ap.add_argument("--restart-after-exit", type=int, default=0, metavar="OLD_PORT",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.restart_after_exit:
        wait_port_free(args.restart_after_exit)

    safe, why, normalized = validate_projection_root(args.root)
    if not safe:
        print("× 投射目录不安全：%s" % why)
        print("  请修改 config.ini 的 [服务器] projection_root，或换一个更具体的文件夹。")
        try:
            input("按回车退出…")
        except EOFError:
            pass
        return 1
    Config.root = normalized
    Config.port = args.port
    Config.host = args.host
    Config.password = args.password

    if not os.path.isdir(Config.root):
        print("× 目录不存在：%s" % Config.root)
        print("  请用 config.ini 的 projection_root 或 --root 指定一个存在的文件夹。")
        try:
            input("按回车退出…")
        except EOFError:
            pass
        return 1

    if Config.host in ("0.0.0.0", "") and not port_available(Config.port):
        print("[错误] 端口 %d 已被其他程序占用，服务无法启动。" % Config.port)
        print("       请先终止占用该端口的程序，或改用其他端口，例如：")
        print("           python app.py --port 8001")
        print("       更换端口后，请同步调整内网穿透映射的目标端口。")
        try:
            input("按回车键退出…")
        except EOFError:
            pass
        return 1

    log_path = init_log()

    print("=" * 62)
    print("  文件服务平台 · 服务进程已启动")
    print("=" * 62)
    print("  存储根目录：%s" % Config.root)
    print("  本机访问地址：http://127.0.0.1:%d" % Config.port)
    for ip in local_ips():
        print("  局域网地址：http://%s:%d" % (ip, Config.port))
    print("  外网访问：通过内网穿透将本机 %d 端口映射至外部即可" % Config.port)
    print("  旧版单密码：%s（出于安全考虑不显示明文）" % ("已启用" if Config.password else "未启用"))
    print("  配置文件：%s" % (CONFIG_FILE if CONFIG_LOADED else "（未找到 config.ini，当前使用内置默认值）"))
    print("  权限分档：全权限=%s｜学习资料=%s｜只读=%s" %
          ("已启用" if PW_FULL else "未启用",
           "已启用" if PW_STUDY else "未启用",
           "已启用" if PW_READ else "未启用"))
    if PW_FULL:
        print("            （全权限档要求访问者姓名 = %s）" % (NAME_FULL or "不限"))
    if PW_STUDY:
        print("            （学习资料档可访问范围：%s）" % STUDY_SUBPATH)
    print("  黑名单：%s" % ("%d 个姓名" % denylist.count() if denylist.count() else "空"))
    print("  并发上限：同时处理 %d 个请求（超出后排队，队列满则拒绝）；打包 %d 路、上传 %d 路"
          % (args.workers, ZIP_SLOTS, UPLOAD_SLOTS))
    print("  列表缓存：%s" % ("关闭" if LIST_CACHE_SECONDS <= 0 else "%.0f 秒" % LIST_CACHE_SECONDS))
    print("  登录防护：同一姓名连续失败 %d 次后锁定 %d 秒（反复失败最长锁定 %d 秒）；全站 %d 次/分钟；"
          "失败延迟 %d~%d ms"
          % (LOGIN_MAX_FAILS, LOGIN_LOCK_SECONDS, LOGIN_LOCK_MAX_SECONDS,
             LOGIN_RATE_PER_MINUTE, LOGIN_FAIL_DELAY_MS, LOGIN_FAIL_DELAY_MAX_MS))
    print("            （不采用 IP 封禁：经端口映射后所有来源 IP 均为 127.0.0.1，按 IP 封禁将导致全站不可用）")
    print("  操作日志：%s" % (log_path or "（目录不可写，本次不记录）"))
    print("  （关闭窗口或按 Ctrl+C 可停止服务）")
    print("=" * 62)

    try:
        httpd = BoundedServer((Config.host, Config.port), Handler,
                              max_workers=args.workers, max_backlog=args.workers * 4)
    except OSError as exc:
        print("[错误] 无法在 %s:%d 上启动服务：%s" % (Config.host, Config.port, exc))
        print("       常见原因为该端口已被其他程序占用。")
        print("       可改用其他端口启动，例如：")
        print("           python app.py --port 8001")
        print("       随后将内网穿透的目标端口调整为同一端口。")
        try:
            input("按回车键退出…")
        except EOFError:
            pass
        return 1

    Handler.workers_limit = args.workers
    tlssrv = None
    if CERTFILE and HTTPS_PORT and HTTPS_PORT != Config.port:
        # 两个口同时开：port 走 HTTP（本机/局域网照旧），HTTPS_PORT 走 HTTPS（给外面用）
        try:
            tlssrv = BoundedServer((Config.host, HTTPS_PORT), Handler,
                                   max_workers=args.workers, max_backlog=args.workers * 4)
            tlssrv.enable_tls(CERTFILE, KEYFILE)
            print("  已同时监听 HTTP :%d 与 HTTPS :%d（证书：%s）" % (Config.port, HTTPS_PORT, CERTFILE))
        except Exception as exc:
            print("[警告] HTTPS 端口 %d 启动失败，当前仅提供 HTTP 服务：%s" % (HTTPS_PORT, exc))
            if tlssrv is not None:
                try:
                    tlssrv.server_close()
                except OSError:
                    pass
                tlssrv = None
    elif CERTFILE:
        try:
            httpd.enable_tls(CERTFILE, KEYFILE)
            print("  已启用 HTTPS（证书：%s），请通过 https:// 访问" % CERTFILE)
        except Exception as exc:
            print("[警告] 证书加载失败，服务已退回 HTTP：%s" % exc)
    if tlssrv is not None:
        threading.Thread(target=tlssrv.serve_forever, kwargs={"poll_interval": 0.5},
                         daemon=True).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        shutdown(httpd)
        httpd.server_close()
        if tlssrv is not None:
            try:
                tlssrv.shutdown()
                tlssrv.server_close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
