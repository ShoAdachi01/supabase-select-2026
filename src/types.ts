export type Column = {
  name: string;
  type: 'number' | 'category';
  unique: number;
  missing: number;
  excluded: boolean;
  reason: string | null;
  examples: (string | number)[];
  min: number | null;
  max: number | null;
};
export type Dataset = {
  id: string;
  name: string;
  source: string;
  created_at: string;
  profile: {
    rows: number;
    columns: Column[];
    preview: Record<string, string | number | null>[];
    issues: { column: string; severity: string; message: string }[];
    missing_cells: number;
    duplicates: number;
    suggested_target: string;
    suggested_task: 'classification' | 'regression';
  };
};
export type Plan = {
  target: string;
  task: 'classification' | 'regression';
  features: string[];
  name: string;
  reason: string;
  provider: string;
};
export type ModelResult = {
  selected_model: string;
  task: 'classification' | 'regression';
  metric: string;
  higher_better: boolean;
  test_score: number;
  baseline_score: number;
  leaderboard: { name: string; score: number; seconds: number; baseline: boolean }[];
  splits: { train: number; validation: number; test: number; strategy: string };
  training_seconds: number;
  importance: { feature: string; value: number }[];
  input_schema: Column[];
  example_input: Record<string, string | number | null>;
  baseline_only: boolean;
  target: string;
  features: string[];
  test_examples: { actual: string | number; predicted: string | number }[];
  labels: string[];
  confusion_matrix: number[][];
  metrics: Record<string, number>;
  notes: string[];
};
export type Run = {
  id: string;
  name: string;
  dataset_id: string;
  status: 'queued' | 'training' | 'ready' | 'failed';
  created_at: string;
  payload: {
    objective: string;
    target: string;
    features: string[];
    task: string;
    events: { title: string; detail: string; at: string }[];
    result?: ModelResult;
    error?: string;
  };
};
export type Prediction = {
  predictions: { value: string | number; probabilities: Record<string, number> | null }[];
  inference_ms: number;
  model: string;
  warnings: string[];
  tokens_used_for_prediction: number;
  prediction_id: string;
};
export type Config = {
  supabase_url: string;
  supabase_key: string;
  mode: string;
  planner: string;
  configured: boolean;
};
