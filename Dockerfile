FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUPABASE_URL=https://ydtjohrtpesfypyhggge.supabase.co \
    SUPABASE_JWKS_URL=https://ydtjohrtpesfypyhggge.supabase.co/auth/v1/.well-known/jwks.json \
    AUTH_REQUIRED=false

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api/app ./app
COPY services/api/prompts ./prompts

EXPOSE 8000

CMD ["sh", "-c", "echo PORT=${PORT:-8000}; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]