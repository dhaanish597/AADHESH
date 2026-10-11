"""Inventory source construction assets and their packaged model metadata without extraction."""

from __future__ import annotations

import hashlib
import json
import pathlib
import posixpath
import shlex
import struct
import zipfile
from collections import Counter, defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "3d-assets"
OUTPUT = ASSETS / "asset-inventory.json"
MODEL_EXTENSIONS = {".glb", ".gltf", ".obj", ".fbx", ".stl", ".blend"}
TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".webp", ".exr", ".hdr", ".tif", ".tiff"}


def glb_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 20:
        raise ValueError("truncated GLB header")
    magic, version, declared_length = struct.unpack_from("<III", data)
    if magic != 0x46546C67 or version != 2 or declared_length != len(data):
        raise ValueError("invalid or unsupported GLB header")
    offset = 12
    document: dict[str, Any] | None = None
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + length]
        offset += length
        if offset > len(data):
            raise ValueError("chunk extends beyond GLB length")
        if kind == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8").rstrip("\0 "))
    if document is None:
        raise ValueError("JSON chunk missing")
    accessors = document.get("accessors", [])
    position_bounds = [
        (accessors[index].get("min"), accessors[index].get("max"))
        for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
        if (index := primitive.get("attributes", {}).get("POSITION")) is not None
        and accessors[index].get("min") is not None
        and accessors[index].get("max") is not None
    ]
    dimensions = None
    if position_bounds:
        dimensions = [
            round(max(pair[1][axis] for pair in position_bounds) - min(pair[0][axis] for pair in position_bounds), 4)
            for axis in range(3)
        ]
    triangles = 0
    vertices = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            position_index = primitive.get("attributes", {}).get("POSITION")
            if position_index is not None:
                vertices += accessors[position_index].get("count", 0)
            index_index = primitive.get("indices")
            if index_index is not None:
                triangles += accessors[index_index].get("count", 0) // 3
    images = document.get("images", [])
    return {
        "glb_valid": True,
        "mesh_count": len(document.get("meshes", [])),
        "node_count": len(document.get("nodes", [])),
        "material_count": len(document.get("materials", [])),
        "texture_count": len(document.get("textures", [])),
        "image_dependencies": [image.get("uri", "embedded bufferView") for image in images],
        "position_bounds_source_units": dimensions,
        "approx_vertex_count": vertices,
        "approx_triangle_count": triangles,
        "glb_extensions": document.get("extensionsUsed", []),
    }


def obj_metadata(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return {
        "object_names": [line[2:].strip() for line in lines if line.startswith("o ") or line.startswith("g ")][:12],
        "vertex_count": sum(line.startswith("v ") for line in lines),
        "face_count": sum(line.startswith("f ") for line in lines),
        "material_libraries": [line.split(maxsplit=1)[1] for line in lines if line.startswith("mtllib ")],
        "texture_coordinate_count": sum(line.startswith("vt ") for line in lines),
        "normal_count": sum(line.startswith("vn ") for line in lines),
    }


def package_dependencies(archive: zipfile.ZipFile, member_names: set[str], model_path: str, model_format: str, data: bytes) -> tuple[list[str], list[str]]:
    references: list[str] = []
    if model_format == "glb":
        references = [image for image in glb_metadata(data).get("image_dependencies", []) if image != "embedded bufferView"]
    elif model_format == "obj":
        references = obj_metadata(data).get("material_libraries", [])
        for mtl in list(references):
            mtl_path = posixpath.normpath(posixpath.join(posixpath.dirname(model_path), mtl))
            if mtl_path not in member_names:
                continue
            for line in archive.read(mtl_path).decode("utf-8", errors="replace").splitlines():
                if line.strip().lower().startswith(("map_", "bump ", "norm ", "disp ", "decal ", "refl ")):
                    try:
                        references.append(shlex.split(line.strip())[-1])
                    except ValueError:
                        pass
    resolved: list[str] = []
    missing: list[str] = []
    for reference in dict.fromkeys(references):
        candidate = posixpath.normpath(posixpath.join(posixpath.dirname(model_path), reference.replace("\\", "/")))
        if candidate.startswith("../") or candidate.startswith("/") or "://" in candidate:
            missing.append(reference)
        elif candidate in member_names:
            resolved.append(candidate)
        else:
            missing.append(reference)
    return resolved, missing


def license_text(archive: zipfile.ZipFile, names: list[str]) -> tuple[str, str | None]:
    candidates = [name for name in names if pathlib.PurePosixPath(name).name.lower() in {"license.txt", "license.md", "license", "readme.txt", "readme.md"}]
    for name in candidates:
        content = archive.read(name).decode("utf-8", errors="replace")
        if "creative commons zero" in content.lower() or "cc0" in content.lower():
            return "CC0-1.0", name
    return "UNKNOWN", candidates[0] if candidates else None


def model_purpose(path: str) -> str:
    name = pathlib.PurePosixPath(path).stem.lower()
    if "construction" in name or name in {"barrier", "fence", "cone"}:
        return "Construction boundary or safety prop"
    if name.startswith("road-") or name.startswith("tile-"):
        return "Road and street layout component"
    if name.startswith("building-") or name.startswith("low-detail-building") or "skyscraper" in name:
        return "Architectural context building"
    if name.startswith("column") or name.startswith("floor") or name.startswith("wall") or name.startswith("roof") or name.startswith("plating"):
        return "Modular building structure component"
    if "dumpster" in name:
        return "Construction waste container"
    if "electricity" in name or "light" in name:
        return "Street utility or lighting prop"
    return "Model purpose inferred from package documentation/name; visual inspection recommended"


def main() -> None:
    archive_reports: list[dict[str, Any]] = []
    packaged_models: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    digests: dict[str, list[str]] = defaultdict(list)
    package_runtime_hashes = {
        "building-a": "kenney_city-kit-commercial_2.1.zip",
        "building-c": "kenney_city-kit-commercial_2.1.zip",
        "column": "kenney_building-kit.zip",
        "floor": "kenney_building-kit.zip",
        "wall": "kenney_building-kit.zip",
        "construction-fence": "kenney_city-kit-roads.zip",
        "construction-barrier": "kenney_city-kit-roads.zip",
        "construction-cone": "kenney_city-kit-roads.zip",
        "dumpster": "kenney_city-kit-roads.zip",
    }
    runtime_paths = {f"{key}.glb": f"web/public/models/kenney/{key}.glb" for key in package_runtime_hashes}
    for path in sorted(ASSETS.rglob("*")):
        if path.is_file() and path != OUTPUT:
            data = path.read_bytes()
            source_files.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "format": path.suffix.lower().lstrip(".") or "unknown"})

    for archive_path in sorted(ASSETS.glob("*.zip")):
        with zipfile.ZipFile(archive_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/") and "/__MACOSX/" not in f"/{name}"]
            member_set = set(members)
            formats = Counter(pathlib.PurePosixPath(name).suffix.lower().lstrip(".") or "unknown" for name in members)
            license_id, license_path = license_text(archive, members)
            model_paths = [name for name in members if pathlib.PurePosixPath(name).suffix.lower() in MODEL_EXTENSIONS]
            texture_paths = [name for name in members if pathlib.PurePosixPath(name).suffix.lower() in TEXTURE_EXTENSIONS]
            other_paths = [name for name in members if pathlib.PurePosixPath(name).suffix.lower() not in MODEL_EXTENSIONS | TEXTURE_EXTENSIONS]
            for name in model_paths:
                model_format = pathlib.PurePosixPath(name).suffix.lower().lstrip(".")
                data = archive.read(name)
                digest = hashlib.sha256(data).hexdigest()
                digests[digest].append(f"{archive_path.name}:{name}")
                record: dict[str, Any] = {
                    "source_path": f"{archive_path.name}/{name}",
                    "format": model_format,
                    "bytes": len(data),
                    "sha256": digest,
                    "purpose": model_purpose(name),
                    "license": license_id,
                    "runtime_suitable": model_format == "glb" and license_id == "CC0-1.0",
                }
                try:
                    if model_format == "glb":
                        record.update(glb_metadata(data))
                        dependencies, missing = package_dependencies(archive, member_set, name, model_format, data)
                        record["resolved_dependencies"] = dependencies
                        record["missing_dependencies"] = missing
                    elif model_format == "obj":
                        record["geometry_metadata"] = obj_metadata(data)
                        dependencies, missing = package_dependencies(archive, member_set, name, model_format, data)
                        record["resolved_dependencies"] = dependencies
                        record["missing_dependencies"] = missing
                    elif model_format == "fbx":
                        record["geometry_metadata"] = "FBX binary/text geometry not parsed: no Blender, Assimp or FBX SDK installed."
                    elif model_format == "blend":
                        record["geometry_metadata"] = "Blender project not inspected: Blender Python (bpy) and Blender executable unavailable."
                    elif model_format == "gltf":
                        record["geometry_metadata"] = "External glTF JSON not encountered in audited archives."
                except (ValueError, KeyError, IndexError, json.JSONDecodeError, struct.error) as error:
                    record["inspection_error"] = str(error)
                runtime_name = pathlib.PurePosixPath(name).stem
                if runtime_name in package_runtime_hashes and package_runtime_hashes[runtime_name] == archive_path.name and model_format == "glb":
                    record["runtime_copy"] = runtime_paths[f"{runtime_name}.glb"]
                    copy = ROOT / runtime_paths[f"{runtime_name}.glb"]
                    record["runtime_copy_matches_source"] = copy.exists() and hashlib.sha256(copy.read_bytes()).hexdigest() == digest
                packaged_models.append(record)
            archive_reports.append({
                "archive": archive_path.relative_to(ROOT).as_posix(),
                "bytes": archive_path.stat().st_size,
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                "member_count": len(members),
                "format_counts": dict(sorted(formats.items())),
                "license": license_id,
                "license_file": license_path,
                "model_count": len(model_paths),
                "texture_count": len(texture_paths),
                "texture_files": [f"{archive_path.name}/{name}" for name in texture_paths],
                "other_files": [f"{archive_path.name}/{name}" for name in other_paths],
            })

    duplicates = [paths for paths in digests.values() if len(paths) > 1]
    report = {
        "title": "AADESH V2 3D source asset audit",
        "generated_by": "scripts/audit_3d_assets.py",
        "scope": "All files recursively under 3d-assets, and all non-macOS entries in its ZIP archives. ZIPs are read in place and preserved.",
        "inspection_limits": [
            "GLB v2 JSON metadata, accessor bounds, mesh/material/texture counts, image references, vertex and triangle estimates were parsed directly.",
            "OBJ vertex, face, group/object, normal, texture coordinate and material-library references were inspected; OBJ material/texture reference resolution is not performed by this audit script.",
            "FBX and Blender binary/model internals were not parsed because Blender, Assimp, bpy and an FBX SDK are unavailable. Their entries remain catalogued and are excluded from runtime.",
            "GLB accessor bounds are source coordinates; glTF node transforms are not baked into these approximate extents. Kenney models use small modular source-unit dimensions, normalized in the scene assembler where placed.",
        ],
        "archive_count": len(archive_reports),
        "archives": archive_reports,
        "model_file_count": len(packaged_models),
        "broken_model_dependency_count": sum(bool(model.get("missing_dependencies")) for model in packaged_models),
        "models": packaged_models,
        "source_files": source_files,
        "exact_duplicate_sha256_groups": duplicates,
        "runtime_registry": "web/lib/site-scene/registry.ts",
        "runtime_models": sorted(key for key, value in package_runtime_hashes.items() if any(item.get("runtime_copy_matches_source") for item in packaged_models if item.get("runtime_copy") == runtime_paths[f"{key}.glb"])),
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(archive_reports)} archives, {len(packaged_models)} model files, {sum(len(a['texture_files']) for a in archive_reports)} texture files, {len(duplicates)} exact duplicate groups")


if __name__ == "__main__":
    main()
