import { useState, useMemo } from 'react';
import { useLeaderboard } from '../hooks/useLeaderboard';
import { LeaderboardFilters } from '../components/leaderboard/LeaderboardFilters';
import { LeaderboardTable } from '../components/leaderboard/LeaderboardTable';
import { OverviewChart } from '../components/leaderboard/OverviewChart';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { kvLabel } from '../utils/kv-config';
import './LeaderboardPage.css';

export function LeaderboardPage() {
  const { rows, loading, error } = useLeaderboard();
  const [benchmark, setBenchmark] = useState('');
  const [model, setModel] = useState('');
  const [kv, setKv] = useState('');

  const benchmarks = useMemo(
    () => [...new Set(rows.map((r) => r.benchmark))].sort(),
    [rows],
  );
  const models = useMemo(
    () => [...new Set(rows.map((r) => r.model_name))].sort(),
    [rows],
  );
  const kvLabels = useMemo(
    () => [...new Set(rows.map((r) => kvLabel(r.kv_type_k, r.kv_type_v)))],
    [rows],
  );

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (benchmark && r.benchmark !== benchmark) return false;
      if (model && r.model_name !== model) return false;
      if (kv && kvLabel(r.kv_type_k, r.kv_type_v) !== kv) return false;
      return true;
    });
  }, [rows, benchmark, model, kv]);

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="leaderboard-page">
      <div>
        <h1 className="leaderboard-page__title">KV Cache Quantization Benchmark</h1>
        <p className="leaderboard-page__subtitle">
          How much accuracy do you lose for how much memory you save?
        </p>
      </div>
      <LeaderboardFilters
        benchmarks={benchmarks}
        models={models}
        kvLabels={kvLabels}
        selectedBenchmark={benchmark}
        selectedModel={model}
        selectedKv={kv}
        onBenchmarkChange={setBenchmark}
        onModelChange={setModel}
        onKvChange={setKv}
      />
      <OverviewChart rows={filtered} />
      <LeaderboardTable rows={filtered} allRows={rows} />
    </div>
  );
}
