import './LeaderboardFilters.css';

interface LeaderboardFiltersProps {
  benchmarks: string[];
  models: string[];
  kvLabels: string[];
  selectedBenchmark: string;
  selectedModel: string;
  selectedKv: string;
  onBenchmarkChange: (v: string) => void;
  onModelChange: (v: string) => void;
  onKvChange: (v: string) => void;
}

export function LeaderboardFilters({
  benchmarks,
  models,
  kvLabels,
  selectedBenchmark,
  selectedModel,
  selectedKv,
  onBenchmarkChange,
  onModelChange,
  onKvChange,
}: LeaderboardFiltersProps) {
  return (
    <div className="leaderboard-filters">
      <div className="leaderboard-filters__group">
        <span className="leaderboard-filters__label">Benchmark</span>
        <select
          className="leaderboard-filters__select"
          value={selectedBenchmark}
          onChange={(e) => onBenchmarkChange(e.target.value)}
        >
          <option value="">All</option>
          {benchmarks.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>
      <div className="leaderboard-filters__group">
        <span className="leaderboard-filters__label">Model</span>
        <select
          className="leaderboard-filters__select"
          value={selectedModel}
          onChange={(e) => onModelChange(e.target.value)}
        >
          <option value="">All</option>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <div className="leaderboard-filters__group">
        <span className="leaderboard-filters__label">KV Config</span>
        <select
          className="leaderboard-filters__select"
          value={selectedKv}
          onChange={(e) => onKvChange(e.target.value)}
        >
          <option value="">All</option>
          {kvLabels.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
