from __future__ import annotations

import json
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .protocol import CadExportError


_GLB_MAGIC = b"glTF"
_GLB_VERSION = 2
_JSON_CHUNK = b"JSON"


@dataclass(frozen=True, slots=True)
class GlbIdentityEvidence:
    """Identity metadata observed by re-reading a GLB from disk."""

    node_names: tuple[str, ...]
    mbse_ids: tuple[str, ...]
    identity_pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Glb:
    document: dict[str, object]
    chunks: tuple[tuple[bytes, bytes], ...]


def _parse_glb(data: bytes, label: str) -> _Glb:
    if len(data) < 20:
        raise CadExportError(f"GLB is truncated: {label}")
    magic, version, total_length = struct.unpack_from("<4sII", data)
    if magic != _GLB_MAGIC:
        raise CadExportError(f"GLB has invalid magic: {label}")
    if version != _GLB_VERSION:
        raise CadExportError(f"GLB version {version} is unsupported: {label}")
    if total_length != len(data):
        raise CadExportError(f"GLB total length is invalid: {label}")
    if total_length % 4:
        raise CadExportError(f"GLB total length is not 4-byte aligned: {label}")

    chunks: list[tuple[bytes, bytes]] = []
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise CadExportError(f"GLB has a truncated chunk header: {label}")
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, offset)
        if chunk_length % 4:
            raise CadExportError(f"GLB chunk is not 4-byte aligned: {label}")
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_length
        if chunk_end > len(data):
            raise CadExportError(f"GLB has a truncated chunk: {label}")
        chunks.append((chunk_type, data[chunk_start:chunk_end]))
        offset = chunk_end

    if not chunks or chunks[0][0] != _JSON_CHUNK:
        raise CadExportError(f"GLB does not begin with a JSON chunk: {label}")
    if sum(chunk_type == _JSON_CHUNK for chunk_type, _ in chunks) != 1:
        raise CadExportError(f"GLB must contain exactly one JSON chunk: {label}")
    json_bytes = chunks[0][1].rstrip(b" \x00")
    try:
        document = json.loads(json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CadExportError(f"GLB JSON chunk is invalid: {label}") from error
    if not isinstance(document, dict):
        raise CadExportError(f"GLB JSON document must be an object: {label}")
    return _Glb(document=document, chunks=tuple(chunks))


def _read_glb(path: Path) -> _Glb:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CadExportError(f"Cannot read GLB {path}: {error}") from error
    return _parse_glb(data, str(path))


def _nodes(document: dict[str, object], label: str) -> list[object]:
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        raise CadExportError(f"GLB nodes are missing or malformed: {label}")
    return nodes


def inspect_glb_identity(path: Path) -> GlbIdentityEvidence:
    """Read node names and viewer identities from a GLB without CadQuery/OCP."""

    glb = _read_glb(Path(path))
    node_names: list[str] = []
    mbse_ids: list[str] = []
    identity_pairs: list[tuple[str, str]] = []
    for node in _nodes(glb.document, str(path)):
        if not isinstance(node, dict):
            raise CadExportError(f"GLB contains a malformed node: {path}")
        name = node.get("name")
        if isinstance(name, str):
            node_names.append(name)
        extras = node.get("extras")
        if extras is not None and not isinstance(extras, dict):
            raise CadExportError(f"GLB node extras are malformed: {path}")
        if isinstance(extras, dict) and "mbse_id" in extras:
            mbse_id = extras["mbse_id"]
            if not isinstance(mbse_id, str) or not mbse_id:
                raise CadExportError(f"GLB node mbse_id is malformed: {path}")
            mbse_ids.append(mbse_id)
            if isinstance(name, str):
                identity_pairs.append((name, mbse_id))
    return GlbIdentityEvidence(
        tuple(node_names), tuple(mbse_ids), tuple(identity_pairs)
    )


def _validated_identity_mapping(
    expected_identities: Mapping[str, str],
) -> dict[str, str]:
    if not isinstance(expected_identities, Mapping) or not expected_identities:
        raise CadExportError("Expected GLB identities must be a non-empty mapping")
    expected = dict(expected_identities)
    if not all(
        isinstance(name, str)
        and name
        and isinstance(object_id, str)
        and object_id
        for name, object_id in expected.items()
    ):
        raise CadExportError("Expected GLB identity names and IDs must be strings")
    if len(set(expected.values())) != len(expected):
        raise CadExportError("Expected GLB identities must be unique")
    return expected


def _enrich_document(
    document: dict[str, object], expected: Mapping[str, str], label: str
) -> None:
    nodes = _nodes(document, label)
    matches: dict[str, list[dict[str, object]]] = {
        name: [] for name in expected
    }
    for node in nodes:
        if not isinstance(node, dict):
            raise CadExportError(f"GLB contains a malformed node: {label}")
        name = node.get("name")
        if isinstance(name, str) and name in matches:
            matches[name].append(node)

        extras = node.get("extras")
        if extras is not None and not isinstance(extras, dict):
            raise CadExportError(f"GLB node extras are malformed: {label}")
        if isinstance(extras, dict) and "mbse_id" in extras:
            existing_id = extras["mbse_id"]
            if not isinstance(existing_id, str) or not existing_id:
                raise CadExportError(f"GLB node mbse_id is malformed: {label}")
            expected_id = expected.get(name) if isinstance(name, str) else None
            if existing_id != expected_id:
                raise CadExportError(
                    f"GLB contains conflicting identity metadata: {label}"
                )

    missing = [name for name, found in matches.items() if not found]
    ambiguous = [name for name, found in matches.items() if len(found) > 1]
    if missing:
        raise CadExportError(
            "GLB is missing expected identity nodes: " + ", ".join(missing)
        )
    if ambiguous:
        raise CadExportError(
            "GLB has ambiguous expected identity nodes: " + ", ".join(ambiguous)
        )

    for name, object_id in expected.items():
        node = matches[name][0]
        extras = node.get("extras")
        if extras is None:
            extras = {}
            node["extras"] = extras
        extras["mbse_id"] = object_id


def _serialize_glb(glb: _Glb) -> bytes:
    json_bytes = json.dumps(
        glb.document,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    chunks = ((_JSON_CHUNK, json_bytes), *glb.chunks[1:])
    total_length = 12 + sum(8 + len(payload) for _, payload in chunks)
    output = bytearray(struct.pack("<4sII", _GLB_MAGIC, _GLB_VERSION, total_length))
    for chunk_type, payload in chunks:
        output.extend(struct.pack("<I4s", len(payload), chunk_type))
        output.extend(payload)
    return bytes(output)


def _write_atomic(path: Path, data: bytes) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise


def enrich_glb_identities(
    path: Path, expected_identities: Mapping[str, str]
) -> GlbIdentityEvidence:
    """Atomically add explicit viewer identities and verify the written GLB."""

    path = Path(path)
    expected = _validated_identity_mapping(expected_identities)
    glb = _read_glb(path)
    _enrich_document(glb.document, expected, str(path))
    _write_atomic(path, _serialize_glb(glb))

    written_glb = _read_glb(path)
    if written_glb.chunks[1:] != glb.chunks[1:]:
        raise CadExportError("Written GLB changed a non-JSON chunk")
    evidence = inspect_glb_identity(path)
    expected_names = set(expected)
    expected_ids = set(expected.values())
    expected_pairs = set(expected.items())
    observed_names = [name for name in evidence.node_names if name in expected_names]
    if len(observed_names) != len(expected) or set(observed_names) != expected_names:
        raise CadExportError("Written GLB has incomplete or ambiguous node identities")
    if len(evidence.mbse_ids) != len(expected) or set(evidence.mbse_ids) != expected_ids:
        raise CadExportError("Written GLB has incomplete or conflicting extras identities")
    if (
        len(evidence.identity_pairs) != len(expected)
        or set(evidence.identity_pairs) != expected_pairs
    ):
        raise CadExportError("Written GLB has mismatched node and extras identities")
    return evidence
