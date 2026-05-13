import { useCallback, useMemo, useState } from 'react';
import { api } from './api/client';
import { AppShell } from './components/AppShell';
import { ErrorBanner } from './components/ErrorBanner';
import { PaperArchive } from './features/papers/PaperArchive';
import { PaperDetail } from './features/papers/PaperDetail';
import { ReportIndex } from './features/reports/ReportIndex';
import { ReportReader } from './features/reports/ReportReader';
import { AgentPanel } from './features/agent/AgentPanel';
import { RunTimeline } from './features/agent/RunTimeline';
import { RunDecisionPanel } from './features/agent/RunDecisionPanel';
import { SearchSessionDecisionPanel } from './features/search/SearchSessionDecisionPanel';
import { ThreadList } from './features/threads/ThreadList';
import type { RunRead } from './api/types';

const terminalRunStatuses = new Set(['succeeded', 'failed', 'partial', 'cancelled']);

export function App() {
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [activePaperId, setActivePaperId] = useState<number | null>(null);
  const [activeRun, setActiveRun] = useState<RunRead | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const requestRefresh = useCallback(() => setRefreshToken((value) => value + 1), []);
  const onRunUpdated = useCallback((run: RunRead | null) => {
    setActiveRun(run);
    if (run && terminalRunStatuses.has(run.status)) {
      requestRefresh();
    }
  }, [requestRefresh]);

  const searchSessionIds = useMemo(() => {
    const ids = new Set<number>();
    for (const event of activeRun?.events ?? []) {
      const value = event.payload.search_session_id;
      if (typeof value === 'number') {
        ids.add(value);
      }
    }
    return [...ids];
  }, [activeRun]);

  const activeRunLabel = activeRunId ? `run #${activeRunId}${activeRun ? ` · ${activeRun.status}` : ''}` : undefined;
  const activePaperLabel = activePaperId ? `paper #${activePaperId} pinned` : undefined;

  return (
    <AppShell
      activeRunLabel={activeRunLabel}
      activePaperLabel={activePaperLabel}
      left={
        <>
          <ThreadList
            selectedThreadId={selectedThreadId}
            refreshToken={refreshToken}
            onSelectThread={setSelectedThreadId}
          />
          <PaperArchive
            selectedPaperId={selectedPaperId}
            activePaperId={activePaperId}
            refreshToken={refreshToken}
            onSelectPaper={setSelectedPaperId}
            onSetActivePaper={setActivePaperId}
          />
          <ReportIndex
            selectedReportId={selectedReportId}
            refreshToken={refreshToken}
            onSelectReport={setSelectedReportId}
          />
        </>
      }
      center={
        <>
          <ErrorBanner message={globalError} />
          <AgentPanel
            selectedThreadId={selectedThreadId}
            activePaperId={activePaperId}
            refreshToken={refreshToken}
            onThreadSelected={setSelectedThreadId}
            onRunSelected={setActiveRunId}
            onRefresh={requestRefresh}
            onError={setGlobalError}
          />
          <RunTimeline
            runId={activeRunId}
            refreshToken={refreshToken}
            onRunLoaded={onRunUpdated}
          />
        </>
      }
      right={
        <>
          <RunDecisionPanel run={activeRun} onRefresh={requestRefresh} />
          {searchSessionIds.map((searchSessionId) => (
            <SearchSessionDecisionPanel
              key={searchSessionId}
              searchSessionId={searchSessionId}
              onRefresh={requestRefresh}
            />
          ))}
          <PaperDetail
            paperId={selectedPaperId}
            activeRunId={activeRunId}
            activePaperId={activePaperId}
            refreshToken={refreshToken}
            onSetActivePaper={setActivePaperId}
            onSelectReport={setSelectedReportId}
            onRefresh={requestRefresh}
          />
          <ReportReader
            reportId={selectedReportId}
            onSelectPaper={(paperId) => {
              setSelectedPaperId(paperId);
              setActivePaperId(paperId);
            }}
          />
        </>
      }
    />
  );
}

export { api };
