#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

REGION="${AWS_REGION:?AWS_REGION is required}"
SECRET_DIR="${RCA_SECRET_DIR:-/etc/rca-demo/secrets}"
PARAMETER_PREFIX="/rca-ai/demo/prod"

install -d -o root -g root -m 0700 "$SECRET_DIR"
stage="$(mktemp -d "$SECRET_DIR/.stage.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT

for name in GROQ_API_KEY CEREBRAS_API_KEY; do
  parameter="$PARAMETER_PREFIX/$name"
  value="$(aws ssm get-parameter --name "$parameter" --with-decryption \
    --region "$REGION" --query Parameter.Value --output text 2>/dev/null)" || {
      echo "secrets: could not read required parameter $parameter" >&2
      exit 1
    }
  if [[ -z "$value" || "$value" == None ]]; then
    echo "secrets: required parameter $parameter is empty" >&2
    exit 1
  fi
  case "$name" in
    GROQ_API_KEY) target=groq_api_key ;;
    CEREBRAS_API_KEY) target=cerebras_api_key ;;
  esac
  printf '%s' "$value" > "$stage/$target"
  chmod 0600 "$stage/$target"
  unset value
done

for file in groq_api_key cerebras_api_key; do
  install -o root -g root -m 0600 "$stage/$file" "$SECRET_DIR/.$file.new"
done
for file in groq_api_key cerebras_api_key; do
  mv -f -- "$SECRET_DIR/.$file.new" "$SECRET_DIR/$file"
done
echo "secrets: provider parameters loaded"
