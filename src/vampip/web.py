from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import mimetypes
import re
import threading
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser

from vampip.database import connect
from vampip.manager_state import get_or_create_api_token
from vampip.service import ManagerService


MAX_REQUEST_BYTES = 1024 * 1024
_LOOPBACK_NAMES = {"127.0.0.1", "localhost"}
_LEASE_RENEW = re.compile(r"^/api/leases/([A-Fa-f0-9]{32})/renew$")
_LEASE_ITEM = re.compile(r"^/api/leases/([A-Fa-f0-9]{32})$")
_RESOURCE_THUMBNAIL = re.compile(r"^/api/resources/([0-9]+)/thumbnail$")
_RESOURCE_LEASE = re.compile(r"^/api/resources/([0-9]+)/lease$")
_TOKEN_IN_LOG = re.compile(r"([?&]token=)[^&\s\"]+")


def _bool_query(values: dict[str, list[str]], key: str) -> bool | None:
    raw = values.get(key, [""])[0].casefold()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


class ManagerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: ManagerService,
        api_token: str,
    ) -> None:
        super().__init__(address, ManagerRequestHandler)
        self.service = service
        self.api_token = api_token


class ManagerRequestHandler(BaseHTTPRequestHandler):
    server: ManagerHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        if len(args) >= 2:
            try:
                if int(str(args[1])) < 400:
                    return
            except ValueError:
                pass
        message = _TOKEN_IN_LOG.sub(r"\1<redacted>", format % args)
        print(f"[VAM-PIP web] {self.client_address[0]} {message}")

    def _send(
        self,
        status: int,
        payload: bytes,
        content_type: str,
        *,
        cache: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers routinely cancel image and search requests as cards are
            # replaced. A disconnected client is not a manager failure.
            self.close_connection = True

    def _json(self, status: int, document: object) -> None:
        payload = (
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        self._send(status, payload, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message, "status": status})

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = urlsplit(f"//{host}").hostname
        return hostname is not None and hostname.casefold() in _LOOPBACK_NAMES

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.hostname.casefold() in _LOOPBACK_NAMES
        )

    def _provided_token(self, query: dict[str, list[str]]) -> str:
        header = self.headers.get("X-VAMPIP-Token", "")
        if header:
            return header
        return query.get("token", [""])[0]

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        provided = self._provided_token(query)
        return bool(provided) and hmac.compare_digest(provided, self.server.api_token)

    def _read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.casefold().startswith("application/json"):
            raise ValueError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        try:
            document = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body is not valid JSON") from exc
        if not isinstance(document, dict):
            raise ValueError("request JSON must be an object")
        return document

    @staticmethod
    def _roots(document: dict[str, Any]) -> list[str]:
        roots = document.get("roots")
        if not isinstance(roots, list) or not all(
            isinstance(item, str) for item in roots
        ):
            raise ValueError("roots must be a list of package references")
        return roots

    def _serve_static(self, path: str) -> None:
        names = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/styles.css": "styles.css",
        }
        name = names.get(path)
        if name is None:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            payload = (
                resources.files("vampip").joinpath("webui").joinpath(name).read_bytes()
            )
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "web UI asset is missing")
            return
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
        }:
            content_type += "; charset=utf-8"
        self._send(
            HTTPStatus.OK,
            payload,
            content_type,
            cache="no-cache" if name == "index.html" else "public, max-age=3600",
        )

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if not self._host_allowed():
            self._error(HTTPStatus.BAD_REQUEST, "loopback Host header required")
            return
        if not parsed.path.startswith("/api/"):
            self._serve_static(parsed.path)
            return
        if not self._authorized(query):
            self._error(HTTPStatus.UNAUTHORIZED, "invalid manager token")
            return
        try:
            if parsed.path == "/api/status":
                self._json(HTTPStatus.OK, self.server.service.status())
                return
            if parsed.path == "/api/packages":
                self._json(
                    HTTPStatus.OK,
                    self.server.service.list_packages(
                        query=query.get("q", [""])[0],
                        state=query.get("state", ["all"])[0],
                        limit=int(query.get("limit", ["100"])[0]),
                        offset=int(query.get("offset", ["0"])[0]),
                    ),
                )
                return
            if parsed.path == "/api/resources":
                result = self.server.service.search_resources(
                    query=query.get("q", [""])[0],
                    resource_type=query.get("type", [""])[0],
                    state=query.get("state", ["all"])[0],
                    favorite=_bool_query(query, "favorite"),
                    limit=int(query.get("limit", ["100"])[0]),
                    offset=int(query.get("offset", ["0"])[0]),
                )
                for item in result.get("items", []):
                    item["thumbnail_url"] = (
                        f"/api/resources/{item['id']}/thumbnail"
                        f"?token={self.server.api_token}"
                    )
                self._json(HTTPStatus.OK, result)
                return
            if parsed.path == "/api/catalog/facets":
                self._json(HTTPStatus.OK, self.server.service.catalog_facets())
                return
            thumbnail = _RESOURCE_THUMBNAIL.fullmatch(parsed.path)
            if thumbnail:
                result = self.server.service.resource_thumbnail(int(thumbnail.group(1)))
                if result is None:
                    self._error(HTTPStatus.NOT_FOUND, "thumbnail not found")
                    return
                thumbnail_path, content_type = result
                payload = thumbnail_path.read_bytes()
                self._send(
                    HTTPStatus.OK,
                    payload,
                    content_type,
                    cache="private, max-age=86400",
                )
                return
            self._error(HTTPStatus.NOT_FOUND, "API route not found")
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:
            self.log_error("GET failed: %s", exc)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal manager error")

    def do_POST(self) -> None:
        self._mutating_request("POST")

    def do_DELETE(self) -> None:
        self._mutating_request("DELETE")

    def _mutating_request(self, method: str) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if not self._host_allowed():
            self.close_connection = True
            self._error(HTTPStatus.BAD_REQUEST, "loopback Host header required")
            return
        if not self._origin_allowed():
            self.close_connection = True
            self._error(HTTPStatus.FORBIDDEN, "cross-origin request refused")
            return
        if not self._authorized(query):
            self.close_connection = True
            self._error(HTTPStatus.UNAUTHORIZED, "invalid manager token")
            return
        try:
            document = self._read_json() if method == "POST" else {}
            service = self.server.service
            if method == "POST" and parsed.path == "/api/scan":
                result: dict[str, object] = {"packages": service.scan_packages()}
                if bool(document.get("catalog", True)):
                    result["catalog"] = service.import_catalog()
                self._json(HTTPStatus.OK, result)
                return
            if method == "POST" and parsed.path == "/api/catalog/import":
                self._json(HTTPStatus.OK, service.import_catalog())
                return
            if method == "POST" and parsed.path == "/api/pins":
                self._json(
                    HTTPStatus.OK,
                    service.pin(
                        self._roots(document),
                        label=(
                            str(document["label"])
                            if document.get("label") is not None
                            else None
                        ),
                        apply=bool(document.get("apply", False)),
                    ),
                )
                return
            if method == "DELETE" and parsed.path.startswith("/api/pins/"):
                root = unquote(parsed.path[len("/api/pins/") :])
                self._json(
                    HTTPStatus.OK,
                    service.unpin(
                        root,
                        apply=query.get("apply", ["false"])[0].casefold() == "true",
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/leases":
                self._json(
                    HTTPStatus.OK,
                    service.lease(
                        self._roots(document),
                        days=float(document.get("days", 3)),
                        label=(
                            str(document["label"])
                            if document.get("label") is not None
                            else None
                        ),
                        apply=bool(document.get("apply", True)),
                    ),
                )
                return
            resource_lease = _RESOURCE_LEASE.fullmatch(parsed.path)
            if method == "POST" and resource_lease:
                self._json(
                    HTTPStatus.OK,
                    service.lease_resource(
                        int(resource_lease.group(1)),
                        days=float(document.get("days", 3)),
                        label=(
                            str(document["label"])
                            if document.get("label") is not None
                            else None
                        ),
                        apply=bool(document.get("apply", True)),
                    ),
                )
                return
            renew = _LEASE_RENEW.fullmatch(parsed.path)
            if method == "POST" and renew:
                self._json(
                    HTTPStatus.OK,
                    service.renew(
                        renew.group(1),
                        days=float(document.get("days", 3)),
                    ),
                )
                return
            lease = _LEASE_ITEM.fullmatch(parsed.path)
            if method == "DELETE" and lease:
                self._json(
                    HTTPStatus.OK,
                    service.release(
                        lease.group(1),
                        apply=query.get("apply", ["true"])[0].casefold() != "false",
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/reconcile":
                self._json(
                    HTTPStatus.OK,
                    service.reconcile(
                        apply=bool(document.get("apply", False)),
                        activate=bool(document.get("activate", False)),
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/deactivate":
                self._json(
                    HTTPStatus.OK,
                    service.deactivate(apply=bool(document.get("apply", False))),
                )
                return
            if method == "POST" and parsed.path == "/api/settings":
                if "auto_reconcile" in document:
                    service.set_auto_reconcile(bool(document["auto_reconcile"]))
                self._json(
                    HTTPStatus.OK,
                    {"auto_reconcile": service.auto_reconcile_enabled()},
                )
                return
            if method == "POST" and parsed.path == "/api/vam/launch":
                self._json(
                    HTTPStatus.OK,
                    service.launch_vam(reconcile=bool(document.get("reconcile", True))),
                )
                return
            self._error(HTTPStatus.NOT_FOUND, "API route not found")
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:
            self.log_error("%s failed: %s", method, exc)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal manager error")


class AutoReconciler:
    def __init__(self, service: ManagerService, interval: float = 15.0) -> None:
        self.service = service
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="vampip-auto-reconcile",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval + 1.0))

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                if not self.service.auto_reconcile_enabled():
                    continue
                status = self.service.status()
                if not status["managed_mode"]:
                    continue
                packages_need_enable = int(status.get("pending_enable", 0)) > 0
                packages_need_disable = int(status.get("pending_disable", 0)) > 0
                vam_running = bool(status["vam"]["running"])
                if packages_need_enable or (packages_need_disable and not vam_running):
                    self.service.reconcile(apply=True)
            except Exception as exc:
                print(f"[VAM-PIP manager] automatic reconciliation failed: {exc}")


def serve_manager(
    service: ManagerService,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
) -> None:
    if host.casefold() not in _LOOPBACK_NAMES:
        raise ValueError("the manager may only bind to 127.0.0.1 or localhost")
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    with connect(service.state_dir) as connection:
        token = get_or_create_api_token(connection)
    server = ManagerHTTPServer((host, port), service, token)
    actual_host, actual_port = server.server_address[:2]
    display_host = "127.0.0.1" if actual_host == "0.0.0.0" else actual_host
    url = f"http://{display_host}:{actual_port}/#token={token}"
    reconciler = AutoReconciler(service)
    reconciler.start()
    print(f"VAM-PIP manager: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        reconciler.stop()
