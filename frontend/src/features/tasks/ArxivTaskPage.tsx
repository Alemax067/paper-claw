import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api/client';
import type { ArxivTaskCategoryRead, ArxivTaskHarvestJobRead, ArxivTaskStatusRead } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { usePolling } from '../../hooks/usePolling';

const runningStatuses = new Set(['running', 'pending', 'stopping']);

export function ArxivTaskPage() {
  const loader = useCallback(() => api.getArxivTaskStatus(), []);
  const { data: status, loading, error, reload } = useAsyncResource(loader, []);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [enabledCatIds, setEnabledCatIds] = useState<string[]>([]);
  const [dailyEnabled, setDailyEnabled] = useState(true);
  const [runTime, setRunTime] = useState('08:00');
  const [selectedCoverageCatId, setSelectedCoverageCatId] = useState<string>('');
  const [historyCatIds, setHistoryCatIds] = useState<string[]>([]);
  const [historyStart, setHistoryStart] = useState(() => defaultDatetimeLocal(-7));
  const [historyEnd, setHistoryEnd] = useState(() => defaultDatetimeLocal(0));

  useEffect(() => {
    if (!status) {
      return;
    }
    setEnabledCatIds(status.enabled_cat_ids);
    setDailyEnabled(status.daily_config.enabled);
    setRunTime(status.daily_config.run_time);
    setSelectedCoverageCatId((current) => current || status.coverage_cat_ids[0] || status.enabled_cat_ids[0] || status.categories[0]?.cat_id || '');
    setHistoryCatIds((current) => (current.length ? current : status.enabled_cat_ids.slice(0, 1)));
  }, [status]);

  const shouldPoll = Boolean(status?.active_job && runningStatuses.has(status.active_job.status));
  usePolling(reload, 2500, shouldPoll);

  const categoryTree = useMemo(() => buildCategoryTree(status?.categories ?? [], new Set(enabledCatIds)), [enabledCatIds, status?.categories]);
  const coverageCatIds = useMemo(() => {
    const ids = new Set<string>();
    for (const catId of status?.coverage_cat_ids ?? []) {
      ids.add(catId);
    }
    for (const catId of status?.enabled_cat_ids ?? []) {
      ids.add(catId);
    }
    return [...ids].sort();
  }, [status?.coverage_cat_ids, status?.enabled_cat_ids]);
  const selectedWindows = useMemo(() => {
    return (status?.recent_windows ?? []).filter((window) => !selectedCoverageCatId || window.cat_id === selectedCoverageCatId);
  }, [selectedCoverageCatId, status?.recent_windows]);
  const dailyJobs = useMemo(() => (status?.recent_jobs ?? []).filter((job) => job.kind === 'daily'), [status?.recent_jobs]);
  const historyJobs = useMemo(() => (status?.recent_jobs ?? []).filter((job) => job.kind === 'history'), [status?.recent_jobs]);

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

  const toggleEnabledCategory = (catId: string) => {
    setEnabledCatIds((current) => (current.includes(catId) ? current.filter((value) => value !== catId) : [...current, catId].sort()));
  };

  const toggleHistoryCategory = (catId: string) => {
    setHistoryCatIds((current) => (current.includes(catId) ? current.filter((value) => value !== catId) : [...current, catId].sort()));
  };

  const saveCategories = () => runAction(() => api.updateArxivTaskCategories({ enabled_cat_ids: enabledCatIds }));
  const saveDailyConfig = () => runAction(() => api.updateArxivTaskDailyConfig({ enabled: dailyEnabled, run_time: runTime }));
  const runDailyNow = () => runAction(() => api.runArxivTaskDailyNow());

  const createHistoryJob = (event: FormEvent) => {
    event.preventDefault();
    if (!historyCatIds.length) {
      setActionError('Select at least one arXiv category for history backfill.');
      return;
    }
    runAction(() => api.createArxivTaskHistoryJob({ cat_ids: historyCatIds, start_time: toIso(historyStart), end_time: toIso(historyEnd) }));
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
          <p>Schedule daily submitted-date windows, backfill historical ranges, and keep harvested arXiv metadata separate from curated papers.</p>
        </div>
        {status && (
          <div className="task-hero__meters">
            <Metric label="enabled cats" value={status.enabled_cat_ids.length} />
            <Metric label="task papers" value={status.total_papers} />
            <Metric label="coverage cats" value={status.coverage_cat_ids.length} />
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
                <p className="eyebrow">Selector</p>
                <h2>Daily categories</h2>
              </div>
              <button className="primary-button" type="button" disabled={saving} onClick={saveCategories}>Save categories</button>
            </div>
            <div className="panel-body stack">
              <CategorySelector
                categories={status.categories}
                tree={categoryTree}
                selectedCatIds={enabledCatIds}
                selectedTitle="Selected daily categories"
                emptySelectedBody="Choose categories from the collapsed catalog below."
                onToggle={toggleEnabledCategory}
              />
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <p className="eyebrow">Daily</p>
              <h2>Incremental run</h2>
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
              <JobList jobs={dailyJobs.slice(0, 4)} emptyTitle="No daily jobs yet" />
            </div>
          </section>

          <section className="panel task-panel--wide">
            <div className="panel-header task-panel-header-row">
              <div>
                <p className="eyebrow">Coverage</p>
                <h2>Retrieved windows</h2>
              </div>
              <select value={selectedCoverageCatId} onChange={(event) => setSelectedCoverageCatId(event.target.value)}>
                {coverageCatIds.map((catId) => <option key={catId} value={catId}>{catId}</option>)}
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
                        <span>{formatDateTime(window.window_start)} → {formatDateTime(window.window_end)}</span>
                      </div>
                      <div className="task-window-card__bar" />
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
                <EmptyState title="No windows for this category" body="Run Daily or create a history backfill to establish coverage." />
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
                <CategorySelector
                  categories={status.categories}
                  tree={buildCategoryTree(status.categories, new Set(historyCatIds))}
                  selectedCatIds={historyCatIds}
                  selectedTitle="Selected history categories"
                  emptySelectedBody="Select one or more categories for the backfill job."
                  onToggle={toggleHistoryCategory}
                />
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
                          <h3>{job.cat_ids.join(', ') || 'no categories'}</h3>
                        </div>
                        <div className="button-row">
                          <button className="secondary-button" type="button" disabled={saving || job.status === 'running'} onClick={() => jobAction(job, 'start')}>Start</button>
                          <button className="secondary-button" type="button" disabled={saving || job.status !== 'running'} onClick={() => jobAction(job, 'pause')}>Pause</button>
                          <button className="danger-button" type="button" disabled={saving || ['stopped', 'succeeded'].includes(job.status)} onClick={() => jobAction(job, 'stop')}>Stop</button>
                        </div>
                      </div>
                      <div className="meta-row">
                        <span>{formatDateTime(job.requested_start)} → {formatDateTime(job.requested_end)}</span>
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
                        <span>{paper.authors.slice(0, 4).join(', ')}</span>
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

function CategorySelector({ categories, tree, selectedCatIds, selectedTitle, emptySelectedBody, onToggle }: { categories: ArxivTaskCategoryRead[]; tree: CategoryArea[]; selectedCatIds: string[]; selectedTitle: string; emptySelectedBody: string; onToggle: (catId: string) => void }) {
  const selectedSet = new Set(selectedCatIds);
  const selectedCategories = categories.filter((category) => selectedSet.has(category.cat_id)).sort((left, right) => left.cat_id.localeCompare(right.cat_id));
  return (
    <div className="task-category-selector">
      <section className="task-selected-panel">
        <div className="section-heading-row">
          <h3>{selectedTitle}</h3>
          <span>{selectedCategories.length} selected</span>
        </div>
        {selectedCategories.length ? (
          <div className="task-selected-scroll">
            {selectedCategories.map((category) => (
              <div key={category.cat_id} className="task-selected-card">
                <div>
                  <span className="task-category-card__id">{category.cat_id}</span>
                  <strong>{category.name}</strong>
                  <span>{categoryPath(category)}</span>
                </div>
                <button type="button" className="task-remove-button" onClick={() => onToggle(category.cat_id)}>Remove</button>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No categories selected" body={emptySelectedBody} />
        )}
      </section>

      <div className="task-category-accordion">
        {tree.map((area) => (
          <Details key={area.key} className="task-category-area" defaultOpen={area.selectedCount > 0}>
            <summary>
              <span>{area.label}</span>
              <span>{area.selectedCount}/{area.totalCount} selected</span>
            </summary>
            <div className="task-category-area__body">
              {area.directCategories.length > 0 && <CategoryLeafGrid categories={area.directCategories} selectedCatIds={selectedCatIds} onToggle={onToggle} />}
              {area.groups.map((group) => (
                <Details key={group.key} className="task-category-subgroup" defaultOpen={group.selectedCount > 0}>
                  <summary>
                    <span>{group.label}</span>
                    <span>{group.selectedCount}/{group.categories.length}</span>
                  </summary>
                  <CategoryLeafGrid categories={group.categories} selectedCatIds={selectedCatIds} onToggle={onToggle} />
                </Details>
              ))}
            </div>
          </Details>
        ))}
      </div>
    </div>
  );
}

function Details({ className, defaultOpen, children }: { className: string; defaultOpen: boolean; children: React.ReactNode }) {
  return defaultOpen ? <details className={className} open>{children}</details> : <details className={className}>{children}</details>;
}

function CategoryLeafGrid({ categories, selectedCatIds, onToggle }: { categories: ArxivTaskCategoryRead[]; selectedCatIds: string[]; onToggle: (catId: string) => void }) {
  return (
    <div className="task-category-grid">
      {categories.map((category) => (
        <label key={category.cat_id} className={`task-category-card ${selectedCatIds.includes(category.cat_id) ? 'is-selected' : ''}`} title={category.description ?? undefined}>
          <input type="checkbox" checked={selectedCatIds.includes(category.cat_id)} onChange={() => onToggle(category.cat_id)} />
          <span className="task-category-card__id">{category.cat_id}{category.is_alias && <span className="task-alias-badge">alias</span>}</span>
          <strong>{category.name}</strong>
          {category.alias_of && <span className="task-category-card__alias">Alias of {category.alias_of}</span>}
        </label>
      ))}
    </div>
  );
}

function JobList({ jobs, emptyTitle }: { jobs: ArxivTaskHarvestJobRead[]; emptyTitle: string }) {
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
            <span>{job.cat_ids.join(', ') || 'no categories'}</span>
            <span>{statsLabel(job.stats)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

type CategoryArea = {
  key: string;
  label: string;
  totalCount: number;
  selectedCount: number;
  directCategories: ArxivTaskCategoryRead[];
  groups: CategorySubgroup[];
};

type CategorySubgroup = {
  key: string;
  label: string;
  selectedCount: number;
  categories: ArxivTaskCategoryRead[];
};

function buildCategoryTree(categories: ArxivTaskCategoryRead[], selectedCatIds: Set<string>): CategoryArea[] {
  const byArea = new Map<string, ArxivTaskCategoryRead[]>();
  for (const category of categories) {
    const key = category.top_area || 'arXiv';
    byArea.set(key, [...(byArea.get(key) ?? []), category]);
  }
  return [...byArea.entries()]
    .map(([area, items]) => {
      const directCategories: ArxivTaskCategoryRead[] = [];
      const groups = new Map<string, ArxivTaskCategoryRead[]>();
      for (const category of sortCategories(items)) {
        const groupLabel = category.group?.trim();
        if (groupLabel) {
          const groupKey = category.group_code ? `${groupLabel} (${category.group_code})` : groupLabel;
          groups.set(groupKey, [...(groups.get(groupKey) ?? []), category]);
        } else {
          directCategories.push(category);
        }
      }
      const groupValues = [...groups.entries()].map(([key, groupItems]) => ({
        key,
        label: key,
        selectedCount: groupItems.filter((category) => selectedCatIds.has(category.cat_id)).length,
        categories: sortCategories(groupItems),
      }));
      return {
        key: area,
        label: area,
        totalCount: items.length,
        selectedCount: items.filter((category) => selectedCatIds.has(category.cat_id)).length,
        directCategories,
        groups: groupValues.sort((left, right) => left.label.localeCompare(right.label)),
      };
    })
    .sort((left, right) => left.label.localeCompare(right.label));
}

function sortCategories(categories: ArxivTaskCategoryRead[]): ArxivTaskCategoryRead[] {
  return [...categories].sort((left, right) => left.archive.localeCompare(right.archive) || left.cat_id.localeCompare(right.cat_id));
}

function categoryPath(category: ArxivTaskCategoryRead): string {
  return [category.top_area, category.group || category.archive].filter(Boolean).join(' · ');
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
    return '—';
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
