import { useMemo } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvMemoryPct, kvLabel } from '../../utils/kv-config';
import './MemoryVsAccuracyChart.css';

const COLORS = ['#6366f1', '#22d3ee', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];

interface MemoryVsAccuracyChartProps {
  rows: LeaderboardRow[];
  selectedModels: string[];
}

interface ScatterPoint {
  memory: number;
  rate: number;
  label: string;
}

export function MemoryVsAccuracyChart({
  rows,
  selectedModels,
}: MemoryVsAccuracyChartProps) {
  const { scatterData, models } = useMemo(() => {
    const filtered = rows.filter((r) => selectedModels.includes(r.model_name));
    const models = [...new Set(filtered.map((r) => r.model_name))];
    const scatterData = new Map<string, ScatterPoint[]>();

    for (const model of models) {
      const points = filtered
        .filter((r) => r.model_name === model)
        .map((r) => ({
          memory: kvMemoryPct(r.kv_type_k, r.kv_type_v),
          rate: Number(r.rate.toFixed(1)),
          label: kvLabel(r.kv_type_k, r.kv_type_v),
        }));
      scatterData.set(model, points);
    }

    return { scatterData, models };
  }, [rows, selectedModels]);

  if (models.length === 0) return null;

  return (
    <div className="memory-vs-accuracy">
      <div className="memory-vs-accuracy__title">
        KV Cache Memory vs Resolution Rate
      </div>
      <ResponsiveContainer width="100%" height={350}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            type="number"
            dataKey="memory"
            name="Memory"
            domain={[55, 105]}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
            tickFormatter={(v: number) => `${v}%`}
            label={{
              value: 'Relative KV Memory Usage',
              position: 'insideBottom',
              offset: -5,
              fill: 'var(--color-text-secondary)',
              fontSize: 12,
            }}
          />
          <YAxis
            type="number"
            dataKey="rate"
            name="Rate"
            domain={[0, 'auto']}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
            tickFormatter={(v: number) => `${v}%`}
            label={{
              value: 'Resolution Rate',
              angle: -90,
              position: 'insideLeft',
              fill: 'var(--color-text-secondary)',
              fontSize: 12,
            }}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              borderRadius: '0.375em',
              color: 'var(--color-text)',
            }}
            formatter={(value: number | undefined, name: string | undefined) => {
              if (name === 'Memory') return [`${value ?? 0}%`, 'Memory'];
              return [`${value ?? 0}%`, 'Rate'];
            }}
          />
          <Legend />
          {models.map((model, i) => (
            <Scatter
              key={model}
              name={model}
              data={scatterData.get(model)}
              fill={COLORS[i % COLORS.length]}
            />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
