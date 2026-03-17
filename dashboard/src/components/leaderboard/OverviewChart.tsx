import { useMemo, useState } from 'react';
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

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function roundedTopPath(x: number, y: number, w: number, h: number, r: number): string {
  const cr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + cr}Q${x},${y} ${x + cr},${y}H${x + w - cr}Q${x + w},${y} ${x + w},${y + cr}V${y + h}Z`;
}

function AggregatedBarShape({ x, y, width, height, fill, payload, dataKey, showRange }: any) {
  const n = payload?.[`${dataKey}_n`] ?? 1;
  const med = payload?.[dataKey] ?? 0;
  const barPath = height > 0 ? roundedTopPath(x, y, width, height, 3) : '';

  if (!showRange || n <= 1 || med === 0 || height <= 0) {
    return <path d={barPath} fill={fill} />;
  }

  const min = payload[`${dataKey}_min`] as number;
  const max = payload[`${dataKey}_max`] as number;
  const baseline = y + height;
  const scale = height / med;
  const minY = baseline - min * scale;
  const maxY = baseline - max * scale;
  const cx = x + width / 2;
  const capHalf = width * 0.25;

  return (
    <g>
      <path d={barPath} fill={fill} />
      <line x1={cx} y1={minY} x2={cx} y2={maxY}
        stroke="var(--color-text)" strokeWidth={1.5} opacity={0.55} />
      <line x1={cx - capHalf} y1={minY} x2={cx + capHalf} y2={minY}
        stroke="var(--color-text)" strokeWidth={2} opacity={0.7} />
      <line x1={cx - capHalf} y1={maxY} x2={cx + capHalf} y2={maxY}
        stroke="var(--color-text)" strokeWidth={2} opacity={0.7} />
    </g>
  );
}

interface OverviewChartProps {
  rows: LeaderboardRow[];
}

export function OverviewChart({ rows }: OverviewChartProps) {
  const [showRange, setShowRange] = useState(false);

  const { data, kvLabels, hasDuplicates } = useMemo(() => {
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
      // Group rates by kvLabel for this model
      const ratesByKv = new Map<string, number[]>();
      for (const r of rows) {
        if (r.model_name !== model) continue;
        const label = kvLabel(r.kv_type_k, r.kv_type_v);
        const arr = ratesByKv.get(label) ?? [];
        arr.push(r.rate);
        ratesByKv.set(label, arr);
      }

      const entry: Record<string, string | number | [number, number]> = { model };
      for (const [label, rates] of ratesByKv) {
        const med = Number(median(rates).toFixed(1));
        const min = Number(Math.min(...rates).toFixed(1));
        const max = Number(Math.max(...rates).toFixed(1));
        entry[label] = med;
        entry[`${label}_n`] = rates.length;
        entry[`${label}_min`] = min;
        entry[`${label}_max`] = max;
      }
      return entry;
    });

    const hasDuplicates = data.some((entry) =>
      sortedKv.some((kv) => ((entry[`${kv}_n`] as number) ?? 0) > 1),
    );

    return { data, kvLabels: sortedKv, hasDuplicates };
  }, [rows]);

  if (data.length === 0) return null;

  return (
    <div className="overview-chart">
      <div className="overview-chart__header">
        <div className="overview-chart__title">Resolution Rate by Model & KV Config</div>
        {hasDuplicates && (
          <button
            className={`overview-chart__range-toggle${showRange ? ' overview-chart__range-toggle--active' : ''}`}
            onClick={() => setShowRange((v) => !v)}
          >
            Min/Max
          </button>
        )}
      </div>
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
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              // Filter to only actual KV bar entries (skip _err, _n, _min, _max)
              const kvEntries = kvLabels
                .map((kv, i) => {
                  const item = payload.find((p) => p.dataKey === kv);
                  if (!item) return null;
                  const val = item.value as number;
                  const rec = item.payload as Record<string, number>;
                  const n = rec[`${kv}_n`] as number | undefined;
                  const min = rec[`${kv}_min`] as number | undefined;
                  const max = rec[`${kv}_max`] as number | undefined;
                  return { kv, val, n, min, max, color: COLORS[i % COLORS.length] };
                })
                .filter(Boolean) as { kv: string; val: number; n: number; min: number; max: number; color: string }[];

              return (
                <div style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '0.375em',
                  color: 'var(--color-text)',
                  padding: '0.5em 0.75em',
                  fontSize: 13,
                }}>
                  <div style={{ marginBottom: '0.3em', fontWeight: 600 }}>{label}</div>
                  {kvEntries.map(({ kv, val, n, min, max, color }) => (
                    <div key={kv} style={{ display: 'flex', alignItems: 'center', gap: '0.4em', lineHeight: 1.6 }}>
                      <span style={{ width: 8, height: 8, background: color, display: 'inline-block', borderRadius: 1 }} />
                      <span>{kv}: {val}%</span>
                      {showRange && n > 1 && <span style={{ color: 'var(--color-text-secondary)' }}>({min}–{max}%, n={n})</span>}
                    </div>
                  ))}
                </div>
              );
            }}
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
              shape={(props: any) => <AggregatedBarShape {...props} dataKey={kv} showRange={showRange} />}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
