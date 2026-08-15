from app.eval import freeze_demo_snapshots, run_golden_eval


def test_golden_eval_all_metrics_pass():
    report = run_golden_eval()
    failed = [m.name for m in report.metrics if not m.pass_]
    assert report.all_passed, f"failed metrics: {failed}"
    assert set(report.cases) == {"IL4R", "FLG", "S100A8"}
    assert report.cases["IL4R"]["verdict"] == "Driver"
    assert report.cases["FLG"]["verdict"] == "Insufficient evidence"
    assert report.cases["S100A8"]["verdict"] == "Passenger"


def test_frozen_demo_snapshots_are_stable():
    a = freeze_demo_snapshots()
    b = freeze_demo_snapshots()
    assert a["cases"]["IL4R"]["content_hash"] == b["cases"]["IL4R"]["content_hash"]
    assert a["cases"]["IL4R"]["snapshot_id"].startswith("BL-IL4R-")
    assert a["eval_all_passed"] is True
    for gene, row in a["cases"].items():
        assert row["verdict"] == row["expected_verdict"]
