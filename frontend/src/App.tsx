import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import { AppShell, type AppPage, type NavMode } from './components/AppShell';
import { PaperArchive } from './features/papers/PaperArchive';
import { PaperDetail } from './features/papers/PaperDetail';
import { ReportIndex } from './features/reports/ReportIndex';
import { ReportReader } from './features/reports/ReportReader';
import { ChatPage } from './features/chat/ChatPage';
import { MemoryPage } from './features/memory/MemoryPage';
import { SettingPage } from './features/settings/SettingPage';
import type { RunRead } from './api/types';

export function App() {
  const [activePage, setActivePage] = useState<AppPage>('chat');
  const [navMode, setNavMode] = useState<NavMode>('title');
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(() => storedNumber('paper-claw:selected-thread-id'));
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(() => storedNumber('paper-claw:active-run-id'));
  const [activePaperId, setActivePaperId] = useState<number | null>(null);
  const [activeRun, setActiveRun] = useState<RunRead | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [globalError, setGlobalError] = useState<string | null>(null);

  useEffect(() => {
    storeNumber('paper-claw:selected-thread-id', selectedThreadId);
  }, [selectedThreadId]);

  useEffect(() => {
    storeNumber('paper-claw:active-run-id', activeRunId);
  }, [activeRunId]);

  const requestRefresh = useCallback(() => setRefreshToken((value) => value + 1), []);
  const onRunUpdated = useCallback((run: RunRead | null) => {
    setActiveRun(run);
  }, []);

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

  const page = (() => {
    if (activePage === 'chat') {
      return (
        <ChatPage
          selectedThreadId={selectedThreadId}
          activePaperId={activePaperId}
          activeRunId={activeRunId}
          activeRun={activeRun}
          refreshToken={refreshToken}
          globalError={globalError}
          onThreadSelected={setSelectedThreadId}
          onRunSelected={setActiveRunId}
          onRunUpdated={onRunUpdated}
          onRefresh={requestRefresh}
          onActivePaperSelected={setActivePaperId}
          onError={setGlobalError}
        />
      );
    }

    if (activePage === 'paper') {
      return (
        <div className="split-page paper-page">
          <aside className="section-sidebar">
            <PaperArchive
              selectedPaperId={selectedPaperId}
              activePaperId={activePaperId}
              refreshToken={refreshToken}
              onSelectPaper={setSelectedPaperId}
              onSetActivePaper={setActivePaperId}
            />
          </aside>
          <main className="workspace-main">
            <PaperDetail
              paperId={selectedPaperId}
              activeRunId={activeRunId}
              activePaperId={activePaperId}
              refreshToken={refreshToken}
              onSetActivePaper={setActivePaperId}
              onSelectReport={(reportId) => {
                setSelectedReportId(reportId);
                setActivePage('report');
              }}
              onRefresh={requestRefresh}
            />
          </main>
        </div>
      );
    }

    if (activePage === 'report') {
      return (
        <div className="split-page report-page">
          <aside className="section-sidebar">
            <ReportIndex selectedReportId={selectedReportId} refreshToken={refreshToken} onSelectReport={setSelectedReportId} />
          </aside>
          <main className="workspace-main">
            <ReportReader
              reportId={selectedReportId}
              onSelectPaper={(paperId) => {
                setSelectedPaperId(paperId);
                setActivePaperId(paperId);
                setActivePage('paper');
              }}
            />
          </main>
        </div>
      );
    }

    if (activePage === 'memory') {
      return <MemoryPage refreshToken={refreshToken} />;
    }

    if (activePage === 'task') {
      return (
        <main className="empty-workspace task-page">
          <div className="empty-state">
            <p className="eyebrow">Task</p>
            <h3>Task workspace</h3>
            <p>This page is intentionally empty while task semantics are still being designed.</p>
          </div>
        </main>
      );
    }

    return <SettingPage />;
  })();

  return (
    <AppShell
      activePage={activePage}
      navMode={navMode}
      activeRunLabel={activeRunLabel}
      activePaperLabel={activePaperLabel}
      onSelectPage={setActivePage}
      onToggleNavMode={() => setNavMode((value) => (value === 'title' ? 'icon' : 'title'))}
    >
      {page}
    </AppShell>
  );
}

function storedNumber(key: string): number | null {
  const raw = window.localStorage.getItem(key);
  if (raw == null) {
    return null;
  }
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function storeNumber(key: string, value: number | null): void {
  if (value == null) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, String(value));
}

export { api };
