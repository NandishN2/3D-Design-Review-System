from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .rules import EngineeringRules, evaluate_rules


@dataclass(frozen=True)
class RuleResult:
    rule: str
    status: str
    severity: str
    message: str


@dataclass(frozen=True)
class PlateFeature:
    area: float
    normal: list[float]
    face_count: int


@dataclass(frozen=True)
class OpeningFeature:
    center: list[float]
    shape: str
    length: float
    width: float
    edge_clearance: float | None
    confidence: float
    method: str


@dataclass(frozen=True)
class GeometryAnalysis:
    dimensions: list[float] | None
    surface_area: float | None
    volume: float | None
    watertight: bool | None
    backend: str
    plates: list[PlateFeature] = field(default_factory=list)
    bend_angles: list[float] = field(default_factory=list)
    openings: list[OpeningFeature] = field(default_factory=list)
    rule_results: list[dict[str, str]] = field(default_factory=list)


def _load_mesh(path: Path) -> Any:
    try:
        import trimesh
    except ImportError as error:
        raise RuntimeError("Install Trimesh with: python -m pip install trimesh") from error

    loaded = trimesh.load(path, force="mesh")
    return loaded.dump(concatenate=True) if isinstance(loaded, trimesh.Scene) else loaded


def _face_groups(mesh: Any, tolerance: float = 0.01) -> list[list[int]]:
    parent = list(range(len(mesh.faces)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for (left, right), angle in zip(mesh.face_adjacency, mesh.face_adjacency_angles):
        if angle <= tolerance:
            union(int(left), int(right))
    groups: dict[int, list[int]] = {}
    for face_index in range(len(mesh.faces)):
        groups.setdefault(find(face_index), []).append(face_index)
    return list(groups.values())


def _plate_features(mesh: Any) -> list[PlateFeature]:
    features = []
    for faces in _face_groups(mesh):
        area = float(mesh.area_faces[faces].sum())
        normal = mesh.face_normals[faces].mean(axis=0)
        length = float((normal**2).sum() ** 0.5)
        if length and area > 0:
            features.append(PlateFeature(area, (normal / length).tolist(), len(faces)))
    return sorted(features, key=lambda feature: feature.area, reverse=True)


def _bend_angles(plates: list[PlateFeature]) -> list[float]:
    import numpy as np

    if not plates:
        return []
    dominant_area = plates[0].area * 0.5
    dominant = [plate for plate in plates if plate.area >= dominant_area]
    orientations: list[PlateFeature] = []
    for plate in dominant:
        duplicate = any(
            abs(float(np.dot(plate.normal, existing.normal))) > 0.996
            for existing in orientations
        )
        if duplicate:
            continue
        orientations.append(plate)

    angles = []
    for index, first in enumerate(orientations):
        for second in orientations[index + 1 :]:
            cosine = abs(float(np.dot(first.normal, second.normal)))
            angle = float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
            if 1.0 < angle < 179.0:
                angles.append(angle)
    return sorted(set(round(angle, 4) for angle in angles))


def _ordered_loop(component: set[int], graph: dict[int, set[int]]) -> list[int]:
    start = min(component)
    ordered = [start]
    previous = None
    current = start
    while True:
        choices = [neighbor for neighbor in graph[current] if neighbor != previous]
        next_vertex = choices[0]
        if next_vertex == start:
            return ordered
        ordered.append(next_vertex)
        previous, current = current, next_vertex


def _classify_opening(projected: Any, length: float, width: float) -> str:
    import numpy as np

    vertex_count = len(projected)
    if vertex_count == 3:
        return "triangular_opening"
    if vertex_count == 4:
        edges = np.roll(projected, -1, axis=0) - projected
        edge_lengths = np.linalg.norm(edges, axis=1)
        corners = []
        for index in range(4):
            incoming = -edges[index - 1] / edge_lengths[index - 1]
            outgoing = edges[index] / edge_lengths[index]
            corners.append(np.degrees(np.arccos(np.clip(np.dot(incoming, outgoing), -1.0, 1.0))))
        if all(abs(angle - 90.0) <= 8.0 for angle in corners):
            return (
                "square_opening"
                if max(edge_lengths) / min(edge_lengths) <= 1.08
                else "rectangular_opening"
            )
        return "quadrilateral_opening"
    if vertex_count == 5:
        return "pentagonal_opening"
    if vertex_count == 6:
        return "hexagonal_opening"

    center = projected.mean(axis=0)
    radii = np.linalg.norm(projected - center, axis=1)
    radial_variation = float(np.std(radii) / max(np.mean(radii), 1e-9))
    if length / max(width, 1e-9) >= 1.2:
        return "obround_slot"
    if radial_variation <= 0.08:
        return "circular_opening"
    return "polygonal_opening"


def _opening_candidates(mesh: Any) -> list[OpeningFeature]:
    """Measure inner boundary loops on sufficiently large planar mesh faces."""
    import numpy as np

    groups = _face_groups(mesh)
    candidates: list[OpeningFeature] = []
    for faces in groups:
        if mesh.area_faces[faces].sum() < mesh.area * 0.08:
            continue
        edge_counts: Counter[tuple[int, int]] = Counter()
        for face_index in faces:
            face = mesh.faces[face_index]
            for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                edge_counts[tuple(sorted((int(first), int(second))))] += 1
        boundary_edges = [edge for edge, count in edge_counts.items() if count == 1]
        graph: dict[int, set[int]] = defaultdict(set)
        for first, second in boundary_edges:
            graph[first].add(second)
            graph[second].add(first)
        components: list[set[int]] = []
        unseen = set(graph)
        while unseen:
            stack = [unseen.pop()]
            component = set(stack)
            while stack:
                vertex = stack.pop()
                for neighbor in graph[vertex]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        component.add(neighbor)
                        stack.append(neighbor)
            components.append(component)
        if len(components) < 2 or any(len(graph[vertex]) != 2 for vertex in graph):
            continue

        loops = []
        for component in components:
            ordered = _ordered_loop(component, graph)
            points = mesh.vertices[ordered]
            center = points.mean(axis=0)
            _, _, basis = np.linalg.svd(points - center)
            projected = (points - center) @ basis[:2].T
            area = abs(
                float(
                    np.dot(projected[:, 0], np.roll(projected[:, 1], -1))
                    - np.dot(projected[:, 1], np.roll(projected[:, 0], -1))
                )
                / 2
            )
            loops.append((area, ordered, projected, center, basis))

        outer_area = max(loop[0] for loop in loops)
        outer_loop = max(loops, key=lambda loop: loop[0])
        for area, ordered, projected, center, basis in loops:
            if area >= outer_area * 0.5 or len(ordered) < 4:
                continue
            _, _, principal = np.linalg.svd(projected, full_matrices=False)
            oriented = projected @ principal[:2].T
            extents = oriented.max(axis=0) - oriented.min(axis=0)
            length, width = sorted((float(extents[0]), float(extents[1])), reverse=True)
            if width <= 0:
                continue
            outer_points = mesh.vertices[outer_loop[1]]
            outer_projected = (outer_points - center) @ basis[:2].T
            distances = []
            for index, point in enumerate(outer_projected):
                next_point = outer_projected[(index + 1) % len(outer_projected)]
                segment = next_point - point
                length_squared = float(np.dot(segment, segment))
                position = 0.0
                if length_squared:
                    position = float(np.clip(-np.dot(point, segment) / length_squared, 0.0, 1.0))
                closest = point + position * segment
                distances.append(float(np.linalg.norm(closest)))
            candidates.append(
                OpeningFeature(
                    center=center.tolist(),
                    shape=_classify_opening(projected, length, width),
                    length=length,
                    width=width,
                    edge_clearance=max(min(distances) - width / 2, 0.0),
                    confidence=0.95 if len(ordered) <= 6 else 0.9,
                    method="planar inner-boundary loop",
                )
            )

    unique: list[OpeningFeature] = []
    for candidate in candidates:
        if candidate.shape == "circular_opening" and any(
            existing.shape == "circular_opening"
            and (
                _same_center(candidate.center, existing.center)
                or _same_circular_axis(
                    candidate.center,
                    existing.center,
                    max(candidate.length, existing.length),
                )
            )
            for existing in unique
        ):
            continue
        if any(
            np.linalg.norm(np.array(candidate.center) - np.array(existing.center)) < 3.0
            and abs(candidate.length - existing.length) < 1.0
            and abs(candidate.width - existing.width) < 1.0
            for existing in unique
        ):
            continue
        unique.append(candidate)
    return unique


def _same_center(first: list[float], second: list[float]) -> bool:
    return all(abs(left - right) < 1.0 for left, right in zip(first, second))


def _same_circular_axis(
    first: list[float], second: list[float], opening_size: float
) -> bool:
    differences = [abs(left - right) for left, right in zip(first, second)]
    aligned_axes = [index for index, difference in enumerate(differences) if difference < 1.0]
    separated_axes = [
        index for index, difference in enumerate(differences) if difference >= 1.0
    ]
    if len(aligned_axes) != 2 or len(separated_axes) != 1:
        return False
    axis = separated_axes[0]
    return differences[axis] <= opening_size


def analyze_mesh(path: Path, rules: EngineeringRules | None = None) -> GeometryAnalysis:
    """Measure geometry available directly from a mesh and apply conservative rules."""
    mesh = _load_mesh(path)
    dimensions = [float(value) for value in mesh.extents]
    watertight = bool(mesh.is_watertight)
    volume = float(abs(mesh.volume)) if watertight else None
    plates = _plate_features(mesh)
    bend_angles = _bend_angles(plates)
    openings = _opening_candidates(mesh)
    effective_rules = rules or EngineeringRules()
    provisional = GeometryAnalysis(
        dimensions=dimensions,
        surface_area=float(mesh.area),
        volume=volume,
        watertight=watertight,
        plates=plates,
        bend_angles=bend_angles,
        openings=openings,
        backend="trimesh",
    )
    return GeometryAnalysis(
        dimensions=dimensions,
        surface_area=float(mesh.area),
        volume=volume,
        watertight=watertight,
        plates=plates,
        bend_angles=bend_angles,
        openings=openings,
        rule_results=evaluate_rules(provisional, effective_rules),
        backend="trimesh",
    )


def as_dict(analysis: GeometryAnalysis | None) -> dict[str, Any] | None:
    if analysis is None:
        return None
    shape_counts: dict[str, int] = {}
    for opening in analysis.openings:
        shape_counts[opening.shape] = shape_counts.get(opening.shape, 0) + 1
    reported_plates = analysis.plates[:50]
    return {
        "dimensions": analysis.dimensions,
        "surface_area": analysis.surface_area,
        "volume": analysis.volume,
        "watertight": analysis.watertight,
        "plates": [asdict(plate) for plate in reported_plates],
        "plate_count": len(analysis.plates),
        "plates_truncated": len(analysis.plates) > len(reported_plates),
        "bend_angles": analysis.bend_angles,
        "openings": [asdict(opening) for opening in analysis.openings],
        "feature_counts": shape_counts,
        "rule_results": analysis.rule_results,
        "backend": analysis.backend,
    }
