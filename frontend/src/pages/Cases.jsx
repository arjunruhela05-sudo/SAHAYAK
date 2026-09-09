import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Filter, Plus, RefreshCw, Search, SlidersHorizontal } from 'lucide-react';
import { api } from '../api';
import RiskBadge from '../components/RiskBadge';

const Cases = () => {
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRisk, setFilterRisk] = useState('ALL');

  const fetchCases = async () => {
    setLoading(true); setError(null);
    try {
      const params = {};
      if (filterRisk !== 'ALL') params.risk = filterRisk;
      if (searchTerm) params.search = searchTerm;
      setCases(await api.getCases(params));
    } catch { setError('Failed to load the priority queue.'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchCases(); }, [filterRisk, searchTerm]);
  const updateStatus = async (id, status) => { try { await api.updateCaseStatus(id, status); await fetchCases(); } catch (err) { setError(err.message || 'Unable to update case status.'); } };

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div><span className="eyebrow">CASE MANAGEMENT</span><h2>Priority queue</h2><p>Review active assessments and open cases that need attention.</p></div>
        <button className="btn btn-primary btn-large" onClick={() => navigate('/assessment')}><Plus size={18} /> New assessment</button>
      </section>

      <section className="queue-toolbar">
        <div className="search-field"><Search size={18} /><input value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Search by case ID…" /></div>
        <div className="filter-field"><Filter size={17} /><select value={filterRisk} onChange={e => setFilterRisk(e.target.value)}><option value="ALL">All risk levels</option><option value="CRITICAL">Critical</option><option value="HIGH">High</option><option value="MODERATE">Moderate</option><option value="LOW">Low</option></select></div>
        <button className="icon-button toolbar-icon" onClick={fetchCases} aria-label="Refresh"><RefreshCw size={17} /></button>
        <div className="toolbar-count"><SlidersHorizontal size={15} /> {cases.length} cases</div>
      </section>

      {loading ? <div className="state-card compact"><div className="spinner" /><strong>Loading priority queue…</strong></div> :
       error ? <div className="state-card error-state"><strong>{error}</strong><button className="btn btn-outline" onClick={fetchCases}>Try again</button></div> :
       <section className="panel table-panel">
        <div className="table-shell">
          <table className="modern-table queue-table">
            <thead><tr><th>Case ID</th><th>SVI score</th><th>Risk</th><th>Status</th><th>Created</th><th>Review</th><th /></tr></thead>
            <tbody>
              {cases.map(c => <tr key={c.case_id}>
                <td><button className="case-link" onClick={() => navigate(`/cases/${c.case_id}`)}>{c.case_id}</button></td>
                <td><span className="score-pill">{c.svi_score ?? '—'}</span></td>
                <td><RiskBadge level={c.risk_level} /></td>
                <td><select className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs" value={c.status || "NEW"} onChange={e=>updateStatus(c.case_id,e.target.value)}><option value="NEW">New</option><option value="UNDER_REVIEW">Under Review</option><option value="ACTION_REQUIRED">Action Required</option><option value="RESOLVED">Resolved</option><option value="CLOSED">Closed</option></select></td>
                <td>{c.created_at || 'N/A'}</td>
                <td><span className={c.human_review_required ? 'review-required' : 'review-complete'}>{c.human_review_required ? 'Required' : 'Complete'}</span></td>
                <td><button className="row-action" onClick={() => navigate(`/cases/${c.case_id}`)}><ArrowUpRight size={16} /></button></td>
              </tr>)}
              {!cases.length && <tr><td colSpan="7"><div className="empty-state"><strong>No matching cases</strong><span>Try a different search or risk filter.</span></div></td></tr>}
            </tbody>
          </table>
        </div>
       </section>}
    </div>
  );
};
export default Cases;
