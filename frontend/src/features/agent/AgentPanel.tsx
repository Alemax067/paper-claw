import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { getErrorMessage } from '../../api/errors';
import type { AgentStreamEvent, RunRead } from '../../api/types';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { usePolling } from '../../hooks/usePolling';
import { SearchSessionDecisionPanel } from '../search/SearchSessionDecisionPanel';
import { MessageComposer } from './MessageComposer';
import { RunDecisionPanel } from './RunDecisionPanel';
import { MessageTranscript } from './MessageTranscript';

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

  const submitMessage = async (message: string) => {
    onError(null);
    setStreamingText('');
    setStreamStatus('Connecting to agent stream...');
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
            reload();
            void loadRun();
          } else if (event.type === 'run_failed') {
            setStreamStatus(null);
            onError(event.error ?? 'Agent run failed');
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
  const searchSessionIds = activeRun ? activeSearchSessionIds(activeRun) : [];
  const hasDecisionControls = Boolean(activeRun || searchSessionIds.length);

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
        {hasDecisionControls && (
          <div className="inline-decision-stack">
            <RunDecisionPanel run={activeRun} onRefresh={onRefresh} />
            {searchSessionIds.map((searchSessionId) => (
              <SearchSessionDecisionPanel key={searchSessionId} searchSessionId={searchSessionId} onRefresh={onRefresh} />
            ))}
          </div>
        )}
        {(streamStatus || streamingText) && (
          <article className="message message-assistant message-streaming">
            <div className="meta-row">
              <span>assistant</span>
              <span>stream</span>
              {streamStatus && <span>{streamStatus}</span>}
            </div>
            {streamingText ? <p>{streamingText}</p> : <p>Waiting for streamed output...</p>}
          </article>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-composer-dock">
        <MessageComposer activePaperId={activePaperId} onSubmit={submitMessage} />
      </div>
    </section>
  );
}

function mergeRuns(runs: RunRead[], activeRun: RunRead): RunRead[] {
  const filtered = runs.filter((run) => run.id !== activeRun.id);
  return [activeRun, ...filtered];
}

function activeSearchSessionIds(run: RunRead): number[] {
  const ids = new Set<number>();
  for (const event of run.events) {
    const value = event.payload.search_session_id;
    if (typeof value === 'number') {
      ids.add(value);
    }
  }
  return [...ids];
}
