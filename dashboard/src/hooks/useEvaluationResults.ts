import { useState, useEffect } from 'react';
import type { EvaluationResults } from '../types/evaluation';
import { fetchEvalResults } from '../api/hf-client';

interface UseEvaluationResultsReturn {
  data: EvaluationResults | null;
  loading: boolean;
  error: string | null;
}

export function useEvaluationResults(
  runId: string | undefined,
): UseEvaluationResultsReturn {
  const [data, setData] = useState<EvaluationResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEvalResults(runId)
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
