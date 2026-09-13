import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _cadquery_is_usable() -> bool:
    """Probe the optional native dependency without importing it into pytest.

    Package metadata alone is insufficient: CadQuery can be present while its
    OCP DLLs are unavailable.  A successful probe exits before native module
    teardown, matching the isolated worker's supported process boundary.
    """

    completed = subprocess.run(
        [sys.executable, "-c", "import cadquery, os; os._exit(0)"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


CADQUERY_AVAILABLE = _cadquery_is_usable()
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
  gltf.scene.updateMatrixWorld(true);
  for (const id of expected) {
    const object = gltf.scene.getObjectByName(id);
    if (!object || object.userData.mbse_id !== id) process.exitCode = 2;
  }
  const box = id => new mbseThreeModules.THREE.Box3().setFromObject(
    gltf.scene.getObjectByName(id));
  const center = id => box(id).getCenter(new mbseThreeModules.THREE.Vector3());
  const mower = center("PART-005");
  const mainDoor = center("PART-008");
  const mowerDoor = center("PART-010");
  const ramp = center("PART-011");
  const shelving = center("PART-012");
  if (!(mower.x < shelving.x)) process.exitCode = 3;
  if (Math.abs(mowerDoor.x - ramp.x) > 0.001) process.exitCode = 4;
  if (!(mowerDoor.z > 0 && ramp.z > mowerDoor.z && mainDoor.z > 0)) process.exitCode = 5;
  let primitives = 0;
  let triangles = 0;
  gltf.scene.traverse(object => {
    if (!object.isMesh) return;
    primitives += 1;
    triangles += object.geometry.index.count / 3;
  });
  if (primitives !== 72 || triangles !== 144) process.exitCode = 6;
  const size = new mbseThreeModules.THREE.Box3().setFromObject(gltf.scene)
    .getSize(new mbseThreeModules.THREE.Vector3());
  if (Math.abs(size.x - 4000) > 0.001 || Math.abs(size.y - 2220.019228920474) > 0.001 || Math.abs(size.z - 1996.54682524941) > 0.001) process.exitCode = 7;
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
