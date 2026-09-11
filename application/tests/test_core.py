from pathlib import Path

from mbse_lite.core import (
    export_xlsx,
    import_xlsx_to_markdown,
    load_model,
    mermaid_graph,
    validate_model,
)
from mbse_lite.viewer import export_viewer


def demo_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "demo_project"


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


def test_web_viewer_contains_model_and_interactive_controls(tmp_path):
    model = load_model(demo_project())
    output = tmp_path / "viewer.html"

    export_viewer(model, output, project_name="Demo Project")
    html = output.read_text(encoding="utf-8")

    assert "Demo Project" in html
    assert "MBSE Lite · local read-only viewer" in html
    assert "objectSearch" in html
    assert "typeFilter" in html
    assert "NEED-001" in html
    assert "flowchart LR" in html
