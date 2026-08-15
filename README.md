# BioLead Evidence Workbench

BioLead is a causal gene-prioritization product for dermatology. It separates **Driver**, **Passenger**, and **Insufficient evidence** calls with a scored, citable dossier. Scientists submit a disease and genes; Clara oversees Retrieve → Extract → Score → Falsify → Decide, explains the dossier, and can take control of the next run — a close-pair rerun, a Live retrieve, a literature search, or a challenge to the current call.

**Live demo:** https://biolead-ai-agent-eight.vercel.app

Hosts: **Vercel** (workbench) · **Render** (API · https://biolead-ai-agent.onrender.com) · **Supabase** (sign-in)

Research use only — not clinical decision support.

## Clara — supervisor reasoning agent

Clara watches every part of the run and can act on it:

- **Sees** the disease, gene list, Demo/Live mode, evidence cards, scorecard, falsification, and verdict
- **Explains** the causal chain in the scientist's language — citations, pillars, why a call landed
- **Controls** the next step: queue a neighbour gene, switch to Live, retrieve papers, focus a candidate, or stress-test the verdict
- **Drives** the workbench after Confirm — disease, genes, mode, and Run analysis

## What you get

| Surface | Role |
| --- | --- |
| **Clara** | Supervisor reasoning agent — controls the session and the causal chain |
| **Workbench** | Disease, candidates, Demo/Live mode, verdicts, and the focused dossier |
| **Causal pipeline** | Retrieve → Extract → Score → Falsify → Decide |
| **Evidence** | Open Targets, Europe PMC, and GWAS Catalog in Live mode; seeded dermatology packs in Demo |

### Seeded demo (atopic dermatitis)

| Gene | Verdict |
| --- | --- |
| **IL4R** | Driver |
| **S100A8** | Passenger |
| **FLG** | Insufficient evidence |

## How a run works

1. **Retrieve** structured evidence (Demo packs or Live public sources).
2. **Extract** provenance-backed cards — trusted hosts or PMIDs only.
3. **Score** with a versioned causal rubric (genetics, perturbation, clinical rescue over expression and co-mention).
4. **Falsify** the leading call against counter-evidence.
5. **Decide** Driver / Passenger / Insufficient, with an exportable dossier.

Clara supervises that chain and can take control of it. She queues the next pair, switches the workbench to Live, and runs the analysis so the scientist can compare calls without leaving the session.

Full rubric: [`docs/reasoning-rubric.md`](docs/reasoning-rubric.md).

## Quick start

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Open **http://localhost:3000**. Use **Demo** for the seeded IL4R / FLG / S100A8 comparison. Switch to **Live** for Open Targets, Europe PMC, and GWAS Catalog.

### Local (without Docker)

**API**

```bash
cd services/api
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Web**

```bash
cd apps/web
npm install
# Windows: set NEXT_PUBLIC_API_URL=http://localhost:8000
# macOS / Linux: export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open **http://localhost:3000**. Health check: http://localhost:8000/health

## Environment

Copy `.env.example` → `.env`. Never commit `.env`.

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | API base URL |
| `CORS_ORIGINS` | Allowed workbench origins |
| `LLM_API_KEY` | Optional OpenAI-compatible key for Clara and ensemble narratives |
| `LLM_MODEL` | Optional; default `gpt-5-mini` |
| `MONGODB_URI` / `MONGODB_DB` | Optional run and chat persistence |
| `REDIS_URL` | Optional evidence cache |
| `NEXT_PUBLIC_SUPABASE_*` / `SUPABASE_*` | Optional sign-in; the workbench runs as a guest without it |

## Tests

```bash
cd services/api
python -m pytest -q

cd apps/web
npx playwright install chromium
npm run test:e2e
```

## Repository

```
apps/web/          Next.js workbench — Clara's control surface
services/api/      FastAPI pipeline and Clara, the supervisor reasoning agent
docs/              Rubric, model card, architecture
fixtures/          Seeded dermatology evidence packs
docker-compose.yml Local stack (web + api + mongo + redis)
```

## License

MIT — see [`LICENSE`](LICENSE).

Public scientific APIs (Open Targets, Europe PMC, GWAS Catalog) remain under their own terms.
