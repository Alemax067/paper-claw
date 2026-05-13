import { useCallback } from 'react';
import { api } from '../../api/client';
import { EmptyState } from '../../components/EmptyState';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';

interface ReportReaderProps {
  reportId: number | null;
  onSelectPaper: (paperId: number) => void;
}

export function ReportReader({ reportId, onSelectPaper }: ReportReaderProps) {
  const loader = useCallback(async () => {
    if (reportId == null) {
      return null;
    }
    return api.getReport(reportId);
  }, [reportId]);
  const { data: report, loading, error } = useAsyncResource(loader, [reportId]);

  return (
    <section className="panel report-reader">
      <div className="panel-header">
        <p className="eyebrow">Report reader</p>
        <h2>{report?.title ?? 'No report selected'}</h2>
      </div>
      <div className="panel-body stack">
        <ErrorBanner message={error} />
        {loading && reportId && <LoadingBlock label="Loading report" />}
        {!report && !loading && (
          <EmptyState title="Open a brief" body="Select a report from the evidence briefs index." />
        )}
        {report && (
          <>
            <div className="meta-row">
              <span>report #{report.id}</span>
              <StatusBadge status={report.status} />
              <span>{report.report_type}</span>
              <span>{report.source_scope}</span>
            </div>
            {report.paper_id && (
              <button className="secondary-button" onClick={() => onSelectPaper(report.paper_id!)}>Open linked paper</button>
            )}
            <div className="report-content">{report.markdown_content || 'No markdown content.'}</div>
            <div className="stack">
              <h3>Evidence</h3>
              {!report.evidence.length && <p className="meta-row">No evidence rows.</p>}
              {report.evidence.map((item, index) => (
                <details className="dossier-record" key={index}>
                  <summary>{String(item.evidence_type ?? item.id ?? index + 1)}</summary>
                  <pre>{JSON.stringify(item, null, 2)}</pre>
                </details>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
