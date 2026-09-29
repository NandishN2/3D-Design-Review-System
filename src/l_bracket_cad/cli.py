from __future__ import annotations

import json
from pathlib import Path

import typer

from .pipeline import as_dict, run_pipeline
from .rules import EngineeringRules

cli = typer.Typer(help="Run the L-Bracket CAD inspection pipeline.")


@cli.command()
def inspect(mesh: Path, rules_json: str | None = None) -> None:
    """Inspect a mesh and print its current pipeline status."""
    rules = EngineeringRules.from_dict(json.loads(rules_json)) if rules_json else None
    result = run_pipeline(mesh, mesh.stem, rules)
    typer.echo(as_dict(result))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
