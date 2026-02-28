import { useState, useEffect } from 'react';
import type { LeaderboardRow } from '../types/leaderboard';
import { fetchLeaderboard } from '../api/hf-client';

interface UseLeaderboardResult {
  rows: LeaderboardRow[];
  loading: boolean;
  error: string | null;
}

export function useLeaderboard(): UseLeaderboardResult {
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLeaderboard()
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { rows, loading, error };
}
