# BioLead golden eval metrics

Scoped to the **curated demo corpus** (IL4R / FLG / S100A8 for atopic dermatitis).  
These are presentation reliability metrics — not a claim that open-world biomedical extraction is 100% accurate.

## How to run

```bash
cd services/api
python scripts/run_golden_eval.py
# or
pytest tests/test_golden_eval.py -q
```

Outputs:
- `fixtures/golden_eval_report.json`
- `fixtures/demo_golden_snapshots.json` (frozen snapshot IDs)

## Acceptance criteria

| Metric | Acceptance |
|--------|------------|
| Provenance coverage | 100% of accepted demo evidence has valid provenance |
| Grounded-decision coverage | Driver rests only on provenance-qualified evidence + falsification PASSED |
| Verdict determinism | Identical snapshot → identical hash/verdict |
| Known contradiction recall | 100% on curated contradiction set |
| Polarity accuracy | IL4R Driver · S100A8 Passenger · FLG Insufficient |
| Entity grounding | 100% demo items gene-grounded |
| Duplicate-study inflation | 0 duplicate `independent_key`s per gene |
| Abstention test | Empty + FLG abstain |
| Citation link integrity | 0 malformed or placeholder URLs in core demo |
| Core-demo network dependency | 0 |

## Product line for the deck

> No causal verdict until we try to prove ourselves wrong.
