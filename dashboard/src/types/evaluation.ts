export interface EvaluationInstances {
  total_instances: number;
  submitted_instances: number;
  completed_instances: number;
  resolved_instances: number;
  unresolved_instances: number;
  empty_patch_instances: number;
  error_instances: number;
  completed_ids: string[];
  incomplete_ids: string[];
  empty_patch_ids: string[];
  submitted_ids: string[];
  resolved_ids: string[];
  unresolved_ids: string[];
  error_ids: string[];
  schema_version: number;
}

export interface EvaluationResults {
  run_id: string;
  dataset: string;
  swebench_version: string;
  total_instances: number;
  predictions_submitted: number;
  resolved: number;
  failed: number;
  error: number;
  instances: EvaluationInstances;
  resolution_rate: number;
}
