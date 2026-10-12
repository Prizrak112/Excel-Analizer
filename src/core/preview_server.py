"""
Локальный preview-сервер для Конструктора.

Показывает HTML в браузере и умеет автоматически перезагружать
вкладку, когда в приложении что-то поменялось.

Технически: HTTP-сервер из стандартной библиотеки + SSE
(Server-Sent Events — односторонний WebSocket).
Внешних зависимостей нет.
"""

from __future__ import annotations

import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# ============================================================
# Наш сервер (расширение стандартного)
# ============================================================

class _PreviewHTTPServer(ThreadingHTTPServer):
    """
    ThreadingHTTPServer + наше состояние.
    daemon_threads — потоки клиентов не мешают выходу из приложения.
    allow_reuse_address — не падать, если порт только что освободился.
    """
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler):
        super().__init__(addr, handler)
        self.html: str = "<h1>Пока пусто</h1>"
        self.version: int = 0
        self.running: bool = True
        self._cond = threading.Condition()

    def update_html(self, html: str):
        """Обновить HTML и разбудить SSE-клиентов. Только если изменилось."""
        with self._cond:
            if html == self.html:
                return  # ничего не поменялось — не дёргаем браузер
            self.html = html
            self.version += 1
            self._cond.notify_all()

    def wait_next_version(self, last_version: int, timeout: float = 15.0) -> int | None:
        """
        Ждёт, пока version станет больше last_version.
        None = таймаут или остановка сервера.
        """
        with self._cond:
            while self.running and self.version <= last_version:
                if not self._cond.wait(timeout=timeout):
                    return None
            if not self.running:
                return None
            return self.version


# ============================================================
# HTTP-обработчик
# ============================================================

class _Handler(BaseHTTPRequestHandler):
    """Обрабатывает GET /, /events и /__ping."""

    def log_message(self, *args, **kwargs):
        pass  # не мусорим в консоль

    def handle_one_request(self):
        """
        ★ Безопасная версия: стандартный http.server не ловит
        ConnectionAbortedError при чтении requestline на Windows,
        из-за чего в консоль валится трейсбек, когда браузер
        закрывает keep-alive соединение.
        """
        try:
            super().handle_one_request()
        except (ConnectionAbortedError,
                ConnectionResetError,
                BrokenPipeError,
                TimeoutError,
                OSError):
            self.close_connection = True

    def handle(self):
        """Обернуть весь цикл — на случай, если ошибка придёт вне
        handle_one_request."""
        try:
            super().handle()
        except (ConnectionAbortedError,
                ConnectionResetError,
                BrokenPipeError,
                TimeoutError,
                OSError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/events":
            self._serve_events()
        elif path == "/__ping":
            self._send(200, "text/plain", b"ok")
        else:
            self._send(404, "text/plain", b"not found")

    # ---------- Главная страница ----------

    def _serve_html(self):
        html = self.server.html
        # Вставляем SSE-скрипт прямо перед </body>
        if "</body>" in html:
            html = html.replace("</body>", _SSE_SCRIPT + "</body>", 1)
        else:
            html += _SSE_SCRIPT
        self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

    def _send(self, code: int, content_type: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    # ---------- SSE: длинный стрим ----------

    def _serve_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # Сообщаем клиенту, что соединение установлено
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
        except OSError:
            return

        # Стартуем с ТЕКУЩЕЙ версии — не шлём reload сразу после подключения.
        last = self.server.version
        while self.server.running:
            v = self.server.wait_next_version(last, timeout=15.0)
            if v is None:
                # Таймаут или остановка — keep-alive пинг, чтобы соединение жило
                if not self.server.running:
                    break
                try:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                except OSError:
                    break
                continue
            last = v
            try:
                self.wfile.write(b"event: reload\ndata: 1\n\n")
                self.wfile.flush()
            except OSError:
                break


# ============================================================
# Скрипт, который вставляется в HTML
# ============================================================

_SSE_SCRIPT = """
<script>
(function () {
    if (window.__ea_preview_sse) return;
    window.__ea_preview_sse = true;

    // ── Восстанавливаем позицию скролла и активную секцию после reload ──
    (function restoreScroll() {
        try {
            var y = sessionStorage.getItem('__ea_scroll_y');
            var hash = sessionStorage.getItem('__ea_scroll_hash');
            if (hash && location.hash !== hash) {
                history.replaceState(null, '', hash);
            }
            if (y !== null) {
                // Восстанавливаем без анимации, сразу
                window.scrollTo(0, parseInt(y, 10) || 0);
            }
        } catch (e) {}
        sessionStorage.removeItem('__ea_scroll_y');
        sessionStorage.removeItem('__ea_scroll_hash');
    })();

    function connect() {
        try {
            const es = new EventSource('/events');
            es.addEventListener('reload', function () {
                try {
                    sessionStorage.setItem('__ea_scroll_y', String(window.scrollY));
                    sessionStorage.setItem('__ea_scroll_hash', location.hash || '');
                } catch (e) {}
                location.reload();
            });
            es.onerror = function () {
                es.close();
                setTimeout(connect, 1000);
            };
        } catch (e) {
            setTimeout(connect, 2000);
        }
    }
    connect();
})();
</script>
"""


# ============================================================
# Публичный класс
# ============================================================

class PreviewServer:
    """
    Локальный preview-сервер.

    Пример:
        server = PreviewServer()
        server.open_in_browser()        # старт + открыть вкладку
        server.show("<h1>Привет!</h1>") # обновить → браузер сам перезагрузится
        ...
        server.stop()
    """

    def __init__(self, host: str = "127.0.0.1",
                 base_port: int = 8765, max_tries: int = 20):
        self.host = host
        self.base_port = base_port
        self.max_tries = max_tries

        self._server: _PreviewHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None

    # ---------- Внутреннее ----------

    def _pick_port(self) -> int | None:
        """Найти свободный порт, начиная с base_port."""
        for i in range(self.max_tries):
            port = self.base_port + i
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((self.host, port))
                    return port
                except OSError:
                    continue
        return None

    # ---------- Свойства ----------

    @property
    def url(self) -> str | None:
        if self.port is None:
            return None
        return f"http://{self.host}:{self.port}/"

    @property
    def is_running(self) -> bool:
        return self._server is not None

    # ---------- Публичное ----------

    def start(self) -> str | None:
        """Запустить сервер. Возвращает URL или None."""
        if self._server is not None:
            return self.url

        port = self._pick_port()
        if port is None:
            print(f"[PreviewServer] Нет свободного порта от {self.base_port}")
            return None

        try:
            server = _PreviewHTTPServer((self.host, port), _Handler)
        except OSError as e:
            print(f"[PreviewServer] Не удалось стартовать: {e}")
            return None

        self._server = server
        self.port = port

        t = threading.Thread(
            target=server.serve_forever,
            name="PreviewServer",
            daemon=True,
        )
        t.start()
        self._thread = t

        print(f"[PreviewServer] Стартовал: {self.url}")
        return self.url

    def show(self, html: str):
        """Обновить HTML. Открытые вкладки перезагрузятся сами."""
        if self._server is None:
            self.start()
        if self._server is not None:
            self._server.update_html(html)

    def open_in_browser(self):
        """Старт (если нужно) + открыть вкладку браузера."""
        url = self.start()
        if url:
            webbrowser.open(url)

    def stop(self):
        """Остановить сервер."""
        if self._server is None:
            return
        try:
            self._server.running = False
            with self._server._cond:
                self._server._cond.notify_all()
            self._server.shutdown()
            self._server.server_close()
        except Exception as e:
            print(f"[PreviewServer] Ошибка остановки: {e}")
        finally:
            self._server = None
            self._thread = None
            self.port = None
            print("[PreviewServer] Остановлен")