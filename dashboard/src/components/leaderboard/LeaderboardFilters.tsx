import './LeaderboardFilters.css';

interface LeaderboardFiltersProps {
  benchmarks: string[];
  models: string[];
  kvLabels: string[];
  agentBranches: string[];
  agentVersions: string[];
  selectedBenchmark: string;
  selectedModel: string;
  selectedKv: string;
  selectedAgentBranch: string;
  selectedAgentVersion: string;
  onBenchmarkChange: (v: string) => void;
  onModelChange: (v: string) => void;
  onKvChange: (v: string) => void;
  onAgentBranchChange: (v: string) => void;
  onAgentVersionChange: (v: string) => void;
}

export function LeaderboardFilters({
  benchmarks,
  models,
  kvLabels,
  agentBranches,
  agentVersions,
  selectedBenchmark,
  selectedModel,
  selectedKv,
  selectedAgentBranch,
  selectedAgentVersion,
  onBenchmarkChange,
  onModelChange,
  onKvChange,
  onAgentBranchChange,
  onAgentVersionChange,
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
      <div className="leaderboard-filters__group">
        <span className="leaderboard-filters__label">Agent Branch</span>
        <select
          className="leaderboard-filters__select"
          value={selectedAgentBranch}
          onChange={(e) => onAgentBranchChange(e.target.value)}
        >
          <option value="">All</option>
          {agentBranches.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>
      <div className="leaderboard-filters__group">
        <span className="leaderboard-filters__label">Agent Version</span>
        <select
          className="leaderboard-filters__select"
          value={selectedAgentVersion}
          onChange={(e) => onAgentVersionChange(e.target.value)}
        >
          <option value="">All</option>
          {agentVersions.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
