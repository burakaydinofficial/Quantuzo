import { useState, useEffect } from 'react';
import type { TrajectoryData } from '../types/trajectory';
import { fetchTrajectory } from '../api/hf-client';

interface UseTrajectoryReturn {
  data: TrajectoryData | null;
  loading: boolean;
  error: string | null;
}

export function useTrajectory(
  runId: string | undefined,
  instanceId: string | undefined,
): UseTrajectoryReturn {
  const [data, setData] = useState<TrajectoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId || !instanceId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchTrajectory(runId, instanceId)
      .then((result) => {
        if (!cancelled) setData(result);
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
  }, [runId, instanceId]);

  return { data, loading, error };
}
