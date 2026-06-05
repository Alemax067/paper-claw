import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { ArxivTaskHarvestJobRead, ArxivTaskSubscriptionRead, ArxivTaskSubscriptionTestPaperRead, ArxivTaskSubscriptionTestRead } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { usePolling } from '../../hooks/usePolling';

const runningStatuses = new Set(['running', 'pending', 'stopping']);

type SubscriptionDraft = {
  id: number | null;
  name: string;
  query: string;
  description: string;
  enabled: boolean;
  originalQuery: string;
};

const emptyDraft: SubscriptionDraft = {
  id: null,
  name: '',
  query: '',
  description: '',
  enabled: true,
  originalQuery: '',
};

export function ArxivTaskPage() {
  const loader = useCallback(() => api.getArxivTaskStatus(), []);
  const { data: status, loading, error, reload } = useAsyncResource(loader, []);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [dailyEnabled, setDailyEnabled] = useState(true);
  const [runTime, setRunTime] = useState('08:00');
  const [selectedCoverageSubscriptionId, setSelectedCoverageSubscriptionId] = useState<number | null>(null);
  const [historySubscriptionIds, setHistorySubscriptionIds] = useState<number[]>([]);
  const [historyStart, setHistoryStart] = useState(() => defaultDatetimeLocal(-7));
  const [historyEnd, setHistoryEnd] = useState(() => defaultDatetimeLocal(0));
  const [draft, setDraft] = useState<SubscriptionDraft>(emptyDraft);
  const [testResult, setTestResult] = useState<ArxivTaskSubscriptionTestRead | null>(null);

  useEffect(() => {
    if (!status) {
      return;
    }
    setDailyEnabled(status.daily_config.enabled);
    setRunTime(status.daily_config.run_time);
    setSelectedCoverageSubscriptionId((current) => current ?? status.coverage_subscription_ids[0] ?? status.enabled_subscription_ids[0] ?? status.subscriptions[0]?.id ?? null);
    setHistorySubscriptionIds((current) => (current.length ? current : status.enabled_subscription_ids.slice(0, 1)));
  }, [status]);

  const shouldPoll = Boolean(status?.active_job && runningStatuses.has(status.active_job.status));
  usePolling(reload, 2500, shouldPoll);

  const subscriptionById = useMemo(() => new Map((status?.subscriptions ?? []).map((subscription) => [subscription.id, subscription])), [status?.subscriptions]);
  const selectedWindows = useMemo(() => {
    return (status?.recent_windows ?? []).filter((window) => selectedCoverageSubscriptionId == null || window.subscription_id === selectedCoverageSubscriptionId);
  }, [selectedCoverageSubscriptionId, status?.recent_windows]);
  const dailyJobs = useMemo(() => (status?.recent_jobs ?? []).filter((job) => job.kind === 'daily'), [status?.recent_jobs]);
  const historyJobs = useMemo(() => (status?.recent_jobs ?? []).filter((job) => job.kind === 'history'), [status?.recent_jobs]);
  const queryNeedsTest = draft.query.trim().length > 0 && (draft.id == null || draft.query !== draft.originalQuery);
  const hasCurrentQueryTest = Boolean(testResult && testResult.query === draft.query);

  const runAction = async (action: () => Promise<unknown>) => {
    setActionError(null);
    setSaving(true);
    try {
      await action();
      reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Task action failed');
    } finally {
      setSaving(false);
    }
  };

  const saveDailyConfig = () => runAction(() => api.updateArxivTaskDailyConfig({ enabled: dailyEnabled, run_time: runTime }));
  const runDailyNow = () => runAction(() => api.runArxivTaskDailyNow());

  const resetDraft = () => {
    setDraft(emptyDraft);
    setTestResult(null);
    setActionError(null);
  };

  const editSubscription = (subscription: ArxivTaskSubscriptionRead) => {
    setDraft({
      id: subscription.id,
      name: subscription.name,
      query: subscription.query,
      description: subscription.description ?? '',
      enabled: subscription.enabled,
      originalQuery: subscription.query,
    });
    setTestResult(null);
    setActionError(null);
  };

  const updateDraft = (patch: Partial<SubscriptionDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    if (patch.query !== undefined) {
      setTestResult(null);
    }
  };

  const testQuery = async () => {
    const query = draft.query.trim();
    if (!query) {
      setActionError('Enter an arXiv advanced query before testing.');
      return;
    }
    setActionError(null);
    setTesting(true);
    try {
      const result = await api.testArxivTaskSubscriptionQuery({ query: draft.query, max_results: 5 });
      setTestResult(result);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Query test failed');
      setTestResult(null);
    } finally {
      setTesting(false);
    }
  };

  const saveSubscription = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim()) {
      setActionError('Subscription name is required.');
      return;
    }
    if (!draft.query.trim()) {
      setActionError('arXiv query is required.');
      return;
    }
    if (queryNeedsTest && !hasCurrentQueryTest) {
      setActionError('Test this query and review the preview before saving.');
      return;
    }
    const request = {
      name: draft.name.trim(),
      query: draft.query,
      description: draft.description.trim() || null,
      enabled: draft.enabled,
    };
    runAction(async () => {
      if (draft.id == null) {
        await api.createArxivTaskSubscription(request);
      } else {
        await api.updateArxivTaskSubscription(draft.id, request);
      }
      resetDraft();
    });
  };

  const toggleSubscriptionEnabled = (subscription: ArxivTaskSubscriptionRead) => {
    return runAction(() => api.updateArxivTaskSubscription(subscription.id, {
      name: subscription.name,
      query: subscription.query,
      description: subscription.description,
      enabled: !subscription.enabled,
    }));
  };

  const deleteSubscription = (subscription: ArxivTaskSubscriptionRead) => {
    if (!window.confirm(`Delete subscription "${subscription.name}"? Harvested links and windows for it will be removed.`)) {
      return;
    }
    return runAction(() => api.deleteArxivTaskSubscription(subscription.id));
  };

  const toggleHistorySubscription = (subscriptionId: number) => {
    setHistorySubscriptionIds((current) => (current.includes(subscriptionId) ? current.filter((value) => value !== subscriptionId) : [...current, subscriptionId].sort((left, right) => left - right)));
  };

  const createHistoryJob = (event: FormEvent) => {
    event.preventDefault();
    if (!historySubscriptionIds.length) {
      setActionError('Select at least one arXiv subscription for history backfill.');
      return;
    }
    runAction(() => api.createArxivTaskHistoryJob({ subscription_ids: historySubscriptionIds, start_time: toIso(historyStart), end_time: toIso(historyEnd) }));
  };

  const jobAction = (job: ArxivTaskHarvestJobRead, action: 'start' | 'pause' | 'stop') => {
    if (action === 'start') {
      return runAction(() => api.startArxivTaskHistoryJob(job.id));
    }
    if (action === 'pause') {
      return runAction(() => api.pauseArxivTaskHistoryJob(job.id));
    }
    return runAction(() => api.stopArxivTaskHistoryJob(job.id));
  };

  return (
    <main className="task-page task-workspace">
      <header className="workspace-header task-hero">
        <div>
          <p className="eyebrow">Task · arXiv</p>
          <h1>Metadata harvest console</h1>
          <p>Run raw arXiv advanced-query subscriptions through a serialized harvest queue, with daily windows and historical backfills.</p>
        </div>
        {status && (
          <div className="task-hero__meters">
            <Metric label="enabled subscriptions" value={status.enabled_subscription_ids.length} />
            <Metric label="task papers" value={status.total_papers} />
            <Metric label="covered subscriptions" value={status.coverage_subscription_ids.length} />
          </div>
        )}
      </header>

      <ErrorBanner message={error} />
      <ErrorBanner message={actionError} />
      {loading && <LoadingBlock label="Loading arXiv task state" />}
      {!status && !loading && <EmptyState title="No task state" body="Run migrations and reload the backend to initialize arXiv task tables." />}

      {status && (
        <div className="task-grid">
          <section className="panel task-panel--wide">
            <div className="panel-header task-panel-header-row">
              <div>
                <p className="eyebrow">Subscriptions</p>
                <h2>Advanced queries</h2>
              </div>
              {draft.id != null && <button className="secondary-button" type="button" disabled={saving} onClick={resetDraft}>New subscription</button>}
            </div>
            <div className="panel-body task-subscription-layout">
              <form className="task-subscription-form" onSubmit={saveSubscription}>
                <label>
                  Name
                  <input value={draft.name} onChange={(event) => updateDraft({ name: event.target.value })} placeholder="LLM agents" />
                </label>
                <label>
                  Query
                  <textarea value={draft.query} onChange={(event) => updateDraft({ query: event.target.value })} placeholder="cat:cs.AI AND (ti:agent OR abs:agent)" rows={5} />
                </label>
                <label>
                  Description
                  <textarea value={draft.description} onChange={(event) => updateDraft({ description: event.target.value })} rows={3} />
                </label>
                <label className="task-check-row">
                  <input type="checkbox" checked={draft.enabled} onChange={(event) => updateDraft({ enabled: event.target.checked })} />
                  <span>Enabled for daily runs</span>
                </label>
                <div className="button-row">
                  <button className="secondary-button" type="button" disabled={saving || testing || !draft.query.trim()} onClick={testQuery}>Test query</button>
                  <button className="primary-button" type="submit" disabled={saving || testing || (queryNeedsTest && !hasCurrentQueryTest)}>
                    {draft.id == null ? 'Save subscription' : 'Update subscription'}
                  </button>
                </div>
              </form>

              <div className="task-query-preview">
                <div className="section-heading-row">
                  <h3>Query preview</h3>
                  {testing && <span>testing...</span>}
                  {testResult && <span>{testResult.total_results} total</span>}
                </div>
                {testResult ? <QueryPreview result={testResult} /> : <EmptyState title="No preview" body="Test the query before saving a new or changed subscription." />}
              </div>

              <SubscriptionList
                subscriptions={status.subscriptions}
                activeId={draft.id}
                saving={saving}
                onEdit={editSubscription}
                onToggleEnabled={toggleSubscriptionEnabled}
                onDelete={deleteSubscription}
              />
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <p className="eyebrow">Daily</p>
              <h2>Incremental queue</h2>
            </div>
            <div className="panel-body stack">
              <div className="task-toggle-row">
                <label className="task-check-row">
                  <input type="checkbox" checked={dailyEnabled} onChange={(event) => setDailyEnabled(event.target.checked)} />
                  <span>Enable scheduler</span>
                </label>
                <label>
                  Run time UTC
                  <input type="time" value={runTime} onChange={(event) => setRunTime(event.target.value)} />
                </label>
              </div>
              <div className="button-row">
                <button className="secondary-button" type="button" disabled={saving} onClick={saveDailyConfig}>Save schedule</button>
                <button className="primary-button" type="button" disabled={saving} onClick={runDailyNow}>Run daily now</button>
              </div>
              <dl className="task-facts">
                <Fact label="last started" value={formatDateTime(status.daily_config.last_started_at)} />
                <Fact label="last finished" value={formatDateTime(status.daily_config.last_finished_at)} />
                <Fact label="active job" value={status.active_job ? `#${status.active_job.id} · ${status.active_job.kind}` : 'none'} />
              </dl>
              <JobList jobs={dailyJobs.slice(0, 4)} emptyTitle="No daily jobs yet" subscriptionById={subscriptionById} />
            </div>
          </section>

          <section className="panel task-panel--wide">
            <div className="panel-header task-panel-header-row">
              <div>
                <p className="eyebrow">Coverage</p>
                <h2>Retrieved windows</h2>
              </div>
              <select value={selectedCoverageSubscriptionId ?? ''} onChange={(event) => setSelectedCoverageSubscriptionId(Number(event.target.value) || null)}>
                {status.subscriptions.map((subscription) => <option key={subscription.id} value={subscription.id}>{subscription.name}</option>)}
              </select>
            </div>
            <div className="panel-body">
              {selectedWindows.length ? (
                <div className="task-window-rail">
                  {selectedWindows.slice(0, 24).map((window) => (
                    <div key={window.id} className="task-window-card">
                      <div className="meta-row">
                        <StatusBadge status={window.status} />
                        <span>{window.kind}</span>
                        <span>{formatDateTime(window.window_start)} to {formatDateTime(window.window_end)}</span>
                      </div>
                      <div className="task-window-card__bar" />
                      <p className="task-query-line">{window.query_snapshot}</p>
                      <div className="meta-row">
                        <span>{window.fetched_count} fetched</span>
                        <span>{window.inserted_count} new</span>
                        <span>{window.updated_count} updated</span>
                        {window.total_results != null && <span>{window.total_results} total</span>}
                        {window.warning_code && <span>{window.warning_code}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No windows for this subscription" body="Run Daily or create a history backfill to establish coverage." />
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <p className="eyebrow">History</p>
              <h2>Backfill jobs</h2>
            </div>
            <div className="panel-body stack">
              <form className="stack" onSubmit={createHistoryJob}>
                <SubscriptionPicker subscriptions={status.subscriptions} selectedIds={historySubscriptionIds} onToggle={toggleHistorySubscription} />
                <label>
                  Start time
                  <input type="datetime-local" value={historyStart} onChange={(event) => setHistoryStart(event.target.value)} />
                </label>
                <label>
                  End time
                  <input type="datetime-local" value={historyEnd} onChange={(event) => setHistoryEnd(event.target.value)} />
                </label>
                <button className="primary-button" type="submit" disabled={saving}>Create history job</button>
              </form>

              {historyJobs.length ? (
                <div className="stack">
                  {historyJobs.map((job) => (
                    <article key={job.id} className="task-job-card">
                      <div className="task-job-card__header">
                        <div>
                          <div className="meta-row"><StatusBadge status={job.status} /><span>job #{job.id}</span></div>
                          <h3>{jobSubscriptionNames(job, subscriptionById)}</h3>
                        </div>
                        <div className="button-row">
                          <button className="secondary-button" type="button" disabled={saving || job.status === 'running'} onClick={() => jobAction(job, 'start')}>Start</button>
                          <button className="secondary-button" type="button" disabled={saving || job.status !== 'running'} onClick={() => jobAction(job, 'pause')}>Pause</button>
                          <button className="danger-button" type="button" disabled={saving || ['stopped', 'succeeded'].includes(job.status)} onClick={() => jobAction(job, 'stop')}>Stop</button>
                        </div>
                      </div>
                      <div className="meta-row">
                        <span>{formatDateTime(job.requested_start)} to {formatDateTime(job.requested_end)}</span>
                        <span>{statsLabel(job.stats)}</span>
                      </div>
                      {job.error_message && <p className="task-error-text">{job.error_message}</p>}
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="No history jobs" body="Create a paused backfill job, then start it when the system is idle." />
              )}
            </div>
          </section>

          <section className="panel task-panel--wide">
            <div className="panel-header">
              <p className="eyebrow">Metadata</p>
              <h2>Latest harvested papers</h2>
            </div>
            <div className="panel-body">
              {status.recent_papers.length ? (
                <div className="task-paper-list">
                  {status.recent_papers.map((paper) => (
                    <article key={paper.id} className="task-paper-card">
                      <div className="meta-row">
                        <span>{paper.arxiv_id}</span>
                        {paper.primary_category && <span>{paper.primary_category}</span>}
                        <span>{formatDate(paper.published_at)}</span>
                      </div>
                      <h3>{paper.title}</h3>
                      <p>{paper.abstract || 'No abstract available.'}</p>
                      <div className="meta-row">
                        <span>{stringifyAuthors(paper.authors).slice(0, 4).join(', ')}</span>
                        {paper.landing_page_url && <a href={paper.landing_page_url} target="_blank" rel="noreferrer">arXiv</a>}
                        {paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer">pdf</a>}
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState title="No harvested metadata" body="Task papers will appear here without changing the curated Papers archive." />
              )}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="task-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function SubscriptionList({ subscriptions, activeId, saving, onEdit, onToggleEnabled, onDelete }: { subscriptions: ArxivTaskSubscriptionRead[]; activeId: number | null; saving: boolean; onEdit: (subscription: ArxivTaskSubscriptionRead) => void; onToggleEnabled: (subscription: ArxivTaskSubscriptionRead) => void; onDelete: (subscription: ArxivTaskSubscriptionRead) => void }) {
  if (!subscriptions.length) {
    return <EmptyState title="No subscriptions" body="Create a subscription from an arXiv advanced query to start harvesting." />;
  }
  return (
    <div className="task-subscription-list">
      {subscriptions.map((subscription) => (
        <article key={subscription.id} className={`task-subscription-card ${activeId === subscription.id ? 'is-selected' : ''}`}>
          <div>
            <div className="meta-row">
              <StatusBadge status={subscription.enabled ? 'enabled' : 'disabled'} />
              <span>#{subscription.id}</span>
              <span>{formatDateTime(subscription.last_refreshed_at)}</span>
            </div>
            <h3>{subscription.name}</h3>
            {subscription.description && <p>{subscription.description}</p>}
            <pre>{subscription.query}</pre>
          </div>
          <div className="button-row">
            <button className="secondary-button" type="button" disabled={saving} onClick={() => onEdit(subscription)}>Edit</button>
            <button className="secondary-button" type="button" disabled={saving} onClick={() => onToggleEnabled(subscription)}>{subscription.enabled ? 'Disable' : 'Enable'}</button>
            <button className="danger-button" type="button" disabled={saving} onClick={() => onDelete(subscription)}>Delete</button>
          </div>
        </article>
      ))}
    </div>
  );
}

function SubscriptionPicker({ subscriptions, selectedIds, onToggle }: { subscriptions: ArxivTaskSubscriptionRead[]; selectedIds: number[]; onToggle: (subscriptionId: number) => void }) {
  if (!subscriptions.length) {
    return <EmptyState title="No subscriptions" body="Create a subscription before backfilling history." />;
  }
  return (
    <div className="task-chip-grid">
      {subscriptions.map((subscription) => (
        <label key={subscription.id} className={`task-subscription-chip ${selectedIds.includes(subscription.id) ? 'is-selected' : ''}`}>
          <input type="checkbox" checked={selectedIds.includes(subscription.id)} onChange={() => onToggle(subscription.id)} />
          <span>{subscription.name}</span>
        </label>
      ))}
    </div>
  );
}

function QueryPreview({ result }: { result: ArxivTaskSubscriptionTestRead }) {
  if (!result.papers.length) {
    return <EmptyState title="No results" body="The query is valid but returned no preview papers." />;
  }
  return (
    <div className="task-preview-list">
      {result.papers.map((paper) => <PreviewPaper key={paper.arxiv_id} paper={paper} />)}
    </div>
  );
}

function PreviewPaper({ paper }: { paper: ArxivTaskSubscriptionTestPaperRead }) {
  return (
    <article className="task-preview-card">
      <div className="meta-row">
        <span>{paper.arxiv_id}</span>
        {paper.primary_category && <span>{paper.primary_category}</span>}
        <span>{formatDate(paper.published_at)}</span>
      </div>
      <h4>{paper.title}</h4>
      <p>{paper.abstract || 'No abstract available.'}</p>
      <div className="meta-row">
        <span>{paper.authors.slice(0, 3).join(', ')}</span>
        {paper.landing_page_url && <a href={paper.landing_page_url} target="_blank" rel="noreferrer">arXiv</a>}
      </div>
    </article>
  );
}

function JobList({ jobs, emptyTitle, subscriptionById }: { jobs: ArxivTaskHarvestJobRead[]; emptyTitle: string; subscriptionById: Map<number, ArxivTaskSubscriptionRead> }) {
  if (!jobs.length) {
    return <EmptyState title={emptyTitle} body="The scheduler records each harvest attempt here." />;
  }
  return (
    <div className="timeline">
      {jobs.map((job) => (
        <div key={job.id} className="timeline-event">
          <div className="meta-row">
            <StatusBadge status={job.status} />
            <span>#{job.id}</span>
            <span>{formatDateTime(job.started_at || job.created_at)}</span>
          </div>
          <div className="meta-row">
            <span>{jobSubscriptionNames(job, subscriptionById)}</span>
            <span>{statsLabel(job.stats)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function jobSubscriptionNames(job: ArxivTaskHarvestJobRead, subscriptionById: Map<number, ArxivTaskSubscriptionRead>): string {
  const names = job.subscription_ids.map((id) => subscriptionById.get(id)?.name ?? `#${id}`);
  return names.join(', ') || 'no subscriptions';
}

function defaultDatetimeLocal(dayOffset: number): string {
  const date = new Date();
  date.setDate(date.getDate() + dayOffset);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

function toIso(value: string): string {
  return new Date(value).toISOString();
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return 'none';
  }
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

function formatDate(value: string | null): string {
  if (!value) {
    return 'unknown date';
  }
  return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: '2-digit' }).format(new Date(value));
}

function statsLabel(stats: Record<string, number>): string {
  const fetched = stats.fetched_count ?? 0;
  const inserted = stats.inserted_count ?? 0;
  const updated = stats.updated_count ?? 0;
  return `${fetched} fetched · ${inserted} new · ${updated} updated`;
}

function stringifyAuthors(authors: unknown[]): string[] {
  return authors.map((author) => {
    if (typeof author === 'string') {
      return author;
    }
    if (author && typeof author === 'object' && 'name' in author && typeof author.name === 'string') {
      return author.name;
    }
    return String(author);
  });
}
