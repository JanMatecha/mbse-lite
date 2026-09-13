from __future__ import annotations

import http.client
import json
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from mbse_lite.cli import build_parser
from mbse_lite.core import load_model
from mbse_lite.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_REQUEST_BODY,
    ServeApplication,
    is_loopback_host,
    make_http_server,
)
from mbse_lite.viewer import export_viewer


def write_project(project: Path) -> Path:
    source = project / "mbse" / "requirements.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Requirements\n\n"
        "Unrelated prose.\n\n"
        "| ID | Name | Requirement | Target Length [m] | Target Depth [m] | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| REQ-008 | Footprint | Fit the site. | 4.0 | 1.2 | Draft |\n"
        "| REQ-009 | Roof | Resist weather. | 2.1 | 1.0 | Draft |\n",
        encoding="utf-8",
    )
    parts = project / "mbse" / "parts.md"
    parts.write_text(
        "| ID | Name | Description |\n"
        "|---|---|---|\n"
        "| PART-001 | Frame | Structural frame |\n",
        encoding="utf-8",
    )
    return source


def add_geometry_profile(project: Path) -> None:
    roles = [
        ("enclosure", "PART-001"),
        ("main_storage", "PART-004"),
        ("mower_compartment", "PART-005"),
        ("main_door", "PART-008"),
        ("mower_door", "PART-010"),
        ("mower_ramp", "PART-011"),
        ("shelving", "PART-012"),
    ]
    (project / "mbse" / "parts.md").write_text(
        "| ID | Name | Description |\n|---|---|---|\n"
        + "".join(f"| {object_id} | {role} | Test part |\n" for role, object_id in roles),
        encoding="utf-8",
    )
    concepts = [
        ("mower_door_candidate", "CON-007"),
        ("main_door_candidate", "CON-010"),
    ]
    (project / "mbse" / "concepts.md").write_text(
        "| ID | Name | Status |\n|---|---|---|\n"
        + "".join(
            f"| {object_id} | {role} | Preferred candidate |\n"
            for role, object_id in concepts
        ),
        encoding="utf-8",
    )
    (project / "visualization.md").write_text(
        "| Visualization Profile | Role | Object ID | Expected Type |\n"
        "|---|---|---|---|\n"
        + "".join(
            f"| garden_shed | {role} | {object_id} | Part |\n"
            for role, object_id in roles
        )
        + "| garden_shed | footprint | REQ-008 | Requirement |\n"
        + "".join(
            f"| garden_shed | {role} | {object_id} | Concept |\n"
            for role, object_id in concepts
        ),
        encoding="utf-8",
    )


def command(**changes: str) -> dict[str, str]:
    payload = {
        "object_id": "REQ-008",
        "attribute": "Status",
        "value": "Confirmed",
        "expected_old_value": "Draft",
    }
    payload.update(changes)
    return payload


@contextmanager
def running_server(application: ServeApplication):
    server = make_http_server(
        application,
        "127.0.0.1",
        0,
        b"<!doctype html><title>test</title>",
        {},
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(port: int, method: str, path: str, body: bytes | None = None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), raw


def test_project_snapshot_is_current_editable_and_provenance_drives_editability(tmp_path):
    write_project(tmp_path)
    snapshot = ServeApplication(tmp_path).project_snapshot()

    assert snapshot["capabilities"] == {"read": True, "write": True}
    requirement = next(
        item for item in snapshot["model"]["objects"] if item["id"] == "REQ-008"
    )
    assert "Status" in requirement["editable_attributes"]
    assert "ID" not in requirement["editable_attributes"]
    assert not Path(tmp_path, "model.json").exists()


def test_successful_update_changes_only_markdown_cell_and_returns_fresh_snapshot(tmp_path):
    source = write_project(tmp_path)
    before = source.read_text(encoding="utf-8").splitlines()
    generated_snapshot = tmp_path / "model.json"
    generated_snapshot.write_bytes(b'{"generated":"do not edit"}\n')

    response = ServeApplication(tmp_path).update_object_attribute(command())

    after = source.read_text(encoding="utf-8").splitlines()
    assert response.status == 200
    assert [
        index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]
    ] == [6]
    requirement = next(
        item
        for item in response.body["model"]["objects"]
        if item["id"] == "REQ-008"
    )
    assert requirement["attributes"]["Status"] == "Confirmed"
    assert load_model(tmp_path).objects["REQ-008"].attributes["Status"] == "Confirmed"
    assert generated_snapshot.read_bytes() == b'{"generated":"do not edit"}\n'


def test_stale_update_is_a_machine_readable_conflict_and_does_not_write(tmp_path):
    source = write_project(tmp_path)
    app = ServeApplication(tmp_path)
    assert app.update_object_attribute(command()).status == 200
    confirmed = source.read_bytes()

    response = app.update_object_attribute(command(value="Rejected"))

    assert response.status == 409
    assert response.body == {
        "error": "conflict",
        "message": "The value changed since this page was loaded.",
        "object_id": "REQ-008",
        "attribute": "Status",
        "expected": "Draft",
        "actual": "Confirmed",
    }
    assert source.read_bytes() == confirmed


@pytest.mark.parametrize(
    ("payload", "status", "error"),
    [
        (command(attribute="ID"), 422, "immutable_attribute"),
        (command(object_id="REQ-999"), 404, "unknown_object"),
        (command(attribute="Type"), 422, "non_writable_attribute"),
        (command(object_id="../../outside"), 404, "unknown_object"),
        ({"object_id": "REQ-008"}, 400, "invalid_request"),
        (command(extra="not allowed"), 400, "invalid_request"),
    ],
)
def test_invalid_or_unsupported_update_targets_are_rejected_without_writing(
    tmp_path, payload, status, error
):
    source = write_project(tmp_path)
    before = source.read_bytes()

    response = ServeApplication(tmp_path).update_object_attribute(payload)

    assert response.status == status
    assert response.body["error"] == error
    assert source.read_bytes() == before


def test_validation_rejection_leaves_original_markdown_valid(tmp_path):
    source = write_project(tmp_path)
    add_geometry_profile(tmp_path)
    before = source.read_bytes()

    response = ServeApplication(tmp_path).update_object_attribute(
        command(attribute="Target Length [m]", value="not-a-number", expected_old_value="4.0")
    )

    assert response.status == 422
    assert response.body["error"] == "validation_error"
    assert source.read_bytes() == before
    assert load_model(tmp_path).objects["REQ-008"].attributes["Target Length [m]"] == "4.0"


def test_http_get_post_and_request_guards(tmp_path):
    source = write_project(tmp_path)
    with running_server(ServeApplication(tmp_path)) as port:
        status, headers, raw = request(port, "GET", "/api/project")
        snapshot = json.loads(raw)
        assert status == 200
        assert headers["Content-Type"].startswith("application/json")
        assert snapshot["capabilities"] == {"read": True, "write": True}

        status, _, raw = request(
            port,
            "POST",
            "/api/object-attribute",
            json.dumps(command()).encode(),
            {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
        )
        assert status == 200
        requirement = next(
            item
            for item in json.loads(raw)["model"]["objects"]
            if item["id"] == "REQ-008"
        )
        assert requirement["attributes"]["Status"] == "Confirmed"

        malformed_before = source.read_bytes()
        status, _, raw = request(
            port,
            "POST",
            "/api/object-attribute",
            b"{not json",
            {"Content-Type": "application/json"},
        )
        assert status == 400
        assert json.loads(raw)["error"] == "invalid_json"
        assert source.read_bytes() == malformed_before

        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.sendall(
                b"POST /api/object-attribute HTTP/1.1\r\n"
                + f"Host: 127.0.0.1:{port}\r\n".encode()
                + b"Content-Type: application/json\r\n"
                + (
                    f"Content-Length: {MAX_REQUEST_BODY + 1}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
            )
            chunks = []
            while chunk := client.recv(4096):
                chunks.append(chunk)
            raw_response = b"".join(chunks)
        status = int(raw_response.split(b"\r\n", 1)[0].split()[1])
        raw = raw_response.split(b"\r\n\r\n", 1)[1]
        assert status == 413
        assert json.loads(raw)["error"] == "request_too_large"

        status, _, _ = request(port, "PUT", "/api/object-attribute", b"")
        assert status == 405

        status, _, raw = request(
            port,
            "POST",
            "/api/object-attribute",
            json.dumps(command()).encode(),
            {"Content-Type": "application/json", "Origin": "https://example.com"},
        )
        assert status == 403
        assert json.loads(raw)["error"] == "cross_origin"

        status, _, raw = request(
            port,
            "POST",
            "/api/object-attribute",
            json.dumps(command()).encode(),
            {"Content-Type": "application/json", "Origin": "http://localhost:not-a-port"},
        )
        assert status == 403
        assert json.loads(raw)["error"] == "cross_origin"


def test_http_provider_uses_api_command_and_preserves_selection_after_refresh(tmp_path):
    write_project(tmp_path)
    output = tmp_path / "bundle" / "index.html"
    export_viewer(load_model(tmp_path), output, project_name="Test", data_provider="http")
    html = output.read_text(encoding="utf-8")

    assert "class HttpDataProvider" in html
    assert "this.capabilities = Object.freeze({ read: true, write: true });" in html
    assert "fetch(path" in html
    assert "this.request('/api/project'" in html
    assert "this.request('/api/object-attribute'" in html
    assert "object_id: object.id" in html
    assert "expected_old_value: expectedOldValue" in html
    assert "error.code === 'conflict'" in html
    assert "applyProjectSnapshot(snapshot, object.id)" in html
    assert "The value changed since this page was loaded. Reloaded current value." in html
    assert "objectEditFeedback = { message: 'Saved'" in html
    assert "class EmbeddedDataProvider" not in html


def test_server_defaults_to_loopback_and_cli_exposes_requested_controls():
    args = build_parser().parse_args(["serve", "project", "--no-open"])

    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8000
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.no_open is True
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.5")
    with pytest.raises(ValueError, match="loopback"):
        make_http_server(ServeApplication(Path.cwd()), "0.0.0.0", 0, b"", {})


def test_server_and_normal_cli_imports_do_not_load_cadquery_ocp_or_server_early():
    source_path = str(Path(__file__).resolve().parents[1] / "src")
    server_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {source_path!r}); import mbse_lite.server; "
            "assert 'cadquery' not in sys.modules; assert 'OCP' not in sys.modules",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    cli_probe = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {source_path!r}); import mbse_lite.cli; "
            "assert 'mbse_lite.server' not in sys.modules; "
            "assert 'cadquery' not in sys.modules; assert 'OCP' not in sys.modules",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert server_probe.returncode == cli_probe.returncode == 0
