import { useState } from 'react';
import { api } from '../../api/client';
import type { ApprovalDecision, RunRead } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
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

  const cancel = async () => {
    if (!run) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.cancelRun(run.id);
      onRefresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Cancel failed');
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
        {!run && <EmptyState title="No run awaiting input" body="When the agent needs a decision, controls appear here." />}
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
              <button className="danger-button" disabled={submitting} onClick={cancel}>Cancel run</button>
            </div>
            <p className="meta-row">Approval and revision record decisions; continuation depends on backend runner support.</p>
          </>
        )}
      </div>
    </section>
  );
}
