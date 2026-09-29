# L-Bracket CAD workspace instructions

- Keep the pipeline stages explicit: ingestion, preprocessing, rendering, detection, mapping, validation, and reporting.
- Prefer small typed Python modules and test behavior at stage boundaries.
- Optional 3D, vision, and retrieval dependencies must remain optional so the core API can run in a clean environment.
- Keep downloaded datasets and generated outputs outside source control.
