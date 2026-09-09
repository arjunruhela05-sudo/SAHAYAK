import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight, Bot, CheckCircle2, Clock3, FilePlus2, FileText, HeartHandshake, HeartPulse,
  Mic, PhoneCall, RefreshCw, Send, ShieldCheck, Sparkles, Video, X,
} from "lucide-react";

import { api } from "../api";
import { useAuth } from "../context/AuthContext";
import VoiceRecorder from "../components/VoiceRecorder";

/**
 * Participant ("user" role) dashboard.
 *
 * Shows ONLY receipt-level information about the person's own
 * submissions — reference, when it was submitted, and whether a human
 * has reviewed it.  It never shows a stress / vulnerability index, a
 * risk level, signals, cues or tracking data: those exist solely for
 * the authorised responder.
 */

const STATUS_LABEL = {
  NEW: "Received — awaiting review",
  UNDER_REVIEW: "Under review",
  ACTION_REQUIRED: "A responder is acting on this",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};
const STATUS_TONE = {
  NEW: "bg-slate-100 text-slate-700",
  UNDER_REVIEW: "bg-amber-50 text-amber-700",
  ACTION_REQUIRED: "bg-teal-50 text-teal-700",
  RESOLVED: "bg-emerald-50 text-emerald-700",
  CLOSED: "bg-slate-100 text-slate-500",
};
const MODE_LABEL = { text: "Written", voice: "Voice", video: "Video" };

export default function UserDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [showVoice, setShowVoice] = useState(false);
  const [showAssistant, setShowAssistant] = useState(false);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hello. I can tell you whether your statements have been received and whether a responder has reviewed them yet." },
  ]);

  const loadCases = async () => {
    try {
      setError("");
      setRefreshing(true);
      // Receipt-level summaries only (no scores, no risk levels).
      const data = await api.getCases({ view: "participant" });
      setCases((Array.isArray(data) ? data : []).filter((c) => c && c.case_id));
    } catch {
      setError("Unable to load your submissions right now.");
      setCases([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { loadCases(); }, []);

  const stats = useMemo(() => ({
    total: cases.length,
    pending: cases.filter((c) => c.status === "NEW" || c.status === "UNDER_REVIEW").length,
    reviewed: cases.filter((c) => c.status === "ACTION_REQUIRED" || c.status === "RESOLVED" || c.status === "CLOSED").length,
  }), [cases]);

  const handleVoiceUpload = async (audioBlob) => {
    const fd = new FormData();
    fd.append("file", audioBlob, `sahayak-${Date.now()}.webm`);
    fd.append("case_id", `SAH-${new Date().getFullYear()}-${String(Date.now()).slice(-6)}`);
    fd.append("consent", "true");
    fd.append("participant_view", "true");
    try {
      const receipt = await api.assessAudio(fd);
      setShowVoice(false);
      navigate("/result", { state: { assessment: receipt, participantView: true } });
    } catch (err) {
      alert(err.message || "Your voice statement could not be sent. Please try again.");
    }
  };

  const reply = (text) => {
    const q = text.toLowerCase();
    if (/(how many|count|kitne)/.test(q)) return `You have submitted ${stats.total} statement${stats.total === 1 ? "" : "s"}. ${stats.pending} ${stats.pending === 1 ? "is" : "are"} waiting for or under review.`;
    if (/(pending|waiting|review|status|kab)/.test(q)) {
      if (!cases.length) return "You have not submitted a statement yet. You can start one with the button above.";
      const latest = cases[0];
      return `Your most recent statement (${latest.case_id}) is: ${STATUS_LABEL[latest.status] || latest.status}.`;
    }
    if (/(score|risk|index|svi|result|stress)/.test(q)) return "Assessment details are reviewed by an authorised responder and are not shown here. If you are in immediate danger, please contact local emergency services.";
    if (/(help|emergency|danger|urgent)/.test(q)) return "If you are in immediate danger, contact your local emergency services right now. You do not need to wait for a review.";
    return 'You can ask "How many statements have I submitted?" or "Is my statement under review?"';
  };

  const sendMessage = (preset = null) => {
    const text = (preset || message).trim();
    if (!text) return;
    setMessages((prev) => [...prev, { role: "user", text }, { role: "assistant", text: reply(text) }]);
    setMessage("");
  };

  return (
    <div className="space-y-6">
      {/* ---------------- header ---------------- */}
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-teal-600">Personal workspace</p>
          <h2 className="mt-1 text-2xl font-extrabold text-[#102a43]">Welcome, {user?.name || "there"}</h2>
          <p className="mt-1 text-xs text-slate-500">Share a statement in writing, by voice or by video. A human responder reviews everything you send.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={loadCases} disabled={refreshing} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[10px] font-bold text-slate-600 transition hover:bg-slate-50 disabled:opacity-60"><RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> Refresh</button>
          <button onClick={() => setShowVoice(true)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[10px] font-bold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700"><Mic size={15} /> Quick voice statement</button>
          <button onClick={() => navigate("/assessment")} className="inline-flex items-center gap-2 rounded-xl bg-[#102f49] px-4 py-2.5 text-[10px] font-bold text-white shadow-sm transition hover:bg-[#174764]"><FilePlus2 size={15} /> New statement</button>
        </div>
      </section>

      {/* ---------------- hero ---------------- */}
      <section className="relative overflow-hidden rounded-[28px] bg-[#102f49] p-6 text-white shadow-lg sm:p-8">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-teal-400/10 blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[1.5fr_.7fr] lg:items-center">
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1.5"><HeartPulse size={12} className="text-teal-300" /><span className="text-[9px] font-bold uppercase tracking-[0.18em] text-teal-200">You are not alone</span></div>
            <h3 className="text-2xl font-bold leading-tight sm:text-3xl">Tell us what happened, in your own way.</h3>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">You can type, speak, or record a video — and use voice-guided mode if you prefer not to use the keyboard. Take your time. There is no right or wrong way to say it.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={() => navigate("/assessment")} className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-3 text-[10px] font-bold text-[#102f49] transition hover:bg-slate-100"><FileText size={15} /> Write or dictate <ArrowUpRight size={13} /></button>
              <button onClick={() => setShowVoice(true)} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-[10px] font-bold text-white transition hover:bg-white/15"><Mic size={15} /> Speak</button>
              <button onClick={() => navigate("/assessment")} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-[10px] font-bold text-white transition hover:bg-white/15"><Video size={15} /> Record video</button>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 lg:grid-cols-1">
            <HeroStat icon={FileText} label="Statements" value={stats.total} />
            <HeroStat icon={Clock3} label="Awaiting review" value={stats.pending} />
            <HeroStat icon={CheckCircle2} label="Reviewed" value={stats.reviewed} />
          </div>
        </div>
      </section>

      {/* ---------------- statements ---------------- */}
      <section className="grid gap-5 lg:grid-cols-[1.4fr_.8fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div><p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">My statements</p><h3 className="mt-1 text-sm font-bold text-slate-900">Submission status</h3></div>
            <ShieldCheck size={18} className="text-teal-600" />
          </div>
          {loading ? (
            <div className="state-card compact"><div className="spinner" /><strong>Loading…</strong></div>
          ) : error ? (
            <div className="state-card compact error-state"><strong>{error}</strong></div>
          ) : !cases.length ? (
            <div className="state-card compact"><FileText size={22} /><strong>No statements yet</strong><span>When you submit a statement it will appear here with its review status.</span></div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {cases.map((c) => (
                <li key={c.case_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <button className="case-link" onClick={() => navigate(`/cases/${c.case_id}`)}>{c.case_id}</button>
                    <p className="mt-0.5 text-[11px] text-slate-500">{MODE_LABEL[c.capture_mode] || "Written"} statement · {c.created_at ? new Date(c.created_at).toLocaleString() : ""}</p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-[10px] font-bold ${STATUS_TONE[c.status] || STATUS_TONE.NEW}`}>{STATUS_LABEL[c.status] || c.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-600"><Sparkles size={20} /></div><div><p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">Sahayak assistant</p><h3 className="mt-1 text-sm font-bold text-slate-900">Check on your submissions</h3></div></div>
            <p className="mt-4 text-xs leading-5 text-slate-500">Ask whether your statement has been received or reviewed.</p>
            <button onClick={() => setShowAssistant(true)} className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-bold text-slate-700 transition hover:bg-slate-50"><Bot size={15} /> Open assistant <ArrowUpRight size={14} className="ml-auto" /></button>
          </div>
          <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5">
            <div className="flex items-start gap-3"><PhoneCall size={18} className="mt-0.5 text-amber-600" /><div><p className="text-sm font-bold text-amber-800">In immediate danger?</p><p className="mt-1 text-xs leading-5 text-amber-700">Contact your local emergency services right now. You do not need to wait for a review.</p></div></div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3"><HeartHandshake size={18} className="mt-0.5 text-teal-600" /><div><p className="text-sm font-bold text-slate-900">How your statement is handled</p><p className="mt-1 text-xs leading-5 text-slate-500">Your words, voice or video are used only to help an authorised responder understand your situation. Recordings are not stored, and a person — not a machine — decides what happens next.</p></div></div>
          </div>
        </div>
      </section>

      {/* ---------------- voice modal ---------------- */}
      {showVoice && (
        <Modal title="Quick voice statement" onClose={() => setShowVoice(false)}>
          <p className="mb-4 text-xs text-slate-500">Tap the microphone, say what you want to share, then tap again to stop. Submit when you are ready.</p>
          <VoiceRecorder onUpload={handleVoiceUpload} participantMode />
        </Modal>
      )}

      {/* ---------------- assistant modal ---------------- */}
      {showAssistant && (
        <Modal title="Sahayak assistant" onClose={() => setShowAssistant(false)}>
          <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs leading-5 ${m.role === "user" ? "bg-[#102f49] text-white" : "bg-slate-100 text-slate-700"}`}>{m.text}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {["How many statements have I submitted?", "Is my statement under review?", "What if I am in danger?"].map((q) => <button key={q} onClick={() => sendMessage(q)} className="rounded-full border border-slate-200 px-3 py-1.5 text-[10px] font-bold text-slate-600 hover:bg-slate-50">{q}</button>)}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); sendMessage(); }} className="mt-3 flex gap-2">
            <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Ask about your submissions…" className="flex-1 rounded-xl border border-slate-200 px-3 py-2.5 text-xs outline-none focus:border-teal-500" />
            <button className="inline-flex items-center gap-2 rounded-xl bg-[#102f49] px-4 py-2.5 text-xs font-bold text-white"><Send size={14} /> Send</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function HeroStat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">
      <div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.12em] text-slate-400"><Icon size={12} className="text-teal-300" />{label}</div>
      <p className="mt-2 text-2xl font-extrabold text-white">{value}</p>
    </div>
  );
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between"><h3 className="text-sm font-bold text-slate-900">{title}</h3><button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close"><X size={18} /></button></div>
        {children}
      </div>
    </div>
  );
}
