import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvLabel, kvSortOrder } from '../../utils/kv-config';
import './ExitStatusComparison.css';

interface ExitStatusComparisonProps {
  rows: LeaderboardRow[];
  selectedModels: string[];
}

const MODEL_COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];

const CATEGORY_OPACITY: Record<string, number> = {
  Submitted: 1.0,
  LimitsExceeded: 0.5,
  Other: 0.25,
};

const categories = ['Submitted', 'LimitsExceeded', 'Other'] as const;

function categorize(exitStatuses: Record<string, number>) {
  let submitted = 0;
  let limitsExceeded = 0;
  let other = 0;
  for (const [status, count] of Object.entries(exitStatuses)) {
    if (status === 'Submitted') submitted += count;
    else if (status === 'LimitsExceeded') limitsExceeded += count;
    else other += count;
  }
  return { Submitted: submitted, LimitsExceeded: limitsExceeded, Other: other };
}

export function ExitStatusComparison({ rows, selectedModels }: ExitStatusComparisonProps) {
  const { data, models } = useMemo(() => {
    const filtered = rows.filter(
      (r) => selectedModels.includes(r.model_name) && r.exit_statuses,
    );

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
        if (match?.exit_statuses) {
          const cats = categorize(match.exit_statuses);
          point[`${model}_Submitted`] = cats.Submitted;
          point[`${model}_LimitsExceeded`] = cats.LimitsExceeded;
          point[`${model}_Other`] = cats.Other;
        }
      }
      return point;
    });

    return { data, models };
  }, [rows, selectedModels]);

  if (data.length === 0) return null;

  return (
    <div className="exit-status-comparison">
      <div className="exit-status-comparison__title">
        Agent Exit Status by KV Config
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
          {models.map((model, modelIdx) =>
            categories.map((cat) => (
              <Bar
                key={`${model}_${cat}`}
                dataKey={`${model}_${cat}`}
                stackId={model}
                fill={MODEL_COLORS[modelIdx % MODEL_COLORS.length]}
                fillOpacity={CATEGORY_OPACITY[cat]}
                legendType="none"
              />
            )),
          )}
        </BarChart>
      </ResponsiveContainer>
      <div className="stacked-bar-legend">
        <div className="stacked-bar-legend__row">
          {models.map((model, i) => (
            <span key={model} className="stacked-bar-legend__item">
              <span
                className="stacked-bar-legend__swatch"
                style={{ backgroundColor: MODEL_COLORS[i % MODEL_COLORS.length] }}
              />
              {model}
            </span>
          ))}
        </div>
        <div className="stacked-bar-legend__row">
          {categories.map((cat) => (
            <span key={cat} className="stacked-bar-legend__item">
              <span
                className="stacked-bar-legend__swatch"
                style={{ backgroundColor: '#9ca3af', opacity: CATEGORY_OPACITY[cat] }}
              />
              {cat}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
