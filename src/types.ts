export type Reference = { path: string; thumbnail: string; public_url: string; sha256: string };
export type Character = {
  id: string;
  name: string;
  created_at: string;
  payload: { description: string; aliases: string[]; references: Reference[]; demo: boolean };
};
export type Coverage = { source: string; status: string; query: string; detail: string };
export type Scan = {
  id: string;
  asset_id: string;
  status: 'queued' | 'searching' | 'complete' | 'failed';
  created_at: string;
  payload: {
    request: { source: string; query: string };
    coverage: Coverage[];
    events: { at: string; message: string }[];
    finding_count: number;
    reused_corrections?: number;
    error?: string;
  };
};
export type Decision =
  'unreviewed' | 'confirmed_match' | 'authorized' | 'not_a_match' | 'investigate';
export type Finding = {
  id: string;
  asset_id: string;
  scan_id: string;
  created_at: string;
  payload: {
    title: string;
    url: string;
    image_url?: string;
    domain: string;
    thumbnail?: string;
    provider: string;
    demo: boolean;
    category: string;
    territory: string;
    match: {
      kind: string;
      reason: string;
      method: string;
      distance?: number;
      reference_index?: number;
    };
    permission: { status: string; reason: string };
    priority: string;
    priority_reason: string;
    commercial_signal?: boolean;
    image_sha256?: string;
    capture_sha256?: string;
    captured_at: string;
    evidence_path?: string;
    review: { decision: Decision; note: string; at?: string };
    reused_correction?: boolean;
    semantic_review?: { kind: string; reason: string; provider: string };
    semantic_review_error?: string;
  };
};
export type License = {
  id: string;
  asset_id: string;
  status: string;
  created_at: string;
  payload: {
    applicant: string;
    email: string;
    domain: string;
    category: string;
    territory: string;
    starts_on: string;
    ends_on: string;
    description: string;
    decision_note?: string;
  };
};
export type Grant = { id: string; asset_id: string; payload: License['payload'] };
export type Workspace = {
  assets: Character[];
  scans: Scan[];
  findings: Finding[];
  licenses: License[];
  grants: Grant[];
  reviews: { id: string }[];
};
export type Config = {
  supabase_url: string;
  supabase_key: string;
  mode: string;
  configured: boolean;
  providers: { public: boolean; google: boolean; serpapi: boolean; gemini: boolean };
};
