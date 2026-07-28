.PHONY: test rebuild-leaderboard rebuild-leaderboard-local

# Run the (stdlib, hermetic) unit tests for the summary/leaderboard/validate tooling.
test:
	python3 -m unittest discover -s tests -v


# Rebuild the derived leaderboard (leaderboard.v2.jsonl) on HuggingFace from
# every run's summary.json. Requires HF_TOKEN with write access to the dataset.
rebuild-leaderboard:
	python3 scripts/push_results.py --rebuild-leaderboard

# Rebuild from local results/*/summary.json into ./leaderboard.v2.jsonl (no HF).
# Useful to validate a rebuild before pushing.
rebuild-leaderboard-local:
	python3 scripts/push_results.py --rebuild-leaderboard --local
