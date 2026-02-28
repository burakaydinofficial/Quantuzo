export interface Prediction {
  model_name_or_path: string;
  instance_id: string;
  model_patch: string;
}

export type PredictionsMap = Record<string, Prediction>;
