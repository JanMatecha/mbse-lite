from __future__ import annotations

import sys
from pathlib import Path

import pytest

import mbse_lite.editing as editing
from mbse_lite.cli import main
from mbse_lite.core import load_model
from mbse_lite.editing import (
    EditConflictError,
    EditingError,
    EditValidationError,
    UpdateObjectAttribute,
    update_object_attribute,
)


def write_simple_project(project: Path) -> Path:
    source = project / "mbse" / "parts.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# Parts\n\n"
        "Unrelated prose stays byte-for-byte unchanged.\n\n"
        "| ID | Name | Description | Status |\n"
        "|---|---|---|---|\n"
        "| PART-001 | Frame | Original description | Draft |\n"
        "| PART-002 | Roof | Unrelated row | Draft |\n",
        encoding="utf-8",
    )
    return source


def write_geometry_project(project: Path) -> Path:
    requirements = project / "mbse" / "requirements.md"
    requirements.parent.mkdir(parents=True)
    requirements.write_text(
        "# Requirements\n\n"
        "| ID | Name | Requirement | Target Length [m] | Target Depth [m] | Status |\n"
        "|---|---|---|---|---|---|\n"
        "| REQ-008 | Footprint | Structured footprint. | 4.0 | 1.2 | Draft |\n",
        encoding="utf-8",
    )
    parts = [
        ("enclosure", "PART-001"),
        ("main_storage", "PART-004"),
        ("mower_compartment", "PART-005"),
        ("main_door", "PART-008"),
        ("mower_door", "PART-010"),
        ("mower_ramp", "PART-011"),
        ("shelving", "PART-012"),
    ]
    concepts = [
        ("mower_door_candidate", "CON-007"),
        ("main_door_candidate", "CON-010"),
    ]
    (project / "mbse" / "parts.md").write_text(
        "# Parts\n\n| ID | Name | Description |\n|---|---|---|\n"
        + "".join(
            f"| {object_id} | {role} | Test part |\n" for role, object_id in parts
        ),
        encoding="utf-8",
    )
    (project / "mbse" / "concepts.md").write_text(
        "# Concepts\n\n| ID | Name | Status |\n|---|---|---|\n"
        + "".join(
            f"| {object_id} | {role} | Preferred candidate |\n"
            for role, object_id in concepts
        ),
        encoding="utf-8",
    )
    (project / "visualization.md").write_text(
        "# Visualization\n\n"
        "| Visualization Profile | Role | Object ID | Expected Type |\n"
        "|---|---|---|---|\n"
        + "".join(
            f"| garden_shed | {role} | {object_id} | Part |\n"
            for role, object_id in parts
        )
        + "| garden_shed | footprint | REQ-008 | Requirement |\n"
        + "".join(
            f"| garden_shed | {role} | {object_id} | Concept |\n"
            for role, object_id in concepts
        ),
        encoding="utf-8",
    )
    return requirements


def test_update_attribute_changes_only_one_cell_and_round_trips_safe_text(tmp_path):
    source = write_simple_project(tmp_path)
    original_lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    new_value = " Příliš & | žluťoučký\nkůň "

    result = update_object_attribute(
        tmp_path,
        UpdateObjectAttribute(
            object_id="PART-001",
            attribute="Description",
            new_value=new_value,
            expected_old_value="Original description",
        ),
    )

    updated_lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    changed_lines = [
        index
        for index, (before, after) in enumerate(zip(original_lines, updated_lines), start=1)
        if before != after
    ]
    assert changed_lines == [7]
    assert "&#124;" in updated_lines[6]
    assert "&#10;" in updated_lines[6]
    assert "&amp;" in updated_lines[6]
    assert load_model(tmp_path).objects["PART-001"].attributes["Description"] == new_value
    assert load_model(tmp_path).objects["PART-002"].attributes["Description"] == "Unrelated row"
    assert result.source_file == "mbse/parts.md"
    assert result.source_ref.row_id == "PART-001"
    assert result.source_ref.column == "Description"
    assert result.changed is True


def test_update_attribute_supports_empty_strings(tmp_path):
    write_simple_project(tmp_path)

    update_object_attribute(
        tmp_path,
        UpdateObjectAttribute("PART-001", "Description", ""),
    )

    assert load_model(tmp_path).objects["PART-001"].attributes["Description"] == ""


def test_dry_run_validates_without_modifying_source(tmp_path):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()

    result = update_object_attribute(
        tmp_path,
        UpdateObjectAttribute(
            "PART-001", "Description", "Proposed", dry_run=True
        ),
    )

    assert source.read_bytes() == before
    assert result.dry_run is True
    assert result.changed is True


def test_expected_old_value_conflict_is_explicit_and_preserves_source(tmp_path):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()

    with pytest.raises(EditConflictError, match="expected 'Stale', found 'Original description'"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute(
                "PART-001",
                "Description",
                "Replacement",
                expected_old_value="Stale",
            ),
        )

    assert source.read_bytes() == before


@pytest.mark.parametrize(
    ("object_id", "attribute", "message"),
    [
        ("PART-999", "Description", "Unknown object ID"),
        ("PART-001", "Unknown field", "has no attribute"),
    ],
)
def test_unknown_object_or_attribute_is_rejected_without_modification(
    tmp_path, object_id, attribute, message
):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()

    with pytest.raises(EditingError, match=message):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute(object_id, attribute, "Replacement"),
        )

    assert source.read_bytes() == before


def test_generic_update_rejects_stable_id_changes(tmp_path):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()

    with pytest.raises(EditingError, match="Stable IDs are immutable"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute("PART-001", "ID", "PART-003"),
        )

    assert source.read_bytes() == before


def test_update_rejects_ambiguous_duplicate_columns_without_modifying_source(tmp_path):
    source = tmp_path / "parts.md"
    source.write_text(
        "| ID | Description | Description |\n"
        "|---|---|---|\n"
        "| PART-001 | First | Second |\n",
        encoding="utf-8",
    )
    before = source.read_bytes()

    with pytest.raises(EditingError, match="is ambiguous"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute("PART-001", "Description", "Replacement"),
        )

    assert source.read_bytes() == before


def test_update_re_resolves_stale_physical_line_by_stable_row_identity(
    tmp_path, monkeypatch
):
    source = write_simple_project(tmp_path)
    stale_model = load_model(tmp_path)
    stale_line = stale_model.objects["PART-001"].attribute_sources["Description"].line
    source.write_text(
        "New unrelated introduction.\nAnother inserted line.\n" + source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    real_load_model = editing.load_model
    project_load_count = 0

    def load_with_stale_initial_provenance(project_path):
        nonlocal project_load_count
        if Path(project_path).resolve() == tmp_path.resolve():
            project_load_count += 1
            if project_load_count == 1:
                return stale_model
        return real_load_model(project_path)

    monkeypatch.setattr(editing, "load_model", load_with_stale_initial_provenance)

    result = update_object_attribute(
        tmp_path,
        UpdateObjectAttribute("PART-001", "Description", "Moved-row update"),
    )

    assert result.source_ref.line == stale_line + 2
    assert load_model(tmp_path).objects["PART-001"].attributes["Description"] == "Moved-row update"
    assert source.read_text(encoding="utf-8").startswith(
        "New unrelated introduction.\nAnother inserted line.\n"
    )


def test_invalid_structured_geometry_update_is_rejected_before_commit(tmp_path):
    source = write_geometry_project(tmp_path)
    before = source.read_bytes()

    with pytest.raises(EditValidationError, match="not a valid number"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute("REQ-008", "Target Length [m]", "invalid"),
        )

    assert source.read_bytes() == before
    assert load_model(tmp_path).objects["REQ-008"].attributes["Target Length [m]"] == "4.0"


def test_external_file_change_before_commit_is_not_overwritten(
    tmp_path, monkeypatch
):
    source = write_simple_project(tmp_path)
    real_validate_candidate = editing._validate_candidate

    def validate_then_change(project_path, source_file, patched_bytes):
        findings = real_validate_candidate(project_path, source_file, patched_bytes)
        source.write_text(
            source.read_text(encoding="utf-8").replace(
                "Original description", "External edit"
            ),
            encoding="utf-8",
        )
        return findings

    monkeypatch.setattr(editing, "_validate_candidate", validate_then_change)

    with pytest.raises(EditConflictError, match="changed before commit"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute("PART-001", "Description", "Command edit"),
        )

    assert load_model(tmp_path).objects["PART-001"].attributes["Description"] == "External edit"


def test_unexpected_post_commit_validation_error_rolls_back_source(
    tmp_path, monkeypatch
):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()
    real_findings = editing._all_validation_findings
    call_count = 0

    def fail_second_validation(project_path):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return (("ERROR", "simulated post-commit failure"),)
        return real_findings(project_path)

    monkeypatch.setattr(editing, "_all_validation_findings", fail_second_validation)

    with pytest.raises(EditValidationError, match="simulated post-commit failure"):
        update_object_attribute(
            tmp_path,
            UpdateObjectAttribute("PART-001", "Description", "Command edit"),
        )

    assert source.read_bytes() == before


def test_cli_update_attribute_is_a_thin_dry_run_proof(tmp_path, monkeypatch, capsys):
    source = write_simple_project(tmp_path)
    before = source.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mbse-lite",
            "update-attribute",
            str(tmp_path),
            "PART-001",
            "Description",
            "Proposed",
            "--expect",
            "Original description",
            "--dry-run",
        ],
    )

    exit_code = main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert source.read_bytes() == before
    assert "Object: PART-001" in output
    assert "Attribute: Description" in output
    assert "Markdown file: mbse/parts.md" in output
    assert "Dry run: validation passed; no files modified" in output
