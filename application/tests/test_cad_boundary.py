import copy
import subprocess
import sys
import tomllib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from mbse_lite.cad import (
    CAD_INSTALL_MESSAGE,
    CadExportError,
    CadGeometryError,
    CadQueryUnavailableError,
    export_project_cad,
    quantity_to_millimetres,
)
import mbse_lite.cad.cadquery_backend as cadquery_backend
import mbse_lite.cad.runner as cad_runner
import mbse_lite.cad as cad_api
from mbse_lite.cli import main
from mbse_lite.core import SourceRef, load_model
from mbse_lite.geometry import Quantity


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def quantity(value: Decimal, unit: str = "m") -> Quantity:
    return Quantity(
        value=value,
        unit=unit,
        source=SourceRef(
            file="mbse/02_requirements.md",
            table_index=0,
            row_index=7,
            row_id="REQ-008",
            column=f"Target Length [{unit}]",
            line=12,
        ),
    )


def test_cadquery_is_an_optional_exactly_selected_dependency():
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    assert pyproject["project"]["dependencies"] == ["openpyxl>=3.1"]
    assert pyproject["project"]["optional-dependencies"]["cad"] == [
        "cadquery==2.8.0"
    ]


def test_general_application_imports_do_not_load_cadquery():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import mbse_lite; import mbse_lite.geometry; "
                "import mbse_lite.cad; "
                "from mbse_lite.cli import build_parser; "
                "assert 'cadquery' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_authoritative_quantity_conversion_is_exact_and_centralized():
    assert quantity_to_millimetres(quantity(Decimal("4.0"))) == Decimal("4000.0")
    assert quantity_to_millimetres(quantity(Decimal("1200"), "mm")) == Decimal(
        "1200"
    )


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (quantity(Decimal("4"), "cm"), "Unsupported CAD length unit 'cm'"),
        (quantity(Decimal("0")), "finite and positive"),
        (quantity(Decimal("NaN")), "finite and positive"),
    ],
)
def test_invalid_quantities_are_rejected_before_cadquery(candidate, message):
    with pytest.raises(CadGeometryError, match=message):
        quantity_to_millimetres(candidate)


def test_backend_import_failure_has_an_actionable_optional_dependency_message(
    monkeypatch,
):
    def unavailable(name):
        assert name == "cadquery"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(cadquery_backend.importlib, "import_module", unavailable)

    with pytest.raises(CadQueryUnavailableError) as caught:
        cadquery_backend._load_cadquery()

    assert str(caught.value) == CAD_INSTALL_MESSAGE
    assert "uv sync --extra cad" in str(caught.value)


def test_cli_reports_missing_cadquery_without_a_traceback(
    tmp_path, monkeypatch, capsys
):
    def unavailable(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=f"ERROR: {CAD_INSTALL_MESSAGE}\n",
        )

    monkeypatch.setattr(cad_runner.subprocess, "run", unavailable)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mbse-lite",
            "export-cad",
            str(garden_shed_project()),
            str(tmp_path / "cad"),
        ],
    )

    exit_code = main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert CAD_INSTALL_MESSAGE in output
    assert "did not publish completion record" in output
    assert "Traceback" not in output
    assert not any((tmp_path / "cad").glob("*.step"))


def test_cli_returns_success_and_prints_known_worker_warning(
    tmp_path, monkeypatch, capsys
):
    output_dir = tmp_path / "cad"
    warning = (
        "WARNING: the isolated CadQuery worker terminated during Windows "
        "interpreter shutdown with known upstream error 0xC0000374."
    )

    def successful_export(model, requested_output_dir):
        assert requested_output_dir == output_dir
        return SimpleNamespace(
            artifacts=(output_dir / "footprint.step",), warning=warning
        )

    monkeypatch.setattr(cad_api, "export_project_cad", successful_export)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mbse-lite",
            "export-cad",
            str(garden_shed_project()),
            str(output_dir),
        ],
    )

    exit_code = main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "CAD export completed successfully." in output
    assert "Written:" in output
    assert "0xC0000374" in output


def test_validation_errors_block_export_before_optional_backend_is_loaded(
    tmp_path, monkeypatch
):
    model = copy.deepcopy(load_model(garden_shed_project()))
    model.objects["REQ-008"].attributes["Target Length [m]"] = "0"

    def must_not_launch(*args, **kwargs):
        raise AssertionError("CAD worker must not launch for an invalid model")

    monkeypatch.setattr(cad_runner.subprocess, "run", must_not_launch)

    with pytest.raises(CadExportError, match="CAD export blocked.*must be positive"):
        export_project_cad(model, tmp_path / "cad")

    assert not (tmp_path / "cad").exists()
