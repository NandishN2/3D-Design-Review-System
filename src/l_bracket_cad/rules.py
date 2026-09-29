from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EngineeringRules:
    require_watertight: bool = True
    minimum_dimension: float = 0.001
    bend_target_degrees: float = 90.0
    bend_tolerance_degrees: float = 2.0
    minimum_opening_length: float | None = None
    maximum_opening_length: float | None = None
    minimum_opening_width: float | None = None
    maximum_opening_width: float | None = None
    minimum_edge_clearance: float | None = None

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> EngineeringRules:
        if not values:
            return cls()
        return cls(**{key: value for key, value in values.items() if hasattr(cls, key)})


def _finding(rule: str, status: str, severity: str, message: str) -> dict[str, str]:
    return {"rule": rule, "status": status, "severity": severity, "message": message}


def evaluate_rules(analysis: Any, rules: EngineeringRules) -> list[dict[str, str]]:
    findings = [
        _finding(
            "positive_dimensions",
            "pass"
            if all(value >= rules.minimum_dimension for value in analysis.dimensions)
            else "fail",
            "high",
            f"All dimensions must be at least {rules.minimum_dimension:g}.",
        )
    ]
    if rules.require_watertight:
        findings.append(
            _finding(
                "watertight_mesh",
                "pass" if analysis.watertight else "fail",
                "high",
                "Mesh must be closed for reliable solid measurements.",
            )
        )

    for angle in analysis.bend_angles:
        difference = abs(angle - rules.bend_target_degrees)
        findings.append(
            _finding(
                "bend_angle",
                "pass" if difference <= rules.bend_tolerance_degrees else "fail",
                "medium",
                f"Measured bend angle {angle:.2f} degrees; target is "
                f"{rules.bend_target_degrees:g} +/- "
                f"{rules.bend_tolerance_degrees:g} degrees.",
            )
        )

    opening_rules_enabled = any(
        value is not None
        for value in (
            rules.minimum_opening_length,
            rules.maximum_opening_length,
            rules.minimum_opening_width,
            rules.maximum_opening_width,
        )
    )
    if opening_rules_enabled:
        for opening in analysis.openings:
            minimum_length_ok = (
                rules.minimum_opening_length is None
                or opening.length >= rules.minimum_opening_length
            )
            maximum_length_ok = (
                rules.maximum_opening_length is None
                or opening.length <= rules.maximum_opening_length
            )
            minimum_width_ok = (
                rules.minimum_opening_width is None
                or opening.width >= rules.minimum_opening_width
            )
            maximum_width_ok = (
                rules.maximum_opening_width is None
                or opening.width <= rules.maximum_opening_width
            )
            findings.append(
                _finding(
                    "opening_size",
                    "pass"
                    if all(
                        (
                            minimum_length_ok,
                            maximum_length_ok,
                            minimum_width_ok,
                            maximum_width_ok,
                        )
                    )
                    else "fail",
                    "high",
                    f"Opening is {opening.length:.2f} long and {opening.width:.2f} wide.",
                )
            )
        if not analysis.openings:
            findings.append(
                _finding(
                    "opening_size",
                    "not_evaluated",
                    "medium",
                    "No opening boundaries were confidently extracted from the mesh.",
                )
            )

    if rules.minimum_edge_clearance is not None:
        for opening in analysis.openings:
            clearance = opening.edge_clearance
            findings.append(
                _finding(
                    "edge_clearance",
                    "pass"
                    if clearance is not None and clearance >= rules.minimum_edge_clearance
                    else "fail",
                    "high",
                    f"Opening edge clearance is {clearance:.2f}."
                    if clearance is not None
                    else "Opening edge clearance could not be measured.",
                )
            )
        if not analysis.openings:
            findings.append(
                _finding(
                    "edge_clearance",
                    "not_evaluated",
                    "medium",
                    "No opening boundaries were confidently extracted from the mesh.",
                )
            )
    return findings
