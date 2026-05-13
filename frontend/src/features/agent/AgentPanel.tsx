import { useCallback, useEffect } from 'react';
import { api } from '../../api/client';
import { getErrorMessage } from '../../api/errors';
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
    try {
      const response = await api.sendAgentMessage({
        thread_id: selectedThreadId,
        active_paper_id: activePaperId,
        message,
      });
      onThreadSelected(response.thread_id);
      onRunSelected(response.run_id);
      onRefresh();
      if (response.error) {
        onError(response.error);
      }
    } catch (caught) {
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
        <MessageComposer activePaperId={activePaperId} onSubmit={submitMessage} />
      </div>
    </section>
  );
}
