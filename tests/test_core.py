from pathlib import Path

from mbse_lite.core import load_model, mermaid_graph, validate_model


def test_demo_project_loads_and_validates():
    project = Path(__file__).parents[1] / "projects" / "demo_project"
    model = load_model(project)

    assert "NEED-001" in model.objects
    assert "REQ-001" in model.objects
    assert "FUN-001" in model.objects
    assert "PART-001" in model.objects
    assert "VER-001" in model.objects
    assert len(model.relations) > 0

    errors = [message for severity, message in validate_model(model) if severity == "ERROR"]
    assert errors == []


def test_mermaid_contains_traceability_edges():
    project = Path(__file__).parents[1] / "projects" / "demo_project"
    graph = mermaid_graph(load_model(project))

    assert "flowchart LR" in graph
    assert "NEED_001 -->|derives| REQ_001" in graph
    assert "REQ_001 -->|verified_by| VER_001" in graph
