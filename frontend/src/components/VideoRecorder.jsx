import React, {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import {
  Activity,
  Camera,
  Eye,
  EyeOff,
  FileVideo,
  Hand,
  HeartHandshake,
  ScanFace,
  Square,
  Trash2,
  Upload,
  Video,
} from 'lucide-react';
import { api } from '../api';

const ANALYSIS_INTERVAL_MS = 50;
const LIVE_UI_INTERVAL_MS = 500;
const LIVE_SCORE_INTERVAL_MS = 4000;

const time = (s) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

const VideoRecorder = ({
  onUpload,
  onUploadFile,
  controlRef,
  onStateChange,
  participantMode = false,
  allowFileUpload = true,
}) => {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const modelsRef = useRef(null);
  const analyzerRef = useRef(null);
  const libRef = useRef(null);
  const recorderRef = useRef(null);
  const loopRef = useRef(null);
  const uiTimerRef = useRef(null);
  const scoreTimerRef = useRef(null);
  const durationTimerRef = useRef(null);
  const lastTsRef = useRef(0);
  const blobRef = useRef(null);
  const featuresRef = useRef(null);
  const statusRef = useRef('init');
  const fileInputRef = useRef(null);

  const [status, setStatus] = useState('init');
  const [progress, setProgress] = useState(
    'Requesting camera & microphone…'
  );
  const [error, setError] = useState(null);
  const [showOverlay, setShowOverlay] = useState(!participantMode);
  const [duration, setDuration] = useState(0);
  const [live, setLive] = useState(null);
  const [liveScore, setLiveScore] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [modelsFailed, setModelsFailed] = useState(false);
  const [videoFile, setVideoFile] = useState(null);
  const [serverFootage, setServerFootage] = useState(null);

  const emit = (state) => onStateChange?.(state);

  const setStatusBoth = (s) => {
    statusRef.current = s;
    setStatus(s);
  };

  function stopLoop() {
    clearInterval(loopRef.current);
    clearInterval(uiTimerRef.current);
    clearInterval(scoreTimerRef.current);
    clearInterval(durationTimerRef.current);
  }

  // ------------------------------------------------------------
  // Camera + microphone setup
  // ------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: 'user',
          },
          audio: true,
        });

        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        streamRef.current = stream;

        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }

        try {
          const lib = await import('../lib/behaviorAnalyzer');

          libRef.current = lib;
          analyzerRef.current = lib.createBehaviorAnalyzer();

          modelsRef.current = await lib.loadModels((msg) => {
            if (!cancelled) {
              setProgress(
                participantMode ? 'Preparing camera…' : msg
              );
            }
          });
        } catch (err) {
          console.warn('MediaPipe models failed to load', err);

          if (!cancelled) {
            setModelsFailed(true);
          }
        }

        if (!cancelled) {
          setStatusBoth('ready');
          emit('idle');
        }
      } catch (err) {
        console.error('Camera/microphone error:', err);

        if (!cancelled) {
          setError(
            'Camera or microphone access was denied or is unavailable.'
          );
          setStatusBoth('error');
          emit('idle');
        }
      }
    })();

    if (allowFileUpload) {
      api
        .getVideoCapabilities()
        .then((c) => {
          if (!cancelled) {
            setServerFootage(Boolean(c?.server_footage_analysis));
          }
        })
        .catch(() => {
          if (!cancelled) {
            setServerFootage(false);
          }
        });
    }

    return () => {
      cancelled = true;

      stopLoop();

      if (
        recorderRef.current &&
        recorderRef.current.state !== 'inactive'
      ) {
        try {
          recorderRef.current.stop();
        } catch {
          // Recorder may already be stopped.
        }
      }

      streamRef.current?.getTracks().forEach((track) => track.stop());

      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------------
  // On-device behavior analysis
  // ------------------------------------------------------------
  const analyseFrame = useCallback(() => {
    const video = videoRef.current;
    const models = modelsRef.current;

    if (
      !video ||
      !models ||
      !analyzerRef.current ||
      video.readyState < 2
    ) {
      return;
    }

    let ts = performance.now();

    if (ts <= lastTsRef.current) {
      ts = lastTsRef.current + 1;
    }

    lastTsRef.current = ts;

    try {
      const faceResult = models.face.detectForVideo(video, ts);
      const handResult = models.hands.detectForVideo(video, ts);
      const poseResult = models.pose
        ? models.pose.detectForVideo(video, ts)
        : null;

      const snapshot = analyzerRef.current.processFrame(
        faceResult,
        handResult,
        poseResult,
        ts
      );

      if (canvasRef.current && !participantMode) {
        if (showOverlay) {
          libRef.current?.drawOverlay(
            canvasRef.current,
            video,
            faceResult,
            handResult,
            poseResult,
            snapshot
          );
        } else {
          canvasRef.current
            .getContext('2d')
            ?.clearRect(
              0,
              0,
              canvasRef.current.width,
              canvasRef.current.height
            );
        }
      }
    } catch (err) {
      console.warn('Frame analysis failed:', err);
    }
  }, [showOverlay, participantMode]);

  useEffect(() => {
    if (status !== 'recording' && status !== 'ready') {
      return undefined;
    }

    loopRef.current = setInterval(
      analyseFrame,
      ANALYSIS_INTERVAL_MS
    );

    return () => clearInterval(loopRef.current);
  }, [status, analyseFrame]);

  // ------------------------------------------------------------
  // Live behavior score
  // ------------------------------------------------------------
  const refreshLiveScore = async () => {
    if (participantMode) return;

    const summary = analyzerRef.current?.summary();

    if (!summary?.available || summary.duration_sec < 3) {
      return;
    }

    try {
      const score = await api.scoreBehavior(summary);
      setLiveScore(score);
    } catch {
      // Cosmetic live score only.
    }
  };

  // ------------------------------------------------------------
  // START RECORDING
  // IMPORTANT:
  // Records BOTH camera video + microphone audio.
  // ------------------------------------------------------------
  const startRecording = () => {
    const stream = streamRef.current;

    if (!stream || statusRef.current === 'recording') {
      return;
    }

    setError(null);

    analyzerRef.current?.reset();
    lastTsRef.current = 0;

    setLive(null);
    setLiveScore(null);
    setDuration(0);

    // Make sure we are recording the COMPLETE camera + microphone stream.
    const chunks = [];

    let mimeType = '';

    if (
      typeof MediaRecorder !== 'undefined' &&
      MediaRecorder.isTypeSupported(
        'video/webm;codecs=vp8,opus'
      )
    ) {
      mimeType = 'video/webm;codecs=vp8,opus';
    } else if (
      typeof MediaRecorder !== 'undefined' &&
      MediaRecorder.isTypeSupported('video/webm')
    ) {
      mimeType = 'video/webm';
    } else if (
      typeof MediaRecorder !== 'undefined' &&
      MediaRecorder.isTypeSupported('video/mp4')
    ) {
      mimeType = 'video/mp4';
    }

    let recorder;

    try {
      recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
    } catch (err) {
      console.error('MediaRecorder initialization failed:', err);

      setError(
        'Video recording is not supported by this browser.'
      );
      setStatusBoth('error');
      emit('idle');

      return;
    }

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    };

    recorder.onerror = (event) => {
      console.error('MediaRecorder error:', event);

      setError('An error occurred while recording the video.');
      setStatusBoth('error');
      emit('idle');
    };

    recorder.onstop = () => {
      const type = recorder.mimeType || mimeType || 'video/webm';

      const blob = new Blob(chunks, {
        type,
      });

      if (!blob.size) {
        setError('The recorded video is empty.');
        setStatusBoth('error');
        emit('idle');
        return;
      }

      blobRef.current = blob;

      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }

      setAudioUrl(URL.createObjectURL(blob));

      emit('ready');
    };

    recorderRef.current = recorder;

    try {
      // Record the complete stream, not just the audio tracks.
      recorder.start(1000);
    } catch (err) {
      console.error('Failed to start recording:', err);

      recorderRef.current = null;
      setError('Unable to start video recording.');
      setStatusBoth('error');
      emit('idle');

      return;
    }

    setStatusBoth('recording');
    emit('recording');

    durationTimerRef.current = setInterval(() => {
      setDuration((d) => d + 1);
    }, 1000);

    if (!participantMode) {
      uiTimerRef.current = setInterval(() => {
        if (analyzerRef.current) {
          setLive(analyzerRef.current.summary());
        }
      }, LIVE_UI_INTERVAL_MS);

      scoreTimerRef.current = setInterval(
        refreshLiveScore,
        LIVE_SCORE_INTERVAL_MS
      );
    }
  };

  // ------------------------------------------------------------
  // STOP RECORDING
  // ------------------------------------------------------------
  const stopRecording = () => {
    if (statusRef.current !== 'recording') {
      return;
    }

    stopLoop();

    const recorder = recorderRef.current;

    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop();
      } catch (err) {
        console.error('Failed to stop recorder:', err);
      }
    }

    const summary = analyzerRef.current?.summary();

    featuresRef.current =
      modelsFailed || !summary
        ? { available: false }
        : summary;

    if (!participantMode) {
      setLive(summary || null);
    }

    setStatusBoth('review');

    refreshLiveScore();
  };

  // ------------------------------------------------------------
  // DISCARD
  // ------------------------------------------------------------
  const discard = () => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }

    blobRef.current = null;
    featuresRef.current = null;
    recorderRef.current = null;

    setAudioUrl(null);
    setLive(null);
    setLiveScore(null);
    setDuration(0);

    analyzerRef.current?.reset();

    setStatusBoth('ready');
    emit('idle');
  };

  // ------------------------------------------------------------
  // UPLOAD LIVE RECORDING
  // ------------------------------------------------------------
  const upload = async () => {
    const blob = blobRef.current;

    if (!blob || !onUpload) {
      return;
    }

    setIsUploading(true);
    emit('uploading');

    try {
      await onUpload(
        blob,
        featuresRef.current || { available: false }
      );
    } catch (err) {
      console.error('Video upload failed:', err);
      throw err;
    } finally {
      setIsUploading(false);
    }
  };

  // ------------------------------------------------------------
  // UPLOAD EXISTING VIDEO FILE
  // ------------------------------------------------------------
  const uploadFile = async () => {
    if (!videoFile || !onUploadFile) {
      return;
    }

    setIsUploading(true);
    emit('uploading');

    try {
      await onUploadFile(videoFile);
    } catch (err) {
      console.error('Video file upload failed:', err);
      throw err;
    } finally {
      setIsUploading(false);
    }
  };

  // ------------------------------------------------------------
  // External control API
  // ------------------------------------------------------------
  useImperativeHandle(controlRef, () => ({
    start: startRecording,
    stop: stopRecording,
    discard,
    upload,

    get state() {
      if (isUploading) {
        return 'uploading';
      }

      if (statusRef.current === 'recording') {
        return 'recording';
      }

      if (blobRef.current) {
        return 'ready';
      }

      return 'idle';
    },
  }));

  // ------------------------------------------------------------
  // Render
  // ------------------------------------------------------------
  const recording = status === 'recording';

  const stats = participantMode ? null : live;

  const tension = stats
    ? Math.max(
        stats.jaw_clench_ratio || 0,
        stats.shoulder_raise_ratio || 0,
        stats.freeze_ratio || 0
      )
    : 0;

  const soothing = stats
    ? (stats.hand_rub_count || 0) +
      (stats.arm_stroke_count || 0) +
      (stats.neck_touch_count || 0) +
      (stats.hair_touch_count || 0)
    : 0;

  return (
    <div className="video-recorder">
      <div className="video-stage">
        <video
          ref={videoRef}
          muted
          playsInline
          autoPlay
          className="video-feed"
        />

        {!participantMode && (
          <canvas
            ref={canvasRef}
            className="video-overlay"
          />
        )}

        {status === 'init' && (
          <div className="video-loading">
            <div className="spinner" />
            <span>{progress}</span>
          </div>
        )}

        {status === 'error' && (
          <div className="video-loading">
            <Camera size={26} />
            <span>{error}</span>
          </div>
        )}

        {recording && (
          <div className="video-rec-badge">
            <i /> REC {time(duration)}
          </div>
        )}

        {!participantMode &&
          status !== 'init' &&
          status !== 'error' && (
            <button
              type="button"
              className="video-toggle"
              onClick={() =>
                setShowOverlay((v) => !v)
              }
              title="Toggle tracking overlay"
            >
              {showOverlay ? (
                <Eye size={14} />
              ) : (
                <EyeOff size={14} />
              )}
              Tracking
            </button>
          )}

        <div className="video-privacy">
          <ScanFace size={13} />

          {participantMode
            ? 'Your camera stays on this device. Only your recorded statement is sent for review.'
            : 'Video is analysed on this device only — frames are never uploaded.'}
        </div>
      </div>

      {modelsFailed &&
        status !== 'error' &&
        !participantMode && (
          <div className="form-error">
            Body-language models could not be loaded
            (check internet access for the first download).
            Audio will still be recorded and analysed.
          </div>
        )}

      <div className="video-controls">
        <button
          className={`record-button ${
            recording ? 'recording' : ''
          }`}
          disabled={
            status === 'init' ||
            status === 'error' ||
            status === 'review' ||
            isUploading
          }
          onClick={
            recording ? stopRecording : startRecording
          }
          aria-label={
            recording
              ? 'Stop recording'
              : 'Start recording'
          }
        >
          {recording ? (
            <Square size={26} fill="currentColor" />
          ) : (
            <Video size={28} />
          )}
        </button>

        <div className="record-status">
          {recording ? (
            <>
              <span className="record-live">
                <i /> Recording
              </span>
              <strong>{time(duration)}</strong>
            </>
          ) : status === 'review' ? (
            <>
              <strong>Recording ready</strong>
              <span>
                {participantMode
                  ? 'Listen back, then submit when you are ready'
                  : 'Review the capture summary below'}
              </span>
            </>
          ) : (
            <>
              <strong>
                {status === 'ready'
                  ? 'Tap to start'
                  : 'Preparing…'}
              </strong>

              <span>
                Look at the camera and describe the
                situation in your own words
              </span>
            </>
          )}
        </div>
      </div>

      {stats && (
        <div className="live-grid">
          <LiveStat
            icon={<Eye size={15} />}
            label="Blink rate"
            value={`${stats.blink_rate_per_min.toFixed(0)}/min`}
            hint={
              stats.blink_burst_count
                ? `${stats.blink_burst_count} bursts`
                : stats.blink_rate_per_min > 25
                ? 'elevated'
                : 'normal'
            }
            warn={stats.blink_rate_per_min > 25}
          />

          <LiveStat
            icon={<ScanFace size={15} />}
            label="Eye contact avoided"
            value={`${(
              stats.gaze_aversion_ratio * 100
            ).toFixed(0)}%`}
            warn={stats.gaze_aversion_ratio > 0.4}
          />

          <LiveStat
            icon={<Hand size={15} />}
            label="Face touches"
            value={stats.face_touch_count}
            hint={`${stats.face_touch_duration_sec.toFixed(0)}s`}
            warn={stats.face_touch_count >= 2}
          />

          <LiveStat
            icon={<HeartHandshake size={15} />}
            label="Self-soothing"
            value={soothing}
            hint={
              stats.finger_clasp_ratio > 0.15
                ? 'fingers clasped'
                : stats.self_hug_ratio > 0.15
                ? 'self-hug'
                : stats.hands_detected_ratio < 0.2
                ? 'hands not in frame'
                : 'rub / stroke / neck / hair'
            }
            warn={
              soothing >= 2 ||
              stats.finger_clasp_ratio > 0.15
            }
          />

          <LiveStat
            icon={<Activity size={15} />}
            label="Hand fidgeting"
            value={`${stats.hand_fidget_rate_per_min.toFixed(
              0
            )}/min`}
            hint={
              stats.hands_detected_ratio < 0.2
                ? 'hands not in frame'
                : undefined
            }
            warn={stats.hand_fidget_rate_per_min > 10}
          />

          <LiveStat
            icon={<Activity size={15} />}
            label="Muscle tension"
            value={`${Math.round(tension * 100)}%`}
            hint={
              stats.freeze_ratio > 0.3
                ? 'frozen stillness'
                : stats.shoulder_raise_ratio > 0.2
                ? 'shoulders raised'
                : stats.jaw_clench_ratio > 0.15
                ? 'jaw clenched'
                : undefined
            }
            warn={tension > 0.2}
          />

          <LiveStat
            icon={<Activity size={15} />}
            label="Swallowing"
            value={`${stats.swallow_rate_per_min.toFixed(
              0
            )}/min`}
            hint="approximate"
            warn={stats.swallow_rate_per_min > 4}
          />

          <LiveStat
            icon={<Activity size={15} />}
            label="Head movement"
            value={`${(
              stats.head_movement_energy * 60
            ).toFixed(0)}°/s`}
            hint={
              stats.head_down_ratio > 0.3
                ? 'often looking down'
                : stats.slouch_ratio > 0.3
                ? 'slouched'
                : undefined
            }
            warn={stats.head_movement_energy > 0.25}
          />

          <LiveStat
            icon={<ScanFace size={15} />}
            label="Facial tension"
            value={`${Math.round(
              ((stats.expression.brow_furrow +
                stats.expression.lip_press +
                stats.expression.mouth_frown) /
                3) *
                100
            )}%`}
            warn={
              (stats.expression.brow_furrow +
                stats.expression.lip_press +
                stats.expression.mouth_frown) /
                3 >
              0.25
            }
          />

          <div className="live-indicator">
            <span>Non-verbal stress indicator</span>

            <strong>
              {liveScore?.available
                ? `${liveScore.indicator.toFixed(0)}/100`
                : '—'}
            </strong>

            <div className="mini-track">
              <div
                className="mini-fill"
                style={{
                  width: `${
                    liveScore?.indicator || 0
                  }%`,
                }}
              />
            </div>

            <small>
              Face visible{' '}
              {(
                stats.face_detected_ratio * 100
              ).toFixed(0)}
              % · pose{' '}
              {(
                stats.pose_detected_ratio * 100
              ).toFixed(0)}
              % · {stats.fps} fps ·{' '}
              {stats.events?.length || 0} tracked events
              · supplementary only
            </small>
          </div>
        </div>
      )}

      {status === 'review' && audioUrl && (
        <div className="audio-review">
          <video
            src={audioUrl}
            controls
            style={{
              width: '100%',
              maxHeight: '320px',
              borderRadius: '12px',
            }}
          />

          {!participantMode &&
            liveScore?.cues?.length ? (
            <ul className="cue-list">
              {liveScore.cues.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          ) : null}

          <div className="recorder-actions">
            <button
              className="btn btn-ghost danger"
              onClick={discard}
              disabled={isUploading}
            >
              <Trash2 size={16} />
              Discard
            </button>

            <button
              className="btn btn-primary"
              onClick={upload}
              disabled={isUploading}
            >
              {isUploading ? (
                'Sending…'
              ) : (
                <>
                  <Upload size={16} />
                  {participantMode
                    ? 'Submit statement'
                    : 'Analyze voice + body language'}
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {allowFileUpload &&
        onUploadFile &&
        status !== 'recording' && (
          <div className="file-upload-row">
            <div className="file-upload-head">
              <FileVideo size={16} />

              <div>
                <strong>
                  Or upload a recorded video
                </strong>

                <span>
                  {serverFootage === false
                    ? 'The server will analyse the audio track; footage analysis is not enabled on this server.'
                    : 'The audio track and the footage (blinking, eye contact, gestures, posture) are analysed on the server. Nothing is stored.'}
                </span>
              </div>
            </div>

            <div className="file-upload-actions">
              <input
                ref={fileInputRef}
                type="file"
                accept="video/mp4,video/webm,video/quicktime,video/x-matroska"
                onChange={(e) =>
                  setVideoFile(
                    e.target.files?.[0] || null
                  )
                }
                disabled={isUploading}
              />

              <button
                className="btn btn-outline"
                onClick={uploadFile}
                disabled={
                  !videoFile || isUploading
                }
              >
                {isUploading ? (
                  'Analysing…'
                ) : (
                  <>
                    <Upload size={15} />
                    {participantMode
                      ? 'Submit video'
                      : 'Analyze video file'}
                  </>
                )}
              </button>
            </div>
          </div>
        )}
    </div>
  );
};

const LiveStat = ({
  icon,
  label,
  value,
  hint,
  warn,
}) => (
  <div
    className={`live-stat ${warn ? 'warn' : ''}`}
  >
    <div className="live-stat-head">
      {icon}
      <span>{label}</span>
    </div>

    <strong>{value}</strong>

    {hint && <small>{hint}</small>}
  </div>
);

export default VideoRecorder;