import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  FileText,
  Mic,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
  X,
} from "lucide-react";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";

import { api } from "../api";
import RiskBadge from "../components/RiskBadge";
import VoiceRecorder from "../components/VoiceRecorder";

const RISK_COLORS = {
  Critical: "#ef4444",
  High: "#f97316",
  Moderate: "#f59e0b",
  Low: "#10b981",
};

const Dashboard = () => {
  const navigate = useNavigate();

  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const [showVoice, setShowVoice] = useState(false);
  const [showCopilot, setShowCopilot] = useState(false);

  const [message, setMessage] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hello. I'm Sahayak Copilot. I can help you review priority cases, risk levels, SVI scores and human-review requirements.",
    },
  ]);

  /* =========================================================
     LOAD REAL DATA
  ========================================================= */

  const loadCases = async () => {
    try {
      setError("");
      setRefreshing(true);

      const data = await api.getCases();

      if (!Array.isArray(data)) {
        throw new Error("Invalid case data");
      }

      setCases(data);
    } catch (err) {
      console.error(err);
      setError("Unable to load operational data.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadCases();
  }, []);

  /* =========================================================
     REAL STATISTICS
  ========================================================= */

  const stats = useMemo(() => {
    const normalized = cases.map((item) => ({
      ...item,
      risk: String(item.risk_level || "").toUpperCase(),
    }));

    return {
      total: normalized.length,

      critical: normalized.filter(
        (item) => item.risk === "CRITICAL"
      ).length,

      high: normalized.filter(
        (item) => item.risk === "HIGH"
      ).length,

      moderate: normalized.filter(
        (item) => item.risk === "MODERATE"
      ).length,

      low: normalized.filter(
        (item) => item.risk === "LOW"
      ).length,

      review: normalized.filter(
        (item) =>
          item.human_review_required === true ||
          item.human_review_required === "true"
      ).length,
    };
  }, [cases]);

  /* =========================================================
     SVI DATA
  ========================================================= */

  const sviData = useMemo(() => {
    return cases
      .filter(
        (item) =>
          item.svi_score !== undefined &&
          item.svi_score !== null &&
          !Number.isNaN(Number(item.svi_score))
      )
      .slice(0, 12)
      .reverse()
      .map((item, index) => ({
        name: item.case_id
          ? item.case_id.replace("SAH-", "").slice(-6)
          : `Case ${index + 1}`,
        score: Number(item.svi_score),
      }));
  }, [cases]);

  /* =========================================================
     RISK DATA
  ========================================================= */

  const riskData = [
    {
      name: "Critical",
      value: stats.critical,
    },
    {
      name: "High",
      value: stats.high,
    },
    {
      name: "Moderate",
      value: stats.moderate,
    },
    {
      name: "Low",
      value: stats.low,
    },
  ];

  const pieData = riskData.filter(
    (item) => item.value > 0
  );

  /* =========================================================
     VOICE ASSESSMENT
  ========================================================= */

  const handleVoiceUpload = async (audioBlob) => {
    try {
      const formData = new FormData();

      formData.append(
        "file",
        audioBlob,
        `sahayak-${Date.now()}.webm`
      );
      formData.append("case_id", `SAH-${new Date().getFullYear()}-${String(Date.now()).slice(-6)}`);
      formData.append("consent", "true");

      const result = await api.assessAudio(formData);

      setShowVoice(false);

      if (result?.case_id) {
        navigate(`/cases/${result.case_id}`);
      } else {
        navigate("/assessment");
      }
    } catch (err) {
      console.error(err);
      setError("Voice assessment could not be processed.");
    }
  };

  /* =========================================================
     COPILOT
  ========================================================= */

  const sendMessage = (preset = null) => {
    const text = (preset || message).trim();

    if (!text || chatLoading) return;

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        text,
      },
    ]);

    setMessage("");
    setChatLoading(true);

    setTimeout(() => {
      const lower = text.toLowerCase();

      let response =
        "I can help you understand the operational queue, risk distribution and cases requiring human review.";

      if (
        lower.includes("critical") ||
        lower.includes("priority")
      ) {
        response = `There are currently ${stats.critical} critical-risk cases in the queue. These should receive immediate attention from an authorised responder.`;
      } else if (
        lower.includes("review") ||
        lower.includes("human")
      ) {
        response = `${stats.review} case${
          stats.review === 1 ? "" : "s"
        } currently require human review. AI recommendations should not replace the responder's final decision.`;
      } else if (lower.includes("high")) {
        response = `There are ${stats.high} high-risk cases currently visible in the operational queue.`;
      } else if (
        lower.includes("moderate")
      ) {
        response = `There are ${stats.moderate} moderate-risk cases currently visible in the operational queue.`;
      } else if (lower.includes("low")) {
        response = `There are ${stats.low} low-risk cases currently visible in the operational queue.`;
      } else if (
        lower.includes("total") ||
        lower.includes("cases")
      ) {
        response = `The system currently contains ${stats.total} recorded assessment${
          stats.total === 1 ? "" : "s"
        }.`;
      } else if (
        lower.includes("svi") ||
        lower.includes("score")
      ) {
        const scores = cases
          .map((item) => Number(item.svi_score))
          .filter((value) => !Number.isNaN(value));

        const average = scores.length
          ? Math.round(
              scores.reduce(
                (sum, value) => sum + value,
                0
              ) / scores.length
            )
          : null;

        response =
          average !== null
            ? `The current average SVI score across available cases is ${average}.`
            : "There are currently no SVI scores available for analysis.";
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: response,
        },
      ]);

      setChatLoading(false);
    }, 500);
  };

  /* =========================================================
     LOADING
  ========================================================= */

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-76px)] bg-[#f5f7fa] p-5 sm:p-7">
        <div className="mx-auto max-w-[1500px] space-y-5">

          <div className="h-52 animate-pulse rounded-3xl bg-slate-200" />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[1, 2, 3, 4].map((item) => (
              <div
                key={item}
                className="h-32 animate-pulse rounded-2xl bg-white"
              />
            ))}
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
            <div className="h-[360px] animate-pulse rounded-2xl bg-white xl:col-span-2" />
            <div className="h-[360px] animate-pulse rounded-2xl bg-white" />
          </div>

        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-76px)] bg-[#f5f7fa] px-4 py-5 sm:px-6 lg:px-8">

      <div className="mx-auto max-w-[1500px] space-y-5">

        {/* =====================================================
            TOP COMMAND HEADER
        ===================================================== */}

        <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">

          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">

            <div className="flex items-center gap-3">

              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#102f49] text-white">
                <Activity size={20} />
              </div>

              <div>

                <div className="flex items-center gap-2">

                  <span className="h-2 w-2 rounded-full bg-teal-500" />

                  <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-teal-600">
                    Operations
                  </p>

                </div>

                <h1 className="mt-1 text-lg font-bold tracking-tight text-[#102f49] sm:text-xl">
                  Operational Command Center
                </h1>

                <p className="text-[10px] text-slate-400">
                  Monitor assessments and coordinate responder action.
                </p>

              </div>

            </div>

            <div className="flex flex-wrap items-center gap-2">

              <div className="flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2">

                <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />

                <span className="text-[9px] font-bold text-emerald-700">
                  System operational
                </span>

              </div>

              <button
                onClick={() => setShowVoice(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[10px] font-bold text-slate-600 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-700"
              >
                <Mic size={15} />
                Voice
              </button>

              <button
                onClick={() => navigate("/assessment")}
                className="inline-flex items-center gap-2 rounded-xl bg-[#102f49] px-4 py-2.5 text-[10px] font-bold text-white transition hover:bg-[#174764]"
              >
                <Plus size={15} />
                New Assessment
              </button>

            </div>

          </div>

        </section>

        {/* =====================================================
            MAIN HERO
        ===================================================== */}

        <section className="relative overflow-hidden rounded-[26px] bg-[#102f49] p-6 text-white shadow-lg sm:p-8">

          <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-teal-400/10 blur-3xl" />

          <div className="absolute -bottom-32 left-1/3 h-72 w-72 rounded-full bg-cyan-400/10 blur-3xl" />

          <div className="relative grid gap-8 lg:grid-cols-[1fr_330px] lg:items-center">

            <div>

              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/10 px-3 py-1.5">

                <ShieldCheck
                  size={12}
                  className="text-teal-300"
                />

                <span className="text-[9px] font-bold uppercase tracking-[0.16em] text-teal-200">
                  Responder workspace
                </span>

              </div>

              <h2 className="max-w-3xl text-3xl font-bold tracking-tight sm:text-4xl">
                Monitor. Assess. Respond.
              </h2>

              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
                A centralized operational view for reviewing
                assessments, identifying high-priority cases and
                keeping human responders in control.
              </p>

              <div className="mt-6 flex flex-wrap gap-3">

                <button
                  onClick={() => setShowVoice(true)}
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-white/15"
                >
                  <Mic size={16} />
                  Start voice assessment
                </button>

                <button
                  onClick={() => setShowCopilot(true)}
                  className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-white/15"
                >
                  <Sparkles size={16} />
                  Ask Sahayak
                </button>

                <button
                  onClick={() => navigate("/cases")}
                  className="inline-flex items-center gap-2 rounded-xl bg-teal-400 px-4 py-2.5 text-xs font-bold text-[#092b3b] transition hover:bg-teal-300"
                >
                  Open priority queue
                  <ArrowRight size={15} />
                </button>

              </div>

            </div>

            {/* COMMAND STATUS */}

            <div className="rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur">

              <div className="flex items-center justify-between">

                <div>

                  <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-slate-400">
                    Live workload
                  </p>

                  <p className="mt-1 text-4xl font-bold">
                    {stats.total}
                  </p>

                  <p className="text-[10px] text-slate-400">
                    total cases
                  </p>

                </div>

                <button
                  onClick={loadCases}
                  className="rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300 transition hover:bg-white/10"
                  title="Refresh"
                >
                  <RefreshCw
                    size={16}
                    className={
                      refreshing
                        ? "animate-spin"
                        : ""
                    }
                  />
                </button>

              </div>

              <div className="my-4 h-px bg-white/10" />

              <div className="grid grid-cols-2 gap-3">

                <MiniStat
                  label="Critical"
                  value={stats.critical}
                  icon={AlertTriangle}
                  iconClass="text-red-300"
                />

                <MiniStat
                  label="Review"
                  value={stats.review}
                  icon={Clock3}
                  iconClass="text-amber-300"
                />

              </div>

            </div>

          </div>

        </section>

        {/* =====================================================
            AI TOOLS
        ===================================================== */}

        <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">

          <ToolCard
            icon={Mic}
            eyebrow="VOICE ASSESSMENT"
            title="Capture spoken assessment"
            description="Record an assessment using voice input and send it through the existing AI-assisted assessment workflow."
            tags={[
              "Voice input",
              "AI processing",
              "Human review",
            ]}
            button="Start voice assessment"
            iconClass="bg-teal-50 text-teal-600"
            buttonClass="border-teal-100 bg-teal-50 text-teal-700 hover:bg-teal-100"
            onClick={() => setShowVoice(true)}
          />

          <ToolCard
            icon={Sparkles}
            eyebrow="AI RESPONDER COPILOT"
            title="Ask Sahayak"
            description="Get quick operational answers about critical cases, human review requirements, SVI scores and risk distribution."
            tags={[
              "Critical",
              "Review",
              "Ask anything",
            ]}
            button="Open AI Copilot"
            iconClass="bg-indigo-50 text-indigo-600"
            buttonClass="border-indigo-100 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
            onClick={() => setShowCopilot(true)}
          />

        </section>

        {/* =====================================================
            METRICS
        ===================================================== */}

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">

          <MetricCard
            icon={FileText}
            label="Total"
            value={stats.total}
            detail="All recorded assessments"
            iconClass="bg-slate-100 text-slate-700"
          />

          <MetricCard
            icon={AlertTriangle}
            label="Critical"
            value={stats.critical}
            detail="Immediate attention"
            iconClass="bg-red-50 text-red-600"
          />

          <MetricCard
            icon={TrendingUp}
            label="High"
            value={stats.high}
            detail="Priority monitoring"
            iconClass="bg-orange-50 text-orange-600"
          />

          <MetricCard
            icon={Users}
            label="Human Review"
            value={stats.review}
            detail="Responder action required"
            iconClass="bg-amber-50 text-amber-600"
          />

        </section>

        {/* =====================================================
            SVI + PIE
        ===================================================== */}

        <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">

          {/* SVI */}

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:col-span-2">

            <div className="flex items-start justify-between">

              <div>

                <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-teal-600">
                  Risk signal
                </p>

                <h3 className="mt-1 text-sm font-bold text-slate-900">
                  SVI Score Movement
                </h3>

                <p className="mt-1 text-[10px] text-slate-400">
                  Vulnerability scores across available cases
                </p>

              </div>

              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-50 text-teal-600">
                <Activity size={17} />
              </div>

            </div>

            <div className="mt-5 h-[290px]">

              {sviData.length > 0 ? (
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <AreaChart
                    data={sviData}
                    margin={{
                      top: 10,
                      right: 10,
                      left: -20,
                      bottom: 0,
                    }}
                  >

                    <defs>

                      <linearGradient
                        id="sviAreaGradient"
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#14b8a6"
                          stopOpacity={0.3}
                        />

                        <stop
                          offset="100%"
                          stopColor="#14b8a6"
                          stopOpacity={0.02}
                        />
                      </linearGradient>

                    </defs>

                    <CartesianGrid
                      strokeDasharray="3 3"
                      vertical={false}
                      stroke="#e8edf1"
                    />

                    <XAxis
                      dataKey="name"
                      tick={{
                        fontSize: 9,
                        fill: "#94a3b8",
                      }}
                      axisLine={false}
                      tickLine={false}
                    />

                    <YAxis
                      domain={[0, 100]}
                      tick={{
                        fontSize: 9,
                        fill: "#94a3b8",
                      }}
                      axisLine={false}
                      tickLine={false}
                    />

                    <Tooltip
                      contentStyle={{
                        borderRadius: "12px",
                        border: "1px solid #e2e8f0",
                        fontSize: "11px",
                      }}
                    />

                    <Area
                      type="monotone"
                      dataKey="score"
                      stroke="#0f9f94"
                      strokeWidth={3}
                      fill="url(#sviAreaGradient)"
                      dot={{
                        r: 3,
                        fill: "#0f9f94",
                        stroke: "#fff",
                        strokeWidth: 2,
                      }}
                      activeDot={{
                        r: 6,
                      }}
                      animationDuration={1200}
                    />

                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart
                  icon={Activity}
                  text="SVI score movement will appear when assessment data is available."
                />
              )}

            </div>

          </div>

          {/* RISK DISTRIBUTION */}

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

            <div className="flex items-start justify-between">

              <div>

                <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-indigo-600">
                  Workload
                </p>

                <h3 className="mt-1 text-sm font-bold text-slate-900">
                  Risk Distribution
                </h3>

              </div>

              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                <BarChart3 size={17} />
              </div>

            </div>

            <div className="relative mt-4 h-[190px]">

              {pieData.length > 0 ? (
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <PieChart>

                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={54}
                      outerRadius={76}
                      paddingAngle={4}
                      animationDuration={1000}
                    >
                      {pieData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={
                            RISK_COLORS[entry.name]
                          }
                        />
                      ))}
                    </Pie>

                    <Tooltip />

                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart
                  icon={BarChart3}
                  text="Risk distribution will appear after cases are recorded."
                />
              )}

              {stats.total > 0 && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center">

                  <div className="text-center">

                    <p className="text-2xl font-bold text-slate-900">
                      {stats.total}
                    </p>

                    <p className="text-[8px] font-bold uppercase tracking-wider text-slate-400">
                      Cases
                    </p>

                  </div>

                </div>
              )}

            </div>

            <div className="grid grid-cols-2 gap-2">

              {riskData.map((item) => (
                <div
                  key={item.name}
                  className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2"
                >

                  <span className="flex items-center gap-2 text-[9px] font-semibold text-slate-500">

                    <span
                      className="h-2 w-2 rounded-full"
                      style={{
                        backgroundColor:
                          RISK_COLORS[item.name],
                      }}
                    />

                    {item.name}

                  </span>

                  <strong className="text-[10px] text-slate-800">
                    {item.value}
                  </strong>

                </div>
              ))}

            </div>

          </div>

        </section>

        {/* =====================================================
            CASES BY RISK
        ===================================================== */}

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">

            <div>

              <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Operational overview
              </p>

              <h3 className="mt-1 text-sm font-bold text-slate-900">
                Cases by Risk Level
              </h3>

              <p className="mt-1 text-[10px] text-slate-400">
                Current assessment distribution across risk classifications.
              </p>

            </div>

            <button
              onClick={loadCases}
              className="inline-flex w-fit items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-[9px] font-bold text-slate-500 transition hover:bg-slate-50"
            >
              <RefreshCw
                size={13}
                className={
                  refreshing
                    ? "animate-spin"
                    : ""
                }
              />
              Refresh
            </button>

          </div>

          <div className="mt-5 h-[270px]">

            <ResponsiveContainer
              width="100%"
              height="100%"
            >
              <BarChart
                data={riskData}
                margin={{
                  top: 10,
                  right: 10,
                  left: -20,
                  bottom: 0,
                }}
              >

                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#e8edf1"
                />

                <XAxis
                  dataKey="name"
                  tick={{
                    fontSize: 10,
                    fill: "#64748b",
                  }}
                  axisLine={false}
                  tickLine={false}
                />

                <YAxis
                  allowDecimals={false}
                  tick={{
                    fontSize: 9,
                    fill: "#94a3b8",
                  }}
                  axisLine={false}
                  tickLine={false}
                />

                <Tooltip
                  cursor={{
                    fill: "#f8fafc",
                  }}
                  contentStyle={{
                    borderRadius: "12px",
                    border: "1px solid #e2e8f0",
                    fontSize: "11px",
                  }}
                />

                <Bar
                  dataKey="value"
                  fill="#168f86"
                  radius={[8, 8, 0, 0]}
                  animationDuration={1000}
                />

              </BarChart>
            </ResponsiveContainer>

          </div>

        </section>

        {/* =====================================================
            RECENT CASES
        ===================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">

          <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">

            <div>

              <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-slate-400">
                Latest activity
              </p>

              <h3 className="mt-1 text-sm font-bold text-slate-900">
                Recent Cases
              </h3>

              <p className="mt-1 text-[10px] text-slate-400">
                Latest assessments requiring operational visibility.
              </p>

            </div>

            <button
              onClick={() => navigate("/cases")}
              className="inline-flex items-center gap-2 text-[10px] font-bold text-teal-600 transition hover:text-teal-700"
            >
              View priority queue
              <ArrowUpRight size={14} />
            </button>

          </div>

          <div className="overflow-x-auto">

            <table className="w-full min-w-[760px] text-left">

              <thead className="bg-slate-50">

                <tr className="text-[9px] font-bold uppercase tracking-wider text-slate-400">

                  <th className="px-5 py-3.5">
                    Case ID
                  </th>

                  <th className="px-5 py-3.5">
                    SVI
                  </th>

                  <th className="px-5 py-3.5">
                    Risk
                  </th>

                  <th className="px-5 py-3.5">
                    Status
                  </th>

                  <th className="px-5 py-3.5">
                    Human Review
                  </th>

                  <th className="px-5 py-3.5 text-right">
                    Action
                  </th>

                </tr>

              </thead>

              <tbody className="divide-y divide-slate-100">

                {cases.slice(0, 8).map((item, index) => {

                  const review =
                    item.human_review_required === true ||
                    item.human_review_required ===
                      "true";

                  return (
                    <tr
                      key={
                        item.case_id ||
                        item._id ||
                        index
                      }
                      className="group transition hover:bg-slate-50"
                    >

                      <td className="px-5 py-4">

                        <button
                          onClick={() =>
                            navigate(
                              `/cases/${item.case_id}`
                            )
                          }
                          className="flex items-center gap-3 text-left"
                        >

                          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500 transition group-hover:bg-teal-50 group-hover:text-teal-600">
                            <FileText size={14} />
                          </div>

                          <div>

                            <p className="text-xs font-bold text-slate-800">
                              {item.case_id ||
                                "Unknown"}
                            </p>

                            <p className="mt-0.5 text-[9px] text-slate-400">
                              Assessment record
                            </p>

                          </div>

                        </button>

                      </td>

                      <td className="px-5 py-4">

                        <span className="inline-flex min-w-[42px] justify-center rounded-lg bg-slate-100 px-2.5 py-1.5 text-[10px] font-bold text-slate-700">
                          {item.svi_score ?? "—"}
                        </span>

                      </td>

                      <td className="px-5 py-4">
                        <RiskBadge
                          level={item.risk_level}
                        />
                      </td>

                      <td className="px-5 py-4">
                        <StatusBadge
                          status={
                            item.status ||
                            "Pending"
                          }
                        />
                      </td>

                      <td className="px-5 py-4">

                        {review ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1.5 text-[9px] font-bold text-amber-700">
                            <Clock3 size={11} />
                            Required
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1.5 text-[9px] font-bold text-emerald-700">
                            <CheckCircle2 size={11} />
                            Not required
                          </span>
                        )}

                      </td>

                      <td className="px-5 py-4 text-right">

                        <button
                          onClick={() =>
                            navigate(
                              `/cases/${item.case_id}`
                            )
                          }
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 transition hover:border-teal-200 hover:bg-teal-50 hover:text-teal-600"
                        >
                          <ArrowUpRight size={14} />
                        </button>

                      </td>

                    </tr>
                  );
                })}

              </tbody>

            </table>

            {!cases.length && (
              <div className="px-5 py-16 text-center">

                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-300">
                  <FileText size={22} />
                </div>

                <p className="mt-4 text-xs font-bold text-slate-700">
                  No assessments recorded
                </p>

                <p className="mx-auto mt-1 max-w-sm text-[10px] leading-5 text-slate-400">
                  Start a new assessment to populate the operational queue.
                </p>

                <button
                  onClick={() =>
                    navigate("/assessment")
                  }
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#102f49] px-4 py-2.5 text-[10px] font-bold text-white"
                >
                  <Plus size={14} />
                  Create assessment
                </button>

              </div>
            )}

          </div>

        </section>

        {/* =====================================================
            HUMAN IN LOOP
        ===================================================== */}

        <section className="rounded-2xl border border-teal-100 bg-teal-50/70 p-5">

          <div className="flex items-start gap-4">

            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-teal-600 shadow-sm">
              <ShieldCheck size={19} />
            </div>

            <div>

              <div className="flex flex-wrap items-center gap-2">

                <h3 className="text-xs font-bold text-slate-800">
                  Human-in-the-loop safeguard
                </h3>

                <span className="rounded-full bg-teal-100 px-2 py-1 text-[8px] font-bold uppercase tracking-wider text-teal-700">
                  Safety first
                </span>

              </div>

              <p className="mt-1 max-w-4xl text-[10px] leading-5 text-slate-500">
                AI supports assessment and decision-making with
                assistive signals. Authorised responders remain
                responsible for reviewing evidence and making final
                decisions.
              </p>

            </div>

          </div>

        </section>

      </div>

      {/* =======================================================
          VOICE MODAL
      ======================================================= */}

      {showVoice && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          onClick={() => setShowVoice(false)}
        >

          <div
            className="w-full max-w-xl overflow-hidden rounded-3xl bg-white shadow-2xl"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">

              <div className="flex items-center gap-3">

                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-50 text-teal-600">
                  <Mic size={19} />
                </div>

                <div>

                  <p className="text-[9px] font-bold uppercase tracking-wider text-teal-600">
                    Sahayak Voice
                  </p>

                  <h3 className="text-sm font-bold text-slate-900">
                    Voice Assessment
                  </h3>

                </div>

              </div>

              <button
                onClick={() =>
                  setShowVoice(false)
                }
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 hover:bg-slate-50"
              >
                <X size={16} />
              </button>

            </div>

            <div className="m-5 rounded-2xl border border-teal-100 bg-teal-50 p-4">

              <div className="flex gap-3">

                <ShieldCheck
                  size={18}
                  className="mt-0.5 shrink-0 text-teal-600"
                />

                <div>

                  <p className="text-xs font-bold text-slate-800">
                    Consent & privacy
                  </p>

                  <p className="mt-1 text-[10px] leading-5 text-slate-500">
                    Continue only when appropriate consent has
                    been provided for voice recording and
                    AI-assisted assessment.
                  </p>

                </div>

              </div>

            </div>

            <div className="mx-5 mb-5 rounded-2xl border border-slate-200 bg-slate-50 p-5">

              <VoiceRecorder
                onUpload={handleVoiceUpload}
              />

            </div>

          </div>

        </div>
      )}

      {/* =======================================================
          COPILOT MODAL
      ======================================================= */}

      {showCopilot && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          onClick={() => setShowCopilot(false)}
        >

          <div
            className="flex h-[min(680px,90vh)] w-full max-w-xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">

              <div className="flex items-center gap-3">

                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                  <Sparkles size={18} />
                </div>

                <div>

                  <p className="text-[9px] font-bold uppercase tracking-wider text-indigo-600">
                    Sahayak AI
                  </p>

                  <h3 className="text-sm font-bold text-slate-900">
                    Responder Copilot
                  </h3>

                </div>

              </div>

              <button
                onClick={() =>
                  setShowCopilot(false)
                }
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-400 hover:bg-slate-50"
              >
                <X size={16} />
              </button>

            </div>

            <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50 p-5">

              {messages.map((item, index) => (
                <div
                  key={index}
                  className={`flex gap-2 ${
                    item.role === "user"
                      ? "justify-end"
                      : ""
                  }`}
                >

                  {item.role === "assistant" && (
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
                      <Bot size={14} />
                    </div>
                  )}

                  <div
                    className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[10px] leading-5 ${
                      item.role === "user"
                        ? "rounded-br-md bg-[#102f49] text-white"
                        : "rounded-bl-md border border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {item.text}
                  </div>

                  {item.role === "user" && (
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-600">
                      <Users size={14} />
                    </div>
                  )}

                </div>
              ))}

              {chatLoading && (
                <div className="flex gap-2">

                  <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
                    <Bot size={14} />
                  </div>

                  <div className="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3">

                    <div className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
                    </div>

                  </div>

                </div>
              )}

            </div>

            <div className="flex gap-2 overflow-x-auto border-t border-slate-100 px-5 py-3">

              <QuickPrompt
                text="Critical cases"
                onClick={() =>
                  sendMessage(
                    "Show critical cases"
                  )
                }
              />

              <QuickPrompt
                text="Needs review"
                onClick={() =>
                  sendMessage(
                    "Which cases need review?"
                  )
                }
              />

              <QuickPrompt
                text="Average SVI"
                onClick={() =>
                  sendMessage(
                    "What is the average SVI score?"
                  )
                }
              />

            </div>

            <div className="border-t border-slate-100 p-4">

              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm">

                <input
                  value={message}
                  onChange={(event) =>
                    setMessage(event.target.value)
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      sendMessage();
                    }
                  }}
                  placeholder="Ask Sahayak about the cases..."
                  className="min-w-0 flex-1 bg-transparent px-2 text-xs text-slate-700 outline-none placeholder:text-slate-400"
                />

                <button
                  onClick={() => sendMessage()}
                  disabled={
                    !message.trim() ||
                    chatLoading
                  }
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#102f49] text-white transition hover:bg-[#16435f] disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <Send size={15} />
                </button>

              </div>

              <p className="mt-2 text-center text-[8px] text-slate-400">
                AI provides decision support. Human responders make final decisions.
              </p>

            </div>

          </div>

        </div>
      )}

      {/* =======================================================
          ERROR
      ======================================================= */}

      {error && (
        <div className="fixed bottom-5 right-5 z-[110] max-w-sm rounded-xl border border-red-100 bg-white px-4 py-3 shadow-xl">

          <div className="flex items-center gap-3">

            <AlertTriangle
              size={16}
              className="shrink-0 text-red-500"
            />

            <span className="text-xs font-semibold text-slate-700">
              {error}
            </span>

            <button
              onClick={loadCases}
              className="text-[10px] font-bold text-teal-600"
            >
              Retry
            </button>

            <button
              onClick={() => setError("")}
              className="text-slate-400"
            >
              <X size={14} />
            </button>

          </div>

        </div>
      )}

    </div>
  );
};

/* =========================================================
   COMPONENTS
========================================================= */

const MetricCard = ({
  label,
  value,
  detail,
  icon: Icon,
  iconClass,
}) => {
  return (
    <div className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">

      <div className="flex items-start justify-between">

        <div>

          <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-slate-400">
            {label}
          </p>

          <p className="mt-2 text-3xl font-bold tracking-tight text-slate-900">
            {value}
          </p>

          <p className="mt-1 text-[9px] text-slate-400">
            {detail}
          </p>

        </div>

        <div
          className={`flex h-10 w-10 items-center justify-center rounded-xl ${iconClass}`}
        >
          <Icon size={18} />
        </div>

      </div>

    </div>
  );
};

const MiniStat = ({
  label,
  value,
  icon: Icon,
  iconClass,
}) => {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">

      <div className="flex items-center gap-2">

        <Icon
          size={13}
          className={iconClass}
        />

        <span className="text-[9px] font-semibold text-slate-400">
          {label}
        </span>

      </div>

      <p className="mt-1 text-lg font-bold text-white">
        {value}
      </p>

    </div>
  );
};

const ToolCard = ({
  icon: Icon,
  eyebrow,
  title,
  description,
  tags,
  button,
  iconClass,
  buttonClass,
  onClick,
}) => {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md">

      <div className="flex items-start justify-between">

        <div className="flex items-center gap-3">

          <div
            className={`flex h-11 w-11 items-center justify-center rounded-xl ${iconClass}`}
          >
            <Icon size={21} />
          </div>

          <div>

            <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">
              {eyebrow}
            </p>

            <h3 className="mt-1 text-sm font-bold text-slate-900">
              {title}
            </h3>

          </div>

        </div>

        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[8px] font-bold text-emerald-600">
          READY
        </span>

      </div>

      <p className="mt-4 text-xs leading-5 text-slate-500">
        {description}
      </p>

      <div className="mt-4 flex flex-wrap gap-2">

        {tags.map((tag) => (
          <span
            key={tag}
            className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-[9px] font-semibold text-slate-500"
          >
            {tag}
          </span>
        ))}

      </div>

      <button
        onClick={onClick}
        className={`mt-5 flex w-full items-center gap-2 rounded-xl border px-4 py-2.5 text-xs font-bold transition ${buttonClass}`}
      >

        <Icon size={15} />

        {button}

        <ArrowUpRight
          size={14}
          className="ml-auto"
        />

      </button>

    </div>
  );
};

const StatusBadge = ({ status }) => {
  const value = String(
    status || "Pending"
  ).toLowerCase();

  let className =
    "bg-slate-100 text-slate-600";

  if (
    value.includes("complete") ||
    value.includes("closed")
  ) {
    className =
      "bg-emerald-50 text-emerald-700";
  } else if (
    value.includes("review") ||
    value.includes("pending")
  ) {
    className =
      "bg-amber-50 text-amber-700";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[9px] font-bold ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status || "Pending"}
    </span>
  );
};

const QuickPrompt = ({
  text,
  onClick,
}) => {
  return (
    <button
      onClick={onClick}
      className="whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[9px] font-semibold text-slate-500 transition hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600"
    >
      {text}
    </button>
  );
};

const EmptyChart = ({
  icon: Icon,
  text,
}) => {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">

      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-100 text-slate-300">
        <Icon size={19} />
      </div>

      <p className="mt-3 max-w-xs text-[10px] leading-5 text-slate-400">
        {text}
      </p>

    </div>
  );
};

export default Dashboard;