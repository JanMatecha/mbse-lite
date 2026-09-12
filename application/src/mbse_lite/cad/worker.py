from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_COMPONENT_ROLES,
    CAD_JOB_RESULT_FILENAME,
    CAD_JOB_SCHEMA_VERSION,
    CAD_REQUIRED_CHECKS,
    CadError,
    CadExportError,
    CadJob,
    parse_cad_job_request,
)


def _suppress_windows_fault_dialogs() -> None:
    """Keep a native worker fault non-interactive so the parent receives its status."""

    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        no_gp_fault_error_box = 0x0002
        no_wer_ui = 0x0020
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetErrorMode(kernel32.GetErrorMode() | no_gp_fault_error_box)
        try:
            ctypes.WinDLL("wer", use_last_error=True).WerSetFlags(no_wer_ui)
        except (AttributeError, OSError):
            pass
    except (AttributeError, OSError):
        pass


def _write_completion_record(path: Path, value: dict[str, object]) -> None:
    """Publish the completion record only after its complete contents are durable."""

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def _validated_completion(job: CadJob, result: Any) -> dict[str, object]:
    """Reject incomplete backend evidence before publishing worker success."""

    try:
        artifacts = tuple(Path(path) for path in result.artifacts)
        checks = result.checks
        manifest = result.manifest
        component_ids = tuple(result.component_ids)
        step_component_ids = tuple(result.step_component_ids)
        glb_node_names = tuple(result.glb_node_names)
        glb_component_ids = tuple(result.glb_component_ids)
        glb_mbse_ids = tuple(result.glb_mbse_ids)
    except (AttributeError, TypeError) as error:
        raise CadExportError("CAD backend returned malformed success evidence") from error

    if tuple(path.name for path in artifacts) != CAD_ARTIFACT_FILENAMES:
        raise CadExportError("CAD backend returned an unexpected artifact set")
    expected_parent = job.output_dir.resolve()
    if any(path.resolve().parent != expected_parent for path in artifacts):
        raise CadExportError("CAD backend returned an artifact outside the job output")
    if any(not path.is_file() or path.stat().st_size <= 0 for path in artifacts):
        raise CadExportError("CAD backend returned a missing or empty artifact")

    if not isinstance(checks, dict) or set(checks) != {
        *CAD_REQUIRED_CHECKS,
        "verified_footprint_extent_mm",
    }:
        raise CadExportError("CAD backend returned malformed semantic checks")
    if any(checks.get(name) is not True for name in CAD_REQUIRED_CHECKS):
        raise CadExportError("CAD backend did not pass every semantic check")
    if checks.get("verified_footprint_extent_mm") != dict(
        job.expected_footprint_extent_mm
    ):
        raise CadExportError("CAD backend verified the wrong footprint extent")

    if not isinstance(manifest, dict):
        raise CadExportError("CAD backend returned a malformed manifest")
    try:
        written_manifest = json.loads(artifacts[-1].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadExportError("CAD backend wrote an unreadable manifest") from error
    if written_manifest != manifest:
        raise CadExportError("CAD backend manifest evidence differs from its artifact")
    backend = manifest.get("backend")
    if (
        manifest.get("schema_version") != "0.6"
        or manifest.get("generated_metadata") is not True
        or manifest.get("source_of_truth") != "project Markdown"
        or not isinstance(backend, dict)
        or backend.get("name") != "cadquery"
        or backend.get("internal_length_unit") != "mm"
    ):
        raise CadExportError("CAD backend returned incomplete manifest evidence")

    expected_components = tuple(
        job.visualization_spec.roles[role].id for role in CAD_COMPONENT_ROLES
    )
    if (
        component_ids != expected_components
        or step_component_ids != expected_components
        or glb_component_ids != expected_components
        or not set(expected_components).issubset(glb_node_names)
        or len(glb_mbse_ids) != len(expected_components)
        or set(glb_mbse_ids) != set(expected_components)
    ):
        raise CadExportError("CAD backend returned invalid stable-identity evidence")

    return {
        "schema_version": CAD_JOB_SCHEMA_VERSION,
        "job_id": job.job_id,
        "status": "completed",
        "backend": backend,
        "artifacts": [
            {"file": path.name, "size_bytes": path.stat().st_size}
            for path in artifacts
        ],
        "checks": checks,
        "component_ids": list(component_ids),
        "step_component_ids": list(step_component_ids),
        "glb_node_names": list(glb_node_names),
        "glb_component_ids": list(glb_component_ids),
        "glb_mbse_ids": list(glb_mbse_ids),
    }


def _run(request_path: Path) -> None:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadExportError(f"Cannot read CAD job request: {error}") from error

    job = parse_cad_job_request(request)

    # This is the only application import path allowed to reach CadQuery/OCP.
    from .cadquery_backend import execute_cad_job

    result = execute_cad_job(job)
    completion = _validated_completion(job, result)
    _write_completion_record(
        job.output_dir / CAD_JOB_RESULT_FILENAME,
        completion,
    )


def main(argv: Sequence[str] | None = None) -> int:
    _suppress_windows_fault_dialogs()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("ERROR: CAD worker expects exactly one job request path", file=sys.stderr)
        return 2
    try:
        _run(Path(arguments[0]))
        # The completion record is closed, fsynced and atomically published at
        # this point. Flush process streams explicitly because os._exit skips
        # Python's normal buffered-I/O and atexit handling.
        sys.stdout.flush()
        sys.stderr.flush()
    except CadError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"ERROR: CadQuery worker failed: {error}", file=sys.stderr)
        return 1
    # CadQuery/OCP teardown is unstable on Windows. This deliberate exit is
    # safe only after the complete success protocol above and is confined to
    # this disposable native worker process.
    os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
