import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, CheckCircle2, FileText, Mic, ShieldCheck, UserRound, Video } from 'lucide-react';
import { api } from '../api';
import VoiceRecorder from '../components/VoiceRecorder';
import VideoRecorder from '../components/VideoRecorder';
import VoiceGuideBar from '../components/VoiceGuideBar';
import { useAuth } from '../context/AuthContext';
import { createVoiceGuide, voiceSupport } from '../lib/voiceGuide';

const steps = [
  { n: 1, label: 'Consent', icon: ShieldCheck },
  { n: 2, label: 'Case details', icon: UserRound },
  { n: 3, label: 'Narrative', icon: FileText },
  { n: 4, label: 'Voice', icon: Mic },
  { n: 5, label: 'Video', icon: Video },
];

const STEP_PROMPT = { 1: 'consent', 2: 'details', 3: 'narrative', 4: 'voice', 5: 'video' };

const Assessment = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  // The assessed person ("user" role) never sees scores, cues or tracking.
  const participantMode = user?.role === 'user';

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({ consent: false, caseId: `SAH-${new Date().getFullYear()}-${String(Date.now()).slice(-6)}`, language: 'en', narrative: '' });

  // ---- voice guide -------------------------------------------------------
  const [guideOn, setGuideOn] = useState(false);
  const [guideLang, setGuideLang] = useState('en-IN');
  const [guideStatus, setGuideStatus] = useState(null);
  const [heard, setHeard] = useState('');
  const [dictating, setDictating] = useState(false);
  const [recorderState, setRecorderState] = useState('idle');
  const guideRef = useRef(null);
  const voiceCtl = useRef(null);
  const videoCtl = useRef(null);
  const stateRef = useRef({ step, formData, loading, recorderState, dictating });
  stateRef.current = { step, formData, loading, recorderState, dictating };

  const change = (e) => { const { name, value, type, checked } = e.target; setFormData((p) => ({ ...p, [name]: type === 'checkbox' ? checked : value })); };
  const goTo = (n) => { setError(null); setStep(Math.max(1, Math.min(5, n))); };
  const next = () => goTo(stateRef.current.step + 1);
  const back = () => goTo(stateRef.current.step - 1);

  const finish = (result) => {
    if (guideRef.current) guideRef.current.say('submitted');
    navigate('/result', { state: { assessment: result, participantView: participantMode } });
  };

  const handleAnalyze = async () => {
    const { formData: fd } = stateRef.current;
    if (!fd.narrative.trim()) { setError('Please provide a narrative before analysis.'); guideRef.current?.say('needNarrative'); return; }
    setLoading(true); setError(null); guideRef.current?.say('submitting');
    try {
      const result = await api.assessNarrative({ case_id: fd.caseId, narrative: fd.narrative, language: fd.language, consent: fd.consent, participantView: participantMode });
      finish(result);
    } catch (err) { setError(err.message || 'Unable to analyze assessment.'); guideRef.current?.say('error'); } finally { setLoading(false); }
  };

  const handleVideoUpload = async (audioBlob, behavior) => {
    const { formData: fd } = stateRef.current;
    setLoading(true); setError(null); guideRef.current?.say('submitting');
    try {
      const result = await api.assessVideo({ audio: audioBlob, caseId: fd.caseId, consent: fd.consent, behavior, language: fd.language, participantView: participantMode });
      finish(result);
    } catch (err) { setError(err.message || 'Unable to analyze the recording.'); guideRef.current?.say('error'); } finally { setLoading(false); }
  };

  const handleVideoFile = async (file) => {
    const { formData: fd } = stateRef.current;
    setLoading(true); setError(null); guideRef.current?.say('submitting');
    try {
      const result = await api.assessVideoFile({ file, caseId: fd.caseId, consent: fd.consent, language: fd.language, participantView: participantMode });
      finish(result);
    } catch (err) { setError(err.message || 'Unable to analyze the video.'); guideRef.current?.say('error'); } finally { setLoading(false); }
  };

  const handleAudioUpload = async (blob) => {
    const { formData: fd } = stateRef.current;
    setLoading(true); setError(null); guideRef.current?.say('submitting');
    try {
      const form = new FormData();
      form.append('file', blob, 'recording.webm'); form.append('case_id', fd.caseId); form.append('consent', String(fd.consent));
      form.append('language', fd.language);
      if (participantMode) form.append('participant_view', 'true');
      const result = await api.assessAudio(form);
      finish(result);
    } catch (err) { setError(err.message || 'Unable to analyze audio.'); guideRef.current?.say('error'); } finally { setLoading(false); }
  };

  // ---- voice command handling -------------------------------------------
  const activeRecorder = () => (stateRef.current.step === 5 ? videoCtl.current : stateRef.current.step === 4 ? voiceCtl.current : null);

  const onCommand = useCallback(async ({ intent }, text) => {
    const g = guideRef.current;
    const s = stateRef.current;
    if (!g) return;
    setHeard(text);

    switch (intent) {
      case 'stopGuide': setGuideOn(false); return;
      case 'help': g.say('help'); return;
      case 'repeat': g.repeat(); return;
      case 'consent':
        setFormData((p) => ({ ...p, consent: true }));
        await g.say('consented');
        return;
      case 'next':
        if (s.step === 1 && !s.formData.consent) { g.say('needConsent'); return; }
        if (s.step === 4 && s.recorderState === 'ready') { g.say('recorded'); return; }
        if (s.step < 5) next();
        return;
      case 'back': if (s.step > 1) back(); return;
      case 'text': if (s.formData.consent) goTo(3); else g.say('needConsent'); return;
      case 'voice': if (s.formData.consent) goTo(4); else g.say('needConsent'); return;
      case 'video': if (s.formData.consent) goTo(5); else g.say('needConsent'); return;
      case 'dictate':
        if (!s.formData.consent) { g.say('needConsent'); return; }
        // From another step, move to the narrative first; its prompt
        // explains how to start dictation.
        if (s.step !== 3) { goTo(3); return; }
        setDictating(true); g.setMode('dictation'); await g.say('dictationOn');
        return;
      case 'stopDictate':
        setDictating(false); g.setMode('commands'); await g.say('dictationOff');
        return;
      case 'clear': setFormData((p) => ({ ...p, narrative: '' })); return;
      case 'start': {
        if (!s.formData.consent) { g.say('needConsent'); return; }
        // From an earlier step, move to the voice step; its prompt asks
        // the person to say "start" when ready.
        if (s.step < 4) { goTo(4); return; }
        const rec = activeRecorder();
        if (!rec || rec.state === 'recording') return;
        await g.say('speakNow');
        rec.start();
        return;
      }
      case 'stop': {
        const rec = activeRecorder();
        if (rec && rec.state === 'recording') {
          rec.stop();
          g.setMode('commands');
          setTimeout(() => g.say('recorded'), 400);
        }
        return;
      }
      case 'submit': {
        if (s.step === 3) { handleAnalyze(); return; }
        const rec = activeRecorder();
        if (rec && rec.state === 'ready') rec.upload();
        else g.say('needNarrative');
        return;
      }
      case 'discard': {
        const rec = activeRecorder();
        if (rec && rec.state === 'ready') { rec.discard(); await g.say(s.step === 5 ? 'video' : 'voice'); }
        return;
      }
      default:
        // Unknown: only nudge for short utterances that were clearly meant
        // as a command; ignore longer speech (someone talking nearby).
        if (s.step !== 3 && String(text || '').trim().split(/\s+/).length <= 4) g.say('notUnderstood');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onDictation = useCallback((text) => {
    setFormData((p) => ({ ...p, narrative: `${p.narrative}${p.narrative && !p.narrative.endsWith(' ') ? ' ' : ''}${text}` }));
  }, []);

  // create / destroy the guide
  useEffect(() => {
    if (!guideOn) {
      if (guideRef.current) { guideRef.current.say('off'); setTimeout(() => guideRef.current?.destroy(), 1200); guideRef.current = null; }
      setDictating(false); setGuideStatus(null);
      return undefined;
    }
    const g = createVoiceGuide({
      lang: guideLang,
      onCommand,
      onDictation,
      onStatus: setGuideStatus,
      onTranscript: ({ text, final }) => { if (final) setHeard(text); },
    });
    guideRef.current = g;
    g.listen();
    (async () => { await g.say('welcome'); await g.say(STEP_PROMPT[stateRef.current.step]); })();
    return () => { g.destroy(); if (guideRef.current === g) guideRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guideOn]);

  useEffect(() => { guideRef.current?.setLang(guideLang); }, [guideLang]);

  // announce each step
  const firstStep = useRef(true);
  useEffect(() => {
    if (firstStep.current) { firstStep.current = false; return; }
    if (guideRef.current) { setDictating(false); guideRef.current.setMode('commands'); guideRef.current.say(STEP_PROMPT[step]); }
  }, [step]);

  // recorder state → guide mode (only "stop" phrases while recording)
  useEffect(() => {
    const g = guideRef.current;
    if (!g) return;
    if (recorderState === 'recording') g.setMode('recording');
    else if (!dictating) g.setMode('commands');
  }, [recorderState, dictating]);

  return <div className="assessment-wrap">
    <section className="assessment-intro">
      <div><span className="eyebrow">GUIDED ASSESSMENT</span><h2>{participantMode ? 'Share your statement' : 'New case assessment'}</h2><p>{participantMode ? 'Take your time. You can type, speak or record a video. A human responder will review what you share.' : 'Complete the short intake below. Your responses remain under human review.'}</p></div>
      <div className="assessment-id"><span>Case ID</span><strong>{formData.caseId || 'Not assigned'}</strong></div>
    </section>

    {(voiceSupport.recognition || voiceSupport.synthesis) && (
      <VoiceGuideBar enabled={guideOn} onToggle={() => setGuideOn((v) => !v)} lang={guideLang} onLangChange={setGuideLang} status={guideStatus} heard={heard} recordingMode={recorderState === 'recording'} />
    )}

    <div className="wizard">
      <div className="wizard-steps">
        {steps.map((item, i) => <React.Fragment key={item.n}>
          <button className={`wizard-step ${step === item.n ? 'current' : ''} ${step > item.n ? 'done' : ''}`} onClick={() => step > item.n && goTo(item.n)}>
            <span>{step > item.n ? <Check size={15} /> : item.n}</span><strong>{item.label}</strong>
          </button>
          {i < steps.length - 1 && <div className={`wizard-line ${step > item.n ? 'filled' : ''}`} />}
        </React.Fragment>)}
      </div>

      <div className="wizard-body">
        {step === 1 && <div className="step-panel">
          <div className="step-heading"><div className="step-icon"><ShieldCheck /></div><div><span className="eyebrow">STEP 01</span><h3>Privacy & consent</h3><p>Please review before starting an assessment.</p></div></div>
          <div className="consent-list">
            <div><CheckCircle2 /><span>AI may analyse submitted text, audio or video (voice and body-language cues) to support a human reviewer.</span></div>
            <div><CheckCircle2 /><span>Results are decision-support only, not a diagnosis or final determination.</span></div>
            <div><CheckCircle2 /><span>An authorized human responder reviews AI outputs before action.</span></div>
            <div><CheckCircle2 /><span>Recordings are processed for analysis and are not stored; information is handled under the service's privacy protocols.</span></div>
          </div>
          <label className="consent-check"><input type="checkbox" name="consent" checked={formData.consent} onChange={change} /><span><strong>I understand and consent</strong><small>I agree to continue with this assessment.{guideOn ? ' You can also say "I consent".' : ''}</small></span></label>
          <div className="step-actions end"><button className="btn btn-primary btn-large" disabled={!formData.consent} onClick={next}>Continue <ArrowRight size={17} /></button></div>
        </div>}

        {step === 2 && <div className="step-panel">
          <div className="step-heading"><div className="step-icon"><UserRound /></div><div><span className="eyebrow">STEP 02</span><h3>Case details</h3><p>Identify the case and choose the language of the response.</p></div></div>
          <div className="form-grid">
            <label className="field"><span>Case ID</span><input name="caseId" value={formData.caseId} onChange={change} placeholder="e.g. SAH-2026-001" /></label>
            <label className="field"><span>Language</span><select name="language" value={formData.language} onChange={change}><option value="en">English</option><option value="hi">Hindi</option><option value="auto">Auto-detect</option><option value="es">Spanish</option><option value="fr">French</option></select></label>
          </div>
          <div className="info-strip"><ShieldCheck size={17} /><span>Case IDs are used to associate this assessment with the appropriate record.</span></div>
          <div className="step-actions"><button className="btn btn-outline" onClick={back}><ArrowLeft size={17} /> Back</button><button className="btn btn-primary btn-large" onClick={next}>Continue <ArrowRight size={17} /></button></div>
        </div>}

        {step === 3 && <div className="step-panel">
          <div className="step-heading"><div className="step-icon"><FileText /></div><div><span className="eyebrow">STEP 03</span><h3>{participantMode ? 'Your statement' : 'Narrative assessment'}</h3><p>{participantMode ? 'Describe what happened in your own words. The whole account is read together, not just single words.' : "Capture the situation in the person's own words where possible. The narrative is analysed as a whole (cross-sentence context and discourse), not word by word."}</p></div></div>
          <label className="field narrative-field"><span>Situation narrative <em>{formData.narrative.length} characters{dictating ? ' · dictating…' : ''}</em></span><textarea name="narrative" value={formData.narrative} onChange={change} placeholder="Describe what happened, relevant circumstances, and anything the responder should know…" autoFocus /></label>
          {error && <div className="form-error">{error}</div>}
          <div className="step-actions"><div><button className="btn btn-outline" onClick={back}><ArrowLeft size={17} /> Back</button><button className="btn btn-ghost" onClick={() => setFormData((p) => ({ ...p, narrative: '' }))}>Clear</button></div><div><button className="btn btn-outline" onClick={next} disabled={loading}><Mic size={15} /> Record voice / video instead</button> <button className="btn btn-primary btn-large" onClick={handleAnalyze} disabled={loading}>{loading ? (participantMode ? 'Sending…' : 'Analyzing…') : (participantMode ? 'Submit statement' : 'Analyze narrative')} <ArrowRight size={17} /></button></div></div>
        </div>}

        {step === 4 && <div className="step-panel">
          <div className="step-heading"><div className="step-icon"><Mic /></div><div><span className="eyebrow">STEP 04</span><h3>Voice {participantMode ? 'statement' : 'assessment'}</h3><p>{participantMode ? 'Record what you want to say. Speak naturally — there is no right or wrong way.' : 'Record a spoken statement. The whole recording is analysed: what is said (context), and how — pauses, breathing, pitch, tremor, pace, tone and fumbling.'}</p></div></div>
          <div className="voice-surface"><VoiceRecorder onUpload={handleAudioUpload} controlRef={voiceCtl} onStateChange={setRecorderState} participantMode={participantMode} /></div>
          {error && <div className="form-error">{error}</div>}
          <div className="step-actions"><button className="btn btn-outline" onClick={back}><ArrowLeft size={17} /> Back</button><div><span className="step-note">{participantMode ? 'You can type your statement instead.' : 'You can use the narrative assessment instead.'}</span> <button className="btn btn-ghost" onClick={next}>Add video <ArrowRight size={15} /></button></div></div>
        </div>}

        {step === 5 && <div className="step-panel">
          <div className="step-heading"><div className="step-icon"><Video /></div><div><span className="eyebrow">STEP 05</span><h3>Video {participantMode ? 'statement' : '& voice assessment'}</h3><p>{participantMode ? 'Look at the camera and describe the situation. You can also upload a video you recorded earlier.' : 'The camera feed is analysed on this device for body-language cues (blinking pattern, eye contact, self-soothing gestures, muscle tension, swallowing, posture, expression) while the voice is analysed for tone, pauses, breathing, tremor and speech patterns. Uploaded video files are analysed on the server.'}</p></div></div>
          <div className="voice-surface"><VideoRecorder onUpload={handleVideoUpload} onUploadFile={handleVideoFile} controlRef={videoCtl} onStateChange={setRecorderState} participantMode={participantMode} /></div>
          {error && <div className="form-error">{error}</div>}
          <div className="step-actions"><button className="btn btn-outline" onClick={back}><ArrowLeft size={17} /> Back</button><span className="step-note">{loading ? (participantMode ? 'Sending your statement…' : 'Analysing voice and body language…') : (participantMode ? 'A human responder reviews every statement.' : 'Body-language cues are supplementary and never decide risk on their own.')}</span></div>
        </div>}
      </div>
    </div>
  </div>;
};
export default Assessment;
