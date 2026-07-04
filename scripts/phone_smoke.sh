#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://mehair-coach.onrender.com}"
DEVICE_NAME="${MEHAIR_SIM_DEVICE:-iPhone 17}"
ARTIFACT_DIR="${MEHAIR_ARTIFACT_DIR:-.artifacts/mobile}"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

BASE_URL="${BASE_URL%/}"
mkdir -p "$ARTIFACT_DIR"
ARTIFACT_DIR="$(cd "$ARTIFACT_DIR" && pwd)"

echo "== mehair coach phone smoke =="
echo "Base URL: $BASE_URL"

echo
echo "== Backend health =="
curl -fsS -w "\nHTTP=%{http_code} TOTAL=%{time_total}s TTFB=%{time_starttransfer}s\n" "$BASE_URL/health"

echo
echo "== OAuth metadata =="
curl -fsS "$BASE_URL/.well-known/oauth-authorization-server" | python3 -m json.tool > "$ARTIFACT_DIR/oauth-authorization-server.json"
python3 - "$ARTIFACT_DIR/oauth-authorization-server.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path))
required = [
    "issuer",
    "client_name",
    "authorization_endpoint",
    "token_endpoint",
    "registration_endpoint",
    "scopes_supported",
]
missing = [key for key in required if not data.get(key)]
if missing:
    raise SystemExit(f"Missing OAuth metadata: {', '.join(missing)}")
print(f"client_name={data['client_name']}")
print(f"issuer={data['issuer']}")
print(f"metadata_file={path}")
PY

echo
echo "== MCP auth challenge =="
challenge_file="$ARTIFACT_DIR/mcp-challenge.txt"
curl -sS -D "$challenge_file.headers" -o "$challenge_file.body" "$BASE_URL/mcp" || true
if ! grep -qi "www-authenticate: Bearer" "$challenge_file.headers"; then
  echo "Expected MCP bearer challenge was not returned." >&2
  cat "$challenge_file.headers" >&2
  exit 1
fi
sed -n '1,20p' "$challenge_file.headers"

echo
echo "== Widget preview =="
widget_file="$ARTIFACT_DIR/widget-preview.html"
curl -fsS "$BASE_URL/docs/widget-preview?state=today-workout" > "$widget_file"
if ! grep -q "mehair coach" "$widget_file"; then
  echo "Widget preview did not contain expected app name." >&2
  exit 1
fi
echo "widget_file=$widget_file"

if [[ "${MEHAIR_SKIP_SIMULATOR:-0}" == "1" ]]; then
  echo
  echo "Simulator skipped because MEHAIR_SKIP_SIMULATOR=1."
  exit 0
fi

if ! command -v xcrun >/dev/null 2>&1; then
  echo
  echo "xcrun not found; backend smoke passed, simulator step skipped."
  exit 0
fi

echo
echo "== iPhone Simulator Safari preview =="
device_id="$(
  DEVELOPER_DIR="$DEVELOPER_DIR" xcrun simctl list devices available |
    awk -v name="$DEVICE_NAME" '$0 ~ name && $0 ~ /Shutdown|Booted/ { gsub(/[()]/, "", $0); print $(NF-1); exit }'
)"

if [[ -z "$device_id" ]]; then
  echo "No available simulator named '$DEVICE_NAME'; backend smoke passed, simulator step skipped."
  exit 0
fi

DEVELOPER_DIR="$DEVELOPER_DIR" xcrun simctl boot "$device_id" >/dev/null 2>&1 || true
open -a Simulator >/dev/null 2>&1 || true
DEVELOPER_DIR="$DEVELOPER_DIR" xcrun simctl bootstatus "$device_id" -b >/dev/null
DEVELOPER_DIR="$DEVELOPER_DIR" xcrun simctl openurl "$device_id" "$BASE_URL/docs/widget-preview?state=today-workout"
sleep "${MEHAIR_SIM_WAIT_SECONDS:-12}"

screenshot="$ARTIFACT_DIR/iphone-widget-preview.png"
DEVELOPER_DIR="$DEVELOPER_DIR" xcrun simctl io "$device_id" screenshot "$screenshot" >/dev/null
echo "screenshot=$screenshot"

echo
echo "Phone smoke passed."
