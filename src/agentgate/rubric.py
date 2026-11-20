"""Rubric loading, validation and weighted scoring."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

JUDGE_TYPES = ("hard_rule", "human_review", "llm_judge")

# Report metric names differ slightly from business-facing rubric names.
METRIC_ALIASES = {
    "fence_compliance": "fence_interception",
    "red_line_compliance": "fence_interception",
    "false_block": "false_block_rate",
    "rule_accuracy": "route_accuracy",
}


class RubricDimension(BaseModel):
    name: str
    weight: float
    judge_type: str
    metric: str
    target: Optional[float] = None
    gate: Optional[float] = None
    direction: str = "higher_is_better"


class Rubric(BaseModel):
    rubric_id: str
    paradigm: str
    pass_threshold: float
    owner: str = ""
    dimensions: List[RubricDimension]


class RubricValidationError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


class DimensionResult(BaseModel):
    name: str
    metric: str
    weight: float
    value: Optional[float] = None
    score: Optional[float] = None
    target: Optional[float] = None
    gate: Optional[float] = None
    gate_passed: Optional[bool] = None
    direction: str
    missing: bool = False


class RubricResult(BaseModel):
    rubric_id: str
    weighted_score: float
    pass_threshold: float
    gate_passed: bool
    passed: bool
    missing_metrics: List[str] = Field(default_factory=list)
    dimensions: List[DimensionResult]


def validate_rubric(rubric: Rubric) -> None:
    errors: List[str] = []

    total = sum(d.weight for d in rubric.dimensions)
    if abs(total - 1.0) > 1e-6:
        errors.append(f"weights must sum to 1.0, got {total}")

    if not 0 <= rubric.pass_threshold <= 1:
        errors.append("pass_threshold must be within 0..1")

    if not any(d.judge_type == "hard_rule" for d in rubric.dimensions):
        errors.append("at least one hard_rule dimension is required")

    names = [d.name for d in rubric.dimensions]
    if len(set(names)) != len(names):
        errors.append("dimension names must be unique")

    for dim in rubric.dimensions:
        if dim.judge_type not in JUDGE_TYPES:
            errors.append(f"invalid judge_type: {dim.judge_type}")
        if dim.weight < 0:
            errors.append(f"negative weight: {dim.name}")
        if dim.direction not in ("higher_is_better", "lower_is_better"):
            errors.append(f"invalid direction: {dim.direction}")

    if errors:
        raise RubricValidationError(errors)


def load_rubric(path: str) -> Rubric:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rubric = Rubric(**data)
    validate_rubric(rubric)
    return rubric


def _normalise(value: float, dimension: RubricDimension) -> float:
    if dimension.direction == "lower_is_better":
        if dimension.target is None or dimension.target <= 0:
            return max(0.0, min(1.0, 1.0 - value))
        return max(0.0, min(1.0, 1.0 - value / dimension.target))

    if dimension.target is None or dimension.target <= 0:
        return max(0.0, min(1.0, value))
    return max(0.0, min(1.0, value / dimension.target))


def score_rubric(rubric: Rubric, metrics: Dict[str, Any]) -> RubricResult:
    dimensions: List[DimensionResult] = []
    missing: List[str] = []
    weighted = 0.0
    total_weight = 0.0
    gate_passed = True

    for dim in rubric.dimensions:
        metric_name = METRIC_ALIASES.get(dim.metric, dim.metric)
        raw = metrics.get(metric_name)

        if raw is None:
            missing.append(metric_name)
            dimensions.append(
                DimensionResult(
                    name=dim.name,
                    metric=metric_name,
                    weight=dim.weight,
                    target=dim.target,
                    gate=dim.gate,
                    direction=dim.direction,
                    missing=True,
                )
            )
            continue

        value = float(raw)
        score = _normalise(value, dim)

        dim_gate: Optional[bool] = None
        if dim.gate is not None:
            if dim.direction == "lower_is_better":
                dim_gate = value <= dim.gate
            else:
                dim_gate = value >= dim.gate
            gate_passed = gate_passed and dim_gate

        weighted += dim.weight * score
        total_weight += dim.weight
        dimensions.append(
            DimensionResult(
                name=dim.name,
                metric=metric_name,
                weight=dim.weight,
                value=value,
                score=score,
                target=dim.target,
                gate=dim.gate,
                gate_passed=dim_gate,
                direction=dim.direction,
            )
        )

    weighted_score = weighted / total_weight if total_weight else 0.0
    passed = gate_passed and weighted_score >= rubric.pass_threshold

    return RubricResult(
        rubric_id=rubric.rubric_id,
        weighted_score=weighted_score,
        pass_threshold=rubric.pass_threshold,
        gate_passed=gate_passed,
        passed=passed,
        missing_metrics=missing,
        dimensions=dimensions,
    )
