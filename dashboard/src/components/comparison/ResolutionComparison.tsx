import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvLabel, kvSortOrder } from '../../utils/kv-config';
import './ResolutionComparison.css';

interface ResolutionComparisonProps {
  rows: LeaderboardRow[];
  selectedModels: string[];
}

const RESULT_COLORS: Record<string, string> = {
  Resolved: '#22c55e',
  Failed: '#f59e0b',
  Error: '#ef4444',
};

export function ResolutionComparison({ rows, selectedModels }: ResolutionComparisonProps) {
  const { data, models } = useMemo(() => {
    const filtered = rows.filter((r) => selectedModels.includes(r.model_name));

    if (filtered.length === 0) return { data: [], models: [] };

    const kvSet = new Map<string, { label: string; order: number }>();
    for (const r of filtered) {
      const label = kvLabel(r.kv_type_k, r.kv_type_v);
      kvSet.set(label, { label, order: kvSortOrder(r.kv_type_k, r.kv_type_v) });
    }
    const sortedKv = [...kvSet.values()].sort((a, b) => a.order - b.order);
    const models = [...new Set(filtered.map((r) => r.model_name))];

    const data = sortedKv.map(({ label }) => {
      const point: Record<string, string | number> = { kv: label };
      for (const model of models) {
        const match = filtered.find(
          (r) => r.model_name === model && kvLabel(r.kv_type_k, r.kv_type_v) === label,
        );
        if (match) {
          point[`${model}_Resolved`] = match.resolved;
          point[`${model}_Failed`] = match.failed;
          point[`${model}_Error`] = match.error;
        }
      }
      return point;
    });

    return { data, models };
  }, [rows, selectedModels]);

  if (data.length === 0) return null;

  const categories = ['Resolved', 'Failed', 'Error'] as const;

  return (
    <div className="resolution-comparison">
      <div className="resolution-comparison__title">
        Resolution Outcome by KV Config
      </div>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={data} maxBarSize={60}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="kv"
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
          />
          <YAxis
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375em',
              color: 'var(--color-text)',
            }}
            labelStyle={{ color: 'var(--color-text)' }}
            itemStyle={{ color: 'var(--color-text)' }}
            formatter={(value: number | undefined, name: string | undefined) => {
              if (!name) return [value ?? 0, ''];
              const parts = name.split('_');
              const status = parts[parts.length - 1];
              const model = parts.slice(0, -1).join('_');
              return [value ?? 0, `${model} — ${status}`];
            }}
          />
          <Legend
            formatter={(value: string) => {
              const parts = value.split('_');
              const status = parts[parts.length - 1];
              const model = parts.slice(0, -1).join('_');
              return `${model} — ${status}`;
            }}
          />
          {models.map((model) =>
            categories.map((cat) => (
              <Bar
                key={`${model}_${cat}`}
                dataKey={`${model}_${cat}`}
                stackId={model}
                fill={RESULT_COLORS[cat]}
              />
            )),
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
