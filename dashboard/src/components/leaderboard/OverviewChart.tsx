import { useMemo, useRef, useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import type { LeaderboardRow } from '../../types/leaderboard';
import { kvLabel, kvSortOrder } from '../../utils/kv-config';
import { modelDisplayName } from '../../utils/format';
import './OverviewChart.css';

const COLORS = [
  '#6366f1', '#22d3ee', '#a78bfa', '#ef4444',
  '#10b981', '#3b82f6', '#f97316', '#ec4899',
  '#f59e0b',
];

function wrapAtHyphens(label: string, maxLen = 16): string[] {
  if (label.length <= maxLen) return [label];

  const breaks: number[] = [];
  for (let i = 0; i < label.length; i++) {
    if (label[i] === '-') breaks.push(i + 1);
  }
  if (breaks.length === 0) return [label];

  const numLines = Math.ceil(label.length / maxLen);
  const target = label.length / numLines;

  const chosen: number[] = [];
  for (let n = 1; n < numLines; n++) {
    const ideal = Math.round(target * n);
    let best = breaks[0];
    let bestDist = Infinity;
    for (const bp of breaks) {
      if (chosen.length > 0 && bp <= chosen[chosen.length - 1]) continue;
      const dist = Math.abs(bp - ideal);
      if (dist < bestDist) {
        bestDist = dist;
        best = bp;
      }
    }
    chosen.push(best);
  }

  chosen.sort((a, b) => a - b);
  const lines: string[] = [];
  let start = 0;
  for (const bp of chosen) {
    lines.push(label.slice(start, bp));
    start = bp;
  }
  lines.push(label.slice(start));
  return lines;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function roundedTopPath(x: number, y: number, w: number, h: number, r: number): string {
  const cr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + cr}Q${x},${y} ${x + cr},${y}H${x + w - cr}Q${x + w},${y} ${x + w},${y + cr}V${y + h}Z`;
}

interface FlatEntry {
  label: string;
  model: string;
  kv: string;
  value: number;
  n: number;
  min: number;
  max: number;
  colorIndex: number;
  isSpacer?: boolean;
}

function AggregatedBarShape({ x, y, width, height, fill, payload, showRange }: any) {
  const entry = payload as FlatEntry;
  if (entry?.isSpacer) return <g />;

  const n = entry?.n ?? 1;
  const value = entry?.value ?? 0;
  const barPath = height > 0 ? roundedTopPath(x, y, width, height, 3) : '';

  if (!showRange || n <= 1 || value === 0 || height <= 0) {
    return <path d={barPath} fill={fill} />;
  }

  const baseline = y + height;
  const scale = height / value;
  const minY = baseline - entry.min * scale;
  const maxY = baseline - entry.max * scale;
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
  const tickXRef = useRef<Map<number, number>>(new Map());

  const { flatData, modelGroups, allKvLabels, hasDuplicates } = useMemo(() => {
    const models = [...new Set(rows.map((r) => r.model_name))];

    const kvOrderMap = new Map<string, number>();
    for (const r of rows) {
      const label = kvLabel(r.kv_type_k, r.kv_type_v);
      if (!kvOrderMap.has(label)) {
        kvOrderMap.set(label, kvSortOrder(r.kv_type_k, r.kv_type_v));
      }
    }
    const allKvLabels = [...kvOrderMap.entries()]
      .sort((a, b) => a[1] - b[1])
      .map(([label]) => label);

    const flatData: FlatEntry[] = [];
    const modelGroups: Array<{ model: string; startIdx: number; endIdx: number }> = [];
    let hasDuplicates = false;

    for (const model of models) {
      if (flatData.length > 0) {
        flatData.push({
          label: `__spacer_${model}`,
          model: '',
          kv: '',
          value: 0,
          n: 0,
          min: 0,
          max: 0,
          colorIndex: -1,
          isSpacer: true,
        });
      }

      const startIdx = flatData.length;

      const ratesByKv = new Map<string, number[]>();
      for (const r of rows) {
        if (r.model_name !== model) continue;
        const label = kvLabel(r.kv_type_k, r.kv_type_v);
        const arr = ratesByKv.get(label) ?? [];
        arr.push(r.rate);
        ratesByKv.set(label, arr);
      }

      const sortedKvs = [...ratesByKv.keys()].sort(
        (a, b) => (kvOrderMap.get(a) ?? 99) - (kvOrderMap.get(b) ?? 99),
      );

      for (const kv of sortedKvs) {
        const rates = ratesByKv.get(kv)!;
        if (rates.length > 1) hasDuplicates = true;
        flatData.push({
          label: `${modelDisplayName(model)}__${kv}`,
          model: modelDisplayName(model),
          kv,
          value: Number(median(rates).toFixed(1)),
          n: rates.length,
          min: Number(Math.min(...rates).toFixed(1)),
          max: Number(Math.max(...rates).toFixed(1)),
          colorIndex: allKvLabels.indexOf(kv),
        });
      }

      modelGroups.push({
        model: modelDisplayName(model),
        startIdx,
        endIdx: flatData.length - 1,
      });
    }

    return { flatData, modelGroups, allKvLabels, hasDuplicates };
  }, [rows]);

  if (flatData.length === 0) return null;

  return (
    <div className="overview-chart">
      <div className="overview-chart__header">
        <div className="overview-chart__title">Resolution Rate by Model &amp; KV Config</div>
        {hasDuplicates && (
          <button
            className={`overview-chart__range-toggle${showRange ? ' overview-chart__range-toggle--active' : ''}`}
            onClick={() => setShowRange((v) => !v)}
          >
            Min/Max
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <BarChart data={flatData} barCategoryGap="8%">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="label"
            interval={0}
            height={60}
            tickLine={false}
            tick={({ x, y, payload }: any) => {
              const label = payload.value as string;
              if (label.startsWith('__spacer_')) return <g />;

              const entryIdx = flatData.findIndex((e) => e.label === label);
              if (entryIdx === -1) return <g />;

              tickXRef.current.set(entryIdx, x);

              const group = modelGroups.find(
                (g) => entryIdx >= g.startIdx && entryIdx <= g.endIdx,
              );
              if (!group || entryIdx !== group.endIdx) return <g />;

              const startX = tickXRef.current.get(group.startIdx) ?? x;
              const cx = (startX + x) / 2;

              const lines = wrapAtHyphens(group.model);
              return (
                <g transform={`translate(${cx},${y})`}>
                  <text textAnchor="middle" fill="var(--color-text-secondary)" fontSize={11}>
                    {lines.map((line, i) => (
                      <tspan key={i} x={0} dy={i === 0 ? 14 : 13}>{line}</tspan>
                    ))}
                  </text>
                </g>
              );
            }}
          />
          <YAxis
            domain={[0, 'auto']}
            tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            cursor={false}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const entry = payload[0]?.payload as FlatEntry;
              if (!entry || entry.isSpacer) return null;

              const modelEntries = flatData.filter(
                (e) => e.model === entry.model && !e.isSpacer,
              );

              return (
                <div style={{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '0.375em',
                  color: 'var(--color-text)',
                  padding: '0.5em 0.75em',
                  fontSize: 13,
                }}>
                  <div style={{ marginBottom: '0.3em', fontWeight: 600 }}>{entry.model}</div>
                  {modelEntries.map((e) => (
                    <div key={e.kv} style={{ display: 'flex', alignItems: 'center', gap: '0.4em', lineHeight: 1.6 }}>
                      <span style={{
                        width: 8, height: 8,
                        background: COLORS[e.colorIndex % COLORS.length],
                        display: 'inline-block', borderRadius: 1,
                      }} />
                      <span>{e.kv}: {e.value}%</span>
                      {showRange && e.n > 1 && (
                        <span style={{ color: 'var(--color-text-secondary)' }}>
                          ({e.min}–{e.max}%, n={e.n})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              );
            }}
          />
          <Bar
            dataKey="value"
            shape={(props: any) => (
              <AggregatedBarShape {...props} showRange={showRange} />
            )}
          >
            {flatData.map((entry, index) => (
              <Cell
                key={index}
                fill={entry.isSpacer ? 'transparent' : COLORS[entry.colorIndex % COLORS.length]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{
        display: 'flex', justifyContent: 'center', gap: '1em',
        flexWrap: 'wrap', fontSize: 12, marginTop: '0.5em',
      }}>
        {allKvLabels.map((kv, i) => (
          <span key={kv} style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.3em',
            color: 'var(--color-text-secondary)',
          }}>
            <span style={{
              width: 10, height: 10,
              background: COLORS[i % COLORS.length],
              display: 'inline-block',
            }} />
            {kv}
          </span>
        ))}
      </div>
    </div>
  );
}
