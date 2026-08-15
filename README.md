# BioLead Evidence Workbench

BioLead is a causal gene-prioritization product for dermatology. It separates **Driver**, **Passenger**, and **Insufficient evidence** calls with a scored, citable dossier — not a literature summary.

Scientists submit a disease and candidate genes. BioLead retrieves evidence, extracts provenance, scores the causal chain, falsifies the call, and returns a decision brief. **Clara** is the supervisor reasoning layer: she watches the session, explains the dossier, and can steer the next step of the chain — a close-pair rerun, a Live retrieve, a literature search, or a challenge to the current verdict.

**Live demo:** https://biolead-ai-agent-eight.vercel.app

Research use only — not clinical decision support.

## What you get

| Surface | Role |
| --- | --- |
| **Workbench** | Disease, candidates, Demo/Live mode, verdicts, and the focused dossier |
| **Causal pipeline** | Retrieve → Extract → Score → Falsify → Decide |
| **Clara** | Session supervisor — watches scores, evidence, and verdicts; can take the next action on the chain |
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

Clara sits above that chain. She can queue a neighbour gene, switch the workbench to Live, and run the next pair so the scientist can compare calls without leaving the session.

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
apps/web/          Next.js workbench and Clara
services/api/      FastAPI retrieve, score, falsify, decide, and Clara
docs/              Rubric, model card, architecture
fixtures/          Seeded dermatology evidence packs
docker-compose.yml Local stack (web + api + mongo + redis)
```

## License

MIT — see [`LICENSE`](LICENSE).

Public scientific APIs (Open Targets, Europe PMC, GWAS Catalog) remain under their own terms.
