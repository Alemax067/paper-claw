import { useCallback, useEffect, useRef, useState } from 'react';
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
  onError,
}: AgentPanelProps) {
  const [streamingText, setStreamingText] = useState('');
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [streamRun, setStreamRun] = useState<RunRead | null>(null);
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

  usePolling(loadRun, 2200, Boolean(activeRunId && activeRun && !terminalRunStatuses.has(activeRun.status)));

  useEffect(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ block: 'end' }));
  }, [selectedThreadId, thread?.messages.length, streamingText, activeRun?.events.length]);

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
    setStreamingText('');
    setStreamStatus('Connecting to agent stream...');
    setStreamRun(null);
    let selectedRunId: number | null = null;
    try {
      const response = await api.sendAgentMessageStream(
        {
          thread_id: selectedThreadId,
          active_paper_id: activePaperId,
          message,
        },
        (event: AgentStreamEvent) => {
          if (selectedRunId !== event.run_id) {
            selectedRunId = event.run_id;
            onThreadSelected(event.thread_id);
            onRunSelected(event.run_id);
            onRefresh();
          }
          setStreamRun((current) => updateStreamRun(current, event));
          if (event.type === 'run_started') {
            setStreamStatus('Agent run started');
          } else if (event.type === 'agent_chunk') {
            const mode = typeof event.payload.mode === 'string' ? event.payload.mode : 'chunk';
            setStreamStatus(`Streaming ${mode}`);
            if (mode === 'messages' && event.message) {
              setStreamingText((current) => current + event.message);
            }
          } else if (event.type === 'run_completed') {
            setStreamStatus(null);
            setStreamingText('');
            setStreamRun(null);
            reload();
            void loadRun();
          } else if (event.type === 'run_failed') {
            setStreamStatus(null);
            onError(event.error ?? 'Agent run failed');
            reload();
            void loadRun();
          } else if (event.type === 'run_cancelled') {
            setStreamStatus(null);
            setStreamingText('');
            setStreamRun(null);
            reload();
            void loadRun();
          }
        },
      );
      if (response.error) {
        onError(response.error);
      }
    } catch (caught) {
      setStreamStatus(null);
      onError(getErrorMessage(caught));
    }
  };

  const threadRuns = activeRun ? mergeRuns(thread?.runs ?? [], activeRun) : thread?.runs ?? [];
  const showRunDecision = activeRun?.status === 'waiting_for_user';
  const showCancelRun = Boolean(activeRunId && activeRun && cancellableRunStatuses.has(activeRun.status));

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
          {streamStatus && <span>{streamStatus}</span>}
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
        {(streamStatus || streamingText || streamRun) && (
          <article className="message message-assistant message-streaming">
            <div className="meta-row">
              <span>assistant</span>
              <span>stream</span>
              {streamStatus && <span>{streamStatus}</span>}
            </div>
            {streamRun && <AgentActivity run={streamRun} />}
            {streamingText ? <p>{streamingText}</p> : <p>Waiting for streamed output...</p>}
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

function updateStreamRun(current: RunRead | null, event: AgentStreamEvent): RunRead {
  const now = new Date().toISOString();
  const base = current ?? {
    id: event.run_id,
    thread_id: event.thread_id,
    workflow: 'paper_qa',
    status: event.status ?? 'running',
    error_message: event.error ?? null,
    input_json: null,
    output_json: null,
    events: [],
    created_at: now,
    updated_at: now,
  };
  const run: RunRead = {
    ...base,
    status: event.status ?? base.status,
    error_message: event.error ?? base.error_message,
    updated_at: now,
  };
  if (!event.event_type || event.sequence == null || run.events.some((item) => item.sequence === event.sequence)) {
    return run;
  }
  const runEvent: RunEventRead = {
    id: event.sequence,
    run_id: event.run_id,
    sequence: event.sequence,
    event_type: event.event_type,
    level: event.error ? 'error' : 'info',
    payload: event.payload,
    created_at: now,
  };
  return { ...run, events: [...run.events, runEvent] };
}

function mergeRuns(runs: RunRead[], activeRun: RunRead): RunRead[] {
  const filtered = runs.filter((run) => run.id !== activeRun.id);
  return [activeRun, ...filtered];
}

