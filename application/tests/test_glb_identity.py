import copy
import json
import struct

import pytest

from mbse_lite.cad.glb_identity import (
    enrich_glb_identities,
    inspect_glb_identity,
)
from mbse_lite.cad.protocol import CadExportError


def _glb(document, bin_chunk=b"\x01\x02\x03\x04"):
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    chunks = [(b"JSON", json_chunk), (b"BIN\x00", bin_chunk)]
    length = 12 + sum(8 + len(payload) for _, payload in chunks)
    result = bytearray(struct.pack("<4sII", b"glTF", 2, length))
    for chunk_type, payload in chunks:
        result.extend(struct.pack("<I4s", len(payload), chunk_type))
        result.extend(payload)
    return bytes(result)


def _chunks(data):
    chunks = []
    offset = 12
    while offset < len(data):
        length, chunk_type = struct.unpack_from("<I4s", data, offset)
        start = offset + 8
        chunks.append((chunk_type, data[start : start + length]))
        offset = start + length
    return chunks


def _document(data):
    json_chunk = _chunks(data)[0][1]
    return json.loads(json_chunk.rstrip(b" ").decode("utf-8"))


def _sample_document():
    return {
        "asset": {"version": "2.0", "generator": "test"},
        "extensionsUsed": ["TEST_extension"],
        "nodes": [
            {"name": "root", "children": [1, 2]},
            {"name": "PART-001", "mesh": 0, "extras": {"foo": "bar"}},
            {"name": "PART-004", "mesh": 1},
        ],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]},
            {"primitives": [{"attributes": {"POSITION": 2}, "material": 0}]},
        ],
        "accessors": [{"count": 3}, {"count": 3}, {"count": 4}],
        "bufferViews": [{"buffer": 0, "byteLength": 12}],
        "buffers": [{"byteLength": 4}],
        "materials": [{"name": "unchanged"}],
        "extensions": {"TEST_extension": {"value": 7}},
    }


def test_enrichment_adds_expected_ids_without_changing_geometry_or_bin(tmp_path):
    path = tmp_path / "model.glb"
    before_document = _sample_document()
    before_geometry = copy.deepcopy(
        {
            key: before_document[key]
            for key in ("meshes", "accessors", "bufferViews", "buffers", "materials")
        }
    )
    bin_chunk = b"\x10\x20\x30\x40\x50\x60\x70\x80"
    path.write_bytes(_glb(before_document, bin_chunk))

    evidence = enrich_glb_identities(
        path, {"PART-001": "PART-001", "PART-004": "PART-004"}
    )

    after = _document(path.read_bytes())
    nodes = {node["name"]: node for node in after["nodes"]}
    assert nodes["PART-001"]["extras"] == {
        "foo": "bar",
        "mbse_id": "PART-001",
    }
    assert nodes["PART-004"]["extras"] == {"mbse_id": "PART-004"}
    assert {key: after[key] for key in before_geometry} == before_geometry
    assert after["extensions"] == before_document["extensions"]
    assert _chunks(path.read_bytes())[1] == (b"BIN\x00", bin_chunk)
    assert evidence.mbse_ids == ("PART-001", "PART-004")
    assert evidence.identity_pairs == (
        ("PART-001", "PART-001"),
        ("PART-004", "PART-004"),
    )


def test_matching_existing_identity_is_accepted_and_second_run_is_idempotent(
    tmp_path,
):
    path = tmp_path / "model.glb"
    document = _sample_document()
    document["nodes"][1]["extras"]["mbse_id"] = "PART-001"
    path.write_bytes(_glb(document))
    expected = {"PART-001": "PART-001", "PART-004": "PART-004"}

    enrich_glb_identities(path, expected)
    first = path.read_bytes()
    enrich_glb_identities(path, expected)

    assert path.read_bytes() == first
    assert inspect_glb_identity(path).mbse_ids == ("PART-001", "PART-004")


def test_conflicting_existing_identity_is_rejected(tmp_path):
    path = tmp_path / "model.glb"
    document = _sample_document()
    document["nodes"][1]["extras"]["mbse_id"] = "PART-999"
    path.write_bytes(_glb(document))

    with pytest.raises(CadExportError, match="conflicting identity metadata"):
        enrich_glb_identities(path, {"PART-001": "PART-001"})


def test_unexpected_existing_identity_is_rejected(tmp_path):
    path = tmp_path / "model.glb"
    document = _sample_document()
    document["nodes"][0]["extras"] = {"mbse_id": "PART-999"}
    path.write_bytes(_glb(document))

    with pytest.raises(CadExportError, match="conflicting identity metadata"):
        enrich_glb_identities(path, {"PART-001": "PART-001"})


def test_missing_expected_node_is_rejected(tmp_path):
    path = tmp_path / "model.glb"
    path.write_bytes(_glb(_sample_document()))

    with pytest.raises(CadExportError, match="missing.*PART-999"):
        enrich_glb_identities(path, {"PART-999": "PART-999"})


def test_duplicate_expected_node_is_rejected(tmp_path):
    path = tmp_path / "model.glb"
    document = _sample_document()
    document["nodes"].append({"name": "PART-001", "mesh": 0})
    path.write_bytes(_glb(document))

    with pytest.raises(CadExportError, match="ambiguous.*PART-001"):
        enrich_glb_identities(path, {"PART-001": "PART-001"})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: b"bad!" + data[4:], "invalid magic"),
        (
            lambda data: data[:4] + struct.pack("<I", 1) + data[8:],
            "version 1 is unsupported",
        ),
        (lambda data: data[:10], "truncated"),
        (lambda data: data[:-4], "total length is invalid"),
        (
            lambda data: data[:12]
            + struct.pack("<I", 0xFFFFFFFC)
            + data[16:],
            "truncated chunk",
        ),
    ],
)
def test_malformed_glb_is_rejected(tmp_path, mutate, message):
    path = tmp_path / "model.glb"
    path.write_bytes(mutate(_glb(_sample_document())))

    with pytest.raises(CadExportError, match=message):
        enrich_glb_identities(path, {"PART-001": "PART-001"})


def test_output_header_and_chunks_remain_four_byte_aligned(tmp_path):
    path = tmp_path / "model.glb"
    path.write_bytes(
        _glb({"asset": {"version": "2.0"}, "nodes": [{"name": "X"}]})
    )

    enrich_glb_identities(path, {"X": "X"})

    data = path.read_bytes()
    _, version, total_length = struct.unpack_from("<4sII", data)
    assert version == 2
    assert total_length == len(data)
    assert total_length % 4 == 0
    assert all(len(payload) % 4 == 0 for _, payload in _chunks(data))
