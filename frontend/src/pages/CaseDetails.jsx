import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Clock3, FileText, ShieldAlert } from 'lucide-react';
import { api } from '../api';
import RiskBadge from '../components/RiskBadge';
import ModalityBreakdown from '../components/ModalityBreakdown';
import NarrativeContextPanel from '../components/NarrativeContextPanel';
import TrackingPattern from '../components/TrackingPattern';
import SVIBar from '../components/SVIBar';
import SignalCard from '../components/SignalCard';
import CaseTimeline from '../components/CaseTimeline';
import { useAuth } from '../context/AuthContext';

const STATUS_LABEL = { NEW: 'Received — awaiting review', UNDER_REVIEW: 'Under review', ACTION_REQUIRED: 'A responder is acting on this', RESOLVED: 'Resolved', CLOSED: 'Closed' };

/** Status-only view for the person who made the statement. */
const ParticipantCase = ({ data }) => {
  const navigate = useNavigate();
  return <div className="page-stack">
    <section className="case-detail-head"><div><button className="back-link" onClick={() => navigate('/user/dashboard')}><ArrowLeft size={16} /> Back to my dashboard</button><span className="eyebrow">MY STATEMENT</span><h2>{data.case_id}</h2><p>Submitted {data.created_at ? new Date(data.created_at).toLocaleString() : ''}</p></div></section>
    <div className="panel receipt-panel">
      <div className="receipt-icon"><CheckCircle2 size={30} /></div>
      <h3>{data.message}</h3>
      <div className="receipt-meta"><span>Status</span><strong>{STATUS_LABEL[data.status] || data.status}</strong><span>Submitted as</span><strong>{data.capture_mode === 'video' ? 'Video statement' : data.capture_mode === 'voice' ? 'Voice statement' : 'Written statement'}</strong></div>
      <div className="human-banner"><ShieldAlert size={18} /><div><strong>A human responder reviews every statement</strong><span>If your situation changes or you are in immediate danger, contact local emergency services.</span></div></div>
    </div>
  </div>;
};

const CaseDetails = () => {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const participant = user?.role === 'user';
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getCase(caseId, participant ? { view: 'participant' } : {}).then(setData).catch((e) => setError(e.message || 'Unable to load case.')).finally(() => setLoading(false));
  }, [caseId, participant]);

  if (loading) return <div className="state-card"><div className="spinner" /><strong>Loading case details…</strong></div>;
  if (error) return <div className="state-card error-state"><ShieldAlert size={25} /><strong>{error}</strong><button className="btn btn-outline" onClick={() => navigate(participant ? '/user/dashboard' : '/cases')}>Back</button></div>;
  if (!data) return <div className="state-card"><strong>Case not found.</strong></div>;
  if (participant) return <ParticipantCase data={data} />;

  const behaviorFeatures = data.behavior_analysis?.features;
  return <div className="page-stack">
    <section className="case-detail-head"><div><button className="back-link" onClick={() => navigate('/cases')}><ArrowLeft size={16} /> Back to queue</button><span className="eyebrow">CASE RECORD · RESPONDER VIEW</span><h2>{data.case_id}</h2><p>Assessment details, evidence and responder context.</p></div><RiskBadge level={data.risk_level} /><select className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold" value={data.status || 'NEW'} onChange={async (e) => { try { const updated = await api.updateCaseStatus(caseId, e.target.value); setData(updated); } catch (err) { setError(err.message || 'Unable to update case status.'); } }}><option value="NEW">New</option><option value="UNDER_REVIEW">Under Review</option><option value="ACTION_REQUIRED">Action Required</option><option value="RESOLVED">Resolved</option><option value="CLOSED">Closed</option></select></section>
    <div className="detail-grid">
      <main className="page-stack">
        <div className="panel"><div className="panel-header"><div><span className="eyebrow">RISK PROFILE</span><h3>Stress &amp; Vulnerability Index</h3></div><span className="record-date">Updated {data.updated_at || 'N/A'}</span></div><SVIBar score={data.svi_score} /></div>
        <section><div className="section-title"><div><span className="eyebrow">SIGNALS</span><h3>Vulnerability profile</h3></div></div><div className="signal-grid">{Object.entries(data.signals || {}).map(([signal, score]) => <SignalCard key={signal} signal={signal} score={score} level={data.vulnerability_profile?.[signal] || 'UNKNOWN'} />)}</div></section>
        {data.narrative_context && <NarrativeContextPanel context={data.narrative_context} />}
        {data.modalities && <ModalityBreakdown modalities={data.modalities} transcript={data.transcript} voiceAnalysis={data.voice_analysis} />}
        {behaviorFeatures && <TrackingPattern features={behaviorFeatures} />}
        <div className="panel"><div className="panel-header"><div><span className="eyebrow">AI ANALYSIS</span><h3>Explanation & evidence</h3></div><FileText size={19} /></div><div className="detail-subsection"><h4>Explanations</h4>{(data.explanation || []).map((x, i) => <div className="explanation-line" key={i}>{x}</div>)}</div><div className="detail-subsection"><h4>Evidence</h4>{(data.evidence || []).map((x, i) => <div className="evidence-item" key={i}><p>“{x.text}”</p><span>{x.signal}</span></div>)}</div></div>
      </main>
      <aside className="page-stack">
        <div className="panel"><div className="panel-header"><div><span className="eyebrow">ACTIVITY</span><h3>Case timeline</h3></div><Clock3 size={18} /></div><CaseTimeline events={data.timeline} /></div>
        <div className="recommendation-panel"><span className="eyebrow">RESPONDER NOTES</span><h3>Recommendations</h3><ul>{(data.recommendations || []).map((x, i) => <li key={i}><span>0{i + 1}</span>{x}</li>)}</ul></div>
        {data.human_review_required && <div className="human-banner vertical"><ShieldAlert size={20} /><div><strong>Review required</strong><span>This case requires human review.</span></div></div>}
      </aside>
    </div>
  </div>;
};
export default CaseDetails;
