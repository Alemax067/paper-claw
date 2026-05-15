import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import { ErrorBanner } from '../../components/ErrorBanner';
import type { RunRead } from '../../api/types';
import { AgentPanel } from '../agent/AgentPanel';
import { ThreadList } from '../threads/ThreadList';

interface ChatPageProps {
  selectedThreadId: number | null;
  activePaperId: number | null;
  activeRunId: number | null;
  activeRun: RunRead | null;
  refreshToken: number;
  globalError: string | null;
  onThreadSelected: (threadId: number | null) => void;
  onRunSelected: (runId: number | null) => void;
  onRunUpdated: (run: RunRead | null) => void;
  onRefresh: () => void;
  onError: (message: string | null) => void;
}

const sidebarLimits = {
  min: 240,
  default: 320,
  max: 520,
};

export function ChatPage({
  selectedThreadId,
  activePaperId,
  activeRunId,
  activeRun,
  refreshToken,
  globalError,
  onThreadSelected,
  onRunSelected,
  onRunUpdated,
  onRefresh,
  onError,
}: ChatPageProps) {
  const [sidebarWidth, setSidebarWidth] = useState(sidebarLimits.default);
  const [dragStart, setDragStart] = useState<{ x: number; width: number } | null>(null);

  useEffect(() => {
    if (!dragStart) {
      return;
    }

    const onMove = (event: PointerEvent) => {
      const nextWidth = dragStart.width + event.clientX - dragStart.x;
      setSidebarWidth(Math.min(sidebarLimits.max, Math.max(sidebarLimits.min, nextWidth)));
    };
    const onUp = () => setDragStart(null);

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [dragStart]);

  const startNewChat = () => {
    onThreadSelected(null);
    onRunSelected(null);
    onRunUpdated(null);
    onError(null);
  };

  const archiveThread = useCallback(
    async (threadId: number) => {
      if (!window.confirm('Delete this chat from the active thread list?')) {
        return;
      }
      await api.archiveThread(threadId);
      if (selectedThreadId === threadId) {
        startNewChat();
      }
      onRefresh();
    },
    [onRefresh, selectedThreadId],
  );

  return (
    <div className="chat-page">
      <aside className="chat-sidebar" style={{ width: sidebarWidth }}>
        <div className="chat-sidebar__header">
          <div>
            <p className="eyebrow">Chat</p>
            <h2>Threads</h2>
          </div>
          <button className="primary-button" type="button" onClick={startNewChat}>
            New chat
          </button>
        </div>
        <ThreadList
          selectedThreadId={selectedThreadId}
          refreshToken={refreshToken}
          onSelectThread={onThreadSelected}
          onArchiveThread={archiveThread}
          variant="sidebar"
        />
      </aside>
      <div
        className="chat-sidebar__resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat history"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setDragStart({ x: event.clientX, width: sidebarWidth });
        }}
      />
      <div className="chat-workspace">
        <ErrorBanner message={globalError} />
        <AgentPanel
          selectedThreadId={selectedThreadId}
          activePaperId={activePaperId}
          activeRunId={activeRunId}
          activeRun={activeRun}
          refreshToken={refreshToken}
          onThreadSelected={onThreadSelected}
          onRunSelected={onRunSelected}
          onRunLoaded={onRunUpdated}
          onRefresh={onRefresh}
          onError={onError}
        />
      </div>
    </div>
  );
}
