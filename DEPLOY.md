# Deploying AI Anki to AWS — the Week 3 runbook

This is the **Week 3 ("Deploy, Observe, Recover")** companion to AI Anki. It takes the
same app you fixed in Week 1 from *running on your laptop* to *live on the internet*,
and sets up the live incident the class diagnoses together.

> **Why AWS and not Cloudflare?** AI Anki is a Python FastAPI server with a SQLite file
> and a Claude-powered endpoint — stateful, long-running compute. That is exactly what
> AWS Lambda is good at and exactly what Cloudflare's edge Workers are *not* (no Python
> server, no local filesystem). So the live class deploys to **AWS**, and you self-learn
> **Cloudflare** on a lightweight hello-world. Picking the right platform for the
> workload is itself the first engineering decision of the week.

The whole thing runs inside the **AWS Always-Free tier**: 1M Lambda requests/month, a
free public Function URL (no API Gateway), and CloudWatch logs/metrics. You only pay
for Anthropic API calls, which the `/generate` endpoint makes.

---

## How it works (the one paragraph to understand before you start)

We ship the app as a **container image** and run it on **Lambda** using the
[AWS Lambda Web Adapter](https://github.com/aws/aws-lambda-web-adapter). The adapter is
a small extension that translates each Lambda invocation into a normal HTTP request to
`uvicorn`, so the *unmodified* FastAPI app runs as-is — no handler, no Mangum, no code
changes. A **Function URL** gives it a public HTTPS address. Two environment variables
do all the configuration:

| Variable | Why it exists |
| --- | --- |
| `ANTHROPIC_API_KEY` | The app's only **secret**. Injected at deploy time, never in the image or git. Dropping it is the live incident. |
| `ANKI_DB_PATH=/tmp/anki.db` | Lambda's filesystem is read-only **except `/tmp`**, so the SQLite file lives there. It re-seeds on every cold start — fine for a demo, and a concrete lesson in why serverless compute is ephemeral. |

The deploy artifacts are [`deploy/Dockerfile`](deploy/Dockerfile),
[`deploy/aws-deploy.sh`](deploy/aws-deploy.sh), and [`.dockerignore`](.dockerignore)
(which keeps `.env`, `*.db`, and `.git` *out* of the image).

---

## Prerequisites

- **AWS CLI v2**, configured for an account you own: `aws configure` (set a default region, e.g. `ap-southeast-1`).
- **Docker** running.
- An **Anthropic API key** — https://platform.claude.com/settings/keys

---

## The fast path (one command)

```bash
ANTHROPIC_API_KEY=sk-ant-... ./deploy/aws-deploy.sh
```

It creates the ECR repo, builds and pushes the image, creates the execution role and the
function, wires a public Function URL, and prints the live URL. Re-running it redeploys.
Then jump to **[Observe](#2-observe)** and **[Recover](#3-recover)** below.

If you'd rather do it by hand the first time (recommended — you learn more), follow the
steps below, which are exactly what the script automates.

---

## 1. Deploy (by hand)

Set a few variables for the session:

```bash
export AWS_REGION=ap-southeast-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_URI=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/ai-anki
```

**a. Build the image** (build context is the repo root):

```bash
docker build --platform linux/amd64 -f deploy/Dockerfile -t ai-anki .
```

**b. Push it to ECR:**

```bash
aws ecr create-repository --repository-name ai-anki --region $AWS_REGION
aws ecr get-login-password --region $AWS_REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
docker tag ai-anki:latest $ECR_URI:latest
docker push $ECR_URI:latest
```

**c. Create an execution role** (one time — lets the function write logs):

```bash
aws iam create-role --role-name ai-anki-lambda-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name ai-anki-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
export ROLE_ARN=$(aws iam get-role --role-name ai-anki-lambda-role --query Role.Arn --output text)
```

**d. Create the function** — note the secret goes in as an env var, not in the image:

```bash
aws lambda create-function --function-name ai-anki --region $AWS_REGION \
  --package-type Image --code ImageUri=$ECR_URI:latest \
  --role $ROLE_ARN --architectures x86_64 --timeout 30 --memory-size 512 \
  --environment "Variables={ANTHROPIC_API_KEY=sk-ant-...,ANKI_DB_PATH=/tmp/anki.db}"
aws lambda wait function-active --function-name ai-anki --region $AWS_REGION
```

**e. Give it a public URL:**

```bash
aws lambda create-function-url-config --function-name ai-anki --region $AWS_REGION --auth-type NONE
aws lambda add-permission --function-name ai-anki --region $AWS_REGION \
  --statement-id FunctionURLAllowPublicAccess --action lambda:InvokeFunctionUrl \
  --principal '*' --function-url-auth-type NONE
aws lambda get-function-url-config --function-name ai-anki --region $AWS_REGION --query FunctionUrl --output text
```

Open the printed URL: the AI Anki UI loads, `/docs` shows the API, and `/decks` returns
the seeded decks. **It's live.**

---

## 2. Observe

CloudWatch captures every log line and a set of metrics for free. Tail the logs and hit
the service in another terminal:

```bash
aws logs tail /aws/lambda/ai-anki --follow --region $AWS_REGION
```

```bash
curl -s "$URL/decks" ; echo            # a healthy request — watch it appear in the logs
```

In the AWS console, **Lambda → ai-anki → Monitor** shows the metrics: invocations,
errors, duration, throttles. **Logs tell you what happened on one request; metrics tell
you how often and how bad across all of them.** Read a healthy request now so you know
what normal looks like *before* anything breaks.

---

## 3. Recover (the live incident)

Break it on purpose, diagnose from the logs, recover. The cleanest break uses the
secret — the same secret discipline from Block 3 of the class.

**Break it** — remove the API key (simulating a rotated/forgotten secret):

```bash
aws lambda update-function-configuration --function-name ai-anki --region $AWS_REGION \
  --environment "Variables={ANKI_DB_PATH=/tmp/anki.db}"
```

Now call the Claude-powered endpoint:

```bash
curl -s -X POST "$URL/decks/1/generate" \
  -H 'content-type: application/json' -d '{"topic":"capital cities","count":3}' ; echo
```

It fails. **Don't read the source.** Read the logs (`aws logs tail ...`) and the HTTP
status. AI Anki turns a missing key into a clean `503` with an `AINotConfigured` signal —
the logs point straight at configuration, not code. Form the hypothesis from that
evidence: *"the deploy lost its `ANTHROPIC_API_KEY`."*

**Recover** — put the secret back and confirm:

```bash
aws lambda update-function-configuration --function-name ai-anki --region $AWS_REGION \
  --environment "Variables={ANTHROPIC_API_KEY=sk-ant-...,ANKI_DB_PATH=/tmp/anki.db}"
aws lambda wait function-updated --function-name ai-anki --region $AWS_REGION
curl -s -X POST "$URL/decks/1/generate" \
  -H 'content-type: application/json' -d '{"topic":"capital cities","count":3}' ; echo   # 200, cards returned
```

Other breaks to try: point `ANKI_DB_PATH` at a read-only path like `/var/anki.db` (every
data request 500s — the logs show the write failure), or drop the function's memory so it
times out. Each one teaches the same loop: **hypothesis → check the evidence → fix →
redeploy → confirm.** Stay calm and read; the logs almost always told you already.

---

## Tear down

```bash
aws lambda delete-function --function-name ai-anki --region $AWS_REGION
aws lambda delete-function-url-config --function-name ai-anki --region $AWS_REGION 2>/dev/null || true
aws ecr delete-repository --repository-name ai-anki --region $AWS_REGION --force
aws iam detach-role-policy --role-name ai-anki-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name ai-anki-lambda-role
```

## Troubleshooting

- **Function URL returns 403** — you skipped step **e**'s `add-permission`; the resource policy is what makes the URL public.
- **`exec format error` in the logs** — image architecture ≠ function architecture. Build `--platform linux/amd64` for an `x86_64` function (or `linux/arm64` + `--architectures arm64`).
- **`sqlite3.OperationalError: unable to open database file`** — `ANKI_DB_PATH` isn't under `/tmp`. Only `/tmp` is writable on Lambda.
- **First call is slow (~2–4s)** — cold start while Lambda boots the container; subsequent calls are fast.
