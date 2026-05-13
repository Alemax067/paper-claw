import type { ReactNode } from 'react';

interface AppShellProps {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  activeRunLabel?: string;
  activePaperLabel?: string;
}

export function AppShell({ left, center, right, activeRunLabel = 'no active run', activePaperLabel = 'no paper pinned' }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="top-strip">
        <div>
          <p className="eyebrow">Paper Claw</p>
          <h1>Research command center</h1>
        </div>
        <div className="top-strip__meters" aria-label="Workspace status">
          <span>{activeRunLabel}</span>
          <span>{activePaperLabel}</span>
        </div>
      </header>
      <aside className="left-rail">{left}</aside>
      <main className="command-deck">{center}</main>
      <aside className="research-bay">{right}</aside>
    </div>
  );
}
