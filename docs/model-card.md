# BioLead Model Card

## Intended use
Research-use-only prioritization aid for dermatology target triage. Helps scientists compare whether a gene looks more like a causal driver, a disease-state passenger, or an under-evidenced candidate.

## Out of scope
- Clinical decision support
- Diagnosis or treatment recommendations
- Claiming experimental validation from literature alone

## System design
1. Collect structured evidence from Open Targets, Europe PMC, and GWAS Catalog (live mode), or curated fixtures (demo mode).
2. Score with a deterministic rubric (`scoring.py`, version `1.0.0`).
3. Demo mode skips LLM calls and uses the frozen deterministic decision path.
4. Live mode can add grounded advocate/falsifier votes and narratives; missing or
   conflicting required voters force abstention rather than upgrading weak evidence.
5. Ground LLM evidence IDs and claim lists to accepted evidence before display.

## Training data
BioLead does not train a custom biological model. Public scientific APIs and curated fixtures supply evidence. Optional LLM providers use their own foundation models.

## Evaluation
- Unit tests for Driver / Passenger / Insufficient cases
- Citation-grounding tests for LLM narrative filtering
- Playwright golden-path UI test for the seeded comparison
- Golden corpus eval (`app/eval.py` → `fixtures/golden_eval_report.json`):
  provenance coverage, contradiction recall, verdict determinism, abstention,
  duplicate inflation, citation link integrity — all scoped to the curated demo corpus
- Frozen presentation snapshots: `fixtures/demo_golden_snapshots.json`
- External reference standard (`fixtures/reference_standard_v1.json`, ~1000 pairs):
  high-confidence DRIVER / NON-DRIVER labels from Open Targets concordance rules;
  UNRESOLVED held out of pos/neg evaluation to reduce label noise
  (see `docs/reference-standard.md`)

## Known limitations
- Public APIs vary in recency, ancestry coverage, and tissue relevance
- Nearest-gene GWAS mapping is low-tier and not treated as causal assignment
- Literature co-mentions are heavily down-weighted
- Absence of a public result is not proof that no evidence exists

## Deployment split
- **Vercel:** Next.js workbench
- **AWS:** FastAPI evidence service, async workers, storage, Bedrock (optional)

## Contact / ownership
BioLead Evidence Workbench.
