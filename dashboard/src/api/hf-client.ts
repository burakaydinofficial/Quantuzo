import type { LeaderboardRow } from '../types/leaderboard';
import type { EvaluationResults } from '../types/evaluation';
import type { TrajectoryData } from '../types/trajectory';
import type { PredictionsMap } from '../types/predictions';

const BASE_URL =
  'https://huggingface.co/datasets/burakaydinofficial/Quantuzo/resolve/main';

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}/${path}`);
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return res.json();
}

async function fetchText(path: string): Promise<string> {
  const res = await fetch(`${BASE_URL}/${path}`);
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return res.text();
}

export async function fetchLeaderboard(): Promise<LeaderboardRow[]> {
  const text = await fetchText('leaderboard.jsonl');
  return text
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as LeaderboardRow);
}

export async function fetchEvalResults(
  runId: string,
): Promise<EvaluationResults> {
  return fetchJson<EvaluationResults>(
    `runs/${runId}/evaluation_results.json`,
  );
}

export async function fetchPredictions(runId: string): Promise<PredictionsMap> {
  return fetchJson<PredictionsMap>(`runs/${runId}/preds.json`);
}

export async function fetchTrajectory(
  runId: string,
  instanceId: string,
): Promise<TrajectoryData> {
  return fetchJson<TrajectoryData>(
    `runs/${runId}/${instanceId}/${instanceId}.traj.json`,
  );
}
