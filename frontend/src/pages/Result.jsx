import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, HeartHandshake, Info, PhoneCall, ShieldAlert, Sparkles } from 'lucide-react';
import RiskBadge from '../components/RiskBadge';
import SVIBar from '../components/SVIBar';
import SignalCard from '../components/SignalCard';
import ModalityBreakdown from '../components/ModalityBreakdown';
import NarrativeContextPanel from '../components/NarrativeContextPanel';
import TrackingPattern from '../components/TrackingPattern';
import { useAuth } from '../context/AuthContext';

/**
 * Receipt shown to the person who made the statement.  Deliberately
 * contains no score, risk level, signal, cue or tracking information.
 */
const ParticipantReceipt = ({ data }) => {
  const navigate = useNavigate();
  return (
    <div className="page-stack">
      <section className="result-top"><div><span className="eyebrow">STATEMENT RECEIVED</span><h2>Thank you</h2><p>Your statement has been submitted safely.</p></div></section>
      <div className="panel receipt-panel">
        <div className="receipt-icon"><CheckCircle2 size={34} /></div>
        <h3>{data?.message || 'Your statement has been received and will be reviewed by an authorised responder.'}</h3>
        <div className="receipt-meta"><span>Reference</span><strong>{data?.case_id}</strong><span>Status</span><strong>{data?.status === 'RECEIVED' ? 'Received — awaiting review' : data?.status}</strong></div>
        <ul className="receipt-steps">
          {(data?.next_steps?.length ? data.next_steps : ['An authorised responder will review your statement.', 'You may be contacted for a follow-up conversation.']).map((s, i) => <li key={i}><HeartHandshake size={15} />{s}</li>)}
        </ul>
        <div className="human-banner"><PhoneCall size={18} /><div><strong>If you are in immediate danger</strong><span>Contact your local emergency services right now. You do not have to wait for a review.</span></div></div>
        <div className="recorder-actions">
          <button className="btn btn-outline" onClick={() => navigate('/user/dashboard')}>Back to my dashboard</button>
          <button className="btn btn-primary" onClick={() => navigate('/assessment')}>Share another statement</button>
        </div>
      </div>
    </div>
  );
};

const Result = () => {
  const { state } = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const data = state?.assessment;
  if (!data) return <div className="state-card"><Info size={28} /><strong>No assessment data found</strong><span>Please perform a new assessment first.</span><button className="btn btn-primary" onClick={() => navigate('/assessment')}>Start new assessment</button></div>;

  // The assessed person only ever sees the receipt — even if a full
  // payload somehow reached this page.
  if (user?.role === 'user' || data.participant_view || state?.participantView) return <ParticipantReceipt data={data} />;

  const confidence = Number(data.confidence || 0) * 100;
  const behaviorFeatures = data.behavior_analysis?.features;
  return <div className="page-stack">
    <section className="result-top"><div><button className="back-link" onClick={() => navigate('/assessment')}><ArrowLeft size={16} /> Back to assessment</button><span className="eyebrow">ASSESSMENT COMPLETE · RESPONDER VIEW</span><h2>Assessment result</h2><p>Review the AI-supported signals below before taking any action.</p></div><RiskBadge level={data.risk_level} /></section>
    {data.human_review_required && <div className="human-banner"><ShieldAlert size={20} /><div><strong>Human review required</strong><span>This assessment must be reviewed by an authorized responder before any action is taken.</span></div></div>}
    <section className="result-grid">
      <div className="result-main">
        <div className="panel result-overview"><div className="result-overview-head"><div><span className="eyebrow">RISK OVERVIEW</span><h3>Stress &amp; Vulnerability Index</h3></div><div className="confidence"><span>Confidence</span><strong>{confidence.toFixed(1)}%</strong></div></div><SVIBar score={data.svi_score} label="Overall vulnerability score" /></div>
        <div><div className="section-title"><div><span className="eyebrow">SIGNALS</span><h3>Vulnerability profile</h3></div></div><div className="signal-grid">{Object.entries(data.signals || {}).map(([signal, score]) => <SignalCard key={signal} signal={signal} score={score} level={data.vulnerability_profile?.[signal] || 'UNKNOWN'} />)}</div></div>
        {data.narrative_context && <NarrativeContextPanel context={data.narrative_context} />}
        {data.modalities && <ModalityBreakdown modalities={data.modalities} transcript={data.transcript} voiceAnalysis={data.voice_analysis} />}
        {behaviorFeatures && <TrackingPattern features={behaviorFeatures} />}
        <div className="panel"><div className="panel-header"><div><span className="eyebrow">EXPLAINABILITY</span><h3>Why this result?</h3></div><Sparkles size={19} /></div><p className="muted-copy">The model identified the following patterns to support this classification.</p><div className="explanation-list">{(data.explanation || []).map((x, i) => <div key={i}><CheckCircle2 size={17} /><span>{x}</span></div>)}</div></div>
      </div>
      <aside className="result-side">
        <div className="panel"><div className="panel-header"><div><span className="eyebrow">EVIDENCE</span><h3>Supporting signals</h3></div></div><div className="evidence-list">{(data.evidence || []).map((ev, i) => <div className="evidence-item" key={i}><p>“{ev.text}”</p><span>{ev.signal}</span></div>)}{!data.evidence?.length && <span className="empty-inline">No evidence supplied.</span>}</div></div>
        <div className="recommendation-panel"><span className="eyebrow">NEXT STEPS</span><h3>Responder recommendations</h3><ul>{(data.recommendations || []).map((x, i) => <li key={i}><span>0{i + 1}</span>{x}</li>)}</ul><div className="recommendation-foot"><Info size={14} /> Final action remains with an authorized human responder.</div></div>
      </aside>
    </section>
  </div>;
};
export default Result;
