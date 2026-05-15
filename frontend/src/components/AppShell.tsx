import type { ReactNode } from 'react';

export type AppPage = 'chat' | 'paper' | 'report' | 'memory' | 'task' | 'setting';
export type NavMode = 'icon' | 'title';

interface AppShellProps {
  activePage: AppPage;
  navMode: NavMode;
  activeRunLabel?: string;
  activePaperLabel?: string;
  onSelectPage: (page: AppPage) => void;
  onToggleNavMode: () => void;
  children: ReactNode;
}

const navItems: Array<{ id: AppPage; label: string; icon: string }> = [
  { id: 'chat', label: 'Chat', icon: 'C' },
  { id: 'paper', label: 'Paper', icon: 'P' },
  { id: 'report', label: 'Report', icon: 'R' },
  { id: 'memory', label: 'Memory', icon: 'M' },
  { id: 'task', label: 'Task', icon: 'T' },
  { id: 'setting', label: 'Setting', icon: 'S' },
];

export function AppShell({
  activePage,
  navMode,
  activeRunLabel = 'no active run',
  activePaperLabel = 'no paper pinned',
  onSelectPage,
  onToggleNavMode,
  children,
}: AppShellProps) {
  const expanded = navMode === 'title';

  return (
    <div className={`app-shell app-shell--${navMode}`}>
      <aside className={`activity-bar activity-bar--${navMode}`} aria-label="Primary navigation">
        <div className="activity-bar__brand">
          <span className="activity-bar__mark">PC</span>
          {expanded && (
            <div>
              <p className="eyebrow">Paper Claw</p>
              <strong>Workspace</strong>
            </div>
          )}
        </div>
        <button
          className="activity-bar__toggle"
          type="button"
          onClick={onToggleNavMode}
          aria-label={expanded ? 'Collapse navigation labels' : 'Expand navigation labels'}
        >
          {expanded ? '«' : '»'}
        </button>
        <nav className="activity-nav">
          {navItems.map((item) => (
            <button
              className={`activity-item ${activePage === item.id ? 'is-active' : ''}`}
              type="button"
              key={item.id}
              onClick={() => onSelectPage(item.id)}
              aria-current={activePage === item.id ? 'page' : undefined}
              aria-label={expanded ? undefined : item.label}
              title={item.label}
            >
              <span className="activity-item__icon" aria-hidden="true">
                {item.icon}
              </span>
              {expanded && <span>{item.label}</span>}
            </button>
          ))}
        </nav>
        <div className="activity-bar__status" aria-label="Workspace status">
          <span title={activeRunLabel}>{activeRunLabel}</span>
          <span title={activePaperLabel}>{activePaperLabel}</span>
        </div>
      </aside>
      <main className="page-frame">{children}</main>
    </div>
  );
}
