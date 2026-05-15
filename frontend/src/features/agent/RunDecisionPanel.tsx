import { useState } from 'react';
import { api } from '../../api/client';
import type { ApprovalDecision, RunRead } from '../../api/types';
import { ErrorBanner } from '../../components/ErrorBanner';
import { StatusBadge } from '../../components/StatusBadge';

interface RunDecisionPanelProps {
  run: RunRead | null;
  onRefresh: () => void;
}

export function RunDecisionPanel({ run, onRefresh }: RunDecisionPanelProps) {
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submitDecision = async (decision: ApprovalDecision) => {
    if (!run) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.submitRunApproval(run.id, { decision, comment: comment || null });
      setComment('');
      onRefresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Decision failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Human loop</p>
        <h2>Run decision</h2>
      </div>
      <div className="panel-body stack">
        <ErrorBanner message={error} />
        {run && (
          <>
            <div className="meta-row">
              <span>run #{run.id}</span>
              <StatusBadge status={run.status} />
            </div>
            <label>
              Decision note
              <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional note for the run event" />
            </label>
            <div className="button-row">
              <button className="secondary-button" disabled={submitting} onClick={() => submitDecision('approve')}>Approve</button>
              <button className="secondary-button" disabled={submitting} onClick={() => submitDecision('revise')}>Request revision</button>
              <button className="danger-button" disabled={submitting} onClick={() => submitDecision('reject')}>Reject</button>
            </div>
            <p className="meta-row">This run is waiting for user input. Decisions are recorded on the run.</p>
          </>
        )}
      </div>
    </section>
  );
}
