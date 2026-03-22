import { useState, useEffect, useRef, useCallback } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  TrendingUp, TrendingDown, Activity, MessageSquare,
  Send, Database, Cpu, Zap, BarChart3, ArrowUpRight,
  ArrowDownRight, RefreshCw, Radio,
} from "lucide-react";

// In dev, Vite proxy rewrites /api/* → localhost:8000/*.
// In production, dashboard is served from FastAPI itself — no prefix needed.
const API = import.meta.env.DEV ? "/api" : "";

// ── Mock data generator ─────────────────────────────────────────────────────

function gen(base, vol, trend) {
  return Array.from({ length: 60 }, (_, i) => {
    const p = base + Math.sin(i / 7) * vol + i * trend;
    return {
      date: new Date(2024, 7, 1 + i).toISOString().split("T")[0],
      open: +(p + Math.random() * 3 - 1.5).toFixed(2),
      high: +(p + Math.random() * 5 + 1).toFixed(2),
      low: +(p - Math.random() * 5 - 1).toFixed(2),
      close: +(p + Math.random() * 4 - 2).toFixed(2),
      volume: Math.floor(40e6 + Math.random() * 50e6),
    };
  });
}

const MOCK_PRICES = { AAPL: gen(178, 12, 0.3), NVDA: gen(420, 30, 1.2), MSFT: gen(410, 15, 0.4) };
const TICKERS = Object.keys(MOCK_PRICES);

function pipelineStatusToRows(tickers) {
  let id = 1;
  const rows = [];
  for (const t of tickers) {
    const time = t.last_data_date ? t.last_data_date.slice(5).replace("-", "/") : "—";
    let fetchStatus, validateStatus;
    if (t.status === "healthy") {
      fetchStatus = "success"; validateStatus = "success";
    } else if (t.status === "stale") {
      fetchStatus = "success"; validateStatus = "failed";
    } else {
      fetchStatus = "failed"; validateStatus = "pending";
    }
    rows.push({ id: id++, ticker: t.ticker, stage: "fetch", status: fetchStatus, dur: "—", time });
    rows.push({ id: id++, ticker: t.ticker, stage: "validate", status: validateStatus, dur: "—", time: validateStatus === "pending" ? "—" : time });
  }
  return rows;
}

function buildAnalysis(ticker, prices) {
  const latest = prices[prices.length - 1];
  const hi = Math.max(...prices.map(p => p.high));
  const lo = Math.min(...prices.map(p => p.low));
  const avgV = Math.round(prices.reduce((s, p) => s + p.volume, 0) / prices.length);
  const gain = (latest.close - prices[0].close).toFixed(2);
  return {
    provider: "Anthropic Claude",
    dataPoints: prices.length,
    text: `**${ticker} Analysis** — The stock has gained ${gain > 0 ? "+" : ""}${gain} over the past ${prices.length} sessions, trending steadily upward. Recent price action shows consolidation near ${latest.close.toFixed(0)} with average daily volume of ${(avgV / 1e6).toFixed(1)}M shares.\n\n**Key Levels:** Resistance at ${hi.toFixed(2)} (period high). Support established near ${lo.toFixed(2)} with buyers stepping in consistently at that zone.\n\n**Outlook:** Momentum is constructive. A break above ${hi.toFixed(2)} on elevated volume would confirm continuation. A pullback into the ${(latest.close * 0.97).toFixed(2)}–${(latest.close * 0.98).toFixed(2)} zone could present an entry opportunity for accumulation.`,
  };
}

function formatDataDate(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── Theme ────────────────────────────────────────────────────────────────────

const C = {
  bg: "#ffffff", surface: "#f8f9fb", surfaceAlt: "#f1f3f7",
  border: "#e2e5eb", borderLight: "#d0d4dc",
  text: "#1a1d26", textMid: "#3d4252", textMuted: "#6b7189", textDim: "#9498ad",
  accent: "#2563eb", accentSoft: "rgba(37,99,235,0.08)", accentMid: "rgba(37,99,235,0.15)",
  green: "#059669", greenSoft: "rgba(5,150,105,0.08)",
  red: "#dc2626", redSoft: "rgba(220,38,38,0.07)",
  amber: "#d97706", amberSoft: "rgba(217,119,6,0.08)",
};

// ── Small components ─────────────────────────────────────────────────────────

const Dot = ({ status }) => {
  const col = { success: C.green, running: C.accent, failed: C.red, pending: C.textDim }[status] || C.textDim;
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 7, height: 7 }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: col, display: "block" }} />
    </span>
  );
};

const Stat = ({ label, value, sub, icon: Icon, color = C.accent }) => {
  const bgMap = { [C.green]: C.greenSoft, [C.red]: C.redSoft, [C.amber]: C.amberSoft };
  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, padding: "16px 18px", display: "flex", alignItems: "flex-start", gap: 14 }}>
      <div style={{ width: 36, height: 36, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center", background: bgMap[color] || C.accentSoft }}>
        <Icon size={17} color={color} strokeWidth={2.2} />
      </div>
      <div>
        <div style={{ fontSize: 10.5, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 600, fontFamily: "'DM Sans', sans-serif" }}>{label}</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: C.text, marginTop: 1, fontFamily: "'Source Code Pro', monospace" }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: C.textMuted, marginTop: 1 }}>{sub}</div>}
      </div>
    </div>
  );
};

const Tip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{ background: "#fff", border: `1px solid ${C.border}`, borderRadius: 10, padding: "10px 14px", fontSize: 11.5, fontFamily: "'Source Code Pro', monospace", boxShadow: "0 4px 16px rgba(0,0,0,0.07)" }}>
      <div style={{ color: C.textMuted, marginBottom: 5, fontFamily: "'DM Sans', sans-serif", fontWeight: 600 }}>{d.date}</div>
      <div style={{ display: "grid", gridTemplateColumns: "auto auto", gap: "2px 14px" }}>
        <span style={{ color: C.textDim }}>Open</span><span style={{ color: C.text }}>{d.open}</span>
        <span style={{ color: C.textDim }}>High</span><span style={{ color: C.green }}>{d.high}</span>
        <span style={{ color: C.textDim }}>Low</span><span style={{ color: C.red }}>{d.low}</span>
        <span style={{ color: C.textDim }}>Close</span><span style={{ color: C.accent }}>{d.close}</span>
        <span style={{ color: C.textDim }}>Vol</span><span style={{ color: C.textMid }}>{(d.volume / 1e6).toFixed(1)}M</span>
      </div>
    </div>
  );
};

// ── Main Dashboard ──────────────────────────────────────────────────────────

export default function Dashboard() {
  const [ticker, setTicker] = useState("AAPL");
  const [priceData, setPriceData] = useState(MOCK_PRICES);
  const [msgs, setMsgs] = useState([{ role: "system", text: "Research assistant ready. Ask anything about the portfolio." }]);
  const [input, setInput] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState(() => buildAnalysis("AAPL", MOCK_PRICES["AAPL"]));
  const [refreshing, setRefreshing] = useState(false);
  const [sseStatus, setSseStatus] = useState("disconnected"); // disconnected | connected | error
  const [lastPipelineEvent, setLastPipelineEvent] = useState(null);
  const [pipelineRows, setPipelineRows] = useState([]);
  const chatEnd = useRef(null);
  const sseRef = useRef(null);

  const fetchPipelineStatus = useCallback(() => {
    fetch(`${API}/pipeline/status`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.tickers) setPipelineRows(pipelineStatusToRows(d.tickers)); })
      .catch(() => {});
  }, []);

  // ── SSE connection to /events/pipeline ──
  useEffect(() => {
    let es;
    function connect() {
      es = new EventSource(`${API}/events/pipeline`);
      sseRef.current = es;

      es.addEventListener("connected", () => {
        setSseStatus("connected");
        fetchPipelineStatus();
      });

      es.addEventListener("pipeline_complete", (e) => {
        const data = JSON.parse(e.data);
        setLastPipelineEvent(data.completed_at);
        fetchPipelineStatus();

        // Auto-refresh: reload all ticker data
        for (const t of TICKERS) {
          fetch(`${API}/prices/${t}`)
            .then(r => r.ok ? r.json() : null)
            .then(d => {
              if (d?.prices) {
                setPriceData(prev => ({ ...prev, [t]: d.prices }));
              }
            })
            .catch(() => {});
        }
      });

      es.onerror = () => {
        setSseStatus("error");
        es.close();
        // Reconnect after 5 seconds
        setTimeout(connect, 5000);
      };
    }

    connect();
    fetchPipelineStatus(); // also fetch on mount in case SSE is slow
    return () => { if (sseRef.current) sseRef.current.close(); };
  }, [fetchPipelineStatus]);

  // Recompute analysis when ticker or data changes
  useEffect(() => {
    if (priceData[ticker]) {
      setAnalysis(buildAnalysis(ticker, priceData[ticker]));
    }
  }, [ticker, priceData]);

  const prices = priceData[ticker] || [];
  const latest = prices[prices.length - 1];
  const prev = prices[prices.length - 2];
  const chg = latest && prev ? +(latest.close - prev.close).toFixed(2) : 0;
  const chgPct = prev ? +((chg / prev.close) * 100).toFixed(2) : 0;
  const up = chg >= 0;
  const hi = prices.length ? Math.max(...prices.map(p => p.high)) : 0;
  const lo = prices.length ? Math.min(...prices.map(p => p.low)) : 0;
  const avgV = prices.length ? Math.round(prices.reduce((s, p) => s + p.volume, 0) / prices.length) : 0;
  const lastDataDate = latest?.date || null;

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  // ── Manual refresh ──
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API}/prices/${ticker}/refresh`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.prices) {
          setPriceData(prev => ({ ...prev, [ticker]: data.prices }));
        }
      }
    } catch {
      // Fallback: regenerate mock data to simulate a refresh
      setPriceData(prev => {
        const bases = { AAPL: [178, 12, 0.3], NVDA: [420, 30, 1.2], MSFT: [410, 15, 0.4] };
        const args = bases[ticker] || [200, 10, 0.5];
        return { ...prev, [ticker]: gen(...args) };
      });
    }
    fetchPipelineStatus();
    setRefreshing(false);
  }, [ticker, fetchPipelineStatus]);

  // ── AI Analysis ──
  const runAnalysis = () => {
    setAnalyzing(true);
    setAnalysis(null);
    setTimeout(() => {
      setAnalysis(buildAnalysis(ticker, prices));
      setAnalyzing(false);
    }, 1800);
  };

  // ── Chat ──
  const sendChat = () => {
    if (!input.trim()) return;
    const q = input.trim();
    setMsgs(m => [...m, { role: "user", text: q }]);
    setInput("");
    setTimeout(() => {
      let r = `On ${ticker}: `;
      const ql = q.toLowerCase();
      if (ql.includes("support")) r += `Support at ${lo.toFixed(2)} with intermediate support near ${(latest.close * 0.98).toFixed(2)}.`;
      else if (ql.includes("resist")) r += `Resistance at ${hi.toFixed(2)}. A break above on heavy volume confirms the uptrend.`;
      else if (ql.includes("buy") || ql.includes("sell")) r += `I provide analysis, not recommendations. Currently ${up ? "positive momentum" : "under pressure"} at ${chgPct}%.`;
      else if (ql.includes("volume")) r += `Avg volume ${(avgV / 1e6).toFixed(1)}M. Latest: ${(latest.volume / 1e6).toFixed(1)}M (${latest.volume > avgV ? "above" : "below"} average).`;
      else r += `Closed ${latest.close} (${up ? "+" : ""}${chg}, ${chgPct}%). Trading ${latest.close > (hi + lo) / 2 ? "above" : "below"} range midpoint.`;
      setMsgs(m => [...m, { role: "assistant", text: r }]);
    }, 800);
  };

  const okCount = pipelineRows.filter(t => t.status === "success").length;
  const sseColors = { connected: C.green, disconnected: C.textDim, error: C.amber };

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.text, fontFamily: "'DM Sans', -apple-system, sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Source+Code+Pro:wght@400;500;600;700&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:4px}
        ::-webkit-scrollbar-track{background:transparent}
        ::-webkit-scrollbar-thumb{background:${C.borderLight};border-radius:2px}
        @keyframes ping{0%{transform:scale(1);opacity:.5}100%{transform:scale(2.5);opacity:0}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @keyframes pulse{0%,100%{opacity:.3}50%{opacity:1}}
        @keyframes spin{to{transform:rotate(360deg)}}
        .anim{animation:fadeUp .35s ease-out both}
        .tk{border:1px solid ${C.border};background:${C.bg};color:${C.textMuted};padding:6px 18px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600;font-family:'Source Code Pro',monospace;transition:all .15s}
        .tk:hover{border-color:${C.borderLight};color:${C.text}}
        .tk.on{border-color:${C.accent};color:${C.accent};background:${C.accentSoft}}
        .ci{background:${C.surface};border:1px solid ${C.border};border-radius:8px;padding:10px 14px;color:${C.text};font-size:13px;font-family:'DM Sans',sans-serif;outline:none;width:100%;transition:border-color .15s}
        .ci:focus{border-color:${C.accent}}
        .ci::placeholder{color:${C.textDim}}
        .ab{background:${C.accent};color:#fff;border:none;padding:9px 22px;border-radius:8px;font-weight:700;font-size:12.5px;cursor:pointer;display:flex;align-items:center;gap:7px;transition:all .15s;font-family:'DM Sans',sans-serif;letter-spacing:.2px}
        .ab:hover{box-shadow:0 3px 14px rgba(37,99,235,.25);transform:translateY(-1px)}
        .ab:disabled{opacity:.45;cursor:not-allowed;transform:none;box-shadow:none}
        .sb{background:${C.accent};color:#fff;border:none;width:34px;height:34px;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .15s}
        .sb:hover{background:#1d4ed8}
        .rb{border:1px solid ${C.border};background:${C.bg};color:${C.textMuted};padding:6px 14px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;font-family:'DM Sans',sans-serif;display:flex;align-items:center;gap:6px;transition:all .15s}
        .rb:hover{border-color:${C.accent};color:${C.accent}}
        .rb:disabled{opacity:.5;cursor:not-allowed}
        .rb .spinner{animation:spin .8s linear infinite}
        .badge{display:inline-flex;align-items:center;gap:4px;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600}
      `}</style>

      {/* ─── Header ─── */}
      <header style={{ padding: "14px 28px", borderBottom: `1px solid ${C.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: C.accent, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <BarChart3 size={16} color="#fff" strokeWidth={2.5} />
          </div>
          <div>
            <div style={{ fontSize: 14.5, fontWeight: 700, letterSpacing: -.2, color: C.text }}>Investment Research Assistant</div>
            <div style={{ fontSize: 10.5, color: C.textDim, fontWeight: 500 }}>AI-Powered Analysis · Intraday Research Pipeline</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {/* SSE status indicator */}
          <div className="badge" style={{ background: sseStatus === "connected" ? C.greenSoft : C.amberSoft, color: sseColors[sseStatus] }}>
            <Radio size={10} />
            {sseStatus === "connected" ? "Updates as at yesterday!" : sseStatus === "error" ? "Reconnecting" : "Connecting"}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}><Dot status="success" /><span style={{ fontSize: 11.5, color: C.textMuted, fontWeight: 500 }}>API</span></div>
        </div>
      </header>

      <div style={{ padding: "22px 26px", display: "flex", flexDirection: "column", gap: 18 }}>
        {/* ─── Ticker bar with refresh and last-updated ─── */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {TICKERS.map(t => <button key={t} className={`tk ${t === ticker ? "on" : ""}`} onClick={() => setTicker(t)}>{t}</button>)}

          {/* Refresh button */}
          <button className="rb" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? "spinner" : ""} />
            {refreshing ? "Refreshing..." : "Refresh Data"}
          </button>

          {/* Last updated + price */}
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>Last data</div>
              <div style={{ fontSize: 12, color: C.textMuted, fontFamily: "'Source Code Pro', monospace", fontWeight: 500 }}>{formatDataDate(lastDataDate)}</div>
            </div>
            <div style={{ width: 1, height: 28, background: C.border }} />
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'Source Code Pro', monospace", color: C.text }}>{latest?.close}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 3, padding: "3px 10px", borderRadius: 6, background: up ? C.greenSoft : C.redSoft }}>
                {up ? <ArrowUpRight size={14} color={C.green} /> : <ArrowDownRight size={14} color={C.red} />}
                <span style={{ fontSize: 13, fontWeight: 600, fontFamily: "'Source Code Pro', monospace", color: up ? C.green : C.red }}>
                  {up ? "+" : ""}{chg} ({chgPct}%)
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ─── Stats ─── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(175px, 1fr))", gap: 10 }}>
          <Stat label="Period High" value={hi.toFixed(2)} icon={TrendingUp} color={C.green} />
          <Stat label="Period Low" value={lo.toFixed(2)} icon={TrendingDown} color={C.red} />
          <Stat label="Avg Volume" value={`${(avgV / 1e6).toFixed(1)}M`} icon={Activity} color={C.accent} />
          <Stat label="Pipeline" value={`${okCount}/${pipelineRows.length}`} sub="tasks completed" icon={Cpu} color={okCount === pipelineRows.length ? C.green : C.amber} />
        </div>

        {/* ─── Main grid ─── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 370px", gap: 14 }}>
          {/* Chart + analysis */}
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>Price — {ticker}</span>
              <button className="ab" onClick={runAnalysis} disabled={analyzing}>
                <Zap size={13} /> {analyzing ? "Analyzing..." : "Run AI Analysis"}
              </button>
            </div>

            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={prices} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
                  <defs>
                    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.accent} stopOpacity={0.15} />
                      <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={C.border} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: C.textDim }} tickFormatter={d => d.slice(5)} interval={9} axisLine={{ stroke: C.border }} tickLine={false} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: C.textDim }} axisLine={false} tickLine={false} width={48} />
                  <Tooltip content={<Tip />} />
                  <Area type="monotone" dataKey="close" stroke={C.accent} fill="url(#g)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div style={{ height: 48 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={prices} margin={{ top: 0, right: 4, bottom: 0, left: 4 }}>
                  <XAxis dataKey="date" hide /><YAxis hide />
                  <Bar dataKey="volume" fill={C.border} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Analysis — always visible, pre-loaded on mount */}
            <div className="anim" style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
                <Zap size={13} color={C.accent} />
                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.accent, textTransform: "uppercase", letterSpacing: .5 }}>AI Analysis</span>
              </div>
              {analyzing ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: C.textMuted, fontSize: 13 }}>
                  <span style={{ animation: "pulse 1.4s ease-in-out infinite", color: C.accent }}>●</span> Calling LLM...
                </div>
              ) : analysis ? (
                <div style={{ fontSize: 13, lineHeight: 1.75, color: C.textMid, whiteSpace: "pre-wrap" }}>
                  {analysis.text.split("**").map((part, i) =>
                    i % 2 === 1 ? <strong key={i} style={{ color: C.text, fontWeight: 600 }}>{part}</strong> : <span key={i}>{part}</span>
                  )}
                </div>
              ) : null}
            </div>
          </div>

          {/* ─── Right column ─── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Chat */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: 16, display: "flex", flexDirection: "column", height: 340 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12 }}>
                <MessageSquare size={13} color={C.accent} />
                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>Research Chat</span>
              </div>
              <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 7, marginBottom: 12, paddingRight: 2 }}>
                {msgs.map((m, i) => (
                  <div key={i} className="anim" style={{
                    padding: "8px 12px", borderRadius: 10, fontSize: 13, lineHeight: 1.6, maxWidth: "90%",
                    alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                    background: m.role === "user" ? C.accentSoft : m.role === "system" ? "transparent" : C.bg,
                    color: m.role === "system" ? C.textDim : C.textMid,
                    border: m.role === "system" ? "none" : `1px solid ${C.border}`,
                    fontStyle: m.role === "system" ? "italic" : "normal",
                    fontWeight: m.role === "user" ? 500 : 400,
                  }}>{m.text}</div>
                ))}
                <div ref={chatEnd} />
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <input className="ci" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendChat()} placeholder={`Ask about ${ticker}...`} />
                <button className="sb" onClick={sendChat}><Send size={13} /></button>
              </div>
            </div>

            {/* Pipeline */}
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 14, padding: 16, flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 12 }}>
                <Database size={13} color={C.accent} />
                <span style={{ fontSize: 11.5, fontWeight: 700, color: C.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>Pipeline</span>
                <span style={{ marginLeft: "auto", fontSize: 10.5, fontFamily: "'Source Code Pro', monospace", color: C.textDim }}>intraday_stock_etl</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                {pipelineRows.map(t => (
                  <div key={t.id} style={{
                    display: "grid", gridTemplateColumns: "7px 50px 64px 1fr 46px", alignItems: "center", gap: 8,
                    padding: "5px 8px", borderRadius: 6, fontSize: 11.5, fontFamily: "'Source Code Pro', monospace",
                    background: t.status === "failed" ? C.redSoft : "transparent",
                  }}>
                    <Dot status={t.status} />
                    <span style={{ color: C.text, fontWeight: 600 }}>{t.ticker}</span>
                    <span style={{ color: C.textMuted }}>{t.stage}</span>
                    <span style={{ color: C.textDim }}>{t.time}</span>
                    <span style={{ color: C.textDim, textAlign: "right" }}>{t.dur}</span>
                  </div>
                ))}
              </div>
              {lastPipelineEvent && (
                <div style={{ marginTop: 10, fontSize: 10.5, color: C.textDim, fontStyle: "italic" }}>
                  Last pipeline run: {new Date(lastPipelineEvent).toLocaleString()}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Footer notice ─── */}
      <div style={{ margin: "0 26px 26px", padding: "14px 18px", background: C.amberSoft, border: `1px solid rgba(217,119,6,0.2)`, borderRadius: 12 }}>
        <div style={{ fontSize: 12, color: C.amber, fontWeight: 700, marginBottom: 4 }}>Data Frequency Notice</div>
        <div style={{ fontSize: 12, color: C.textMid, lineHeight: 1.65 }}>
          Alpha Vantage's free tier returns end-of-day data only, so intraday pipeline runs will show the same daily candle until the next trading day closes.
          For true intraday bars (5-min / 15-min / 60-min), I would switch to Alpha Vantage's intraday endpoint or a provider such as Polygon or Alpaca that streams intraday prices.
          The pipeline architecture stays the same — only the fetcher service would change.
        </div>
      </div>
    </div>
  );
}
