"""Evaluate BioLead against the external reference standard (high-confidence labels only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "fixtures" / "reference_standard_v1.json"


def load_reference_standard(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def eval_ready_pairs(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        pair
        for pair in report.get("pairs", [])
        if pair.get("label") in {"driver", "non_driver"} and pair.get("confidence") == "high"
    ]


def summarize_reference_standard(path: Path | None = None) -> dict[str, Any]:
    report = load_reference_standard(path)
    ready = eval_ready_pairs(report)
    by_label = {"driver": 0, "non_driver": 0, "unresolved": 0}
    for pair in report.get("pairs", []):
        label = str(pair.get("label") or "unresolved")
        by_label[label] = by_label.get(label, 0) + 1
    return {
        "dataset": report.get("dataset"),
        "version": report.get("version"),
        "n_pairs": report.get("n_pairs"),
        "label_counts": by_label,
        "n_eval_ready_high_confidence": len(ready),
        "n_diseases": report.get("n_diseases"),
        "presentation_statement": report.get("presentation_statement"),
        "evaluation_policy": report.get("evaluation_policy"),
    }
