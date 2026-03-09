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
import './OverviewChart.css';

const COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#a78bfa', '#ef4444', '#10b981'];

interface OverviewChartProps {
  rows: LeaderboardRow[];
}

export function OverviewChart({ rows }: OverviewChartProps) {
  const { data, kvLabels } = useMemo(() => {
    const models = [...new Set(rows.map((r) => r.model_name))];
    const kvSet = new Map<string, number>();
    for (const r of rows) {
      const label = kvLabel(r.kv_type_k, r.kv_type_v);
      kvSet.set(label, kvSortOrder(r.kv_type_k, r.kv_type_v));
    }
    const sortedKv = [...kvSet.entries()]
      .sort((a, b) => a[1] - b[1])
      .map(([label]) => label);

    const data = models.map((model) => {
      const entry: Record<string, string | number> = { model };
      for (const r of rows) {
        if (r.model_name === model) {
          entry[kvLabel(r.kv_type_k, r.kv_type_v)] = Number(r.rate.toFixed(1));
        }
      }
      return entry;
    });

    return { data, kvLabels: sortedKv };
  }, [rows]);

  if (data.length === 0) return null;

  return (
    <div className="overview-chart">
      <div className="overview-chart__title">Resolution Rate by Model & KV Config</div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} barCategoryGap="20%">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="model"
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
          />
          <YAxis
            domain={[0, 'auto']}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375em',
              color: 'var(--color-text)',
            }}
            formatter={(value: number | undefined) => [`${value ?? 0}%`, undefined]}
          />
          <Legend content={() => (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1em', flexWrap: 'wrap', fontSize: 12 }}>
              {kvLabels.map((kv, i) => (
                <span key={kv} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3em', color: 'var(--color-text-secondary)' }}>
                  <span style={{ width: 10, height: 10, background: COLORS[i % COLORS.length], display: 'inline-block' }} />
                  {kv}
                </span>
              ))}
            </div>
          )} />
          {kvLabels.map((kv, i) => (
            <Bar
              key={kv}
              dataKey={kv}
              fill={COLORS[i % COLORS.length]}
              radius={[3, 3, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
