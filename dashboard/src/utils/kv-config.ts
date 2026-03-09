export interface KvConfig {
  label: string;
  k: string;
  v: string;
  memoryPct: number;
}

const KV_CONFIGS: KvConfig[] = [
  { label: 'f16', k: 'f16', v: 'f16', memoryPct: 100 },
  { label: 'q8', k: 'q8_0', v: 'q8_0', memoryPct: 75 },
  { label: 'q5', k: 'q5_0', v: 'q5_0', memoryPct: 69 },
  { label: 'q5_1', k: 'q5_1', v: 'q5_1', memoryPct: 69 },
  { label: 'q8/q4', k: 'q8_0', v: 'q4_0', memoryPct: 69 },
  { label: 'q4', k: 'q4_0', v: 'q4_0', memoryPct: 63 },
];

const ORDER_MAP = new Map(KV_CONFIGS.map((c, i) => [`${c.k}/${c.v}`, i]));

export function kvLabel(k: string, v: string): string {
  const cfg = KV_CONFIGS.find((c) => c.k === k && c.v === v);
  return cfg ? cfg.label : `${k}/${v}`;
}

export function kvMemoryPct(k: string, v: string): number {
  const cfg = KV_CONFIGS.find((c) => c.k === k && c.v === v);
  return cfg ? cfg.memoryPct : 100;
}

export function kvSortOrder(k: string, v: string): number {
  return ORDER_MAP.get(`${k}/${v}`) ?? 99;
}

export function getKvConfigs(): KvConfig[] {
  return KV_CONFIGS;
}
