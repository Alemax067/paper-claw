import { toApiError } from './errors';
import type {
  AgentMessageRequest,
  AgentMessageResponse,
  ApprovalRequest,
  ArtifactRead,
  ConfirmSearchCandidateRequest,
  PaperDetail,
  PaperSummary,
  RejectSearchSessionRequest,
  ReportRead,
  ReportSummary,
  RunEventRead,
  RunRead,
  SearchSessionRead,
  ThreadDetail,
  ThreadSummary,
  UploadArtifactRequest,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => requestJson<{ status: string }>('/api/health'),

  listThreads: () => requestJson<ThreadSummary[]>('/api/threads'),
  getThread: (threadId: number) => requestJson<ThreadDetail>(`/api/threads/${threadId}`),

  getRun: (runId: number) => requestJson<RunRead>(`/api/runs/${runId}`),
  listRunEvents: (runId: number, afterSequence?: number) => {
    const suffix = afterSequence === undefined ? '' : `?after_sequence=${afterSequence}`;
    return requestJson<RunEventRead[]>(`/api/agent/runs/${runId}/events${suffix}`);
  },
  sendAgentMessage: (request: AgentMessageRequest) =>
    requestJson<AgentMessageResponse>('/api/agent/messages', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
  cancelRun: (runId: number) => requestJson<RunRead>(`/api/agent/runs/${runId}/cancel`, { method: 'POST' }),
  submitRunApproval: (runId: number, request: ApprovalRequest) =>
    requestJson<RunRead>(`/api/agent/runs/${runId}/approval`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listPapers: () => requestJson<PaperSummary[]>('/api/papers'),
  getPaper: (paperId: number) => requestJson<PaperDetail>(`/api/papers/${paperId}`),

  getSearchSession: (searchSessionId: number) => requestJson<SearchSessionRead>(`/api/search-sessions/${searchSessionId}`),
  confirmSearchCandidate: (searchSessionId: number, request: ConfirmSearchCandidateRequest) =>
    requestJson<SearchSessionRead>(`/api/search-sessions/${searchSessionId}/confirm`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),
  rejectSearchSession: (searchSessionId: number, request: RejectSearchSessionRequest) =>
    requestJson<SearchSessionRead>(`/api/search-sessions/${searchSessionId}/reject`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listReports: () => requestJson<ReportSummary[]>('/api/reports'),
  getReport: (reportId: number) => requestJson<ReportRead>(`/api/reports/${reportId}`),

  getArtifact: (artifactId: number) => requestJson<ArtifactRead>(`/api/artifacts/${artifactId}`),
  uploadPaperArtifact: (paperId: number, request: UploadArtifactRequest) => {
    const formData = new FormData();
    formData.append('file', request.file);
    formData.append('role', request.role);
    if (request.runId != null) {
      formData.append('run_id', String(request.runId));
    }
    return requestJson<ArtifactRead>(`/api/papers/${paperId}/artifacts/upload`, {
      method: 'POST',
      body: formData,
    });
  },
};
