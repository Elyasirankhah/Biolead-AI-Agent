from app.reference_standard import eval_ready_pairs, load_reference_standard

# Import metric helpers from the eval script module path.
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_reference_eval.py"
_SPEC = importlib.util.spec_from_file_location("run_reference_eval", _SCRIPT)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)


def test_macro_f1_is_class_balanced_not_micro():
    rows = [
        {"gold_label": "driver", "biolead_verdict": "Driver"},
        {"gold_label": "driver", "biolead_verdict": "Driver"},
        {"gold_label": "driver", "biolead_verdict": "Driver"},
        {"gold_label": "non_driver", "biolead_verdict": "Passenger"},
        {"gold_label": "non_driver", "biolead_verdict": "Driver"},  # one miss
    ]
    metrics = _MOD.confusion_counts(rows, treat_abstain_as_negative=False)
    # Micro would overweight drivers; macro averages class F1s equally.
    assert metrics["driver"]["precision"] == 0.75
    assert metrics["driver"]["recall"] == 1.0
    assert metrics["non_driver"]["recall"] == 0.5
    assert metrics["macro_f1"] == round((metrics["driver"]["f1"] + metrics["non_driver"]["f1"]) / 2, 4)


def test_balanced_subsample_equalizes_classes():
    rows = (
        [{"gold_label": "driver", "biolead_verdict": "Driver", "i": i} for i in range(10)]
        + [{"gold_label": "non_driver", "biolead_verdict": "Passenger", "i": i} for i in range(4)]
    )
    balanced = _MOD.balanced_subsample(rows, seed=0)
    assert len(balanced) == 8
    assert sum(1 for r in balanced if r["gold_label"] == "driver") == 4
    assert sum(1 for r in balanced if r["gold_label"] == "non_driver") == 4


def test_abstention_tracked_separately():
    rows = [
        {"gold_label": "driver", "biolead_verdict": "Insufficient evidence"},
        {"gold_label": "non_driver", "biolead_verdict": "Passenger"},
    ]
    metrics = _MOD.confusion_counts(rows, treat_abstain_as_negative=False)
    assert metrics["n_abstain"] == 1
    assert metrics["abstention_rate"] == 0.5


def test_eval_ready_pool_is_imbalanced_as_expected():
    ready = eval_ready_pairs(load_reference_standard())
    drivers = sum(1 for p in ready if p["label"] == "driver")
    nondrivers = sum(1 for p in ready if p["label"] == "non_driver")
    assert drivers > nondrivers
    assert drivers + nondrivers == len(ready)
