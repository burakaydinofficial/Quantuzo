import type { LeaderboardRow } from '../types/leaderboard';

export function resolutionRate(resolved: number, total: number): number {
  if (total === 0) return 0;
  return (resolved / total) * 100;
}

export function deltaBaseline(
  row: LeaderboardRow,
  allRows: LeaderboardRow[],
): number | null {
  const baseline = allRows.find(
    (r) =>
      r.model_name === row.model_name &&
      r.benchmark === row.benchmark &&
      r.kv_type_k === 'f16' &&
      r.kv_type_v === 'f16',
  );
  if (!baseline) return null;
  return row.rate - baseline.rate;
}

export function patchGenerationRate(
  submitted: number,
  total: number,
): number {
  if (total === 0) return 0;
  return (submitted / total) * 100;
}

export function successWhenAttempted(
  resolved: number,
  submitted: number,
): number {
  if (submitted === 0) return 0;
  return (resolved / submitted) * 100;
}
