import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import { getErrorMessage } from '../../api/errors';
import type { RunRead } from '../../api/types';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { usePolling } from '../../hooks/usePolling';
import { MessageComposer } from './MessageComposer';
import { RunDecisionPanel } from './RunDecisionPanel';
import { MessageTranscript } from './MessageTranscript';
import { AgentActivity } from './AgentActivity';
import { SearchSessionDecisionPanel } from '../search/SearchSessionDecisionPanel';

interface AgentPanelProps {
  selectedThreadId: number | null;
  activePaperId: number | null;
  activeRunId: number | null;
  activeRun: RunRead | null;
  refreshToken: number;
  onThreadSelected: (threadId: number) => void;
  onRunSelected: (runId: number) => void;
  onRunLoaded: (run: RunRead | null) => void;
  onRefresh: () => void;
  onActivePaperSelected?: (paperId: number | null) => void;
  onError: (message: string | null) => void;
}

const terminalRunStatuses = new Set(['succeeded', 'failed', 'partial', 'cancelled']);
const cancellableRunStatuses = new Set(['pending', 'running', 'waiting_for_user']);

export function AgentPanel({
  selectedThreadId,
  activePaperId,
  activeRunId,
  activeRun,
  refreshToken,
  onThreadSelected,
  onRunSelected,
  onRunLoaded,
  onRefresh,
  onActivePaperSelected,
  onError,
}: AgentPanelProps) {
  const [submitStatus, setSubmitStatus] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const loader = useCallback(async () => {
    if (selectedThreadId == null) {
      return null;
    }
    return api.getThread(selectedThreadId);
  }, [selectedThreadId]);
  const { data: thread, loading, error, reload } = useAsyncResource(loader, [refreshToken]);

  const loadRun = useCallback(async () => {
    if (activeRunId == null) {
      onRunLoaded(null);
      return;
    }
    const run = await api.getRun(activeRunId);
    onRunLoaded(run);
  }, [activeRunId, onRunLoaded]);

  useEffect(() => {
    reload();
  }, [selectedThreadId, reload]);

  useEffect(() => {
    void loadRun();
  }, [loadRun]);

  useEffect(() => {
    if (selectedThreadId == null || !thread?.runs.length) {
      return;
    }
    if (activeRunId != null && thread.runs.some((run) => run.id === activeRunId)) {
      return;
    }
    const latestRun = [...thread.runs].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0];
    onRunSelected(latestRun.id);
    onRunLoaded(latestRun);
  }, [activeRunId, onRunLoaded, onRunSelected, selectedThreadId, thread?.runs]);

  useEffect(() => {
    if (selectedThreadId == null || !thread) {
      return;
    }
    onActivePaperSelected?.(thread.current_focus_paper_id);
  }, [onActivePaperSelected, selectedThreadId, thread]);

  usePolling(loadRun, 2200, Boolean(activeRunId && (!activeRun || !terminalRunStatuses.has(activeRun.status))));

  useEffect(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: 'end' }));
  }, [selectedThreadId, thread?.messages.length, submitStatus, activeRun?.events.length]);

  const cancelRun = async () => {
    if (!activeRunId || !activeRun || !cancellableRunStatuses.has(activeRun.status)) {
      return;
    }
    onError(null);
    try {
      await api.cancelRun(activeRunId);
      onRefresh();
      void loadRun();
    } catch (caught) {
      onError(getErrorMessage(caught));
    }
  };

  const submitMessage = async (message: string) => {
    onError(null);
    setSubmitStatus('Starting agent run...');
    try {
      const response = await api.sendAgentMessage({
        thread_id: selectedThreadId,
        active_paper_id: activePaperId,
        message,
      });
      onThreadSelected(response.thread_id);
      onRunSelected(response.run_id);
      setSubmitStatus('Agent run is running in the background');
      onRefresh();
      window.setTimeout(() => setSubmitStatus(null), 1800);
    } catch (caught) {
      setSubmitStatus(null);
      onError(getErrorMessage(caught));
    }
  };

  const threadRuns = activeRun ? mergeRuns(thread?.runs ?? [], activeRun) : thread?.runs ?? [];
  const candidateRecommendations = useMemo(() => pendingCandidateRecommendations(activeRun), [activeRun]);
  const showRunDecision = activeRun?.status === 'waiting_for_user';
  const showCancelRun = Boolean(activeRunId && activeRun && cancellableRunStatuses.has(activeRun.status));
  const showRunActivity = Boolean(
    activeRun &&
      activeRun.status !== 'succeeded' &&
      (activeRun.events.length > 0 || !terminalRunStatuses.has(activeRun.status) || activeRun.error_message)
  );

  return (
    <section className="chat-main" aria-label="Chat workspace">
      <header className="chat-status-bar">
        <div>
          <p className="eyebrow">Agent chat</p>
          <h1>{thread?.title ?? 'New research thread'}</h1>
        </div>
        <div className="chat-status-bar__meters">
          {activeRun ? <StatusBadge status={activeRun.status} /> : <span>no active run</span>}
          {activeRunId && <span>run #{activeRunId}</span>}
          {activePaperId ? <span>paper #{activePaperId} pinned</span> : <span>no paper pinned</span>}
          {submitStatus && <span>{submitStatus}</span>}
        </div>
      </header>
      <div className="chat-transcript-scroll">
        <ErrorBanner message={error} />
        {loading && selectedThreadId && <LoadingBlock label="Loading transcript" />}
        <MessageTranscript messages={thread?.messages ?? []} runs={threadRuns} />
        {showRunDecision && (
          <div className="inline-decision-stack">
            <RunDecisionPanel run={activeRun} onRefresh={onRefresh} />
          </div>
        )}
        {candidateRecommendations.length > 0 && (
          <div className="inline-decision-stack">
            {candidateRecommendations.map((recommendation) => (
              <SearchSessionDecisionPanel
                key={recommendation.searchSessionId}
                searchSessionId={recommendation.searchSessionId}
                candidateIds={recommendation.candidateIds}
                recommendationReason={recommendation.reason}
                onRefresh={onRefresh}
                onActivePaperSelected={onActivePaperSelected}
              />
            ))}
          </div>
        )}
        {showRunActivity && activeRun && (
          <article className="message message-assistant message-streaming">
            <div className="meta-row">
              <span>assistant</span>
              <span>{terminalRunStatuses.has(activeRun.status) ? 'run activity' : 'background run'}</span>
              <span>{activeRun.status}</span>
            </div>
            <AgentActivity run={activeRun} />
            {terminalRunStatuses.has(activeRun.status) ? (
              activeRun.error_message ? <p>{activeRun.error_message}</p> : null
            ) : (
              <p>Agent run is continuing on the backend. This view will refresh from persisted events.</p>
            )}
          </article>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-composer-dock">
        <MessageComposer activePaperId={activePaperId} canCancelRun={showCancelRun} onSubmit={submitMessage} onCancelRun={cancelRun} />
      </div>
    </section>
  );
}

interface CandidateRecommendation {
  searchSessionId: number;
  candidateIds: number[];
  reason: string | null;
}

function pendingCandidateRecommendations(run: RunRead | null): CandidateRecommendation[] {
  const finished = new Set<number>();
  const recommendations = new Map<number, CandidateRecommendation>();
  for (const event of run?.events ?? []) {
    const value = event.payload.search_session_id;
    if (typeof value !== 'number') {
      continue;
    }
    if (event.event_type === 'search_candidate_confirmed' || event.event_type === 'search_session_rejected') {
      finished.add(value);
      continue;
    }
    if (event.event_type === 'paper_candidates_recommended') {
      const ids = Array.isArray(event.payload.candidate_ids)
        ? event.payload.candidate_ids.filter((candidateId): candidateId is number => typeof candidateId === 'number')
        : [];
      recommendations.set(value, {
        searchSessionId: value,
        candidateIds: ids,
        reason: typeof event.payload.reason === 'string' ? event.payload.reason : null,
      });
    }
  }
  return [...recommendations.values()].filter((recommendation) => !finished.has(recommendation.searchSessionId));
}

function mergeRuns(runs: RunRead[], activeRun: RunRead): RunRead[] {
  const filtered = runs.filter((run) => run.id !== activeRun.id);
  return [activeRun, ...filtered];
}

