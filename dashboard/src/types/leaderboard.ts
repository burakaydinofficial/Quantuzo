export interface LeaderboardRow {
  run_id: string;
  timestamp: string;
  model_name: string;
  model_file: string;
  kv_type_k: string;
  kv_type_v: string;
  ctx_size: number;
  accelerator: string;
  agent_version: string;
  agent_branch: string;
  benchmark: string;
  total: number;
  resolved: number;
  failed: number;
  error: number;
  rate: number;
}
