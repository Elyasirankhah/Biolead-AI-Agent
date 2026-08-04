# Infra notes (AWS)

This folder documents a production-oriented target. The prototype runs locally via Docker Compose.

Suggested path:
1. Build and push `services/api` image to ECR.
2. Create an ECS service with one task definition running uvicorn on port 8000.
3. Put an Application Load Balancer in front with HTTPS.
4. Set `CORS_ORIGINS` to your workbench origin.
5. Point the workbench `NEXT_PUBLIC_API_URL` at the ALB.

A starter CDK sketch lives in `cdk_stack.py`. It is intentionally minimal — an architecture anchor, not a full production stack.
