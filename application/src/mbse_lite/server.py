from __future__ import annotations

import base64
import ipaddress
import json
import logging
import mimetypes
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .core import load_model
from .editing import (
    EditConflictError,
    EditingError,
    EditValidationError,
    UpdateObjectAttribute,
    editable_attribute_names,
    update_object_attribute,
)
from .view_architecture import (
    build_default_view_assets,
    build_viewer_manifest,
    build_viewer_model,
    default_view_definitions,
)
from .viewer import _sanitize_svg, export_viewer
from .visualization import build_generated_views


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_REQUEST_BODY = 64 * 1024
_UPDATE_FIELDS = {"object_id", "attribute", "value", "expected_old_value"}


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: dict[str, object]


class ServeApplication:
    """Transport-independent local editing application boundary."""

    def __init__(self, project_dir: str | Path):
        project_path = Path(project_dir).resolve()
        if not project_path.is_dir():
            raise EditingError(f"Project directory does not exist: {project_path}")
        self.project_path = project_path
        self._write_lock = threading.RLock()

    def project_snapshot(self) -> dict[str, object]:
        model = load_model(self.project_path)
        definitions = list(default_view_definitions())
        assets: dict[str, str | bytes] = dict(build_default_view_assets(model))
        generated = build_generated_views(model)
        definitions.extend(generated.views)
        assets.update(generated.assets)

        asset_errors: dict[str, str] = {}
        svg_sources = {
            view.source
            for view in definitions
            if view.type == "svg" and view.source is not None
        }
        for source in svg_sources.intersection(assets):
            content = assets[source]
            if not isinstance(content, str):
                asset_errors[source] = f"SVG view asset must be UTF-8 text: {source}"
                del assets[source]
                continue
            try:
                assets[source] = _sanitize_svg(content)
            except ValueError as error:
                asset_errors[source] = f"SVG asset is invalid or unsafe: {error}"
                del assets[source]

        gltf_sources = {
            view.source
            for view in definitions
            if view.type == "gltf" and view.source is not None
        }
        return {
            "manifest": build_viewer_manifest(self.project_path.name, definitions),
            "model": build_viewer_model(model),
            "assets": {
                source: content
                for source, content in assets.items()
                if isinstance(content, str)
            },
            "binaryAssets": {
                source: base64.b64encode(content).decode("ascii")
                for source, content in assets.items()
                if isinstance(content, bytes) and source in gltf_sources
            },
            "assetErrors": asset_errors,
            "capabilities": {"read": True, "write": True},
        }

    def update_object_attribute(self, payload: object) -> ApiResponse:
        if not isinstance(payload, dict):
            return _error(400, "invalid_request", "The JSON body must be an object.")
        provided = set(payload)
        if provided != _UPDATE_FIELDS:
            missing = sorted(_UPDATE_FIELDS - provided)
            extra = sorted(provided - _UPDATE_FIELDS)
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unsupported: " + ", ".join(extra))
            return _error(
                400,
                "invalid_request",
                "Invalid request fields (" + "; ".join(details) + ").",
            )
        if any(not isinstance(payload[field], str) for field in _UPDATE_FIELDS):
            return _error(400, "invalid_request", "All request fields must be strings.")

        object_id = payload["object_id"]
        attribute = payload["attribute"]
        value = payload["value"]
        expected = payload["expected_old_value"]
        if not object_id or not attribute:
            return _error(400, "invalid_request", "object_id and attribute must not be empty.")

        with self._write_lock:
            model = load_model(self.project_path)
            obj = model.objects.get(object_id)
            if obj is None:
                return _error(404, "unknown_object", f"Unknown object ID: {object_id}")
            if attribute.strip().casefold() == "id":
                return _error(422, "immutable_attribute", "Stable IDs cannot be edited.")
            if attribute not in editable_attribute_names(obj):
                return _error(
                    422,
                    "non_writable_attribute",
                    f"{object_id}.{attribute} is not a writable scalar attribute.",
                )
            actual = obj.attributes[attribute]
            if actual != expected:
                return ApiResponse(
                    409,
                    {
                        "error": "conflict",
                        "message": "The value changed since this page was loaded.",
                        "object_id": object_id,
                        "attribute": attribute,
                        "expected": expected,
                        "actual": actual,
                    },
                )

            try:
                update_object_attribute(
                    self.project_path,
                    UpdateObjectAttribute(
                        object_id=object_id,
                        attribute=attribute,
                        new_value=value,
                        expected_old_value=expected,
                    ),
                )
            except EditConflictError:
                current = load_model(self.project_path).objects.get(object_id)
                current_value = current.attributes.get(attribute) if current else None
                return ApiResponse(
                    409,
                    {
                        "error": "conflict",
                        "message": "The value changed since this page was loaded.",
                        "object_id": object_id,
                        "attribute": attribute,
                        "expected": expected,
                        "actual": current_value,
                    },
                )
            except EditValidationError as error:
                return _error(422, "validation_error", str(error))
            except EditingError as error:
                return _error(422, "editing_rejected", str(error))
            return ApiResponse(200, self.project_snapshot())


def _error(status: int, code: str, message: str) -> ApiResponse:
    return ApiResponse(status, {"error": code, "message": message})


def is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _handler_class(
    application: ServeApplication,
    index_html: bytes,
    static_assets: Mapping[str, tuple[str, bytes]],
):
    class LocalRequestHandler(BaseHTTPRequestHandler):
        server_version = "MBSELiteLocal/0.9"

        def _json(self, response: ApiResponse) -> None:
            content = json.dumps(response.body, ensure_ascii=False).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def _host_is_local(self) -> bool:
            host = self.headers.get("Host", "")
            parsed = urlsplit("//" + host)
            return bool(parsed.hostname and is_loopback_host(parsed.hostname))

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlsplit(self.path).path
            if not self._host_is_local():
                self._json(_error(403, "forbidden_host", "Only loopback Host headers are accepted."))
                return
            if path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(index_html)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(index_html)
                return
            if path == "/api/project":
                try:
                    self._json(ApiResponse(200, application.project_snapshot()))
                except Exception:
                    logging.exception("Failed to build the project snapshot")
                    self._json(
                        _error(
                            500,
                            "internal_error",
                            "The project snapshot could not be built.",
                        )
                    )
                return
            if path == "/api/object-attribute":
                self._method_not_allowed()
                return
            asset = static_assets.get(path)
            if asset is not None:
                content_type, content = asset
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
                return
            self._json(_error(404, "not_found", "Resource not found."))

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._host_is_local():
                self._json(
                    _error(
                        403,
                        "forbidden_host",
                        "Only loopback Host headers are accepted.",
                    )
                )
                return
            path = urlsplit(self.path).path
            if path in {"/", "/api/project"}:
                self._method_not_allowed()
                return
            if path != "/api/object-attribute":
                self._json(_error(404, "not_found", "Resource not found."))
                return
            origin = self.headers.get("Origin")
            if origin:
                try:
                    origin_url = urlsplit(origin)
                    same_origin = (
                        origin_url.scheme == "http"
                        and bool(origin_url.hostname)
                        and is_loopback_host(origin_url.hostname or "")
                        and origin_url.port == self.server.server_address[1]
                        and origin_url.username is None
                        and origin_url.password is None
                        and origin_url.path in {"", "/"}
                        and not origin_url.query
                        and not origin_url.fragment
                    )
                except ValueError:
                    same_origin = False
                if not same_origin:
                    self._json(_error(403, "cross_origin", "Cross-origin writes are not allowed."))
                    return
            content_type = (
                self.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .casefold()
            )
            if content_type != "application/json":
                self._json(
                    _error(
                        400,
                        "invalid_content_type",
                        "Content-Type must be application/json.",
                    )
                )
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._json(_error(400, "invalid_request", "A valid Content-Length is required."))
                return
            if length < 0:
                self._json(_error(400, "invalid_request", "Content-Length must not be negative."))
                return
            if length > MAX_REQUEST_BODY:
                self._json(_error(413, "request_too_large", "The JSON request body is too large."))
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(_error(400, "invalid_json", "The request body is not valid UTF-8 JSON."))
                return
            try:
                self._json(application.update_object_attribute(payload))
            except Exception:
                logging.exception("Unexpected local update failure")
                self._json(_error(500, "internal_error", "The update could not be completed."))

        def _method_not_allowed(self) -> None:
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET, POST")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed

        def log_message(self, format: str, *args: object) -> None:
            logging.info("%s - %s", self.address_string(), format % args)

    return LocalRequestHandler


def make_http_server(
    application: ServeApplication,
    host: str,
    port: int,
    index_html: bytes,
    static_assets: Mapping[str, tuple[str, bytes]],
) -> ThreadingHTTPServer:
    if not is_loopback_host(host):
        raise ValueError("The V0.9 server may bind only to a loopback address.")
    return ThreadingHTTPServer(
        (host, port), _handler_class(application, index_html, static_assets)
    )


def _prepared_bundle(
    project_path: Path, bundle_dir: Path
) -> tuple[bytes, dict[str, tuple[str, bytes]]]:
    index_path = bundle_dir / "index.html"
    export_viewer(
        load_model(project_path),
        index_path,
        project_name=project_path.name,
        data_provider="http",
    )
    static_assets: dict[str, tuple[str, bytes]] = {}
    vendor_dir = bundle_dir / "assets" / "vendor"
    for path in vendor_dir.iterdir():
        if path.is_file():
            content_type = (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            static_assets["/assets/vendor/" + path.name] = (content_type, path.read_bytes())
    return index_path.read_bytes(), static_assets


def serve_project(
    project_dir: str | Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> None:
    application = ServeApplication(project_dir)
    with tempfile.TemporaryDirectory(prefix="mbse-lite-serve-") as temporary:
        index_html, static_assets = _prepared_bundle(
            application.project_path, Path(temporary)
        )
        server = make_http_server(application, host, port, index_html, static_assets)
        actual_host, actual_port = server.server_address[:2]
        display_host = "127.0.0.1" if actual_host == "0.0.0.0" else actual_host
        url = f"http://{display_host}:{actual_port}/"
        print(f"MBSE Lite editable application: {url}")
        print(f"Project: {application.project_path}")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopping MBSE Lite server.")
        finally:
            server.server_close()


__all__ = [
    "ApiResponse",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "MAX_REQUEST_BODY",
    "ServeApplication",
    "is_loopback_host",
    "make_http_server",
    "serve_project",
]
