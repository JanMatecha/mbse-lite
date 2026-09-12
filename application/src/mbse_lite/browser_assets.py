from __future__ import annotations

import hashlib
import json
from importlib.resources import files


THREE_VERSION = "0.180.0"
MERMAID_VERSION = "11.17.2"
VENDOR_OUTPUT_ROOT = "assets/vendor"
THREE_ASSET_NAME = f"three-viewer-{THREE_VERSION}.min.js"
MERMAID_ASSET_NAME = f"mermaid-{MERMAID_VERSION}.min.js"
THREE_ASSET_PATH = f"{VENDOR_OUTPUT_ROOT}/{THREE_ASSET_NAME}"
MERMAID_ASSET_PATH = f"{VENDOR_OUTPUT_ROOT}/{MERMAID_ASSET_NAME}"
_VENDOR_RESOURCE_NAMES = (
    THREE_ASSET_NAME,
    MERMAID_ASSET_NAME,
    "manifest.json",
    "three-LICENSE.txt",
    "mermaid-LICENSE.txt",
)


def browser_dependency_assets() -> dict[str, bytes]:
    """Load and integrity-check the packaged offline browser dependencies."""

    vendor_root = files("mbse_lite").joinpath("_vendor", "viewer")
    try:
        manifest_bytes = vendor_root.joinpath("manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        packaged = {
            name: vendor_root.joinpath(name).read_bytes()
            for name in _VENDOR_RESOURCE_NAMES
        }
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise RuntimeError("Packaged viewer dependency assets are missing or invalid") from error

    expected_versions = {"three": THREE_VERSION, "mermaid": MERMAID_VERSION}
    for dependency, expected_version in expected_versions.items():
        metadata = manifest.get("dependencies", {}).get(dependency, {})
        if metadata.get("version") != expected_version:
            raise RuntimeError(
                f"Packaged {dependency} version does not match {expected_version}"
            )
        asset_name = metadata.get("asset")
        if asset_name not in packaged:
            raise RuntimeError(f"Packaged {dependency} asset is not listed or available")
        digest = hashlib.sha256(packaged[asset_name]).hexdigest()
        if digest != metadata.get("sha256"):
            raise RuntimeError(f"Packaged {dependency} asset failed its SHA-256 check")

    return {
        f"{VENDOR_OUTPUT_ROOT}/{name}": content
        for name, content in packaged.items()
    }


__all__ = [
    "MERMAID_ASSET_PATH",
    "MERMAID_VERSION",
    "THREE_ASSET_PATH",
    "THREE_VERSION",
    "browser_dependency_assets",
]
