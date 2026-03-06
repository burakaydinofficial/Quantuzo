import { useState, useMemo } from 'react';
import { useLeaderboard } from '../hooks/useLeaderboard';
import { DegradationCurve } from '../components/comparison/DegradationCurve';
import { MemoryVsAccuracyChart } from '../components/comparison/MemoryVsAccuracyChart';
import { ExitStatusComparison } from '../components/comparison/ExitStatusComparison';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import './ModelComparisonPage.css';

export function ModelComparisonPage() {
  const { rows, loading, error } = useLeaderboard();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [benchmark, setBenchmark] = useState('');

  const benchmarks = useMemo(
    () => [...new Set(rows.map((r) => r.benchmark))].sort(),
    [rows],
  );

  const models = useMemo(
    () => [...new Set(rows.map((r) => r.model_name))].sort(),
    [rows],
  );

  const filtered = useMemo(() => {
    if (!benchmark) return rows;
    return rows.filter((r) => r.benchmark === benchmark);
  }, [rows, benchmark]);

  function toggleModel(m: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m);
      else next.add(m);
      return next;
    });
  }

  if (loading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={error} />;

  const selectedModels = [...selected];

  return (
    <div className="comparison-page">
      <h1 className="comparison-page__title">Model Comparison</h1>

      <div className="comparison-page__benchmark-filter">
        <span className="comparison-page__benchmark-label">Benchmark</span>
        <select
          className="comparison-page__benchmark-select"
          value={benchmark}
          onChange={(e) => setBenchmark(e.target.value)}
        >
          <option value="">All</option>
          {benchmarks.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div className="comparison-page__selector">
        <span className="comparison-page__selector-label">Select models to compare</span>
        <div className="comparison-page__model-chips">
          {models.map((m) => (
            <button
              key={m}
              className={
                selected.has(m)
                  ? 'comparison-page__chip comparison-page__chip--selected'
                  : 'comparison-page__chip'
              }
              onClick={() => toggleModel(m)}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {selectedModels.length === 0 ? (
        <div className="comparison-page__hint">
          Select models above to compare their KV quantization degradation curves
        </div>
      ) : (
        <div className="comparison-page__charts">
          <DegradationCurve rows={filtered} selectedModels={selectedModels} />
          <MemoryVsAccuracyChart rows={filtered} selectedModels={selectedModels} />
          <ExitStatusComparison rows={filtered} selectedModels={selectedModels} />
        </div>
      )}
    </div>
  );
}
