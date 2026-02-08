#!/bin/bash
# Download model from HuggingFace
#
# Downloads GGUF model files with validation and resume support.
# Detects failed downloads, error pages, and gated model blocks.
#
# Usage:
#   ./scripts/download_model.sh MODEL_CONFIG
#
# Examples:
#   ./scripts/download_model.sh qwen3-coder-next-q4
#   ./scripts/download_model.sh gpt-oss-20b-mxfp4

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SPEC_DIR="$PROJECT_DIR/spec"
MODELS_DIR="$PROJECT_DIR/models"

# GGUF magic bytes (ASCII: "GGUF")
GGUF_MAGIC="47475546"

usage() {
    echo "Usage: $0 MODEL_CONFIG"
    echo ""
    echo "Downloads model from HuggingFace based on config in spec/models/"
    echo ""
    echo "Available models:"
    for conf in "$SPEC_DIR/models/"*.conf; do
        name=$(basename "$conf" .conf)
        if grep -q "MODEL_REPO=" "$conf" 2>/dev/null; then
            echo "  $name"
        fi
    done
    exit 1
}

# Validate GGUF file by checking magic bytes
validate_gguf() {
    local file="$1"

    if [[ ! -f "$file" ]]; then
        return 1
    fi

    # Check file size (error pages are typically < 1MB)
    local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    if [[ "$size" -lt 1000000 ]]; then
        echo "ERROR: File too small (${size} bytes) - likely an error page" >&2
        return 1
    fi

    # Check GGUF magic bytes
    local magic=$(xxd -p -l 4 "$file" 2>/dev/null)
    if [[ "$magic" != "$GGUF_MAGIC" ]]; then
        echo "ERROR: Invalid GGUF file (bad magic bytes: $magic)" >&2
        # Show first few bytes to help debug
        echo "First 100 bytes of file:" >&2
        head -c 100 "$file" | cat -v >&2
        echo "" >&2
        return 1
    fi

    return 0
}

# Parse arguments
if [[ $# -lt 1 ]] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    usage
fi

MODEL_CONFIG="$1"
MODEL_CONF="$SPEC_DIR/models/${MODEL_CONFIG}.conf"

if [[ ! -f "$MODEL_CONF" ]]; then
    echo "ERROR: Config not found: $MODEL_CONF"
    echo ""
    usage
fi

# Load config
set -a
source "$MODEL_CONF"
set +a

# Validate required fields
if [[ -z "$MODEL_REPO" ]]; then
    echo "ERROR: MODEL_REPO not defined in $MODEL_CONF"
    echo "Add MODEL_REPO=username/repo-name to enable auto-download"
    exit 1
fi

if [[ -z "$MODEL_FILE" ]]; then
    echo "ERROR: MODEL_FILE not defined in $MODEL_CONF"
    exit 1
fi

# Setup paths
DEST_FILE="$MODELS_DIR/$MODEL_FILE"
TEMP_FILE="$DEST_FILE.downloading"
URL="https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE"

echo "================================================"
echo "Model Downloader"
echo "================================================"
echo "Model:  $MODEL_CONFIG"
echo "File:   $MODEL_FILE"
echo "Repo:   $MODEL_REPO"
echo "URL:    $URL"
echo "Dest:   $DEST_FILE"
echo "================================================"
echo ""

# Check if already downloaded
if [[ -f "$DEST_FILE" ]]; then
    echo "File already exists, validating..."
    if validate_gguf "$DEST_FILE"; then
        echo "Valid GGUF file already present. Skipping download."
        exit 0
    else
        echo "Existing file is invalid, removing and re-downloading..."
        rm -f "$DEST_FILE"
    fi
fi

# Create models directory
mkdir -p "$MODELS_DIR"

# Download with resume support
echo "Downloading..."
HTTP_CODE=$(curl -L -C - -w "%{http_code}" -o "$TEMP_FILE" "$URL" 2>&1 | tail -1)
CURL_EXIT=$?

# Check curl exit code
if [[ $CURL_EXIT -ne 0 ]]; then
    echo "ERROR: Download failed (curl exit code: $CURL_EXIT)"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Check HTTP status
if [[ "$HTTP_CODE" -lt 200 ]] || [[ "$HTTP_CODE" -ge 400 ]]; then
    echo "ERROR: HTTP error $HTTP_CODE"
    if [[ "$HTTP_CODE" == "401" ]] || [[ "$HTTP_CODE" == "403" ]]; then
        echo "This may be a gated model. Visit https://huggingface.co/$MODEL_REPO"
        echo "to accept the license and download manually."
    fi
    rm -f "$TEMP_FILE"
    exit 1
fi

# Validate downloaded file
echo ""
echo "Validating download..."
if ! validate_gguf "$TEMP_FILE"; then
    echo ""
    echo "Downloaded file is not a valid GGUF."
    echo "This could mean:"
    echo "  - The model is gated (requires license acceptance)"
    echo "  - The filename is incorrect"
    echo "  - HuggingFace returned an error page"
    echo ""
    echo "Visit: https://huggingface.co/$MODEL_REPO"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Move to final location
mv "$TEMP_FILE" "$DEST_FILE"

echo ""
echo "Download complete: $DEST_FILE"
echo "Size: $(ls -lh "$DEST_FILE" | awk '{print $5}')"
