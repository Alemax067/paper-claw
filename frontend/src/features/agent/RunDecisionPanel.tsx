import { useState } from 'react';
import { api } from '../../api/client';
import type { JsonValue, RunDecisionType, RunRead } from '../../api/types';
import { ErrorBanner } from '../../components/ErrorBanner';
import { StatusBadge } from '../../components/StatusBadge';

interface RunDecisionPanelProps {
  run: RunRead | null;
  onRefresh: () => void;
}

interface ActionRequest {
  name?: string;
  args?: Record<string, unknown>;
  description?: string;
}

interface ReviewConfig {
  allowed_decisions?: RunDecisionType[];
  [key: string]: unknown;
}

export function RunDecisionPanel({ run, onRefresh }: RunDecisionPanelProps) {
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const interrupt = latestInterrupt(run);
  const actions = interrupt?.actionRequests ?? [];
  const reviews = interrupt?.reviewConfigs ?? [];

  const submitDecision = async (decision: RunDecisionType) => {
    if (!run) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.submitRunApproval(run.id, {
        decisions: actions.map((_, index) => decisionPayload(decision, reviews[index], comment)),
        comment: comment || null,
      });
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
            {actions.length > 0 ? (
              <div className="stack">
                {actions.map((action, index) => (
                  <article className="search-candidate-card" key={`${action.name ?? 'action'}-${index}`}>
                    <div className="meta-row">
                      <strong>{action.name ?? `Action ${index + 1}`}</strong>
                      <span>{allowedDecisions(reviews[index]).join(', ')}</span>
                    </div>
                    {action.description && <p>{action.description}</p>}
                    {action.args && <pre>{JSON.stringify(action.args, null, 2)}</pre>}
                  </article>
                ))}
              </div>
            ) : (
              <p className="meta-row">This run is waiting for a decision, but no action details were provided.</p>
            )}
            <label>
              Decision note
              <textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Optional note for the run event" />
            </label>
            <div className="button-row">
              <button className="secondary-button" disabled={submitting || !canSubmit(reviews, 'approve')} onClick={() => submitDecision('approve')}>Approve</button>
              <button className="danger-button" disabled={submitting || !canSubmit(reviews, 'reject')} onClick={() => submitDecision('reject')}>Reject</button>
            </div>
            <p className="meta-row">Decisions are submitted in the order requested by the agent.</p>
          </>
        )}
      </div>
    </section>
  );
}

function latestInterrupt(run: RunRead | null): { actionRequests: ActionRequest[]; reviewConfigs: ReviewConfig[] } | null {
  const event = [...(run?.events ?? [])].reverse().find((item) => item.event_type === 'agent_interrupt_requested');
  if (!event) {
    return null;
  }
  return {
    actionRequests: asObjectArray(event.payload.action_requests).map((item) => ({
      name: typeof item.name === 'string' ? item.name : undefined,
      args: asRecord(item.args),
      description: typeof item.description === 'string' ? item.description : undefined,
    })),
    reviewConfigs: asObjectArray(event.payload.review_configs).map((item) => ({
      ...item,
      allowed_decisions: asDecisionArray(item.allowed_decisions),
    })),
  };
}

function decisionPayload(type: RunDecisionType, review: ReviewConfig | undefined, comment: string) {
  if (!allowedDecisions(review).includes(type)) {
    return { type: 'reject' as const, args: comment ? { comment } : undefined };
  }
  return { type, args: comment ? { comment } : undefined };
}

function canSubmit(reviews: ReviewConfig[], decision: RunDecisionType): boolean {
  if (!reviews.length) {
    return decision === 'approve' || decision === 'reject';
  }
  return reviews.every((review) => allowedDecisions(review).includes(decision));
}

function allowedDecisions(review: ReviewConfig | undefined): RunDecisionType[] {
  return review?.allowed_decisions?.length ? review.allowed_decisions : ['approve', 'reject'];
}

function asObjectArray(value: JsonValue | unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [];
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

function asDecisionArray(value: unknown): RunDecisionType[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.filter((item): item is RunDecisionType => item === 'approve' || item === 'edit' || item === 'reject' || item === 'respond');
}
