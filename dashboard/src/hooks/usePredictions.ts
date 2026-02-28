import { useState, useEffect } from 'react';
import type { PredictionsMap } from '../types/predictions';
import { fetchPredictions } from '../api/hf-client';

interface UsePredictionsReturn {
  data: PredictionsMap | null;
  loading: boolean;
  error: string | null;
}

export function usePredictions(
  runId: string | undefined,
): UsePredictionsReturn {
  const [data, setData] = useState<PredictionsMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPredictions(runId)
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
  }, [runId]);

  return { data, loading, error };
}
