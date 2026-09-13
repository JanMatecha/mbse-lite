from __future__ import annotations

import threading
from pathlib import Path

import pytest

import mbse_lite.editing as editing
from mbse_lite.core import load_model
from mbse_lite.editing import (
    CreateRequirement,
    EditValidationError,
    EditingError,
    RequirementCreationUnavailableError,
    RequirementTableConflictError,
    create_requirement,
    resolve_requirement_creation_target,
    UpdateObjectAttribute,
    update_object_attribute,
)
from mbse_lite.server import ServeApplication


def write_requirements(
    project: Path,
    headers: tuple[str, ...] = ("ID", "Name", "Requirement", "Status"),
    rows: tuple[tuple[str, ...], ...] = (
        ("REQ-001", "First", "First requirement.", "Draft"),
        ("REQ-003", "Third", "Third requirement.", "Confirmed"),
    ),
    *,
    name: str = "requirements.md",
    trailing: str = "\nTrailing prose remains unchanged.\n",
) -> Path:
    source = project / "mbse" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "# Requirements\n\n"
        + "| "
        + " | ".join(headers)
        + " |\n|"
        + "|".join("---" for _ in headers)
        + "|\n"
        + "".join("| " + " | ".join(row) + " |\n" for row in rows)
        + trailing,
        encoding="utf-8",
    )
    return source


@pytest.mark.parametrize(
    ("headers", "values"),
    [
        (
            ("ID", "Name", "Requirement", "Status"),
            {"Name": "New", "Requirement": "New requirement.", "Status": "Draft"},
        ),
        (
            ("ID", "Name", "Description", "Status"),
            {"Name": "New", "Description": "New description.", "Status": "Draft"},
        ),
        (
            (
                "ID",
                "Name",
                "Requirement",
                "Target Length [m]",
                "Target Depth [m]",
                "Status",
            ),
            {
                "Name": "New",
                "Requirement": "New requirement.",
                "Target Length [m]": "",
                "Target Depth [m]": "",
                "Status": "Draft",
            },
        ),
    ],
)
def test_create_requirement_discovers_actual_schema(tmp_path, headers, values):
    source_rows = (
        tuple("REQ-017" if header == "ID" else "Existing" for header in headers),
    )
    source = write_requirements(tmp_path, headers, source_rows)
    target = resolve_requirement_creation_target(tmp_path)

    result = create_requirement(
        tmp_path, CreateRequirement(values, target.table_revision)
    )

    assert result.created_object_id == "REQ-018"
    created = load_model(tmp_path).objects["REQ-018"]
    assert created.type == "Requirement"
    assert created.attributes == values
    assert created.source_ref is not None
    assert created.source_ref.file == "mbse/requirements.md"
    assert source.read_text(encoding="utf-8").count("REQ-018") == 1


def test_allocation_uses_max_suffix_and_does_not_reuse_gaps(tmp_path):
    write_requirements(tmp_path)
    target = resolve_requirement_creation_target(tmp_path)

    result = create_requirement(
        tmp_path,
        CreateRequirement(
            {"Name": "Fourth", "Requirement": "Not second.", "Status": "Draft"},
            target.table_revision,
        ),
    )

    assert result.created_object_id == "REQ-004"
    assert "REQ-002" not in load_model(tmp_path).objects


@pytest.mark.parametrize(
    ("existing_id", "expected_id"),
    [("REQ-0007", "REQ-0008"), ("REQ-999", "REQ-1000")],
)
def test_allocation_preserves_width_and_expands_when_needed(
    tmp_path, existing_id, expected_id
):
    write_requirements(
        tmp_path,
        rows=((existing_id, "Existing", "Existing requirement.", "Draft"),),
    )
    target = resolve_requirement_creation_target(tmp_path)

    result = create_requirement(
        tmp_path,
        CreateRequirement(
            {"Name": "Next", "Requirement": "Next requirement.", "Status": "Draft"},
            target.table_revision,
        ),
    )

    assert result.created_object_id == expected_id
    assert expected_id in load_model(tmp_path).objects


def test_creation_inserts_exactly_one_row_and_preserves_every_existing_byte(tmp_path):
    source = write_requirements(tmp_path)
    before = source.read_bytes()
    target = resolve_requirement_creation_target(tmp_path)

    create_requirement(
        tmp_path,
        CreateRequirement(
            {"Name": "Fourth", "Requirement": "One row.", "Status": "Draft"},
            target.table_revision,
        ),
    )

    after = source.read_bytes()
    line_ending = b"\r\n" if b"\r\n" in before else b"\n"
    inserted = b"| REQ-004 | Fourth | One row. | Draft |" + line_ending
    assert after.count(inserted) == 1
    assert after.replace(inserted, b"", 1) == before


def test_unicode_and_markdown_cell_controls_round_trip_without_extra_rows(tmp_path):
    source = write_requirements(tmp_path)
    target = resolve_requirement_creation_target(tmp_path)
    value = "Příliš | žluťoučký\nkůň & bezpečný"

    create_requirement(
        tmp_path,
        CreateRequirement(
            {"Name": "Čeština", "Requirement": value, "Status": "Draft"},
            target.table_revision,
        ),
    )

    text = source.read_text(encoding="utf-8")
    assert "&#124;" in text
    assert "&#10;" in text
    assert "&amp;" in text
    assert text.count("REQ-004") == 1
    assert load_model(tmp_path).objects["REQ-004"].attributes["Requirement"] == value


def test_missing_or_ambiguous_requirement_table_is_rejected(tmp_path):
    (tmp_path / "parts.md").write_text(
        "| ID | Name |\n|---|---|\n| PART-001 | Frame |\n", encoding="utf-8"
    )
    with pytest.raises(RequirementCreationUnavailableError, match="No existing"):
        resolve_requirement_creation_target(tmp_path)

    write_requirements(tmp_path, name="requirements-a.md")
    write_requirements(
        tmp_path,
        rows=(("REQ-010", "Other", "Other requirement.", "Draft"),),
        name="requirements-b.md",
    )
    with pytest.raises(RequirementCreationUnavailableError, match="ambiguous"):
        resolve_requirement_creation_target(tmp_path)


def test_unknown_columns_browser_id_and_global_collision_are_rejected(tmp_path, monkeypatch):
    source = write_requirements(tmp_path)
    before = source.read_bytes()
    target = resolve_requirement_creation_target(tmp_path)
    for values, message in (
        ({"Unknown": "x"}, "Unknown Requirement columns"),
        ({"ID": "REQ-999"}, "assigned by the application"),
    ):
        with pytest.raises(EditingError, match=message):
            create_requirement(
                tmp_path, CreateRequirement(values, target.table_revision)
            )
        assert source.read_bytes() == before

    monkeypatch.setattr(editing, "_next_requirement_id", lambda model: "REQ-003")
    with pytest.raises(EditingError, match="not globally unique"):
        create_requirement(
            tmp_path,
            CreateRequirement(
                {"Name": "Collision", "Requirement": "No.", "Status": "Draft"},
                target.table_revision,
            ),
        )
    assert source.read_bytes() == before


def test_candidate_validation_failure_changes_no_file(tmp_path, monkeypatch):
    source = write_requirements(tmp_path)
    before = source.read_bytes()
    target = resolve_requirement_creation_target(tmp_path)
    monkeypatch.setattr(
        editing, "_all_validation_findings", lambda project: (("ERROR", "simulated"),)
    )

    with pytest.raises(EditValidationError, match="simulated"):
        create_requirement(
            tmp_path,
            CreateRequirement(
                {"Name": "Invalid", "Requirement": "No.", "Status": "Draft"},
                target.table_revision,
            ),
        )
    assert source.read_bytes() == before


def test_post_commit_failure_restores_original_file(tmp_path, monkeypatch):
    source = write_requirements(tmp_path)
    before = source.read_bytes()
    target = resolve_requirement_creation_target(tmp_path)
    real_findings = editing._all_validation_findings
    calls = 0

    def fail_post_commit(project):
        nonlocal calls
        calls += 1
        if calls == 2:
            return (("ERROR", "post-commit failure"),)
        return real_findings(project)

    monkeypatch.setattr(editing, "_all_validation_findings", fail_post_commit)
    with pytest.raises(EditValidationError, match="post-commit failure"):
        create_requirement(
            tmp_path,
            CreateRequirement(
                {"Name": "Rollback", "Requirement": "No.", "Status": "Draft"},
                target.table_revision,
            ),
        )
    assert source.read_bytes() == before


def test_created_requirement_has_provenance_is_immediately_editable_and_unconnected(tmp_path):
    write_requirements(tmp_path)
    target = resolve_requirement_creation_target(tmp_path)
    result = create_requirement(
        tmp_path,
        CreateRequirement(
            {"Name": "Editable", "Requirement": "Text.", "Status": "Draft"},
            target.table_revision,
        ),
    )

    model = load_model(tmp_path)
    created = model.objects[result.created_object_id]
    assert created.attribute_sources["Status"].row_id == result.created_object_id
    assert all(
        relation.source != result.created_object_id and relation.target != result.created_object_id
        for relation in model.relations
    )
    update_object_attribute(
        tmp_path,
        UpdateObjectAttribute(
            result.created_object_id, "Status", "Confirmed", expected_old_value="Draft"
        ),
    )
    assert load_model(tmp_path).objects[result.created_object_id].attributes["Status"] == "Confirmed"


def test_stale_revision_and_external_table_edit_change_no_creation_rows(tmp_path):
    source = write_requirements(tmp_path)
    stale = resolve_requirement_creation_target(tmp_path)
    source.write_text(
        source.read_text(encoding="utf-8").replace("| Draft |", "| Reviewed |", 1),
        encoding="utf-8",
    )
    externally_edited = source.read_bytes()

    with pytest.raises(RequirementTableConflictError) as conflict:
        create_requirement(
            tmp_path,
            CreateRequirement(
                {"Name": "Stale", "Requirement": "No.", "Status": "Draft"},
                stale.table_revision,
            ),
        )

    assert conflict.value.expected == stale.table_revision
    assert conflict.value.actual != stale.table_revision
    assert source.read_bytes() == externally_edited
    assert "REQ-004" not in load_model(tmp_path).objects


def test_same_revision_attempts_are_serialized_and_cannot_duplicate_ids(tmp_path):
    source = write_requirements(tmp_path)
    app = ServeApplication(tmp_path)
    revision = resolve_requirement_creation_target(tmp_path).table_revision
    payload = {
        "values": {"Name": "Concurrent", "Requirement": "One wins.", "Status": "Draft"},
        "expected_table_revision": revision,
    }
    barrier = threading.Barrier(3)
    responses = []

    def run():
        barrier.wait()
        responses.append(app.create_requirement(payload))

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(response.status for response in responses) == [201, 409]
    assert source.read_text(encoding="utf-8").count("REQ-004") == 1
    assert "REQ-005" not in load_model(tmp_path).objects
