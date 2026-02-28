export interface TrajectoryMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface TrajectoryInfo {
  model_stats: {
    instance_cost: number;
    api_calls: number;
  };
  mini_version: string;
  exit_status: string;
  submission: string;
}

export interface TrajectoryData {
  info: TrajectoryInfo;
  messages: TrajectoryMessage[];
}
