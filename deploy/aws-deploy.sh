#!/usr/bin/env bash
#
# Deploy AI Anki to AWS Lambda as a container image with a public Function URL.
#
# This is the convenience wrapper for the runbook in DEPLOY.md — read that first so you
# understand each step. Re-running this script redeploys (build → push → update).
#
# Prerequisites:
#   - AWS CLI v2, configured (`aws configure`) for an account you own.
#   - Docker running.
#   - An Anthropic API key (the one secret this app needs).
#
# Usage:
#   ANTHROPIC_API_KEY=sk-ant-... ./deploy/aws-deploy.sh
#
# Override any of these with environment variables:
set -euo pipefail

REGION="${AWS_REGION:-ap-southeast-1}"
FUNCTION_NAME="${FUNCTION_NAME:-ai-anki}"
ECR_REPO="${ECR_REPO:-ai-anki}"
ROLE_NAME="${ROLE_NAME:-ai-anki-lambda-role}"
# linux/amd64 is the most portable choice for a class on mixed hardware. To use the
# cheaper arm64 (Graviton) runtime instead, set PLATFORM=linux/arm64 and ARCH=arm64.
PLATFORM="${PLATFORM:-linux/amd64}"
ARCH="${ARCH:-x86_64}"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "ERROR: set ANTHROPIC_API_KEY before running (it is the app's only secret)." >&2
  echo "  ANTHROPIC_API_KEY=sk-ant-... ./deploy/aws-deploy.sh" >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Account ${ACCOUNT_ID}, region ${REGION}, function ${FUNCTION_NAME}"

# 1. ECR repository ---------------------------------------------------------
echo "==> Ensuring ECR repository '${ECR_REPO}' exists"
aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${REGION}" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "${ECR_REPO}" --region "${REGION}" >/dev/null

# 2. Build + push the image -------------------------------------------------
echo "==> Logging Docker in to ECR"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "==> Building image for ${PLATFORM}"
docker build --platform "${PLATFORM}" -f "${REPO_ROOT}/deploy/Dockerfile" -t "${ECR_REPO}:latest" "${REPO_ROOT}"
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"

echo "==> Pushing to ${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

# 3. Execution role (create on first run) -----------------------------------
if ! aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  echo "==> Creating Lambda execution role '${ROLE_NAME}'"
  aws iam create-role --role-name "${ROLE_NAME}" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }' >/dev/null
  # Lets the function write logs to CloudWatch — that is what makes "Observe" possible.
  aws iam attach-role-policy --role-name "${ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "    waiting 10s for the new role to propagate..."
  sleep 10
fi
ROLE_ARN="$(aws iam get-role --role-name "${ROLE_NAME}" --query Role.Arn --output text)"

# 4. Create or update the function ------------------------------------------
if aws lambda get-function --function-name "${FUNCTION_NAME}" --region "${REGION}" >/dev/null 2>&1; then
  echo "==> Updating existing function code + config"
  aws lambda update-function-code --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --image-uri "${ECR_URI}:latest" >/dev/null
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}" --region "${REGION}"
  aws lambda update-function-configuration --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --environment "Variables={ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},ANKI_DB_PATH=/tmp/anki.db}" >/dev/null
else
  echo "==> Creating function '${FUNCTION_NAME}'"
  aws lambda create-function --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --package-type Image --code "ImageUri=${ECR_URI}:latest" \
    --role "${ROLE_ARN}" --architectures "${ARCH}" \
    --timeout 30 --memory-size 512 \
    --environment "Variables={ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},ANKI_DB_PATH=/tmp/anki.db}" >/dev/null
  aws lambda wait function-active --function-name "${FUNCTION_NAME}" --region "${REGION}"
fi

# 5. Public Function URL ----------------------------------------------------
if ! aws lambda get-function-url-config --function-name "${FUNCTION_NAME}" --region "${REGION}" >/dev/null 2>&1; then
  echo "==> Creating a public Function URL"
  aws lambda create-function-url-config --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --auth-type NONE >/dev/null
  # Without this resource policy the URL returns 403 — a common first-deploy gotcha.
  aws lambda add-permission --function-name "${FUNCTION_NAME}" --region "${REGION}" \
    --statement-id FunctionURLAllowPublicAccess --action lambda:InvokeFunctionUrl \
    --principal "*" --function-url-auth-type NONE >/dev/null
fi

URL="$(aws lambda get-function-url-config --function-name "${FUNCTION_NAME}" --region "${REGION}" --query FunctionUrl --output text)"
echo ""
echo "==> Live: ${URL}"
echo "    UI        ${URL}"
echo "    API docs  ${URL}docs"
echo "    Logs      aws logs tail /aws/lambda/${FUNCTION_NAME} --follow --region ${REGION}"
