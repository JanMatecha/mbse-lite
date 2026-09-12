import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


CADQUERY_AVAILABLE = importlib.util.find_spec("cadquery") is not None


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


@pytest.mark.skipif(
    not CADQUERY_AVAILABLE, reason="requires the optional cad dependency"
)
def test_real_export_uses_a_child_process_without_loading_cadquery_in_parent(
    tmp_path,
):
    output_dir = tmp_path / "cad"
    script = """
import sys
from pathlib import Path
from mbse_lite.cad import export_project_cad
from mbse_lite.core import load_model

assert "cadquery" not in sys.modules
result = export_project_cad(load_model(Path(sys.argv[1])), Path(sys.argv[2]))
assert result.completion_record.is_file()
assert all(path.is_file() and path.stat().st_size > 0 for path in result.artifacts)
assert result.worker_exit_code == 0
assert result.warning is None
assert "cadquery" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(garden_shed_project()), str(output_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
