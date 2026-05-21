export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = Record<string, JsonValue>;

export type RunStatus = 'pending' | 'waiting_for_user' | 'running' | 'succeeded' | 'partial' | 'failed' | 'cancelled';
export type ThreadStatus = 'active' | 'archived';
export type RunDecisionType = 'approve' | 'edit' | 'reject' | 'respond';
export type ArtifactUploadRole = 'pdf' | 'source';

export interface AgentMessageRequest {
  thread_id?: number | null;
  message: string;
  active_paper_id?: number | null;
  model?: string | null;
  api_key?: string | null;
  base_url?: string | null;
  temperature?: number;
  max_tokens?: number;
  timeout?: number;
  max_retries?: number;
  chat_provider_name?: string | null;
  metadata?: Record<string, unknown>;
}

export interface AgentMessageResponse {
  thread_id: number;
  run_id: number;
  assistant_message_id: number | null;
  status: RunStatus | string;
  message: string | null;
  error: string | null;
}

export interface AgentStreamEvent {
  type: string;
  thread_id: number;
  run_id: number;
  sequence?: number | null;
  event_type?: string | null;
  status?: RunStatus | string | null;
  message?: string | null;
  assistant_message_id?: number | null;
  error?: string | null;
  payload: Record<string, unknown>;
}

export interface MessageRead {
  id: number;
  thread_id: number;
  role: string;
  content_text: string | null;
  content_json: JsonObject | null;
  source: string;
  run_id: number | null;
  created_at: string;
}

export interface RunEventRead {
  id: number;
  run_id: number;
  sequence: number;
  event_type: string;
  level: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface RunRead {
  id: number;
  thread_id: number | null;
  workflow: string;
  status: RunStatus | string;
  error_message: string | null;
  input_json: JsonObject | null;
  output_json: JsonObject | null;
  events: RunEventRead[];
  created_at: string;
  updated_at: string;
}

export interface ThreadSummary {
  id: number;
  title: string;
  surface: string;
  status: ThreadStatus | string;
  current_focus_paper_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadDetail extends ThreadSummary {
  messages: MessageRead[];
  runs: RunRead[];
}

export interface MemoryRead {
  id: number;
  path: string;
  title: string | null;
  memory_type: string;
  scope_type: string;
  scope_id: string | null;
  paper_id: number | null;
  content_text: string;
  content_json: JsonObject | null;
  source: string;
  status: string;
  source_thread_id: number | null;
  source_paper_id: number | null;
  last_accessed_at: string | null;
  metadata: JsonObject;
  created_at: string;
  updated_at: string;
}

export interface RuntimeSettingsRead {
  environment: string;
  data_dir: string;
  storage_root: string | null;
  database_configured: boolean;
  chat: JsonObject;
  embedding: JsonObject;
  arxiv: JsonObject;
  openalex: JsonObject;
  parsing: JsonObject;
}

export interface ArtifactRead {
  id: number;
  kind: string;
  status: string;
  storage_backend: string;
  storage_uri: string | null;
  original_filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  checksum_sha256: string | null;
}

export interface PaperSummary {
  id: number;
  title: string;
  abstract: string | null;
  year: number | null;
  venue: string | null;
  status: string;
  current_pdf_url: string | null;
}

export interface PaperDetail extends PaperSummary {
  authors: unknown[];
  identifiers: Record<string, unknown>[];
  source_records: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  parse_jobs: Record<string, unknown>[];
  processed_documents: Record<string, unknown>[];
  reports: Record<string, unknown>[];
}

export interface SearchCandidateRead {
  id: number;
  rank: number;
  source: string;
  source_record_id: string | null;
  paper_id: number | null;
  title: string;
  abstract: string | null;
  authors: unknown[];
  year: number | null;
  doi: string | null;
  arxiv_id: string | null;
  openalex_id: string | null;
  landing_page_url: string | null;
  pdf_url: string | null;
  score: number | null;
}

export interface SearchSessionRead {
  id: number;
  thread_id: number | null;
  run_id: number | null;
  query_text: string;
  status: string;
  selected_candidate_id: number | null;
  candidates: SearchCandidateRead[];
}

export interface RunDecision {
  type: RunDecisionType;
  args?: Record<string, unknown> | null;
  edited_action?: { name: string; args: Record<string, unknown> } | null;
  message?: string | null;
}

export interface ApprovalRequest {
  decisions?: RunDecision[];
  decision?: 'approve' | 'reject' | 'revise' | 'cancel' | null;
  comment?: string | null;
}

export interface ReportSummary {
  id: number;
  title: string;
  paper_id: number | null;
  processed_document_id: number | null;
  report_type: string;
  status: string;
  source_scope: string;
  created_at: string;
  updated_at: string;
}

export interface ReportRead extends ReportSummary {
  markdown_content: string | null;
  json_content: JsonObject | null;
  source_refs: unknown[];
  evidence: Record<string, unknown>[];
}

export interface UploadArtifactRequest {
  file: File;
  role: ArtifactUploadRole;
  runId?: number | null;
}
