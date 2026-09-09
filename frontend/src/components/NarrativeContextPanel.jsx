import React from 'react';
import { BookOpenText, TrendingUp } from 'lucide-react';

const pretty = (k) => k.replace(/_/g, ' ');

/**
 * Responder view of the whole-passage reading: which signals emerged
 * only from cross-sentence context, and the discourse features
 * (escalation, helplessness, present-tense danger, fragmentation …).
 */
const NarrativeContextPanel = ({ context }) => {
  if (!context) return null;
  const d = context.discourse || {};
  const signals = Object.entries(context.signals || {});
  const subs = Object.entries(context.sub_scores || {});

  return (
    <div className="panel">
      <div className="panel-header">
        <div><span className="eyebrow">WHOLE-PASSAGE CONTEXT</span><h3>How the account reads as a whole</h3></div>
        <BookOpenText size={19} />
      </div>
      <div className="fusion-row">
        <div className="fusion-chip primary"><span><TrendingUp size={13} /> Narrative stress index</span><strong>{Number(context.indicator || 0).toFixed(0)}</strong><small>{context.engine === 'context' ? 'semantic + discourse' : 'discourse only (semantic model off)'}</small></div>
        <div className="fusion-chip"><span>SVI adjustment</span><strong>+{Number(context.adjustment || 0).toFixed(1)}</strong><small>capped, text stays primary</small></div>
        {d.trajectory && <div className="fusion-chip"><span>Trajectory</span><strong className="fusion-chip-text">{d.trajectory}</strong><small>{d.sentence_count} sentences · {d.word_count} words</small></div>}
      </div>

      {subs.length > 0 && (
        <div className="sub-score-list" style={{ marginBottom: 12 }}>
          {subs.map(([k, v]) => (
            <div className="sub-score" key={k}>
              <div><span>{pretty(k)}</span><strong>{Number(v).toFixed(0)}</strong></div>
              <div className="mini-track"><div className="mini-fill" style={{ width: `${Math.min(100, Number(v))}%` }} /></div>
            </div>
          ))}
        </div>
      )}

      {context.cues?.length ? <ul className="cue-list">{context.cues.map((c, i) => <li key={i}>{c}</li>)}</ul> : <span className="empty-inline">No discourse-level cues.</span>}

      {signals.length > 0 && (
        <div className="detail-subsection">
          <h4>Signals found by reading sentences together</h4>
          {signals.map(([sig, s]) => (
            <div className="evidence-item" key={sig}>
              <p>“{s.evidence}”</p>
              <span>{pretty(sig)} · {s.level} · similarity {Number(s.similarity || 0).toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default NarrativeContextPanel;
