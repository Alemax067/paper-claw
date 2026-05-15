import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { getErrorMessage } from '../../api/errors';
import type { AgentStreamEvent } from '../../api/types';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { MessageComposer } from './MessageComposer';
import { MessageTranscript } from './MessageTranscript';

interface AgentPanelProps {
  selectedThreadId: number | null;
  activePaperId: number | null;
  refreshToken: number;
  onThreadSelected: (threadId: number) => void;
  onRunSelected: (runId: number) => void;
  onRefresh: () => void;
  onError: (message: string | null) => void;
}

export function AgentPanel({ selectedThreadId, activePaperId, refreshToken, onThreadSelected, onRunSelected, onRefresh, onError }: AgentPanelProps) {
  const [streamingText, setStreamingText] = useState('');
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const loader = useCallback(async () => {
    if (selectedThreadId == null) {
      return null;
    }
    return api.getThread(selectedThreadId);
  }, [selectedThreadId]);
  const { data: thread, loading, error, reload } = useAsyncResource(loader, [refreshToken]);

  useEffect(() => {
    reload();
  }, [selectedThreadId, reload]);

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
          } else if (event.type === 'run_failed') {
            setStreamStatus(null);
            onError(event.error ?? 'Agent run failed');
            reload();
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

  return (
    <section className="panel agent-panel">
      <div className="panel-header">
        <p className="eyebrow">Agent uplink</p>
        <h2>{thread?.title ?? 'New research thread'}</h2>
      </div>
      <div className="panel-body stack">
        <ErrorBanner message={error} />
        {loading && selectedThreadId && <LoadingBlock label="Loading transcript" />}
        <MessageTranscript messages={thread?.messages ?? []} />
        {(streamStatus || streamingText) && (
          <article className="message message-assistant">
            <div className="meta-row">
              <span>assistant</span>
              <span>stream</span>
              {streamStatus && <span>{streamStatus}</span>}
            </div>
            {streamingText ? <p>{streamingText}</p> : <p>Waiting for streamed output...</p>}
          </article>
        )}
        <MessageComposer activePaperId={activePaperId} onSubmit={submitMessage} />
      </div>
    </section>
  );
}
