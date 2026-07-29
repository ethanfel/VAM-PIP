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
from urllib.parse import parse_qs, quote, unquote, urlsplit
import webbrowser

from vampip.database import connect
from vampip.manager_state import get_or_create_api_token
from vampip.service import LiveActionBusyError, ManagerService


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

    @staticmethod
    def _boolean(
        document: dict[str, Any],
        key: str,
        default: bool,
    ) -> bool:
        value = document.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        return value

    @staticmethod
    def _package_version(document: dict[str, Any]) -> int | None:
        value = document.get("package_version")
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            or value > 2_147_483_647
        ):
            raise ValueError("package_version must be an integer from 0 to 2147483647")
        return value

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
            cache="no-cache",
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
            if parsed.path == "/api/activity":
                self._json(HTTPStatus.OK, self.server.service.activity())
                return
            if parsed.path == "/api/status":
                self._json(HTTPStatus.OK, self.server.service.status())
                return
            if parsed.path == "/api/session-plugins":
                self._json(
                    HTTPStatus.OK,
                    self.server.service.session_plugins(),
                )
                return
            if parsed.path == "/api/vam/scene":
                self._json(HTTPStatus.OK, self.server.service.scene())
                return
            if parsed.path == "/api/vam/persons":
                self._json(HTTPStatus.OK, self.server.service.persons())
                return
            if parsed.path == "/api/vam/person/equipment":
                unexpected_fields = sorted(set(query) - {"target_uid", "token"})
                if unexpected_fields:
                    raise ValueError(
                        "unsupported Person equipment query field(s): "
                        + ", ".join(unexpected_fields)
                    )
                target_values = query.get("target_uid", [])
                if len(target_values) != 1 or not target_values[0]:
                    raise ValueError("target_uid must be supplied exactly once")
                result = self.server.service.person_equipment(target_values[0])
                thumbnail_token = quote(self.server.api_token, safe="")
                for item in result.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    resource_id = item.get("id")
                    if (
                        isinstance(resource_id, int)
                        and not isinstance(resource_id, bool)
                        and resource_id > 0
                    ):
                        item["thumbnail_url"] = (
                            f"/api/resources/{resource_id}/thumbnail"
                            f"?token={thumbnail_token}"
                        )
                self._json(HTTPStatus.OK, result)
                return
            if parsed.path == "/api/vam/person/hair":
                unexpected_fields = sorted(set(query) - {"target_uid", "token"})
                if unexpected_fields:
                    raise ValueError(
                        "unsupported Person hair query field(s): "
                        + ", ".join(unexpected_fields)
                    )
                target_values = query.get("target_uid", [])
                if len(target_values) != 1 or not target_values[0]:
                    raise ValueError("target_uid must be supplied exactly once")
                self._json(
                    HTTPStatus.OK,
                    self.server.service.person_hair(target_values[0]),
                )
                return
            if parsed.path in {
                "/api/workspace/categories",
                "/api/person/categories",
            }:
                self._json(
                    HTTPStatus.OK,
                    self.server.service.workspace_categories(),
                )
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
                    resource_types=query.get("type", []),
                    category=query.get("category", [""])[0],
                    state=query.get("state", ["all"])[0],
                    favorite=_bool_query(query, "favorite"),
                    target_uid=(query.get("target_uid", [""])[0] or None),
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
        except LiveActionBusyError as exc:
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
                catalog = self._boolean(document, "catalog", True)
                result: dict[str, object] = {"packages": service.scan_packages()}
                if catalog:
                    result["catalog"] = service.import_catalog()
                self._json(HTTPStatus.OK, result)
                return
            if method == "POST" and parsed.path == "/api/catalog/import":
                self._json(HTTPStatus.OK, service.import_catalog())
                return
            if method == "POST" and parsed.path == "/api/session-plugins/import":
                include_disabled = document.get("include_disabled", False)
                apply = document.get("apply", False)
                if not isinstance(include_disabled, bool):
                    raise ValueError("include_disabled must be a boolean")
                if not isinstance(apply, bool):
                    raise ValueError("apply must be a boolean")
                self._json(
                    HTTPStatus.OK,
                    service.import_session_plugins(
                        include_disabled=include_disabled,
                        apply=apply,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/pins":
                apply = self._boolean(document, "apply", False)
                self._json(
                    HTTPStatus.OK,
                    service.pin(
                        self._roots(document),
                        label=(
                            str(document["label"])
                            if document.get("label") is not None
                            else None
                        ),
                        apply=apply,
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
                apply = self._boolean(document, "apply", True)
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
                        apply=apply,
                    ),
                )
                return
            resource_lease = _RESOURCE_LEASE.fullmatch(parsed.path)
            if method == "POST" and resource_lease:
                apply = self._boolean(document, "apply", True)
                package_version = self._package_version(document)
                lease_kwargs: dict[str, object] = {
                    "days": float(document.get("days", 3)),
                    "label": (
                        str(document["label"])
                        if document.get("label") is not None
                        else None
                    ),
                    "apply": apply,
                }
                if package_version is not None:
                    lease_kwargs["package_version"] = package_version
                self._json(
                    HTTPStatus.OK,
                    service.lease_resource(
                        int(resource_lease.group(1)),
                        **lease_kwargs,
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
                apply = self._boolean(document, "apply", False)
                activate = self._boolean(document, "activate", False)
                self._json(
                    HTTPStatus.OK,
                    service.reconcile(
                        apply=apply,
                        activate=activate,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/deactivate":
                apply = self._boolean(document, "apply", False)
                self._json(
                    HTTPStatus.OK,
                    service.deactivate(apply=apply),
                )
                return
            if method == "POST" and parsed.path == "/api/settings":
                if "auto_reconcile" in document:
                    service.set_auto_reconcile(
                        self._boolean(document, "auto_reconcile", False)
                    )
                self._json(
                    HTTPStatus.OK,
                    {"auto_reconcile": service.auto_reconcile_enabled()},
                )
                return
            if method == "POST" and parsed.path == "/api/vam/launch":
                reconcile = self._boolean(document, "reconcile", True)
                self._json(
                    HTTPStatus.OK,
                    service.launch_vam(reconcile=reconcile),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/resource/apply":
                resource_id = document.get("resource_id")
                target_uid = document.get("target_uid")
                package_version = self._package_version(document)
                if (
                    isinstance(resource_id, bool)
                    or not isinstance(resource_id, int)
                    or resource_id < 1
                ):
                    raise ValueError("resource_id must be a positive integer")
                if target_uid is not None and not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string or null")
                days = document.get("days", 3)
                if isinstance(days, bool) or not isinstance(days, (int, float)):
                    raise ValueError("days must be a number")
                merge = document.get("merge", False)
                if not isinstance(merge, bool):
                    raise ValueError("merge must be a boolean")
                create_if_missing = document.get("create_if_missing", False)
                if not isinstance(create_if_missing, bool):
                    raise ValueError("create_if_missing must be a boolean")
                confirm_replace = document.get("confirm_replace", False)
                if not isinstance(confirm_replace, bool):
                    raise ValueError("confirm_replace must be a boolean")
                confirm_critical = document.get("confirm_critical", False)
                if not isinstance(confirm_critical, bool):
                    raise ValueError("confirm_critical must be a boolean")
                apply_kwargs: dict[str, object] = {
                    "target_uid": target_uid,
                    "days": float(days),
                    "merge": merge,
                    "create_if_missing": create_if_missing,
                    "confirm_replace": confirm_replace,
                    "confirm_critical": confirm_critical,
                }
                if package_version is not None:
                    apply_kwargs["package_version"] = package_version
                self._json(
                    HTTPStatus.OK,
                    service.apply_resource(
                        resource_id,
                        **apply_kwargs,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/custom-unity-asset/choice":
                allowed_fields = {
                    "target_uid",
                    "choice_index",
                    "choice_token",
                }
                unexpected_fields = sorted(set(document) - allowed_fields)
                if unexpected_fields:
                    raise ValueError(
                        "unsupported Custom Unity Asset choice field(s): "
                        + ", ".join(unexpected_fields)
                    )
                target_uid = document.get("target_uid")
                choice_index = document.get("choice_index")
                choice_token = document.get("choice_token")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                if (
                    isinstance(choice_index, bool)
                    or not isinstance(choice_index, int)
                    or choice_index < 1
                ):
                    raise ValueError("choice_index must be a positive integer")
                if not isinstance(choice_token, str):
                    raise ValueError("choice_token must be a string")
                self._json(
                    HTTPStatus.OK,
                    service.select_custom_unity_asset_choice(
                        target_uid,
                        choice_index,
                        choice_token,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/person/clothing":
                allowed_fields = {
                    "resource_id",
                    "target_uid",
                    "active",
                    "revision",
                    "days",
                    "package_version",
                }
                unexpected_fields = sorted(set(document) - allowed_fields)
                if unexpected_fields:
                    raise ValueError(
                        "unsupported Person clothing field(s): "
                        + ", ".join(unexpected_fields)
                    )
                resource_id = document.get("resource_id")
                target_uid = document.get("target_uid")
                active = document.get("active")
                revision = document.get("revision")
                days = document.get("days", 3)
                package_version = self._package_version(document)
                if (
                    isinstance(resource_id, bool)
                    or not isinstance(resource_id, int)
                    or resource_id < 1
                ):
                    raise ValueError("resource_id must be a positive integer")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                if not isinstance(active, bool):
                    raise ValueError("active must be a boolean")
                if not isinstance(revision, str):
                    raise ValueError("revision must be a string")
                if isinstance(days, bool) or not isinstance(days, (int, float)):
                    raise ValueError("days must be a number")
                clothing_kwargs: dict[str, object] = {
                    "target_uid": target_uid,
                    "active": active,
                    "revision": revision,
                    "days": float(days),
                }
                if package_version is not None:
                    clothing_kwargs["package_version"] = package_version
                self._json(
                    HTTPStatus.OK,
                    service.set_person_clothing(
                        resource_id,
                        **clothing_kwargs,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/person/apply":
                resource_id = document.get("resource_id")
                target_uid = document.get("target_uid")
                package_version = self._package_version(document)
                if (
                    isinstance(resource_id, bool)
                    or not isinstance(resource_id, int)
                    or resource_id < 1
                ):
                    raise ValueError("resource_id must be a positive integer")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                days = document.get("days", 3)
                if isinstance(days, bool) or not isinstance(days, (int, float)):
                    raise ValueError("days must be a number")
                merge = document.get("merge", False)
                if not isinstance(merge, bool):
                    raise ValueError("merge must be a boolean")
                confirm_critical = document.get("confirm_critical", False)
                if not isinstance(confirm_critical, bool):
                    raise ValueError("confirm_critical must be a boolean")
                person_kwargs: dict[str, object] = {
                    "target_uid": target_uid,
                    "days": float(days),
                    "merge": merge,
                    "confirm_critical": confirm_critical,
                }
                if package_version is not None:
                    person_kwargs["package_version"] = package_version
                self._json(
                    HTTPStatus.OK,
                    service.apply_person_resource(
                        resource_id,
                        **person_kwargs,
                    ),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/person/add":
                target_uid = document.get("target_uid")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                self._json(HTTPStatus.OK, service.add_person(target_uid))
                return
            if method == "POST" and parsed.path == "/api/vam/person/select":
                target_uid = document.get("target_uid")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                self._json(HTTPStatus.OK, service.select_person(target_uid))
                return
            if method == "POST" and parsed.path == "/api/vam/atom/add":
                category_id = document.get("category_id")
                target_uid = document.get("target_uid")
                if not isinstance(category_id, str):
                    raise ValueError("category_id must be a string")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                self._json(
                    HTTPStatus.OK,
                    service.add_atom(category_id, target_uid),
                )
                return
            if method == "POST" and parsed.path == "/api/vam/atom/select":
                target_uid = document.get("target_uid")
                if not isinstance(target_uid, str):
                    raise ValueError("target_uid must be a string")
                self._json(HTTPStatus.OK, service.select_atom(target_uid))
                return
            self._error(HTTPStatus.NOT_FOUND, "API route not found")
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except FileNotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except FileExistsError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except LiveActionBusyError as exc:
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
                activity = self.service.activity()
                operation = activity.get("operation", {})
                if isinstance(operation, dict) and bool(operation.get("busy")):
                    continue
                status = self.service.status()
                if self.service.rescan_discovered_packages_if_idle() is not None:
                    continue
                if not self.service.auto_reconcile_enabled():
                    continue
                packages_need_enable = int(status.get("pending_enable", 0)) > 0
                packages_need_disable = int(status.get("pending_disable", 0)) > 0
                vam_running = bool(status["vam"]["running"])
                if not status["managed_mode"]:
                    continue
                if packages_need_enable or (packages_need_disable and not vam_running):
                    self.service.reconcile_if_idle(apply=True)
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
