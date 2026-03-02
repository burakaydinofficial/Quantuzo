#!/bin/bash
# Download split GGUF models from HuggingFace
#
# Handles multi-part GGUF files (e.g. Model-00001-of-00002.gguf).
# Detects part count from MODEL_FILE, downloads all parts with
# resume support, and validates GGUF magic bytes on each.
#
# Called by download_model.sh when MODEL_DOWNLOAD_SCRIPT is set.
#
# Usage (via delegation):
#   MODEL_DOWNLOAD_SCRIPT=scripts/split-gguf.sh
#   → download_model.sh passes: --model-config /path/to/model.conf --models-dir DIR

set -e

usage() {
    echo "Usage: $0 --model-config PATH --models-dir DIR"
    echo "This script is called by download_model.sh, not directly."
    exit 1
}

MODEL_CONF=""
MODELS_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model-config) MODEL_CONF="$2"; shift 2 ;;
        --models-dir)   MODELS_DIR="$2";  shift 2 ;;
        *) echo "ERROR: Unknown argument: $1"; usage ;;
    esac
done

if [[ -z "$MODEL_CONF" ]] || [[ -z "$MODELS_DIR" ]]; then
    usage
fi

if [[ ! -f "$MODEL_CONF" ]]; then
    echo "ERROR: Config not found: $MODEL_CONF"
    exit 1
fi

# GGUF magic bytes (ASCII: "GGUF")
GGUF_MAGIC="47475546"

# Load config
set -a
source "$MODEL_CONF"
set +a

if [[ -z "$MODEL_REPO" ]]; then
    echo "ERROR: MODEL_REPO not defined in $MODEL_CONF"
    exit 1
fi

if [[ -z "$MODEL_FILE" ]]; then
    echo "ERROR: MODEL_FILE not defined in $MODEL_CONF"
    exit 1
fi

# Parse split pattern from MODEL_FILE
# Expected format: Name-00001-of-00002.gguf
if [[ "$MODEL_FILE" =~ ^(.+)-([0-9]+)-of-([0-9]+)(\.gguf)$ ]]; then
    BASE="${BASH_REMATCH[1]}"
    TOTAL="${BASH_REMATCH[3]}"
    SUFFIX="${BASH_REMATCH[4]}"
    # Remove leading zeros for arithmetic
    TOTAL_NUM=$((10#$TOTAL))
else
    echo "ERROR: MODEL_FILE doesn't match split pattern: $MODEL_FILE"
    echo "Expected format: Name-00001-of-NNNNN.gguf"
    exit 1
fi

# Detect HF subfolder from filename
# e.g. Qwen3.5-27B-BF16-00001-of-00002.gguf -> BF16 subfolder
HF_SUBFOLDER=""
if [[ "$BASE" =~ -([A-Z][A-Z0-9]+)$ ]]; then
    CANDIDATE="${BASH_REMATCH[1]}"
    # Common subfolder patterns on HuggingFace
    case "$CANDIDATE" in
        BF16|FP16|FP32|F16|F32) HF_SUBFOLDER="$CANDIDATE" ;;
    esac
fi

# Validate GGUF file by checking magic bytes
validate_gguf() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        return 1
    fi

    local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    if [[ "$size" -lt 1000000 ]]; then
        echo "ERROR: File too small (${size} bytes) - likely an error page" >&2
        return 1
    fi

    local magic=$(xxd -p -l 4 "$file" 2>/dev/null)
    if [[ "$magic" != "$GGUF_MAGIC" ]]; then
        echo "ERROR: Invalid GGUF file (bad magic bytes: $magic)" >&2
        head -c 100 "$file" | cat -v >&2
        echo "" >&2
        return 1
    fi

    return 0
}

# Build part filenames and download
echo "================================================"
echo "Split GGUF Downloader"
echo "================================================"
echo "Config: $MODEL_CONF"
echo "Repo:   $MODEL_REPO"
echo "Parts:  $TOTAL_NUM"
if [[ -n "$HF_SUBFOLDER" ]]; then
    echo "HF Dir: $HF_SUBFOLDER/"
fi
echo "Dest:   $MODELS_DIR/"
echo "================================================"
echo ""

mkdir -p "$MODELS_DIR"

FAILED=0
for i in $(seq 1 "$TOTAL_NUM"); do
    # Zero-pad to match the width of TOTAL
    PADDED=$(printf "%0${#TOTAL}d" "$i")
    PART_FILE="${BASE}-${PADDED}-of-${TOTAL}${SUFFIX}"
    DEST_FILE="$MODELS_DIR/$PART_FILE"
    TEMP_FILE="$DEST_FILE.downloading"

    # Build URL with optional subfolder
    if [[ -n "$HF_SUBFOLDER" ]]; then
        URL="https://huggingface.co/$MODEL_REPO/resolve/main/$HF_SUBFOLDER/$PART_FILE"
    else
        URL="https://huggingface.co/$MODEL_REPO/resolve/main/$PART_FILE"
    fi

    echo "--- Part $i of $TOTAL_NUM: $PART_FILE ---"

    # Check if already downloaded and valid
    if [[ -f "$DEST_FILE" ]]; then
        echo "  File exists, validating..."
        if validate_gguf "$DEST_FILE"; then
            echo "  Valid GGUF, skipping."
            echo ""
            continue
        else
            echo "  Invalid, re-downloading..."
            rm -f "$DEST_FILE"
        fi
    fi

    echo "  URL: $URL"
    echo "  Downloading..."

    HTTP_CODE=$(curl -L -C - -w "%{http_code}" -o "$TEMP_FILE" "$URL" 2>&1 | tail -1)
    CURL_EXIT=$?

    if [[ $CURL_EXIT -ne 0 ]]; then
        echo "  ERROR: Download failed (curl exit code: $CURL_EXIT)"
        rm -f "$TEMP_FILE"
        FAILED=1
        continue
    fi

    if [[ "$HTTP_CODE" -lt 200 ]] || [[ "$HTTP_CODE" -ge 400 ]]; then
        echo "  ERROR: HTTP error $HTTP_CODE"
        if [[ "$HTTP_CODE" == "401" ]] || [[ "$HTTP_CODE" == "403" ]]; then
            echo "  This may be a gated model. Visit https://huggingface.co/$MODEL_REPO"
        fi
        rm -f "$TEMP_FILE"
        FAILED=1
        continue
    fi

    echo "  Validating..."
    if ! validate_gguf "$TEMP_FILE"; then
        echo "  ERROR: Downloaded file is not a valid GGUF."
        echo "  This could mean:"
        echo "    - The model is gated (requires license acceptance)"
        echo "    - The filename or subfolder is incorrect"
        echo "    - HuggingFace returned an error page"
        echo "  Visit: https://huggingface.co/$MODEL_REPO"
        rm -f "$TEMP_FILE"
        FAILED=1
        continue
    fi

    mv "$TEMP_FILE" "$DEST_FILE"
    echo "  OK ($(ls -lh "$DEST_FILE" | awk '{print $5}'))"
    echo ""
done

if [[ $FAILED -ne 0 ]]; then
    echo "ERROR: Some parts failed to download. Check errors above."
    exit 1
fi

echo "================================================"
echo "All $TOTAL_NUM parts downloaded successfully."
echo "================================================"
