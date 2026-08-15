# BioLead Dermatology Reference Standard

Scope: **skin disease only**.

## Presentation statement

> Because no universal gold standard exists for therapeutic target causality, we constructed a high-confidence dermatology reference standard using independent, externally curated evidence sources and strict concordance rules.

## Why this exists

Open Targets itself notes that the lack of appropriate gold standards across therapeutic areas limits benchmarking. BioLead does **not** invent expert labels for thousands of cases. It builds a **dermatology reference standard** from external curated evidence with concordance rules, and treats non-concordant cases as `unresolved`.

## Scope

Included: atopic eczema/dermatitis, psoriasis, acne, alopecia areata, vitiligo, rosacea, urticaria, hidradenitis, bullous disease, contact/seborrheic dermatitis, lichen planus, prurigo, ichthyosis, EB, keloid, cutaneous cancers, cutaneous lupus, dermatomyositis, scleroderma/morphea, and closely related derm indications.

Excluded: asthma, IBD, diabetes, CAD, CNS, non-skin cancers, rheumatoid arthritis, and other non-dermatology areas.

## Labels

| Label | Meaning | Used in pos/neg eval? |
| --- | --- | --- |
| `driver` | High-confidence causal / therapeutic driver | Yes |
| `non_driver` | High-confidence not a causal driver (correlative-only) | Yes |
| `unresolved` | Insufficient concordance | **No** |

## Concordance rules (v1.1)

**DRIVER** (any one):
1. clinical ≥ 0.80 **and** genetics ≥ 0.40
2. clinical ≥ 0.90 **and** overall ≥ 0.60 **and** max(genetics, animal, pathway) ≥ 0.25
3. genetics ≥ 0.75 **and** clinical ≥ 0.50
4. genetics ≥ 0.80 **and** animal ≥ 0.55 **and** overall ≥ 0.60

**NON-DRIVER** (any one):
1. correlative (expression/literature) ≥ 0.50 **and** max(genetics, clinical, animal, somatic) < 0.20
2. literature ≥ 0.60 with negligible genetics/clinical/animal pillars

**UNRESOLVED**: everything else.

Open Targets disease IDs are resolved via search (MONDO/EFO). Clinical evidence uses Platform `clinical` / `clinical_precedence` scores.

## Corpus

- File: `fixtures/reference_standard_v1.json`
- Target size: **1000** dermatology target–disease pairs
- Primary source: Open Targets Platform GraphQL
- AD clinical seed anchors: IL4R, IL13, JAK1

## Rebuild

```bash
cd services/api
.\.venv\Scripts\python scripts\build_reference_standard.py --target-n 1000 --per-disease 55
```

## BioLead evaluation on high-confidence labels

Run:

```bash
cd services/api
.\.venv\Scripts\python scripts\run_reference_eval.py --concurrency 8
```

Output: `fixtures/reference_eval_report.json`

### Imbalance handling
Gold labels are driver-heavy (~2:1). The report therefore includes:
1. **Macro-F1** (class-averaged; not micro-averaged)
2. A **balanced undersampled subset** (equal n per class)
3. Separate abstention metrics so majority-class volume cannot inflate the headline

### Metric policy
- `driver` ↔ BioLead `Driver`
- `non_driver` ↔ BioLead `Passenger`
- `Insufficient evidence` = abstention (reported separately; also shown as miss in the strict view)

