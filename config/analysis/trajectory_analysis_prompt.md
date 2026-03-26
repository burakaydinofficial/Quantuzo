# Trajectory Analysis — Phase 2

You are analyzing a software engineering agent's trajectory on a SWE-bench task. You will receive a compact step log (steps.json) extracted from the full trajectory.

## Your task

Analyze the agent's behavior and produce a JSON object with the fields described below. Be factual and precise. Only extract what you can observe in the data — do not speculate.

## Step types in the input

- `"type": "step"` — A normal agent action with a command and observation
- `"type": "repeated_command"` — Phase 1 detected this command was repeated identically N times consecutively. The `count` and `step_range` show how many times and which steps.
- `"type": "format_error"` / `"type": "format_error_burst"` — The agent produced empty or malformed output. A burst collapses multiple consecutive format errors with a `count`.
- `"type": "post_container_death"` — Steps after the Docker container died (2h timeout). These are collapsed and irrelevant to the analysis. Ignore them.

## Output format

Respond with ONLY a JSON object. No markdown, no explanation, no code fences.

```json
{
  "failure_reason": "<enum>",
  "behavioral_loop": {
    "detected": <boolean>,
    "start_step": <int|null>,
    "description": "<string|null>"
  },
  "problem_approach": {
    "identified_correct_file": <boolean>,
    "identified_root_cause": <boolean>,
    "distinct_strategies": <int>,
    "fix_attempted": <boolean>,
    "had_viable_fix": <boolean>
  },
  "summary": "<string, 1-3 sentences>"
}
```

## failure_reason enum

Choose exactly one. Pick the FIRST matching reason from this list:

1. `"resolved"` — The instance was marked as resolved (you will be told this).
2. `"context_overflow"` — Exit status is BadRequestError (you will be told this). The agent exceeded the 64K context window.
3. `"submitted_incorrect"` — The agent submitted a patch but it did not pass tests (you will be told this).
4. `"format_error_dominated"` — More than 50% of the agent's steps were format errors (empty/malformed output). Check the stats.step_counts fields.
5. `"exact_loop"` — The agent's remaining steps were dominated by `repeated_command` entries. The agent got stuck repeating identical commands.
6. `"behavioral_loop"` — The agent repeated the same approach pattern without fundamentally changing strategy. Examples: editing the same lines with similar sed commands, running the same test after reverting, searching for the same pattern with slight flag variations. NOT the same as exact_loop — here the commands differ slightly but the approach is the same.
7. `"wrong_target"` — The agent spent the majority of its productive steps on the wrong file or fundamentally misunderstood the problem described in the task.
8. `"insufficient_capability"` — The agent genuinely tried multiple distinct approaches (different files, different strategies) but could not solve the problem. It was not stuck in a loop — it was trying and failing.

Notes:
- If an exact_loop or behavioral_loop started after genuine work, the failure reason is still the loop — that's what prevented the agent from solving the task.
- Container death is NOT a failure reason. It's recorded separately. Choose the reason based on what the agent was doing, not how it was stopped.
- For resolved and submitted_incorrect instances, still fill in problem_approach and summary.
- If resolution is "not_submitted", the agent did not submit a patch. Choose from reasons 4-8 based on behavior.

## behavioral_loop field

- `detected`: true if you observe the agent repeating the same approach pattern (not exact commands, but same strategy) 3+ times
- `start_step`: the step number where the behavioral loop began (use the `step` field from the first repetitive step)
- `description`: brief factual description of what pattern repeated, e.g. "Editing line 289 of models.py with similar sed replacements, reverting with git checkout, re-editing"

If no behavioral loop is detected, set `detected: false`, `start_step: null`, `description: null`.

## problem_approach field

- `identified_correct_file`: Did the agent find and focus on the correct source file for the bug? true if it read/edited the right file.
- `identified_root_cause`: Did the agent demonstrate understanding of WHY the bug occurs (not just WHERE)? true only if the agent's thoughts or edits show understanding of the mechanism.
- `distinct_strategies`: Count of fundamentally different fix approaches the agent tried. Reading different parts of the same file is NOT a new strategy. Editing a different function or trying a different fix mechanism IS. Minimum is 0 (never attempted a fix).
- `fix_attempted`: Did the agent execute at least one edit command (sed, patch, echo > file, etc.) trying to fix the bug?
- `had_viable_fix`: At any point, did the agent have a patch that was on the right track (even if incomplete)? true only if the edit targeted the correct area with a reasonable approach.

## summary field

1-3 factual sentences describing what happened. Include: what the agent explored, what it tried, and how/why it stopped. Do not editorialize.
