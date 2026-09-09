import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  Paperclip,
  ShieldAlert,
} from 'lucide-react';

import { api } from '../api';
import RiskBadge from '../components/RiskBadge';
import ModalityBreakdown from '../components/ModalityBreakdown';
import NarrativeContextPanel from '../components/NarrativeContextPanel';
import TrackingPattern from '../components/TrackingPattern';
import SVIBar from '../components/SVIBar';
import SignalCard from '../components/SignalCard';
import CaseTimeline from '../components/CaseTimeline';
import { useAuth } from '../context/AuthContext';

const STATUS_LABEL = {
  NEW: 'Received — awaiting review',
  UNDER_REVIEW: 'Under review',
  ACTION_REQUIRED: 'A responder is acting on this',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
};

/* =========================================================
   USER / VICTIM VIEW
========================================================= */

const ParticipantCase = ({ data }) => {
  const navigate = useNavigate();

  return (
    <div className="page-stack">
      <section className="case-detail-head">
        <div>
          <button
            className="back-link"
            onClick={() => navigate('/user/dashboard')}
          >
            <ArrowLeft size={16} />
            Back to my dashboard
          </button>

          <span className="eyebrow">MY STATEMENT</span>

          <h2>{data.case_id}</h2>

          <p>
            Submitted{' '}
            {data.created_at
              ? new Date(data.created_at).toLocaleString()
              : ''}
          </p>
        </div>
      </section>

      <div className="panel receipt-panel">
        <div className="receipt-icon">
          <CheckCircle2 size={30} />
        </div>

        <h3>{data.message}</h3>

        <div className="receipt-meta">
          <span>Status</span>

          <strong>
            {STATUS_LABEL[data.status] || data.status}
          </strong>

          <span>Submitted as</span>

          <strong>
            {data.capture_mode === 'video'
              ? 'Video statement'
              : data.capture_mode === 'voice'
                ? 'Voice statement'
                : 'Written statement'}
          </strong>
        </div>

        <div className="human-banner">
          <ShieldAlert size={18} />

          <div>
            <strong>
              A human responder reviews every statement
            </strong>

            <span>
              If your situation changes or you are in immediate danger,
              contact local emergency services.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

/* =========================================================
   ADDITIONAL EVIDENCE PREVIEW
========================================================= */

const EvidencePreview = ({ caseId, item }) => {
  const url = api.getCaseEvidenceUrl(
    caseId,
    item.id
  );

  const type = String(
    item.content_type || ''
  ).toLowerCase();

  const filename = String(
    item.filename || 'Evidence file'
  );

  const extension = filename
    .split('.')
    .pop()
    ?.toLowerCase();

  const isImage =
    type.startsWith('image/');

  const isVideo =
    type.startsWith('video/');

  const isAudio =
    type.startsWith('audio/');

  const isPdf =
    type === 'application/pdf' ||
    extension === 'pdf';

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">

      {/* File header */}

      <div className="mb-3 flex items-center justify-between gap-3">

        <div className="flex min-w-0 items-center gap-2">

          <Paperclip
            size={15}
            className="shrink-0 text-teal-600"
          />

          <div className="min-w-0">

            <strong className="block truncate text-xs text-slate-800">
              {filename}
            </strong>

            <span className="text-[10px] text-slate-500">
              {Math.ceil(
                (item.size || 0) / 1024
              )}{' '}
              KB
            </span>

          </div>
        </div>

        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          download={filename}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-100"
        >
          <Download size={13} />
          Open
        </a>

      </div>

      {/* Image */}

      {isImage && (
        <img
          src={url}
          alt={filename}
          className="max-h-96 w-full rounded-lg object-contain bg-white"
        />
      )}

      {/* Video */}

      {isVideo && (
        <video
          controls
          preload="metadata"
          src={url}
          className="max-h-96 w-full rounded-lg bg-slate-900"
        />
      )}

      {/* Audio */}

      {isAudio && (
        <audio
          controls
          preload="metadata"
          src={url}
          className="w-full"
        />
      )}

      {/* PDF */}

      {isPdf && (
        <iframe
          title={filename}
          src={url}
          className="h-96 w-full rounded-lg border border-slate-200 bg-white"
        />
      )}

      {/* Other formats */}

      {!isImage &&
        !isVideo &&
        !isAudio &&
        !isPdf && (
          <div className="rounded-lg bg-white p-4 text-center">
            <FileText
              size={28}
              className="mx-auto mb-2 text-slate-400"
            />

            <p className="text-[11px] text-slate-500">
              Preview is not available for this file format.
            </p>

            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              download={filename}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-bold text-teal-600"
            >
              <Download size={13} />
              Open file
            </a>
          </div>
        )}

    </div>
  );
};

/* =========================================================
   AUTHORITY / RESPONDER CASE DETAILS
========================================================= */

const CaseDetails = () => {
  const { caseId } = useParams();
  const navigate = useNavigate();

  const { user } = useAuth();

  const participant =
    user?.role === 'user';

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    api
      .getCase(
        caseId,
        participant
          ? { view: 'participant' }
          : {}
      )
      .then(setData)
      .catch((e) => {
        setError(
          e.message ||
            'Unable to load case.'
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [caseId, participant]);

  /* Loading */

  if (loading) {
    return (
      <div className="state-card">
        <div className="spinner" />

        <strong>
          Loading case details…
        </strong>
      </div>
    );
  }

  /* Error */

  if (error) {
    return (
      <div className="state-card error-state">

        <ShieldAlert size={25} />

        <strong>{error}</strong>

        <button
          className="btn btn-outline"
          onClick={() =>
            navigate(
              participant
                ? '/user/dashboard'
                : '/cases'
            )
          }
        >
          Back
        </button>

      </div>
    );
  }

  /* No case */

  if (!data) {
    return (
      <div className="state-card">
        <strong>
          Case not found.
        </strong>
      </div>
    );
  }

  /* Victim view */

  if (participant) {
    return (
      <ParticipantCase data={data} />
    );
  }

  const behaviorFeatures =
    data.behavior_analysis?.features;

  const submittedEvidence =
    data.submitted_evidence || [];

  return (
    <div className="page-stack">

      {/* =====================================================
          HEADER
      ===================================================== */}

      <section className="case-detail-head">

        <div>

          <button
            className="back-link"
            onClick={() =>
              navigate('/cases')
            }
          >
            <ArrowLeft size={16} />
            Back to queue
          </button>

          <span className="eyebrow">
            CASE RECORD · RESPONDER VIEW
          </span>

          <h2>{data.case_id}</h2>

          <p>
            Assessment details, evidence and responder context.
          </p>

        </div>

        <RiskBadge
          level={data.risk_level}
        />

        <select
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold"
          value={
            data.status || 'NEW'
          }
          onChange={async (e) => {
            try {
              const updated =
                await api.updateCaseStatus(
                  caseId,
                  e.target.value
                );

              setData(updated);
            } catch (err) {
              setError(
                err.message ||
                  'Unable to update case status.'
              );
            }
          }}
        >
          <option value="NEW">
            New
          </option>

          <option value="UNDER_REVIEW">
            Under Review
          </option>

          <option value="ACTION_REQUIRED">
            Action Required
          </option>

          <option value="RESOLVED">
            Resolved
          </option>

          <option value="CLOSED">
            Closed
          </option>
        </select>

      </section>

      <div className="detail-grid">

        {/* ===================================================
            MAIN CONTENT
        =================================================== */}

        <main className="page-stack">

          {/* =================================================
              ORIGINAL VICTIM SUBMISSION
          ================================================= */}

          <div className="panel">

            <div className="panel-header">

              <div>

                <span className="eyebrow">
                  VICTIM SUBMISSION
                </span>

                <h3>
                  Original evidence
                </h3>

              </div>

              <span className="record-date">
                {data.capture_mode ===
                'video'
                  ? 'Video'
                  : data.capture_mode ===
                      'voice'
                    ? 'Audio'
                    : 'Written'}
              </span>

            </div>

            {/* Written statement */}

            {(data.narrative ||
              data.transcript) && (
              <div className="submission-text">

                <span className="submission-label">
                  Statement
                </span>

                <p>
                  {data.narrative ||
                    data.transcript}
                </p>

              </div>
            )}

            {/* Original video */}

            {data.media?.kind ===
              'video' && (
              <div className="submission-media">

                <span className="submission-label">
                  Video recording
                </span>

                <video
                  controls
                  preload="metadata"
                  src={api.getCaseMediaUrl(
                    caseId
                  )}
                />

              </div>
            )}

            {/* Original audio */}

            {data.media?.kind ===
              'audio' && (
              <div className="submission-media">

                <span className="submission-label">
                  Audio recording
                </span>

                <audio
                  controls
                  preload="metadata"
                  src={api.getCaseMediaUrl(
                    caseId
                  )}
                />

              </div>
            )}

            {/* =================================================
                ADDITIONAL EVIDENCE
            ================================================= */}

            {submittedEvidence.length >
              0 && (
              <div className="case-evidence-list">

                <div className="submission-label">
                  Additional supporting evidence
                </div>

                <div className="grid gap-3">

                  {submittedEvidence.map(
                    (item) => (
                      <EvidencePreview
                        key={item.id}
                        caseId={caseId}
                        item={item}
                      />
                    )
                  )}

                </div>

              </div>
            )}

            {/* Nothing submitted */}

            {!data.narrative &&
              !data.transcript &&
              !data.media &&
              submittedEvidence.length ===
                0 && (
                <p className="muted-copy">
                  No original submission content is available for this case.
                </p>
              )}

          </div>

          {/* =================================================
              RISK PROFILE
          ================================================= */}

          <div className="panel">

            <div className="panel-header">

              <div>

                <span className="eyebrow">
                  RISK PROFILE
                </span>

                <h3>
                  Stress &amp; Vulnerability Index
                </h3>

              </div>

              <span className="record-date">
                Updated{' '}
                {data.updated_at ||
                  'N/A'}
              </span>

            </div>

            <SVIBar
              score={data.svi_score}
            />

          </div>

          {/* =================================================
              SIGNALS
          ================================================= */}

          <section>

            <div className="section-title">

              <div>

                <span className="eyebrow">
                  SIGNALS
                </span>

                <h3>
                  Vulnerability profile
                </h3>

              </div>

            </div>

            <div className="signal-grid">

              {Object.entries(
                data.signals || {}
              ).map(
                ([
                  signal,
                  score,
                ]) => (
                  <SignalCard
                    key={signal}
                    signal={signal}
                    score={score}
                    level={
                      data
                        .vulnerability_profile?.[
                        signal
                      ] ||
                      'UNKNOWN'
                    }
                  />
                )
              )}

            </div>

          </section>

          {/* =================================================
              NARRATIVE CONTEXT
          ================================================= */}

          {data.narrative_context && (
            <NarrativeContextPanel
              context={
                data.narrative_context
              }
            />
          )}

          {/* =================================================
              MODALITY ANALYSIS
          ================================================= */}

          {data.modalities && (
            <ModalityBreakdown
              modalities={
                data.modalities
              }
              transcript={
                data.transcript
              }
              voiceAnalysis={
                data.voice_analysis
              }
            />
          )}

          {/* =================================================
              BEHAVIOUR
          ================================================= */}

          {behaviorFeatures && (
            <TrackingPattern
              features={
                behaviorFeatures
              }
            />
          )}

          {/* =================================================
              AI ANALYSIS
          ================================================= */}

          <div className="panel">

            <div className="panel-header">

              <div>

                <span className="eyebrow">
                  AI ANALYSIS
                </span>

                <h3>
                  Explanation &amp; evidence
                </h3>

              </div>

              <FileText size={19} />

            </div>

            <div className="detail-subsection">

              <h4>
                Explanations
              </h4>

              {(data.explanation ||
                []).map(
                (x, i) => (
                  <div
                    className="explanation-line"
                    key={i}
                  >
                    {x}
                  </div>
                )
              )}

            </div>

            <div className="detail-subsection">

              <h4>
                Evidence
              </h4>

              {(data.evidence ||
                []).map(
                (x, i) => (
                  <div
                    className="evidence-item"
                    key={i}
                  >
                    <p>
                      “{x.text}”
                    </p>

                    <span>
                      {x.signal}
                    </span>
                  </div>
                )
              )}

            </div>

          </div>

        </main>

        {/* ===================================================
            SIDEBAR
        =================================================== */}

        <aside className="page-stack">

          {/* Timeline */}

          <div className="panel">

            <div className="panel-header">

              <div>

                <span className="eyebrow">
                  ACTIVITY
                </span>

                <h3>
                  Case timeline
                </h3>

              </div>

              <Clock3 size={18} />

            </div>

            <CaseTimeline
              events={
                data.timeline
              }
            />

          </div>

          {/* Recommendations */}

          <div className="recommendation-panel">

            <span className="eyebrow">
              RESPONDER NOTES
            </span>

            <h3>
              Recommendations
            </h3>

            <ul>

              {(data.recommendations ||
                []).map(
                (x, i) => (
                  <li key={i}>

                    <span>
                      0{i + 1}
                    </span>

                    {x}

                  </li>
                )
              )}

            </ul>

          </div>

          {/* Human review */}

          {data.human_review_required && (
            <div className="human-banner vertical">

              <ShieldAlert
                size={20}
              />

              <div>

                <strong>
                  Review required
                </strong>

                <span>
                  This case requires human review.
                </span>

              </div>

            </div>
          )}

        </aside>

      </div>

    </div>
  );
};

export default CaseDetails;