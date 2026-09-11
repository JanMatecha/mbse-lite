from pathlib import Path

from mbse_lite.core import (
    Model,
    ModelObject,
    Relation,
    export_xlsx,
    import_xlsx_to_markdown,
    load_model,
    mermaid_graph,
    validate_model,
)
from mbse_lite.viewer import export_viewer


def demo_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "demo_project"


def finding_messages(model: Model, severity: str) -> list[str]:
    return [message for level, message in validate_model(model) if level == severity]


def test_demo_project_loads_and_validates():
    model = load_model(demo_project())

    assert "NEED-001" in model.objects
    assert "REQ-001" in model.objects
    assert "FUN-001" in model.objects
    assert "PART-001" in model.objects
    assert "VER-001" in model.objects
    assert len(model.relations) > 0

    errors = [message for severity, message in validate_model(model) if severity == "ERROR"]
    assert errors == []


def test_invalid_id_format_is_an_error():
    model = Model(objects={"REQ-01": ModelObject(id="REQ-01", type="Requirement")})

    assert "Invalid ID format: REQ-01; expected PREFIX-NNN" in finding_messages(model, "ERROR")


def test_unknown_id_prefix_is_an_error():
    model = Model(objects={"UNKNOWN-001": ModelObject(id="UNKNOWN-001", type="Unknown")})

    assert "Unknown ID prefix: UNKNOWN in UNKNOWN-001" in finding_messages(model, "ERROR")


def test_duplicate_id_remains_an_error():
    model = Model(
        objects={"NEED-001": ModelObject(id="NEED-001", type="Need")},
        duplicate_ids=["NEED-001"],
    )

    assert "Duplicate ID: NEED-001" in finding_messages(model, "ERROR")


def test_function_with_different_outgoing_relation_still_warns_about_realization():
    model = Model(
        objects={
            "FUN-001": ModelObject(id="FUN-001", type="Function"),
            "PART-001": ModelObject(id="PART-001", type="Part"),
        },
        relations=[Relation(source="FUN-001", relation="connects_to", target="PART-001")],
    )

    assert "Function FUN-001 has no outgoing realized_by relation" in finding_messages(model, "WARNING")


def test_generic_relations_do_not_replace_required_requirement_traceability():
    model = Model(
        objects={
            "NEED-001": ModelObject(id="NEED-001", type="Need"),
            "REQ-001": ModelObject(id="REQ-001", type="Requirement"),
            "FUN-001": ModelObject(id="FUN-001", type="Function"),
        },
        relations=[
            Relation(source="NEED-001", relation="connects_to", target="REQ-001"),
            Relation(source="REQ-001", relation="connects_to", target="FUN-001"),
            Relation(source="FUN-001", relation="realized_by", target="REQ-001"),
        ],
    )

    warnings = finding_messages(model, "WARNING")
    assert "Requirement REQ-001 has no incoming derives relation from a Need" in warnings
    assert "Requirement REQ-001 has no outgoing satisfied_by relation" in warnings
    assert "Requirement REQ-001 has no outgoing verified_by relation" in warnings


def test_valid_model_has_no_validation_findings():
    model = Model(
        objects={
            "NEED-001": ModelObject(id="NEED-001", type="Need"),
            "REQ-001": ModelObject(id="REQ-001", type="Requirement"),
            "FUN-001": ModelObject(id="FUN-001", type="Function"),
            "PART-001": ModelObject(id="PART-001", type="Part"),
            "VER-001": ModelObject(id="VER-001", type="Verification"),
        },
        relations=[
            Relation(source="NEED-001", relation="derives", target="REQ-001"),
            Relation(source="REQ-001", relation="satisfied_by", target="FUN-001"),
            Relation(source="REQ-001", relation="verified_by", target="VER-001"),
            Relation(source="FUN-001", relation="realized_by", target="PART-001"),
        ],
    )

    assert validate_model(model) == []


def test_mermaid_contains_traceability_edges():
    graph = mermaid_graph(load_model(demo_project()))

    assert "flowchart LR" in graph
    assert "NEED_001 -->|derives| REQ_001" in graph
    assert "REQ_001 -->|verified_by| VER_001" in graph


def test_xlsx_round_trip_to_normalized_markdown(tmp_path):
    original = load_model(demo_project())
    xlsx = tmp_path / "model.xlsx"
    imported_dir = tmp_path / "imported"

    export_xlsx(original, xlsx)
    written = import_xlsx_to_markdown(xlsx, imported_dir)
    imported = load_model(imported_dir)

    assert written
    assert set(original.objects) == set(imported.objects)
    assert {(r.source, r.relation, r.target) for r in original.relations} == {
        (r.source, r.relation, r.target) for r in imported.relations
    }


def test_load_model_reads_nested_project_areas(tmp_path):
    mbse = tmp_path / "mbse"
    project_management = tmp_path / "project_management"
    mbse.mkdir()
    project_management.mkdir()

    (mbse / "01_needs.md").write_text(
        "# Needs\n\n| ID | Name | Description | Status |\n|---|---|---|---|\n| NEED-001 | Example | Example need | Draft |\n",
        encoding="utf-8",
    )
    (project_management / "01_tasks.md").write_text(
        "# Tasks\n\n| ID | Name | Owner | Status |\n|---|---|---|---|\n| TASK-001 | Review need | TBD | Planned |\n",
        encoding="utf-8",
    )
    (project_management / "03_relations.md").write_text(
        "# Project-management relations\n\n| Source | Relation | Target |\n|---|---|---|\n| TASK-001 | evaluates | NEED-001 |\n",
        encoding="utf-8",
    )

    model = load_model(tmp_path)

    assert model.objects["NEED-001"].source_file == "mbse/01_needs.md"
    assert model.objects["TASK-001"].source_file == "project_management/01_tasks.md"
    assert model.relations[0].source_file == "project_management/03_relations.md"


def test_web_viewer_contains_model_and_separated_areas(tmp_path):
    model = load_model(demo_project())
    output = tmp_path / "viewer.html"

    export_viewer(model, output, project_name="Demo Project")
    html = output.read_text(encoding="utf-8")

    assert "Demo Project" in html
    assert "MBSE Lite · local read-only viewer" in html
    assert "Project Management" in html
    assert "Project Data" in html
    assert "mbseSearch" in html
    assert "pmSearch" in html
    assert "NEED-001" in html
    assert "flowchart LR" in html


def test_web_viewer_includes_supporting_non_object_tables(tmp_path):
    mbse = tmp_path / "mbse"
    mbse.mkdir()
    (mbse / "inventory.md").write_text(
        "# Inventory\n\n| Category | Item | Status |\n|---|---|---|\n| Machine | Battery mower | Confirmed |\n",
        encoding="utf-8",
    )

    output = tmp_path / "viewer.html"
    export_viewer(load_model(tmp_path), output, project_name="Supporting Data")
    html = output.read_text(encoding="utf-8")

    assert "mbse/inventory.md" in html
    assert "Battery mower" in html
    assert "Supporting Data" in html
