# L-Bracket CAD

A first working system for reviewing L-bracket CAD models. The project follows this staged path:

`CAD -> mesh preprocessing -> clean mesh -> geometry feature extraction -> geometry validation -> design review`

The later reporting path is reserved for `design result -> engineering documents -> ChromaDB/RAG -> LLM -> engineering report`.

## Quick start

Create a virtual environment and install the core package:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run the API:

```powershell
uvicorn l_bracket_cad.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive API. Run the basic test suite with `pytest`.

## Mesh support

Install the optional mesh stack when you are ready to process real models:

```powershell
python -m pip install -e ".[mesh]"
```

The current API accepts `.stl`, `.obj`, and `.ply` files. STEP support is intentionally a separate adapter because it requires a CAD kernel such as Open Cascade; the interface is reserved in `pipeline.py` so that CAD conversion does not leak into the rest of the pipeline.

## Engineering rules

The upload endpoint accepts an optional `rules_json` multipart field. For example:

```json
{
	"minimum_dimension": 3.0,
	"bend_target_degrees": 90.0,
	"bend_tolerance_degrees": 2.0,
	"minimum_opening_length": 8.0,
	"maximum_opening_length": 15.0,
	"minimum_opening_width": 4.0,
	"maximum_opening_width": 8.0,
	"minimum_edge_clearance": 5.0
}
```

The current deterministic extractor reports bounding-box dimensions, surface area, volume, dominant plate orientations, bend-angle candidates, and generalized planar openings such as obround slots. Opening rules are marked `not_evaluated` when the mesh does not provide a confident boundary loop.

## Dataset

The intended training source is the [Parametric Bracket Library](https://github.com/archimedes-market/parametric-bracket-library/). Keep downloaded data outside source control and place local experiments under `data/`.

## Current stage

Implemented:

- mesh upload and job creation
- mesh metadata extraction and basic cleanup
- geometry measurements and conservative watertightness/dimension rules
- configurable dimension, bend, opening-size, and edge-clearance rule evaluation
- direct 3D geometry analysis without an image-rendering dependency
- pipeline status endpoint
- CLI and tests

Planned next:

- STEP import through Open Cascade
- feature measurements for openings, plates, bends, and edge clearances
- YOLOv8 dataset conversion and inference
- camera-ray 2D-to-3D mapping
- bracket geometry rules and design-review findings
- engineering-document ingestion and RAG reports
