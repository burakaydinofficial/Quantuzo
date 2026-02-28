import type { LeaderboardRow } from '../../types/leaderboard';
import type { EvaluationResults } from '../../types/evaluation';
import { MetricCard } from '../shared/MetricCard';
import { kvLabel } from '../../utils/kv-config';
import { fmtPct, fmtDelta } from '../../utils/format';
import { deltaBaseline, patchGenerationRate, successWhenAttempted } from '../../utils/metrics';
import './RunSummaryCard.css';

interface RunSummaryCardProps {
  row: LeaderboardRow;
  allRows: LeaderboardRow[];
  evalResults: EvaluationResults | null;
}

export function RunSummaryCard({ row, allRows, evalResults }: RunSummaryCardProps) {
  const delta = deltaBaseline(row, allRows);
  const deltaSentiment =
    delta === null || delta === 0
      ? 'neutral' as const
      : delta > 0
        ? 'positive' as const
        : 'negative' as const;

  return (
    <div className="run-summary">
      <MetricCard label="Model" value={row.model_name} />
      <MetricCard
        label="KV Config"
        value={kvLabel(row.kv_type_k, row.kv_type_v)}
      />
      <MetricCard label="Context Size" value={`${(row.ctx_size / 1024).toFixed(0)}K`} />
      <MetricCard label="Accelerator" value={row.accelerator} />
      <MetricCard label="Resolution Rate" value={fmtPct(row.rate)} />
      <MetricCard
        label="Delta from f16"
        value={fmtDelta(delta)}
        sentiment={deltaSentiment}
      />
      {evalResults && (
        <>
          <MetricCard
            label="Patch Generation"
            value={fmtPct(
              patchGenerationRate(
                evalResults.predictions_submitted,
                evalResults.total_instances,
              ),
            )}
          />
          <MetricCard
            label="Success When Attempted"
            value={fmtPct(
              successWhenAttempted(
                evalResults.resolved,
                evalResults.predictions_submitted,
              ),
            )}
          />
        </>
      )}
    </div>
  );
}
