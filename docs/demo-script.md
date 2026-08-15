# BioLead 5-Minute Demo Script

## Setup
1. `docker compose up --build` **or**
   - API: `uvicorn app.main:app --reload --port 8000`
   - Web: `npm run dev` in `apps/web`
2. Open `http://localhost:3000`
3. Keep mode on **Demo** for a reproducible walkthrough.
4. Optional pre-check: `cd services/api && python scripts/run_golden_eval.py`

## Story (one disease, three genes)
Disease: **Atopic dermatitis**  
Candidates: **IL4R**, **FLG**, **S100A8**  
Frozen snapshots: `fixtures/demo_golden_snapshots.json`

### Minute 0–1 — Frame the problem
“In derm discovery, genes that look hot in inflamed skin are often passengers. BioLead is a decision workbench that separates drivers from passengers with auditable evidence—not a chatbot summary.”

**Anchor line:** “No causal verdict until we try to prove ourselves wrong.”

### Minute 1–2 — Run the comparison
Click **Run analysis**. Walk the pipeline stages. Point to the three candidates with distinct outcomes. Open the **Causal Decision Ledger**.

### Minute 2–3 — Driver: IL4R
Open IL4R. Show:
- Verdict **Driver**
- Falsification **PASSED** (counter-hypotheses were checked)
- Convergent pillars: genetics, perturbation, clinical, mechanism
- Dupilumab clinical evidence with PMID link
- Direction: **inhibit**
- Snapshot ID (reproducible)

### Minute 3–4 — Passenger: S100A8
Switch to S100A8. Show:
- Strong expression / association
- Explicit counter-evidence: no rescue, no causal genetics
- Verdict **Passenger**, not “interesting”

### Minute 4–4:30 — Abstain: FLG
Switch to FLG. Show:
- Strong human genetics + barrier biology
- Low actionability → **Insufficient evidence**
- “Causal relevance and tractable intervention are different questions.”

### Minute 4:30–5 — Audit + close
1. Expand evidence links / export JSON dossier.
2. Mention that **Live mode** supports scientist feedback (wrong direction / irrelevant / important → re-run). Demo stays immutable.
3. Close: LLM extracts; deterministic rules decide; snapshot is versioned.

## Backup if APIs fail
Stay in Demo mode. Offline seeded fixtures are the golden path for the presentation.  
Full rehearsal checklist: [presentation-rehearsal.md](presentation-rehearsal.md)
