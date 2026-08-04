# BioLead Model Card

## Intended use
Research-use-only prioritization aid for dermatology target triage. Helps scientists compare whether a gene looks more like a causal driver, a disease-state passenger, or an under-evidenced candidate.

## Out of scope
- Clinical decision support
- Diagnosis or treatment recommendations
- Claiming experimental validation from literature alone

## System design
1. Collect structured evidence from Open Targets, Europe PMC, and GWAS Catalog (live mode), or curated fixtures (demo mode).
2. Score with a deterministic rubric (`scoring.py`, versioned).
3. Optionally use an LLM only to write advocate / falsifier narratives.
4. Ground LLM claim lists to known evidence IDs before display.

## Training data
BioLead does not train a custom biological model. Public scientific APIs and curated fixtures supply evidence. Optional LLM providers use their own foundation models.

## Evaluation
- Unit tests for Driver / Passenger / Insufficient cases
- Citation-grounding tests for LLM narrative filtering
- Playwright golden-path UI test for the seeded comparison

## Known limitations
- Public APIs vary in recency, ancestry coverage, and tissue relevance
- Nearest-gene GWAS mapping is low-tier and not treated as causal assignment
- Literature co-mentions are heavily down-weighted
- Absence of a public result is not proof that no evidence exists

## Runtime
- Next.js workbench (`apps/web`)
- FastAPI evidence service (`services/api`), optional MongoDB and LLM

## Contact / ownership
Research prototype.
