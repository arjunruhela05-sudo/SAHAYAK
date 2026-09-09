import React, { useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Mic, Square, Trash2, Upload } from 'lucide-react';

const time = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

/**
 * Microphone recorder.
 *
 * `controlRef` exposes { start, stop, discard, upload, state } so the
 * voice-command guide can drive it hands-free.  `onStateChange(state)`
 * fires on idle | recording | ready | uploading.
 */
const VoiceRecorder = ({ onUpload, controlRef, onStateChange, participantMode = false }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [duration, setDuration] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const mediaRecorder = useRef(null);
  const timerRef = useRef(null);
  const blobRef = useRef(null);

  const emit = (state) => onStateChange?.(state);

  const startRecording = async () => {
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') return;
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const rec = new MediaRecorder(stream);
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        blobRef.current = blob;
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        emit('ready');
      };
      rec.start(1000);
      mediaRecorder.current = rec;
      setDuration(0);
      setIsRecording(true);
      emit('recording');
      timerRef.current = setInterval(() => setDuration((d) => d + 1), 1000);
    } catch {
      setError('Microphone access denied or not available.');
      emit('idle');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      mediaRecorder.current.stop();
      mediaRecorder.current.stream.getTracks().forEach((t) => t.stop());
    }
    setIsRecording(false);
    clearInterval(timerRef.current);
  };

  const remove = () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    blobRef.current = null;
    setAudioBlob(null);
    setAudioUrl(null);
    setDuration(0);
    emit('idle');
  };

  const upload = async () => {
    const blob = blobRef.current;
    if (!blob) return;
    setIsUploading(true);
    emit('uploading');
    try { await onUpload(blob); } finally { setIsUploading(false); }
  };

  useImperativeHandle(controlRef, () => ({
    start: startRecording,
    stop: stopRecording,
    discard: remove,
    upload,
    get state() {
      if (isUploading) return 'uploading';
      if (isRecording) return 'recording';
      if (blobRef.current) return 'ready';
      return 'idle';
    },
  }));

  useEffect(() => () => {
    clearInterval(timerRef.current);
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      try { mediaRecorder.current.stop(); mediaRecorder.current.stream.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
    }
  }, []);

  return (
    <div className="recorder-block">
      <div className="recorder">
        <button className={`record-button ${isRecording ? 'recording' : ''}`} onClick={isRecording ? stopRecording : startRecording} disabled={isUploading} aria-label={isRecording ? 'Stop recording' : 'Start recording'}>
          {isRecording ? <Square size={27} fill="currentColor" /> : <Mic size={29} />}
        </button>
        <div className="record-status">
          {isRecording
            ? <><span className="record-live"><i /> Recording</span><strong>{time(duration)}</strong></>
            : <><strong>{audioBlob ? 'Recording ready' : 'Tap to record'}</strong><span>{audioBlob ? (participantMode ? 'Listen back, then submit when you are ready' : 'Review your audio below') : 'Speak naturally, in your own words'}</span></>}
        </div>
      </div>
      {error && <div className="form-error">{error}</div>}
      {audioUrl && (
        <div className="audio-review">
          <audio src={audioUrl} controls />
          <div className="recorder-actions">
            <button className="btn btn-ghost danger" onClick={remove} disabled={isUploading}><Trash2 size={16} /> Discard</button>
            <button className="btn btn-primary" onClick={upload} disabled={isUploading}>{isUploading ? 'Sending…' : <><Upload size={16} /> {participantMode ? 'Submit statement' : 'Upload & analyze'}</>}</button>
          </div>
        </div>
      )}
    </div>
  );
};
export default VoiceRecorder;
