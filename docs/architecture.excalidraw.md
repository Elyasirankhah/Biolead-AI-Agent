# BioLead architecture diagram (Excalidraw-style)

Copy into Excalidraw as boxes/arrows.

```
[Scientist]
    |
    v
[Vercel · Next.js Workbench]
  - query form
  - pipeline timeline
  - decision brief / comparison
  - JSON export
    |
    | HTTPS  NEXT_PUBLIC_API_URL
    v
[AWS ALB]
    |
    v
[ECS Fargate · FastAPI]
  - /api/analyze
  - /api/demo
  - /api/analyze/stream
  - CORS_ORIGINS = Vercel URL
    |
    +--> [Step Functions] --> [ECS Evidence Workers]
                                |-- Open Targets
                                |-- Europe PMC
                                |-- GWAS Catalog
                                |-- Bedrock (optional narrative)
                                |-- Aurora (normalized evidence)
                                +-- S3 (raw payloads / exports)
    |
    +--> [ElastiCache TTL]
    +--> [CloudWatch / X-Ray / SQS DLQ]
```

Local equivalent: `docker compose up` → web:3000, api:8000.
