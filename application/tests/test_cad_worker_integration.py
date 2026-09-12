import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


CADQUERY_AVAILABLE = importlib.util.find_spec("cadquery") is not None
EXPECTED_COMPONENT_IDS = (
    "PART-001",
    "PART-004",
    "PART-005",
    "PART-008",
    "PART-010",
    "PART-011",
    "PART-012",
)


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


@pytest.mark.skipif(
    not CADQUERY_AVAILABLE, reason="requires the optional cad dependency"
)
def test_real_export_uses_a_child_process_without_loading_cadquery_in_parent(
    tmp_path,
):
    output_dir = tmp_path / "cad"
    expected_literal = repr(EXPECTED_COMPONENT_IDS)
    script = f"""
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
assert result.glb_mbse_ids == {expected_literal}
assert result.manifest["stable_identity"]["glb"]["preserves_current_viewer_extras_mbse_id"] is True
assert "cadquery" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(garden_shed_project()), str(output_dir)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr

    node = shutil.which("node")
    if node is None:
        return
    bundle = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "mbse_lite"
        / "_vendor"
        / "viewer"
        / "three-viewer-0.180.0.min.js"
    )
    glb = output_dir / "conceptual-preview.glb"
    javascript = """
const fs = require("fs");
const vm = require("vm");
globalThis.self = globalThis;
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const data = fs.readFileSync(process.argv[2]);
const arrayBuffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
const expected = JSON.parse(process.argv[3]);
new mbseThreeModules.GLTFLoader().parse(arrayBuffer, "", (gltf) => {
  for (const id of expected) {
    const object = gltf.scene.getObjectByName(id);
    if (!object || object.userData.mbse_id !== id) process.exitCode = 2;
  }
}, (error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    loaded = subprocess.run(
        [
            node,
            "-e",
            javascript,
            str(bundle),
            str(glb),
            json.dumps(EXPECTED_COMPONENT_IDS),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert loaded.returncode == 0, loaded.stdout + loaded.stderr
