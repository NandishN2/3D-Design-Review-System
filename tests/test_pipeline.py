from pathlib import Path

from fastapi.testclient import TestClient

from l_bracket_cad.api import app
from l_bracket_cad.pipeline import Stage, inspect_mesh, run_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "triangle.stl"


def test_mesh_inspection_is_available_without_optional_backend() -> None:
    summary = inspect_mesh(FIXTURE)
    assert summary.extension == ".stl"
    assert summary.filename == "triangle.stl"
    assert summary.backend


def test_pipeline_keeps_later_stages_explicit() -> None:
    result = run_pipeline(FIXTURE, "test-job")
    assert result.completed_stages == [Stage.INGESTION, Stage.PREPROCESSING, Stage.VALIDATION]
    assert Stage.DETECTION in result.pending_stages
    assert Stage.VALIDATION not in result.pending_stages
    assert result.geometry is not None
    assert result.geometry.dimensions == [1.0, 1.0, 0.0]
    assert result.geometry.rule_results[1]["status"] == "fail"


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_upload_returns_geometry_analysis() -> None:
    with FIXTURE.open("rb") as mesh_file:
        response = TestClient(app).post(
            "/pipeline/jobs",
            files={"file": ("triangle.stl", mesh_file, "model/stl")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["geometry"]["dimensions"] == [1.0, 1.0, 0.0]
    assert payload["geometry"]["rule_results"][1]["rule"] == "watertight_mesh"


def test_upload_accepts_custom_rules() -> None:
    with FIXTURE.open("rb") as mesh_file:
        response = TestClient(app).post(
            "/pipeline/jobs",
            files={"file": ("triangle.stl", mesh_file, "model/stl")},
            data={"rules_json": '{"minimum_dimension": 2.0}'},
        )

    assert response.status_code == 200
    findings = response.json()["geometry"]["rule_results"]
    assert findings[0]["rule"] == "positive_dimensions"
    assert findings[0]["status"] == "fail"


def test_upload_accepts_swagger_placeholder_rules() -> None:
    with FIXTURE.open("rb") as mesh_file:
        response = TestClient(app).post(
            "/pipeline/jobs",
            files={"file": ("triangle.stl", mesh_file, "model/stl")},
            data={"rules_json": "string"},
        )

    assert response.status_code == 200


def test_circular_counterbores_count_as_physical_holes() -> None:
    model = Path("data/uploads/d87807b627064c05bb2d540b2b67b7e5.stl")
    if not model.exists():
        return

    with model.open("rb") as mesh_file:
        response = TestClient(app).post(
            "/pipeline/jobs",
            files={"file": ("bracket.stl", mesh_file, "model/stl")},
        )

    assert response.status_code == 200
    counts = response.json()["geometry"]["feature_counts"]
    assert counts["circular_opening"] == 2
    assert counts["rectangular_opening"] == 4
    assert counts["obround_slot"] == 2


def test_large_plate_lists_are_truncated_in_api_output() -> None:
    model = Path("data/uploads/82a451f757884d1ab1cec6add585a3a9.stl")
    if not model.exists():
        return

    with model.open("rb") as mesh_file:
        response = TestClient(app).post(
            "/pipeline/jobs",
            files={"file": ("complex.stl", mesh_file, "model/stl")},
        )

    geometry = response.json()["geometry"]
    assert response.status_code == 200
    assert len(geometry["plates"]) <= 50
    assert geometry["plates_truncated"] is True
    assert geometry["plate_count"] > 50


