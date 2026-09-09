import React, { useMemo, useState } from 'react';
import { Activity, ChevronDown, ChevronUp, Radar } from 'lucide-react';

/**
 * Responder-only view of the body-movement tracking pattern captured
 * during a video assessment: a per-second cue chart and the timeline of
 * detected episodes (face / neck touches, hand rubbing, finger clasping,
 * arm stroking, self-hug, jaw clench, raised shoulders, freeze, swallow,
 * blink bursts, gaze away, head down …).
 *
 * Never rendered on the participant's screen.
 */

const EVENT_META = {
  face_touch: { label: 'Face touch', group: 'self-touch', color: '#d92d20' },
  neck_touch: { label: 'Neck / throat touch', group: 'self-touch', color: '#d92d20' },
  hair_touch: { label: 'Hair touch', group: 'self-touch', color: '#d92d20' },
  hand_rub: { label: 'Rubbing hands', group: 'self-soothing', color: '#b54708' },
  arm_stroke: { label: 'Stroking arm', group: 'self-soothing', color: '#b54708' },
  finger_clasp: { label: 'Fingers clasped', group: 'self-soothing', color: '#b54708' },
  self_hug: { label: 'Self-hug / arms crossed', group: 'self-soothing', color: '#b54708' },
  jaw_clench: { label: 'Jaw clenched', group: 'tension', color: '#7a5af8' },
  shoulder_raise: { label: 'Shoulders raised', group: 'tension', color: '#7a5af8' },
  freeze: { label: 'Frozen stillness', group: 'tension', color: '#7a5af8' },
  swallow: { label: 'Swallow (approx.)', group: 'throat', color: '#0d9d98' },
  blink_burst: { label: 'Blink burst', group: 'eyes', color: '#1570ef' },
  gaze_away: { label: 'Gaze away', group: 'eyes', color: '#1570ef' },
  head_down: { label: 'Head down', group: 'head', color: '#475467' },
  head_shake: { label: 'Head shake', group: 'head', color: '#475467' },
  posture_shift: { label: 'Posture shift', group: 'head', color: '#475467' },
  fidget: { label: 'Fidget burst', group: 'hands', color: '#f79009' },
};

const LANES = ['self-touch', 'self-soothing', 'tension', 'throat', 'eyes', 'head', 'hands'];
const SERIES = [
  { key: 'self_touch', label: 'Self-touch', color: '#d92d20' },
  { key: 'tension', label: 'Tension', color: '#7a5af8' },
  { key: 'gaze_away', label: 'Gaze away', color: '#1570ef' },
  { key: 'hand_motion', label: 'Hand motion', color: '#f79009', scale: 2 },
  { key: 'head_motion', label: 'Head motion', color: '#475467', scale: 2 },
  { key: 'expression', label: 'Facial tension', color: '#0d9d98' },
];

const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

const TrackingPattern = ({ features }) => {
  const [open, setOpen] = useState(true);
  const { events, timeline, duration, counts } = useMemo(() => {
    const ev = features?.events || [];
    const tl = features?.timeline || [];
    const dur = Math.max(features?.duration_sec || 0, tl.length ? tl[tl.length - 1].t + 1 : 0, ...ev.map((e) => e.start + (e.duration || 0)), 1);
    const c = {};
    for (const e of ev) c[e.type] = (c[e.type] || 0) + 1;
    return { events: ev, timeline: tl, duration: dur, counts: Object.entries(c).sort((a, b) => b[1] - a[1]) };
  }, [features]);

  if (!features || (!events.length && !timeline.length)) return null;

  const W = 720, H = 120, PAD = 6;
  const x = (t) => PAD + (t / duration) * (W - 2 * PAD);
  const path = (key, scale = 1) => timeline.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${(H - PAD - Math.min(1, (p[key] || 0) * scale) * (H - 2 * PAD)).toFixed(1)}`).join(' ');

  return (
    <div className="panel tracking-panel">
      <button type="button" className="panel-header tracking-head" onClick={() => setOpen((o) => !o)}>
        <div><span className="eyebrow">TRACKING PATTERN · RESPONDER VIEW</span><h3>Body-movement timeline</h3></div>
        <div className="channel-right"><Radar size={18} />{open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</div>
      </button>
      {open && (
        <>
          <p className="muted-copy">{events.length} episodes detected over {fmt(duration)} · tracker {features.tracker || 'v6'}{features.source === 'uploaded_video' ? ' · from uploaded footage' : ' · on-device'}. Not shown to the person assessed.</p>

          {timeline.length > 1 && (
            <div className="track-chart">
              <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Per-second cue intensities">
                <rect x="0" y="0" width={W} height={H} fill="#f8fafc" rx="8" />
                {[0.25, 0.5, 0.75].map((g) => <line key={g} x1={PAD} x2={W - PAD} y1={H - PAD - g * (H - 2 * PAD)} y2={H - PAD - g * (H - 2 * PAD)} stroke="#e4eaf0" strokeDasharray="3 4" />)}
                {SERIES.map((s) => <path key={s.key} d={path(s.key, s.scale)} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round" />)}
              </svg>
              <div className="track-legend">{SERIES.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
            </div>
          )}

          {events.length > 0 && (
            <div className="track-lanes">
              {LANES.map((lane) => {
                const laneEvents = events.filter((e) => EVENT_META[e.type]?.group === lane);
                if (!laneEvents.length) return null;
                return (
                  <div className="track-lane" key={lane}>
                    <span className="track-lane-label">{lane}</span>
                    <div className="track-lane-bar">
                      {laneEvents.map((e, i) => {
                        const meta = EVENT_META[e.type] || { label: e.type, color: '#98a2b3' };
                        const left = (e.start / duration) * 100;
                        const width = Math.max(((e.duration || 0.3) / duration) * 100, 0.6);
                        return <i key={i} style={{ left: `${left}%`, width: `${width}%`, background: meta.color }} title={`${meta.label} · ${fmt(e.start)} · ${(e.duration || 0).toFixed(1)}s${e.note ? ` · ${e.note}` : ''}`} />;
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="track-axis"><span>0:00</span><span>{fmt(duration / 2)}</span><span>{fmt(duration)}</span></div>
            </div>
          )}

          <div className="track-counts">
            {counts.map(([type, n]) => {
              const meta = EVENT_META[type] || { label: type, color: '#98a2b3' };
              return <span className="data-chip" key={type}><i style={{ background: meta.color }} />{meta.label} × {n}</span>;
            })}
            {!counts.length && <span className="empty-inline"><Activity size={13} /> No discrete movement episodes were detected.</span>}
          </div>
        </>
      )}
    </div>
  );
};

export default TrackingPattern;
