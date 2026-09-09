import React, { useState } from 'react';
import { AudioLines, ChevronDown, ChevronUp, FileText, Layers, ScanFace, Waves } from 'lucide-react';

const pretty = (key) => key.replace(/_/g, ' ');

const SubScores = ({ scores }) => {
  const entries = Object.entries(scores || {});
  if (!entries.length) return null;
  return (
    <div className="sub-score-list">
      {entries.map(([k, v]) => (
        <div className="sub-score" key={k}>
          <div><span>{pretty(k)}</span><strong>{Number(v).toFixed(0)}</strong></div>
          <div className="mini-track"><div className="mini-fill" style={{ width: `${Math.min(100, Number(v))}%` }} /></div>
        </div>
      ))}
    </div>
  );
};

const Channel = ({ icon, title, block, note, children }) => {
  const [open, setOpen] = useState(true);
  if (!block) return null;
  return (
    <div className={`channel-card ${block.available ? '' : 'unavailable'}`}>
      <button type="button" className="channel-head" onClick={() => setOpen((o) => !o)}>
        <div className="channel-title">{icon}<div><strong>{title}{block.label ? <em className="channel-label">{block.label}</em> : null}</strong><span>{block.available ? `${Number(block.indicator).toFixed(0)}/100 supplementary indicator` : 'Not available for this assessment'}</span></div></div>
        <div className="channel-right">
          {block.available && <div className="mini-track wide"><div className="mini-fill" style={{ width: `${block.indicator}%` }} /></div>}
          {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </div>
      </button>
      {open && block.available && (
        <div className="channel-body">
          {note && <p className="muted-copy">{note}</p>}
          <SubScores scores={block.sub_scores} />
          {block.cues?.length ? <ul className="cue-list">{block.cues.map((c, i) => <li key={i}>{c}</li>)}</ul> : <span className="empty-inline">No notable cues.</span>}
          {children}
        </div>
      )}
    </div>
  );
};

/** Small arousal / energy / pitch chart over the recording (tone timeline). */
const VoiceTimeline = ({ timeline }) => {
  if (!timeline || timeline.length < 2) return null;
  const W = 720, H = 90, PAD = 6;
  const tMax = timeline[timeline.length - 1].t + 3;
  const x = (t) => PAD + (t / tMax) * (W - 2 * PAD);
  const norm = (vals) => {
    const nums = vals.filter((v) => v !== null && v !== undefined);
    const lo = Math.min(...nums), hi = Math.max(...nums);
    return (v) => (v === null || v === undefined ? null : hi > lo ? (v - lo) / (hi - lo) : 0.5);
  };
  const series = [
    { key: 'arousal', label: 'Arousal', color: '#d92d20' },
    { key: 'energy', label: 'Loudness', color: '#f79009' },
    { key: 'pitch_st', label: 'Pitch', color: '#1570ef' },
    { key: 'rate', label: 'Pace', color: '#0d9d98' },
  ];
  return (
    <div className="track-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Voice tone over time">
        <rect x="0" y="0" width={W} height={H} fill="#f8fafc" rx="8" />
        {series.map((s) => {
          const n = norm(timeline.map((p) => p[s.key]));
          const d = timeline.map((p, i) => { const v = n(p[s.key]); return v === null ? '' : `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${(H - PAD - v * (H - 2 * PAD)).toFixed(1)}`; }).join(' ');
          return <path key={s.key} d={d} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round" />;
        })}
      </svg>
      <div className="track-legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}<span className="muted-copy">3-second windows, relative to the speaker's own opening baseline</span></div>
    </div>
  );
};

/**
 * Visualises how text, voice and behaviour were fused into the final SVI.
 * Expects `assessment.modalities` from /api/assess-audio or /api/assess-video.
 * Responder view only.
 */
const ModalityBreakdown = ({ modalities, transcript, voiceAnalysis }) => {
  if (!modalities) return null;
  const m = modalities;
  const used = m.modalities_used || ['text'];
  const reliability = m.behavior?.reliability;
  const toneTimeline = voiceAnalysis?.prosody?.tone?.timeline;

  return (
    <div className="panel modality-panel">
      <div className="panel-header">
        <div><span className="eyebrow">MULTIMODAL FUSION</span><h3>How the score was built</h3></div>
        <Layers size={19} />
      </div>

      <div className="fusion-row">
        <div className="fusion-chip primary"><FileText size={14} /><span>Text (primary)</span><strong>{m.text_svi.toFixed(1)}</strong></div>
        {used.includes('voice') && <div className="fusion-chip"><AudioLines size={14} /><span>Voice</span><strong>+{m.voice_adjustment.toFixed(1)}</strong><small>indicator {m.voice_indicator.toFixed(0)}{m.tone?.label ? ` · tone: ${m.tone.label}` : ''}</small></div>}
        {used.includes('behavior') && <div className="fusion-chip"><ScanFace size={14} /><span>Body language</span><strong>+{m.behavior_adjustment.toFixed(1)}</strong><small>indicator {m.behavior_indicator.toFixed(0)}{reliability != null ? ` · ${(reliability * 100).toFixed(0)}% reliable` : ''}</small></div>}
        <div className="fusion-chip total"><span>Final SVI</span><strong>{m.fused_svi.toFixed(1)}</strong><small>{m.fusion_method.replace(/_/g, ' ').replace(/\+/g, ' + ')}</small></div>
      </div>

      {m.incongruence_flag && (
        <div className="human-banner" style={{ marginBottom: 14 }}>
          <ScanFace size={18} />
          <div><strong>Words and delivery disagree</strong><span>The narrative was relatively calm but the voice and/or body language showed clear distress. Consider a gentle follow-up in a private setting.</span></div>
        </div>
      )}

      <div className="channel-grid">
        <Channel icon={<Waves size={17} />} title="Voice tone (whole recording)" block={m.tone} note="Arousal relative to the speaker's own opening baseline, flat / monotone delivery, strain, loudness & pace instability, and the trajectory across the recording (steady / escalating / collapsing / volatile).">
          <VoiceTimeline timeline={toneTimeline} />
        </Channel>
        <Channel icon={<AudioLines size={17} />} title="Voice nuance (prosody)" block={m.prosody} note="Pauses, pitch stability & range, jitter / shimmer, breathing, tremor, speech rate and vocal depth measured from the recording." />
        <Channel icon={<FileText size={17} />} title="Speech pattern (fumbling)" block={m.disfluency} note="Filler sounds, repetitions, restarts, hedging, unfinished sentences and hesitation gaps in the transcript." />
        <Channel icon={<ScanFace size={17} />} title="Body language (video)" block={m.behavior} note="Blinking pattern, eye contact, face / neck / hair touching, self-soothing gestures (rubbing hands, clasping fingers, stroking arms, self-hug), muscle tension (jaw, shoulders, freeze, slouch), swallowing, head / posture and facial tension." />
        <Channel icon={<AudioLines size={17} />} title="Basic acoustics" block={m.acoustic} note="Coarse loudness, noisiness and pitch-variability statistics." />
      </div>

      {transcript && (
        <details className="transcript-box">
          <summary>Transcript used for the text assessment</summary>
          <p>“{transcript}”</p>
        </details>
      )}
    </div>
  );
};

export default ModalityBreakdown;
