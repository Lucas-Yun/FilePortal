# -*- coding: utf-8 -*-
"""有界并发服务器：线程池 + 队列上限，人再多也不会把电脑拖垮。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, addr, handler, max_workers=16, max_backlog=64):
        super().__init__(addr, handler)
        self.max_workers = max_workers
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fs")
        # 同时处理的 + 排队的最多这么多个，超了就直接断开，保护机器
        self._slots = threading.BoundedSemaphore(max_workers + max_backlog)
        self.dropped = 0

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.dropped += 1
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            self._pool.submit(self._run, request, client_address)
        except RuntimeError:
            self._slots.release()
            try:
                request.close()
            except OSError:
                pass

    def _run(self, request, client_address):
        try:
            self.process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def enable_tls(self, certfile, keyfile=""):
        """把监听口套上 TLS（config.ini 里配了 certfile/keyfile 才会走这里）。"""
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile or None)
        # TLS 1.0 / 1.1 are deprecated; explicitly disable them and enforce 1.2+.
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        self.socket = ctx.wrap_socket(self.socket, server_side=True)
        self.tls_enabled = True


def shutdown(server):
    server._pool.shutdown(wait=False, cancel_futures=True)
