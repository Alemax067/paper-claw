import { useCallback } from 'react';
import { api } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { MarkdownMessage } from '../agent/MarkdownMessage';
import { ArtifactUpload } from './ArtifactUpload';

interface PaperDetailProps {
  paperId: number | null;
  activeRunId: number | null;
  activePaperId: number | null;
  refreshToken: number;
  onSetActivePaper: (paperId: number) => void;
  onSelectReport: (reportId: number) => void;
  onRefresh: () => void;
}

export function PaperDetail({ paperId, activeRunId, activePaperId, refreshToken, onSetActivePaper, onSelectReport, onRefresh }: PaperDetailProps) {
  const loader = useCallback(async () => {
    if (paperId == null) {
      return null;
    }
    return api.getPaper(paperId);
  }, [paperId]);
  const { data: paper, loading, error, reload } = useAsyncResource(loader, [refreshToken]);
  const latestReadyDocument = [...(paper?.processed_documents ?? [])]
    .reverse()
    .find((document: Record<string, unknown>) => document.status === 'ready' && typeof document.content_markdown === 'string' && document.content_markdown.length > 0);

  const refresh = () => {
    reload();
    onRefresh();
  };

  return (
    <section className="panel paper-dossier">
      <div className="panel-header">
        <p className="eyebrow">Paper dossier</p>
        <h2>{paper?.title ?? 'No paper selected'}</h2>
      </div>
      <div className="panel-body stack">
        <ErrorBanner message={error} />
        {loading && paperId && <LoadingBlock label="Loading paper" />}
        {!paper && !loading && (
          <EmptyState title="Open a dossier" body="Select a paper from the archive or pin one as active agent context." />
        )}
        {paper && (
          <>
            <div className="meta-row">
              <span>paper #{paper.id}</span>
              <StatusBadge status={paper.status} />
              {paper.year && <span>{paper.year}</span>}
              {paper.venue && <span>{paper.venue}</span>}
              {paper.id === activePaperId && <span>active context</span>}
            </div>
            {paper.abstract && <p>{paper.abstract}</p>}
            <div className="button-row">
              <button className="secondary-button" onClick={() => onSetActivePaper(paper.id)}>Use as active context</button>
            </div>
            <DossierSection title="Identifiers" items={paper.identifiers} />
            <DossierSection title="Source records" items={paper.source_records} />
            <DossierSection title="Artifacts" items={paper.artifacts} />
            <DossierSection title="Parse jobs" items={paper.parse_jobs} />
            <DossierSection title="Processed documents" items={paper.processed_documents} />
            <div className="stack">
              <h3>Parsed document</h3>
              {latestReadyDocument ? (
                <details className="dossier-record" open>
                  <summary>ready document #{String(latestReadyDocument.id)}</summary>
                  <MarkdownMessage content={String(latestReadyDocument.content_markdown)} />
                </details>
              ) : (
                <p className="meta-row">No ready parsed document.</p>
              )}
            </div>
            <div className="stack">
              <h3>Reports</h3>
              {!paper.reports.length && <p className="meta-row">No reports linked.</p>}
              {paper.reports.map((report) => {
                const id = Number(report.id);
                return (
                  <button className="report-card" key={id} onClick={() => onSelectReport(id)}>
                    <div className="meta-row">
                      <span>#{String(report.id)}</span>
                      {typeof report.status === 'string' && <StatusBadge status={report.status} />}
                      {typeof report.report_type === 'string' && <span>{report.report_type}</span>}
                    </div>
                    <h3>{String(report.title ?? 'Untitled report')}</h3>
                  </button>
                );
              })}
            </div>
            <div className="stack">
              <h3>Attach source material</h3>
              <ArtifactUpload paperId={paper.id} activeRunId={activeRunId} onUploaded={refresh} />
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function DossierSection({ title, items }: { title: string; items: Record<string, unknown>[] }) {
  return (
    <div className="stack">
      <h3>{title}</h3>
      {!items.length && <p className="meta-row">No records.</p>}
      {items.map((item, index) => (
        <details className="dossier-record" key={index}>
          <summary>{recordTitle(item, index)}</summary>
          <pre>{JSON.stringify(item, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}

function recordTitle(item: Record<string, unknown>, index: number): string {
  const label = item.title ?? item.role ?? item.kind ?? item.strategy ?? item.type ?? item.id ?? index + 1;
  return String(label);
}
