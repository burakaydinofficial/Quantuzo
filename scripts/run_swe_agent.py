#!/usr/bin/env python3
"""
SWE-agent runner for patch generation.
Connects to llama.cpp server via OpenAI-compatible API.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from datasets import load_dataset


def wait_for_server(base_url: str, timeout: int = 300) -> bool:
    """Wait for llama-server to be ready."""
    health_url = base_url.replace("/v1", "/health")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                print(f"Server ready at {base_url}")
                return True
        except requests.RequestException:
            pass
        print("Waiting for server...")
        time.sleep(10)

    return False


def generate_patch(instance: dict, base_url: str, model_name: str) -> dict:
    """Generate a patch for a single SWE-bench instance."""

    # Construct prompt for the model
    problem_statement = instance.get("problem_statement", "")
    repo = instance.get("repo", "")
    instance_id = instance.get("instance_id", "")

    prompt = f"""You are a software engineer tasked with fixing a bug in a Python repository.

Repository: {repo}
Instance ID: {instance_id}

Problem Statement:
{problem_statement}

Please provide a git diff patch that fixes this issue. Output only the patch in unified diff format, starting with --- and +++.
"""

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are an expert software engineer. Respond only with the git diff patch."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4096,
                "temperature": 0.0,
            },
            timeout=300
        )
        response.raise_for_status()

        result = response.json()
        patch = result["choices"][0]["message"]["content"]

        return {
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
            "status": "success"
        }

    except Exception as e:
        return {
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": "",
            "status": "error",
            "error": str(e)
        }


def main():
    # Configuration from environment
    base_url = os.environ.get("OPENAI_API_BASE", "http://llama-server:8080/v1")
    model_name = os.environ.get("MODEL_NAME", "qwen3-4b")
    run_id = os.environ.get("RUN_ID", "default")
    dataset_name = os.environ.get("DATASET", "princeton-nlp/SWE-bench_Lite")
    instance_filter = os.environ.get("INSTANCE_FILTER", "")
    ctx_size = int(os.environ.get("CTX_SIZE", "32768"))
    kv_type_k = os.environ.get("KV_TYPE_K", "f16")
    kv_type_v = os.environ.get("KV_TYPE_V", "f16")

    results_dir = Path("/results") / run_id
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"SWE-Agent Runner")
    print(f"  API Base: {base_url}")
    print(f"  Model: {model_name}")
    print(f"  Run ID: {run_id}")
    print(f"  Dataset: {dataset_name}")
    print(f"  Context Size: {ctx_size}")
    print(f"  KV Config: K:{kv_type_k}/V:{kv_type_v}")

    # Wait for server
    if not wait_for_server(base_url):
        print("Error: Server did not become ready")
        sys.exit(1)

    # Load dataset
    print(f"Loading dataset: {dataset_name}")
    dataset = load_dataset(dataset_name, split="test")

    # Filter instances if specified
    if instance_filter:
        filter_ids = set(instance_filter.split("|"))
        dataset = dataset.filter(lambda x: x["instance_id"] in filter_ids)
        print(f"Filtered to {len(dataset)} instances")

    # Generate patches
    patches = []
    total = len(dataset)

    for i, instance in enumerate(dataset):
        instance_id = instance["instance_id"]
        print(f"[{i+1}/{total}] Processing: {instance_id}")

        patch_result = generate_patch(instance, base_url, model_name)
        patches.append(patch_result)

        # Save intermediate results
        with open(results_dir / "patches.json", "w") as f:
            json.dump(patches, f, indent=2)

    # Final summary
    success_count = sum(1 for p in patches if p["status"] == "success")
    print(f"\nPatch generation complete: {success_count}/{total} successful")
    print(f"Results saved to: {results_dir / 'patches.json'}")


if __name__ == "__main__":
    main()
