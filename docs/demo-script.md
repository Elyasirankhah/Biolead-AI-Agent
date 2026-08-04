# BioLead 5-Minute Demo Script

## Setup
1. `docker compose up --build` **or**
   - API: `uvicorn app.main:app --reload --port 8000`
   - Web: `npm run dev` in `apps/web`
2. Open `http://localhost:3000`
3. Keep mode on **Demo** for a reproducible walkthrough.

## Story (one disease, three genes)
Disease: **Atopic dermatitis**  
Candidates: **IL4R**, **FLG**, **S100A8**

### Minute 0–1 — Frame the problem
“In derm discovery, genes that look hot in inflamed skin are often passengers. BioLead is a decision workbench that separates drivers from passengers with auditable evidence—not a chatbot summary.”

### Minute 1–2 — Run the comparison
Click **Run analysis**. Walk the pipeline stages. Point to the three candidates with distinct outcomes.

### Minute 2–3 — Driver: IL4R
Open IL4R. Show:
- Verdict **Driver**
- Convergent pillars: genetics, perturbation, clinical, mechanism
- Dupilumab clinical evidence with PMID link
- Direction: **inhibit**

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

### Minute 4:30–5 — Audit + scale-out
1. Expand evidence links / export JSON dossier.
2. Mention scoring policy version and falsification case.
3. Close with deploy map: **Next.js workbench + FastAPI evidence API (AWS ECS/ALB sketch in docs/infra).**

## Backup if APIs fail
Stay in Demo mode. Offline seeded fixtures are the golden path for the presentation.
