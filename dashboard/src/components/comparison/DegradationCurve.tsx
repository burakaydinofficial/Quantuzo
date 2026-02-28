import { useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvLabel, kvSortOrder } from '../../utils/kv-config';
import './DegradationCurve.css';

const COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];

interface DegradationCurveProps {
  rows: LeaderboardRow[];
  selectedModels: string[];
}

export function DegradationCurve({ rows, selectedModels }: DegradationCurveProps) {
  const { data, models } = useMemo(() => {
    const filtered = rows.filter((r) => selectedModels.includes(r.model_name));
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
        if (match) point[model] = Number(match.rate.toFixed(1));
      }
      return point;
    });

    return { data, models };
  }, [rows, selectedModels]);

  if (data.length === 0) return null;

  return (
    <div className="degradation-curve">
      <div className="degradation-curve__title">
        Accuracy Degradation by KV Quantization Level
      </div>
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="kv"
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
          <Legend />
          {models.map((model, i) => (
            <Line
              key={model}
              type="monotone"
              dataKey={model}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
