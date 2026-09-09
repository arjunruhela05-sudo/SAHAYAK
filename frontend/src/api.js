const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const CASE_STATUSES = ["NEW", "UNDER_REVIEW", "ACTION_REQUIRED", "RESOLVED", "CLOSED"];

async function remote(endpoint, options = {}) {
  const isForm = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body?.message || body?.detail || body?.error || `API Error ${response.status}`;
    throw new Error(message);
  }
  return body;
}

const normalizeCases = (response) => {
  if (Array.isArray(response)) return response;
  if (Array.isArray(response?.cases)) return response.cases;
  if (Array.isArray(response?.data)) return response.data;
  return [];
};

const normalizeTimeline = (events = []) => events.map((event) => ({
  ...event,
  details: event.details ?? event.description ?? "",
}));

const normalizeCase = (item) => item ? ({
  ...item,
  timeline: normalizeTimeline(item.timeline),
}) : null;

const normalizeStatus = (status) => {
  const map = {
    "Pending Review": "NEW",
    "Under Review": "UNDER_REVIEW",
    "Escalated": "ACTION_REQUIRED",
    "Completed": "RESOLVED",
    "Closed": "CLOSED",
  };
  return map[status] || status;
};

const displayStatus = (status) => {
  const map = {
    NEW: "New",
    UNDER_REVIEW: "Under Review",
    ACTION_REQUIRED: "Action Required",
    RESOLVED: "Resolved",
    CLOSED: "Closed",
  };
  return map[status] || status;
};

export const api = {
  async checkHealth() {
    return remote("/api/health");
  },

  /**
   * Text assessment.  `participantView: true` (the assessed person's own
   * screen) makes the backend return a receipt with no score / risk /
   * cue instead of the full assessment.
   */
  async assessNarrative(data) {
    if (!data?.consent) throw new Error("Consent is required for assessment.");
    return remote("/api/assess", {
      method: "POST",
      body: JSON.stringify({
        case_id: String(data.case_id || "").trim(),
        narrative: String(data.narrative || "").trim(),
        language: data.language || "en",
        consent: Boolean(data.consent),
        participant_view: Boolean(data.participantView),
      }),
    });
  },

  async transcribeAudio(file) {
    const formData = file instanceof FormData ? file : (() => {
      const fd = new FormData();
      fd.append("file", file, "recording.webm");
      return fd;
    })();
    return remote("/api/transcribe", { method: "POST", body: formData });
  },

  async assessAudio(formData, { caseId, consent, participantView } = {}) {
    const fd = new FormData();
    if (formData instanceof FormData) {
      for (const [key, value] of formData.entries()) fd.append(key, value);
    } else if (formData instanceof Blob) {
      fd.append("file", formData, "recording.webm");
    } else {
      throw new Error("Audio payload is required.");
    }

    // Backend contract requires: file, case_id, consent.
    if (!fd.has("file") && fd.has("audio")) {
      fd.append("file", fd.get("audio"), "recording.webm");
      fd.delete("audio");
    }
    if (!fd.has("case_id") && caseId) fd.append("case_id", caseId);
    if (!fd.has("consent") && consent !== undefined) fd.append("consent", String(Boolean(consent)));
    if (!fd.has("participant_view") && participantView !== undefined) fd.append("participant_view", String(Boolean(participantView)));

    if (!fd.has("file")) throw new Error("Audio file is required.");
    if (!String(fd.get("case_id") || "").trim()) throw new Error("Case ID is required for audio assessment.");
    if (String(fd.get("consent")) !== "true") throw new Error("Consent is required for audio assessment.");

    return remote("/api/assess-audio", { method: "POST", body: fd });
  },

  /**
   * Voice + body-language assessment.
   * `behavior` is the aggregated feature object produced on-device by
   * VideoRecorder (see src/lib/behaviorAnalyzer.js). The video itself is
   * never uploaded.
   */
  async assessVideo({ audio, caseId, consent, behavior, language, participantView }) {
    if (!(audio instanceof Blob)) throw new Error("Audio recording is required.");
    if (!String(caseId || "").trim()) throw new Error("Case ID is required for video assessment.");
    if (!consent) throw new Error("Consent is required for video assessment.");

    const fd = new FormData();
    fd.append("file", audio, "recording.webm");
    fd.append("case_id", String(caseId).trim());
    fd.append("consent", "true");
    fd.append("behavior", JSON.stringify(behavior || { available: false }));
    if (language) fd.append("language", language);
    if (participantView) fd.append("participant_view", "true");
    return remote("/api/assess-video", { method: "POST", body: fd });
  },

  /**
   * Upload a recorded video *file*.  The backend extracts the audio track
   * (full voice pipeline) and analyses the footage itself for body
   * language (blinking, eye contact, self-soothing gestures, tension,
   * swallowing, posture).  Frames are processed in memory, never stored.
   */
  async assessVideoFile({ file, caseId, consent, language, participantView, analyzeFootage = "always" }) {
    if (!(file instanceof Blob)) throw new Error("A video file is required.");
    if (!String(caseId || "").trim()) throw new Error("Case ID is required for video assessment.");
    if (!consent) throw new Error("Consent is required for video assessment.");

    const name = file.name || "upload.mp4";
    const fd = new FormData();
    fd.append("file", file, name);
    fd.append("case_id", String(caseId).trim());
    fd.append("consent", "true");
    fd.append("behavior", "{}");
    fd.append("analyze_footage", analyzeFootage);
    if (language) fd.append("language", language);
    if (participantView) fd.append("participant_view", "true");
    return remote("/api/assess-video", { method: "POST", body: fd });
  },

  /** Whether the server can analyse uploaded video footage for body language. */
  async getVideoCapabilities() {
    try {
      return await remote("/api/video-capabilities");
    } catch {
      return { server_footage_analysis: false, browser_tracking: true };
    }
  },

  /** Live, non-persisted scoring of behaviour features (responder view only). */
  async scoreBehavior(behavior) {
    return remote("/api/behavior-score", { method: "POST", body: JSON.stringify(behavior) });
  },

  /**
   * List cases.  `view: "participant"` returns receipt-level summaries
   * (status only — no score, no risk level) for the assessed person's
   * own dashboard.
   */
  async getCases(params = {}) {
    const query = new URLSearchParams();
    if (params.search) query.set("query", params.search);
    if (params.risk && params.risk !== "ALL") query.set("risk_level", params.risk);
    if (params.status && params.status !== "ALL") query.set("status", normalizeStatus(params.status));
    if (params.view) query.set("view", params.view);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return normalizeCases(await remote(`/api/cases${suffix}`)).map(normalizeCase);
  },

  async getCase(caseId, { view } = {}) {
    const suffix = view ? `?view=${encodeURIComponent(view)}` : "";
    const result = await remote(`/api/cases/${encodeURIComponent(caseId)}${suffix}`);
    return normalizeCase(result);
  },

  getCaseMediaUrl(caseId) {
    return `${API_BASE_URL}/api/cases/${encodeURIComponent(caseId)}/media`;
  },

  async updateCaseStatus(caseId, status) {
    const normalized = normalizeStatus(status);
    if (!CASE_STATUSES.includes(normalized)) throw new Error(`Unsupported case status: ${status}`);
    return normalizeCase(await remote(`/api/cases/${encodeURIComponent(caseId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: normalized }),
    }));
  },

  async addTimelineEvent(caseId, { event, description = "" }) {
    return normalizeCase(await remote(`/api/cases/${encodeURIComponent(caseId)}/timeline`, {
      method: "POST",
      body: JSON.stringify({ event, description }),
    }));
  },

  // Kept as an explicit compatibility method so old UI code fails clearly rather than silently mutating local state.
  async updateCase(caseId, patch = {}) {
    if (patch.status !== undefined) return this.updateCaseStatus(caseId, patch.status);
    throw new Error("Only case status updates are supported by the current backend API.");
  },

  async deleteCase() {
    throw new Error("Case deletion is not available in the current backend API.");
  },

  async getAnalyticsOverview() {
    return remote("/api/analytics/overview");
  },

  async getRiskDistribution() {
    return remote("/api/analytics/risk-distribution");
  },

  async getSVIStatistics() {
    return remote("/api/analytics/svi");
  },

  async getSignalFrequency() {
    return remote("/api/analytics/signals");
  },

  normalizeStatus,
  displayStatus,
};
