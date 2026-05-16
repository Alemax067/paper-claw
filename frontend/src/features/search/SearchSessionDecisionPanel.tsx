import { useCallback, useState } from 'react';
import { api } from '../../api/client';
import { ErrorBanner } from '../../components/ErrorBanner';
import { LoadingBlock } from '../../components/LoadingBlock';
import { StatusBadge } from '../../components/StatusBadge';
import { useAsyncResource } from '../../hooks/useAsyncResource';

interface SearchSessionDecisionPanelProps {
  searchSessionId: number;
  candidateIds?: number[];
  recommendationReason?: string | null;
  onRefresh: () => void;
  onActivePaperSelected?: (paperId: number) => void;
}

export function SearchSessionDecisionPanel({ searchSessionId, candidateIds, recommendationReason, onRefresh, onActivePaperSelected }: SearchSessionDecisionPanelProps) {
  const [reason, setReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const loader = useCallback(() => api.getSearchSession(searchSessionId), [searchSessionId]);
  const { data: session, loading, error, reload } = useAsyncResource(loader, [searchSessionId]);
  const recommendedCandidates = candidateIds?.length
    ? session?.candidates.filter((candidate) => candidateIds.includes(candidate.id))
    : session?.candidates;

  const confirm = async (candidateId: number) => {
    setActionError(null);
    try {
      const updated = await api.confirmSearchCandidate(searchSessionId, { candidate_id: candidateId, update_thread_focus: true });
      const selected = updated.candidates.find((candidate) => candidate.id === updated.selected_candidate_id);
      if (selected?.paper_id != null) {
        onActivePaperSelected?.(selected.paper_id);
      }
      reload();
      onRefresh();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Confirmation failed');
    }
  };

  const reject = async () => {
    setActionError(null);
    try {
      await api.rejectSearchSession(searchSessionId, { reason: reason || null });
      setReason('');
      reload();
      onRefresh();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Rejection failed');
    }
  };

  if (!loading && session && session.status !== 'waiting_for_confirmation') {
    return null;
  }

  return (
    <section className="panel search-confirmation-panel">
      <div className="panel-header">
        <p className="eyebrow">Search confirmation</p>
        <h2>Candidate selection</h2>
      </div>
      <div className="panel-body stack">
        <ErrorBanner message={error || actionError} />
        {loading && <LoadingBlock label="Loading search session" />}
        {session && (
          <>
            <div className="meta-row">
              <span>session #{session.id}</span>
              <StatusBadge status={session.status} />
              <span>{session.query_text}</span>
            </div>
            {recommendationReason && <p className="candidate-reason">{recommendationReason}</p>}
            {recommendedCandidates?.map((candidate) => (
              <article className="candidate-card" key={candidate.id}>
                <div className="meta-row">
                  <span>rank {candidate.rank}</span>
                  <span>{candidate.source}</span>
                  {candidate.year && <span>{candidate.year}</span>}
                  {candidate.score != null && <span>score {candidate.score.toFixed(2)}</span>}
                </div>
                <h3>{candidate.title}</h3>
                {candidate.abstract && <p className="candidate-abstract">{candidate.abstract}</p>}
                <div className="meta-row">
                  {candidate.doi && <span>doi {candidate.doi}</span>}
                  {candidate.arxiv_id && <span>arxiv {candidate.arxiv_id}</span>}
                  {candidate.openalex_id && <span>{candidate.openalex_id}</span>}
                </div>
                <div className="button-row">
                  <button className="primary-button" onClick={() => confirm(candidate.id)}>Confirm candidate</button>
                </div>
              </article>
            ))}
            <label>
              Reject reason
              <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Optional reason" />
            </label>
            <button className="danger-button" onClick={reject}>Reject search session</button>
          </>
        )}
      </div>
    </section>
  );
}
