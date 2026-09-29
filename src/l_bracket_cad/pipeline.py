from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .geometry import GeometryAnalysis, analyze_mesh
from .geometry import as_dict as geometry_as_dict
from .rules import EngineeringRules


class Stage(StrEnum):
    INGESTION = "ingestion"
    PREPROCESSING = "preprocessing"
    DETECTION = "detection"
    MAPPING = "mapping"
    VALIDATION = "validation"
    REPORTING = "reporting"


@dataclass(frozen=True)
class MeshSummary:
    filename: str
    extension: str
    vertices: int | None
    faces: int | None
    bounds: list[list[float]] | None
    watertight: bool | None
    backend: str


@dataclass(frozen=True)
class PipelineResult:
    job_id: str
    source: MeshSummary
    geometry: GeometryAnalysis | None
    completed_stages: list[Stage]
    pending_stages: list[Stage]


SUPPORTED_MESH_EXTENSIONS = {".stl", ".obj", ".ply"}
def inspect_mesh(path: Path) -> MeshSummary:
    """Read mesh metadata without making the rest of the pipeline depend on one backend."""
    extension = path.suffix.lower()
    if extension not in SUPPORTED_MESH_EXTENSIONS:
        raise ValueError(f"Unsupported mesh format: {extension or 'missing extension'}")
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        import trimesh
    except ImportError:
        return MeshSummary(
            filename=path.name,
            extension=extension,
            vertices=None,
            faces=None,
            bounds=None,
            watertight=None,
            backend="metadata-only (install .[mesh] for Trimesh)",
        )

    loaded = trimesh.load(path, force="mesh")
    mesh = loaded.dump(concatenate=True) if isinstance(loaded, trimesh.Scene) else loaded
    return MeshSummary(
        filename=path.name,
        extension=extension,
        vertices=len(mesh.vertices),
        faces=len(mesh.faces),
        bounds=mesh.bounds.tolist(),
        watertight=bool(mesh.is_watertight),
        backend="trimesh",
    )


def run_pipeline(
    path: Path,
    job_id: str,
    rules: EngineeringRules | None = None,
) -> PipelineResult:
    source = inspect_mesh(path)
    try:
        geometry = analyze_mesh(path, rules)
    except RuntimeError:
        geometry = None
    return PipelineResult(
        job_id=job_id,
        source=source,
        geometry=geometry,
        completed_stages=[Stage.INGESTION, Stage.PREPROCESSING]
        + ([Stage.VALIDATION] if geometry is not None else []),
        pending_stages=[Stage.DETECTION, Stage.MAPPING, Stage.REPORTING],
    )


def as_dict(result: PipelineResult) -> dict[str, Any]:
    return {
        "job_id": result.job_id,
        "source": {
            "filename": result.source.filename,
            "extension": result.source.extension,
            "vertices": result.source.vertices,
            "faces": result.source.faces,
            "bounds": result.source.bounds,
            "watertight": result.source.watertight,
            "backend": result.source.backend,
        },
        "geometry": geometry_as_dict(result.geometry),
        "completed_stages": [stage.value for stage in result.completed_stages],
        "pending_stages": [stage.value for stage in result.pending_stages],
    }
