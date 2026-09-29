from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .pipeline import as_dict, run_pipeline
from .rules import EngineeringRules

app = FastAPI(title="L-Bracket CAD", version="0.1.0")
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "l-bracket-cad"}


@app.post("/pipeline/jobs")
def create_job(
    file: UploadFile = File(...),
    rules_json: str | None = Form(
        default=None,
        description="Optional JSON rules, for example {\"minimum_dimension\": 3.0}",
    ),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".stl", ".obj", ".ply"}:
        raise HTTPException(status_code=415, detail="Upload an STL, OBJ, or PLY mesh")

    job_id = uuid.uuid4().hex
    destination = UPLOAD_DIR / f"{job_id}{suffix}"
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    try:
        rules = (
            None
            if not rules_json or rules_json.strip().lower() == "string"
            else EngineeringRules.from_dict(json.loads(rules_json))
        )
        return as_dict(run_pipeline(destination, job_id, rules))
    except json.JSONDecodeError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="rules_json must be valid JSON") from error
    except (FileNotFoundError, ValueError) as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(error)) from error

