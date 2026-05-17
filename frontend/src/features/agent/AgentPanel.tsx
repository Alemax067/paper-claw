import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api/client';
import { getErrorMessage } from '../../api/errors';
import type { AgentStreamEvent, RunEventRead, RunRead } from '../../api/types';
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
  const terminalRefreshKeyRef = useRef<string | null>(null);
  const activeRunRef = useRef<RunRead | null>(null);

  useEffect(() => {
    activeRunRef.current = activeRun;
  }, [activeRun]);

  const loader = useCallback(async () => {
    if (selectedThreadId == null) {
      return null;
    }
    return api.getThread(selectedThreadId);
  }, [selectedThreadId]);
  const { data: thread, loading, error, reload, setData: setThread } = useAsyncResource(loader, [refreshToken]);

  const loadRun = useCallback(async () => {
    if (activeRunId == null) {
      onRunLoaded(null);
      return;
    }
    const run = await api.getRun(activeRunId);
    onRunLoaded(run);
    if (terminalRunStatuses.has(run.status)) {
      const refreshKey = `${run.id}:${run.status}:${run.updated_at}`;
      if (terminalRefreshKeyRef.current !== refreshKey) {
        terminalRefreshKeyRef.current = refreshKey;
        reload();
        onRefresh();
      }
    }
  }, [activeRunId, onRefresh, onRunLoaded, reload]);

  useEffect(() => {
    terminalRefreshKeyRef.current = null;
  }, [activeRunId, selectedThreadId]);

  useEffect(() => {
    reload();
  }, [selectedThreadId, reload]);

  useEffect(() => {
    void loadRun();
  }, [loadRun]);

  useEffect(() => {
    if (selectedThreadId == null || activeRunId != null || !thread?.runs.length) {
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

  const currentRun = activeRun?.id === activeRunId && activeRun.thread_id === selectedThreadId ? activeRun : null;
  const activeRunBelongsToSelectedThread = Boolean(activeRunId && activeRun?.thread_id === selectedThreadId);
  const displayedRunId = activeRunBelongsToSelectedThread ? activeRunId : null;
  const hasAssistantMessageForActiveRun = Boolean(
    displayedRunId && thread?.messages.some((message) => message.role === 'assistant' && message.run_id === displayedRunId)
  );
  const isCurrentRunTerminal = Boolean(currentRun && terminalRunStatuses.has(currentRun.status));
  const isWaitingForAssistantMessage = Boolean(
    displayedRunId && currentRun?.status === 'succeeded' && !hasAssistantMessageForActiveRun
  );

  usePolling(loadRun, 2200, Boolean(displayedRunId && (!currentRun || !terminalRunStatuses.has(currentRun.status))));
  usePolling(reload, 700, isWaitingForAssistantMessage);

  useEffect(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: 'end' }));
  }, [selectedThreadId, thread?.messages.length, submitStatus, currentRun?.events.length, isWaitingForAssistantMessage]);

  const cancelRun = async () => {
    if (!activeRunId || !currentRun || !cancellableRunStatuses.has(currentRun.status)) {
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
      const response = await api.sendAgentMessageStream(
        {
          thread_id: selectedThreadId,
          active_paper_id: activePaperId,
          message,
        },
        async (event) => {
          if (event.type === 'run_started') {
            onThreadSelected(event.thread_id);
            const startedRun = runFromStreamEvent(event);
            activeRunRef.current = startedRun;
            onRunLoaded(startedRun);
            onRunSelected(event.run_id);
            setSubmitStatus('Agent run is running');
            setThread(await api.getThread(event.thread_id));
            onRefresh();
            return;
          }
          const streamedRun = mergeStreamEventIntoRun(activeRunRef.current?.id === event.run_id ? activeRunRef.current : null, event);
          if (streamedRun) {
            activeRunRef.current = streamedRun;
            onRunLoaded(streamedRun);
          }
          if (event.type === 'run_completed' || event.type === 'run_failed' || event.type === 'run_waiting_for_user') {
            const persistedRun = await api.getRun(event.run_id);
            activeRunRef.current = persistedRun;
            onRunLoaded(persistedRun);
            setThread(await api.getThread(event.thread_id));
            onRefresh();
          }
        }
      );
      onThreadSelected(response.thread_id);
      onRunSelected(response.run_id);
      const persistedRun = await api.getRun(response.run_id);
      activeRunRef.current = persistedRun;
      onRunLoaded(persistedRun);
      setThread(await api.getThread(response.thread_id));
      setSubmitStatus(null);
      onRefresh();
    } catch (caught) {
      setSubmitStatus(null);
      onError(getErrorMessage(caught));
    }
  };

  const threadRuns = currentRun ? mergeRuns(thread?.runs ?? [], currentRun) : thread?.runs ?? [];
  const candidateRecommendations = useMemo(() => pendingCandidateRecommendations(currentRun), [currentRun]);
  const showRunDecision = currentRun?.status === 'waiting_for_user';
  const showCancelRun = Boolean(activeRunId && currentRun && cancellableRunStatuses.has(currentRun.status));
  const showRunActivity = Boolean(
    currentRun &&
      (!isCurrentRunTerminal || currentRun.error_message || isWaitingForAssistantMessage) &&
      (currentRun.events.length > 0 || !isCurrentRunTerminal || currentRun.error_message || isWaitingForAssistantMessage)
  );

  return (
    <section className="chat-main" aria-label="Chat workspace">
      <header className="chat-status-bar">
        <div>
          <p className="eyebrow">Agent chat</p>
          <h1>{thread?.title ?? 'New research thread'}</h1>
        </div>
        <div className="chat-status-bar__meters">
          {currentRun ? <StatusBadge status={currentRun.status} /> : <span>{displayedRunId ? 'loading run' : 'no active run'}</span>}
          {displayedRunId && <span>run #{displayedRunId}</span>}
          {activePaperId ? <span>paper #{activePaperId} pinned</span> : <span>no paper pinned</span>}
          {submitStatus && <span>{submitStatus}</span>}
        </div>
      </header>
      <div className="chat-transcript-scroll">
        <ErrorBanner message={error} />
        {loading && selectedThreadId && <LoadingBlock label="Loading transcript" />}
        <MessageTranscript messages={thread?.messages ?? []} runs={threadRuns} />
        {showRunDecision && currentRun && (
          <div className="inline-decision-stack">
            <RunDecisionPanel run={currentRun} onRefresh={onRefresh} />
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
        {showRunActivity && currentRun && (
          <article className="message message-assistant message-streaming">
            <div className="meta-row">
              <span>assistant</span>
              <span>{isCurrentRunTerminal ? 'run activity' : 'background run'}</span>
              <span>{currentRun.status}</span>
            </div>
            <AgentActivity run={currentRun} />
            {isWaitingForAssistantMessage ? (
              <p>Agent run succeeded. Loading assistant reply...</p>
            ) : isCurrentRunTerminal ? (
              currentRun.error_message ? <p>{currentRun.error_message}</p> : null
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

function runFromStreamEvent(event: AgentStreamEvent): RunRead {
  const now = new Date().toISOString();
  const runEvent = streamEventToRunEvent(event);
  return {
    id: event.run_id,
    thread_id: event.thread_id,
    workflow: 'paper_qa',
    status: event.status ?? 'running',
    error_message: event.error ?? null,
    input_json: null,
    output_json: null,
    events: runEvent ? [runEvent] : [],
    created_at: now,
    updated_at: now,
  };
}

function mergeStreamEventIntoRun(run: RunRead | null, event: AgentStreamEvent): RunRead | null {
  if (!event.status && event.sequence == null && event.event_type == null) {
    return run;
  }
  const base = run ?? runFromStreamEvent(event);
  const runEvent = streamEventToRunEvent(event);
  const events = runEvent ? mergeRunEvents(base.events, runEvent) : base.events;
  return {
    ...base,
    thread_id: event.thread_id,
    status: event.status ?? base.status,
    error_message: event.error ?? base.error_message,
    events,
    updated_at: new Date().toISOString(),
  };
}

function streamEventToRunEvent(event: AgentStreamEvent): RunEventRead | null {
  if (event.sequence == null || event.event_type == null) {
    return null;
  }
  return {
    id: event.sequence,
    run_id: event.run_id,
    sequence: event.sequence,
    event_type: event.event_type,
    level: event.error ? 'error' : event.event_type.includes('failed') ? 'error' : 'info',
    payload: event.payload,
    created_at: new Date().toISOString(),
  };
}

function mergeRunEvents(events: RunEventRead[], event: RunEventRead): RunEventRead[] {
  const filtered = events.filter((item) => item.sequence !== event.sequence);
  return [...filtered, event].sort((left, right) => left.sequence - right.sequence);
}

