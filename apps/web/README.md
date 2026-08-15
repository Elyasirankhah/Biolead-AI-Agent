# BioLead Workbench (Vercel)

Next.js UI for the BioLead Evidence Workbench.

## Local
```bash
npm install
set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

## Vercel
1. Set project **Root Directory** to `apps/web`
2. Add env var `NEXT_PUBLIC_API_URL` pointing at the AWS ALB / API URL
3. Deploy

If the API is unreachable, the UI falls back to the seeded offline demo.
