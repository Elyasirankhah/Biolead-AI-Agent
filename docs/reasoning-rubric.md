# BioLead Reasoning Rubric v1.1.0

## Goal
Classify a gene–disease pair as **Driver**, **Passenger**, or **Insufficient evidence** for dermatology research prioritization. Research-use-only.

## Causal reasoning stance
BioLead is a **causal-inference agent**, not a literature reader.
Each verdict is anchored to a causal chain:

```
Variant  →  Gene expression / function  →  Disease phenotype  →  Clinical rescue
```

Each evidence pillar corresponds to an edge in that chain:

| Chain edge | Strongest pillar | Meaning |
| --- | --- | --- |
| Variant → Gene | Mendelian randomization, Colocalization | Genetic instrument identifies the causal gene, not a neighbor |
| Gene → Disease | Human genetics, Causal perturbation | LoF/GoF or CRISPR-style intervention changes phenotype |
| Gene → Clinical rescue | Clinical pharmacology | Target-engaging therapy improves disease |
| Mechanism edge | Mechanistic coherence | Explains *how* in disease-relevant tissue |

Signal = agreement across multiple edges. Noise = association on a single edge only (expression, co-mention).

## Score dimensions
Keep these separate until the final policy step:

| Dimension | Meaning |
| --- | --- |
| Causality | Strength of causal / near-causal support after penalties |
| Actionability | Evidence that intervention can change disease phenotype |
| Evidence quality | Directness, source quality, tissue relevance |

## Evidence hierarchy (weights, v1.1.0)
1. Mendelian randomization — 30
2. Colocalization — 26
3. Human genetics — 22
4. Causal perturbation — 22
5. Clinical / pharmacology — 20
6. Mechanistic coherence — 12
7. Differential expression — 6
8. Literature co-mention — 4

Mendelian randomization and colocalization sit at the top because they *identify* the causal gene from a variant signal; they are what turns a locus into a target.

## Quality multipliers
- High = 1.0
- Moderate = 0.7
- Low = 0.4

Tissue mismatch multiplies strength by 0.55. Within a category, additional supporting items diminish (`0.55^n`) so paper volume cannot masquerade as independent proof.

## Contradictions
Supporting and contradicting items are both retained. Contradictions reduce causality and actionability. Expression-only association without causal rescue is not enough for Driver.

## Decision policy
1. **Passenger** if correlational signal exists, causality < 32, quality ≥ 45, and causal counter-evidence is present.
2. **Insufficient evidence** if quality < 35 or fewer than two independent causal pillars.
3. **Driver** if causality ≥ 58 and at least two independent causal pillars.
4. Otherwise **Insufficient evidence**.

Missing evidence means abstain, not Passenger.

## Ensemble policy
The final verdict is the merge of three votes:

1. Deterministic rubric (always votes)
2. LLM advocate (grounded)
3. LLM falsifier (grounded)

When `ENSEMBLE_REQUIRED=true` (default), both LLM voters must return grounded traces or the result abstains. LLM votes cannot invent Driver without meeting the same scientific thresholds; disagreement collapses to Insufficient.

## Seeded benchmark expectations
| Gene | Disease | Expected |
| --- | --- | --- |
| IL4R | Atopic dermatitis | Driver |
| FLG | Atopic dermatitis | Insufficient evidence |
| S100A8 | Atopic dermatitis | Passenger |
