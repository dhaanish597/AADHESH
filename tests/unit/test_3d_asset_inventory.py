import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "3d-assets" / "asset-inventory.json"


def test_asset_audit_covers_every_source_archive_and_reused_model() -> None:
    report = json.loads(INVENTORY.read_text(encoding="utf-8"))
    source_archives = sorted(path.name for path in (ROOT / "3d-assets").glob("*.zip"))
    reported_archives = sorted(Path(item["archive"]).name for item in report["archives"])
    assert reported_archives == source_archives
    assert report["archive_count"] == len(source_archives) == 7
    assert report["broken_model_dependency_count"] == 0

    runtime_models = [model for model in report["models"] if model.get("runtime_copy")]
    assert len(runtime_models) == 9
    assert all(model["runtime_copy_matches_source"] for model in runtime_models)
    assert all((ROOT / model["runtime_copy"]).is_file() for model in runtime_models)
    assert all(model["glb_valid"] for model in runtime_models)
    assert all(model["approx_triangle_count"] > 0 for model in runtime_models)


def test_cc0_provenance_and_unknown_blender_licenses_are_kept_distinct() -> None:
    report = json.loads(INVENTORY.read_text(encoding="utf-8"))
    archives = {Path(item["archive"]).name: item for item in report["archives"]}
    for name in ("kenney_building-kit.zip", "kenney_city-kit-commercial_2.1.zip", "kenney_city-kit-roads.zip"):
        item = archives[name]
        assert item["license"] == "CC0-1.0"
        with zipfile.ZipFile(ROOT / item["archive"]) as source:
            license_text = source.read(item["license_file"]).decode("utf-8")
            assert "Creative Commons Zero" in license_text

    blender_archives = [item for item in report["archives"] if item["archive"].endswith(".blend.zip")]
    assert len(blender_archives) == 3
    assert all(item["license"] == "UNKNOWN" for item in blender_archives)
    assert not any(model["runtime_suitable"] for model in report["models"] if model["format"] == "blend")
