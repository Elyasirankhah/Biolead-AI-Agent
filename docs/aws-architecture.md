# BioLead Deployment Architecture

## Runtime map (local / prototype)

```mermaid
flowchart TB
  Scientist[Scientist Browser] --> Web[Next.js Workbench]
  Web -->|HTTPS NEXT_PUBLIC_API_URL| Api[FastAPI Evidence API]
  Api --> OT[Open Targets]
  Api --> EPMC[Europe PMC]
  Api --> GWAS[GWAS Catalog]
  Api --> LLM[LLM provider optional]
  Api --> DB[(MongoDB optional)]
```

## Production-oriented AWS sketch

```mermaid
flowchart TB
  Scientist[Scientist Browser] --> Web[Next.js Workbench]
  Web -->|HTTPS| ALB[AWS ALB]
  ALB --> Api[ECS Fargate FastAPI]
  Api --> SF[Step Functions]
  SF --> Workers[ECS Evidence Workers]
  Workers --> OT[Open Targets]
  Workers --> EPMC[Europe PMC]
  Workers --> GWAS[GWAS Catalog]
  Workers --> Bedrock[Amazon Bedrock optional]
  Workers --> Aurora[(Aurora PostgreSQL)]
  Workers --> S3[(S3 raw evidence and exports)]
  Api --> Redis[ElastiCache]
  Api --> CW[CloudWatch and X-Ray]
```

## AWS services

| Layer | Service | Role |
| --- | --- | --- |
| API | ALB + ECS Fargate | FastAPI `/api/analyze`, `/api/demo`, SSE |
| Orchestration | Step Functions + ECS workers | Evidence collection fan-out |
| LLM | Bedrock (optional) | Narrative voters |
| Data | Aurora PostgreSQL | Normalized evidence + runs |
| Object store | S3 | Raw API payloads, dossier exports |
| Cache | ElastiCache | Source TTL cache |
| Ops | CloudWatch, X-Ray, SQS DLQ | Observability |

## API environment variables

```bash
CORS_ORIGINS=http://localhost:3000
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5-mini
ENSEMBLE_REQUIRED=true
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=biolead
```

## Minimal path

1. Local Docker Compose for demo and review.
2. Deploy API container to ECS Fargate behind an ALB.
3. Point the workbench `NEXT_PUBLIC_API_URL` at the ALB.
4. Add Step Functions / Aurora / ElastiCache once the core loop is stable.

Add your Excalidraw / flowchart export beside this file when ready.
