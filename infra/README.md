# Infra notes (AWS + Vercel)

This folder documents the production target. The prototype runs locally via Docker Compose; production uses:

- **Vercel** for `apps/web`
- **AWS ECS Fargate + ALB** for `services/api`
- Optional Step Functions workers, Aurora, S3, ElastiCache, Bedrock

## Suggested first AWS path
1. Build and push `services/api` image to ECR.
2. Create an ECS service with one task definition running uvicorn on port 8000.
3. Put an Application Load Balancer in front with HTTPS.
4. Set `CORS_ORIGINS` to your Vercel URL.
5. Point Vercel `NEXT_PUBLIC_API_URL` at the ALB.

## IaC
A starter CDK sketch lives in `cdk_stack.py`. It is intentionally minimal and meant as an architecture anchor for the presentation, not a full production stack.
