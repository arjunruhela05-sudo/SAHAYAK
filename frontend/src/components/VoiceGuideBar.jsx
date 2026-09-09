import React, { useState } from 'react';
import { AudioLines, ChevronDown, ChevronUp, Ear, Info, MicOff, Volume2 } from 'lucide-react';
import { GUIDE_LANGS, voiceSupport } from '../lib/voiceGuide';

/**
 * Toggle + status strip for the hands-free voice guide.
 *
 * `status` = { state: idle | listening | speaking | spoke | error | mode, detail }
 */
const VoiceGuideBar = ({ enabled, onToggle, lang, onLangChange, status, heard, recordingMode }) => {
  const [showHelp, setShowHelp] = useState(false);
  const supported = voiceSupport.recognition && voiceSupport.synthesis;

  const state = status?.state;
  const pill = !enabled
    ? { text: 'Voice guidance off', cls: 'off' }
    : state === 'speaking'
      ? { text: 'Speaking…', cls: 'speaking' }
      : state === 'error'
        ? { text: status?.detail || 'Voice error', cls: 'error' }
        : recordingMode
          ? { text: 'Recording — say "I am done" to stop', cls: 'listening' }
          : { text: 'Listening for commands', cls: 'listening' };

  return (
    <div className={`voice-guide ${enabled ? 'on' : ''}`}>
      <div className="voice-guide-main">
        <button type="button" className={`voice-guide-toggle ${enabled ? 'on' : ''}`} onClick={onToggle} disabled={!supported} title={supported ? 'Toggle voice guidance' : 'Voice guidance needs Chrome or Edge'}>
          {enabled ? <Ear size={16} /> : <MicOff size={16} />}
          <span>{enabled ? 'Voice-guided mode on' : 'Voice-guided mode'}</span>
        </button>
        <span className={`voice-pill ${pill.cls}`}><i />{pill.text}</span>
        {enabled && (
          <select className="voice-lang" value={lang} onChange={(e) => onLangChange(e.target.value)} aria-label="Voice guide language">
            {GUIDE_LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        )}
        <button type="button" className="voice-help-btn" onClick={() => setShowHelp((v) => !v)}>
          <Info size={14} /> What can I say? {showHelp ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>

      {enabled && heard && (
        <div className="voice-heard"><AudioLines size={13} /> Heard: <em>“{heard}”</em></div>
      )}

      {!supported && (
        <div className="voice-heard"><Volume2 size={13} /> Voice guidance uses the browser's speech engine — please use Chrome or Edge.</div>
      )}

      {showHelp && (
        <div className="voice-help">
          <div><b>Consent</b><span>“I consent” · “मैं सहमत हूँ”</span></div>
          <div><b>Move</b><span>“proceed” / “next” · “back” · “आगे बढ़ो” · “वापस”</span></div>
          <div><b>Choose</b><span>“text” · “voice” · “video”</span></div>
          <div><b>Record</b><span>“start” → the app says “speak now” · “I am done” / “stop recording” · “हो गया”</span></div>
          <div><b>Send</b><span>“submit” · “record again” · “भेज दो” · “दोबारा”</span></div>
          <div><b>Dictate</b><span>“start dictation” … “stop dictation” · “बोलकर लिखो”</span></div>
          <div><b>Other</b><span>“repeat” · “help” · “stop voice mode”</span></div>
        </div>
      )}
    </div>
  );
};

export default VoiceGuideBar;
