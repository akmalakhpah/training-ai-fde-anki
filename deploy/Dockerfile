# AI Anki on AWS Lambda — container image + AWS Lambda Web Adapter.
#
# The Web Adapter is an external Lambda extension that bridges Lambda's runtime API to
# an ordinary HTTP server. That means we run the *unmodified* FastAPI app under uvicorn:
# no Mangum, no handler function, no app-code changes. See DEPLOY.md for the runbook.
#
# Build context is the repo root:
#   docker build -f deploy/Dockerfile -t ai-anki .

FROM public.ecr.aws/docker/library/python:3.12-slim

# Lambda Web Adapter: drop the binary in as a Lambda extension.
# Pin the version on purpose so the build is reproducible.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .

# The adapter forwards each Lambda invocation to a web server listening on $PORT.
ENV PORT=8000

# Lambda's filesystem is read-only except for /tmp, so the SQLite file must live there.
# anki.db is re-created and re-seeded on every cold start — fine for a teaching demo,
# not how you'd persist real data (that's the lesson: serverless compute is ephemeral).
ENV ANKI_DB_PATH=/tmp/anki.db

# ANTHROPIC_API_KEY is intentionally NOT set here — it is a secret and is injected at
# deploy time as a Lambda environment variable. Removing it is the Week 3 live incident.

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
