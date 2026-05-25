"use client";

import { useState, useEffect } from "react";
import Head from "next/head";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://your-railway-app.up.railway.app";

interface AnalysisResult {
  symbol: string;
  signal: string;
  composite_score: number;
  confidence: number;
  position_size_pct: number;
  entry_price: number | null;
  stop_loss: number | null;
  target_price: number | null;
  rationale: string;
  red_team_status: string;
  red_team_score: number;
  red_team_flags: string[];
  fundamental_verdict: string;
  fundamental_score: number;
  roe: number;
  debt_equity: number;
  peg_ratio: number;
  technical_signal: string;
  technical_score: number;
  momentum_6m: number;
  momentum_12m: number;
  rsi_14: number;
  ema_trend: string;
  news_score: number;
  news_sentiment: number;
  news_recommendation: string;
  news_headlines: string[];
  timestamp: string;
}

const signalColors: Record<string, string> = {
  STRONG_BUY: "bg-emerald-500",
  BUY: "bg-green-400",
  WEAK_BUY: "bg-green-300",
  HOLD: "bg-yellow-400",
  WEAK_SELL: "bg-orange-400",
  SELL: "bg-red-400",
  STRONG_SELL: "bg-red-600",
  AVOID: "bg-gray-800",
};

const signalEmojis: Record<string, string> = {
  STRONG_BUY: "🟢",
  BUY: "🟢",
  WEAK_BUY: "🟡",
  HOLD: "⚪",
  WEAK_SELL: "🟠",
  SELL: "🔴",
  STRONG_SELL: "🔴",
  AVOID: "🚫",
};

export default function Home() {
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [topPicks, setTopPicks] = useState<AnalysisResult[]>([]);
  const [avoidList, setAvoidList] = useState<AnalysisResult[]>([]);
  const [activeTab, setActiveTab] = useState<"analyze" | "top" | "avoid" | "index">("analyze");
  const [indexResults, setIndexResults] = useState<AnalysisResult[]>([]);
  const [indexLoading, setIndexLoading] = useState(false);

  const analyzeStock = async () => {
    if (!symbol) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/analyze/${symbol.toUpperCase()}`);
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const loadTopPicks = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/top-picks`);
      const data = await res.json();
      setTopPicks(data.picks || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const loadAvoidList = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/avoid-list`);
      const data = await res.json();
      setAvoidList(data.stocks || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const analyzeIndex = async () => {
    setIndexLoading(true);
    try {
      const res = await fetch(`${API_BASE}/analyze-index`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      setIndexResults(data || []);
    } catch (e) {
      console.error(e);
    }
    setIndexLoading(false);
  };

  useEffect(() => {
    if (activeTab === "top") loadTopPicks();
    if (activeTab === "avoid") loadAvoidList();
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Head>
        <title>Nifty200 Momentum 30 | Agentic Trading</title>
      </Head>

      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-blue-600 rounded-lg flex items-center justify-center text-lg font-bold">
              📈
            </div>
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-emerald-400 to-blue-400 bg-clip-text text-transparent">
                Nifty200 Momentum 30
              </h1>
              <p className="text-xs text-slate-400">Agentic Trading Intelligence</p>
            </div>
          </div>
          <div className="flex gap-2 text-xs">
            <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 border border-red-500/30">🔴 Red Team</span>
            <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 border border-green-500/30">🟢 Green Team</span>
            <span className="px-2 py-1 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">🔵 Blue Team</span>
            <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30">📰 News</span>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="max-w-7xl mx-auto px-4 py-4">
        <div className="flex gap-2 bg-slate-900 rounded-lg p-1">
          {(["analyze", "top", "avoid", "index"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all ${
                activeTab === tab
                  ? "bg-slate-700 text-white shadow-lg"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }`}
            >
              {tab === "analyze" && "🔍 Analyze Stock"}
              {tab === "top" && "🏆 Top Picks"}
              {tab === "avoid" && "🚫 Avoid List"}
              {tab === "index" && "📊 Full Index"}
            </button>
          ))}
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 pb-12">
        {/* ANALYZE TAB */}
        {activeTab === "analyze" && (
          <div className="space-y-6">
            <div className="bg-slate-900 rounded-xl p-6 border border-slate-800">
              <h2 className="text-lg font-semibold mb-4">Analyze Single Stock</h2>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="Enter NSE symbol (e.g., RELIANCE.NS)"
                  className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  onKeyDown={(e) => e.key === "Enter" && analyzeStock()}
                />
                <button
                  onClick={analyzeStock}
                  disabled={loading}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  {loading ? "Analyzing..." : "Analyze"}
                </button>
              </div>
            </div>

            {result && (
              <div className="space-y-4">
                {/* Main Signal Card */}
                <div className={`rounded-xl p-6 border-2 ${
                  result.signal === "STRONG_BUY" || result.signal === "BUY"
                    ? "border-emerald-500/50 bg-emerald-950/30"
                    : result.signal === "AVOID"
                    ? "border-red-500/50 bg-red-950/30"
                    : "border-yellow-500/50 bg-yellow-950/30"
                }`}>
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h2 className="text-3xl font-bold">{result.symbol}</h2>
                      <p className="text-slate-400">Nifty200 Momentum 30 Constituent</p>
                    </div>
                    <div className={`px-6 py-3 rounded-xl text-2xl font-bold ${signalColors[result.signal]} text-white shadow-lg`}>
                      {signalEmojis[result.signal]} {result.signal.replace("_", " ")}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <p className="text-xs text-slate-400">Composite Score</p>
                      <p className="text-2xl font-bold">{result.composite_score}/100</p>
                    </div>
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <p className="text-xs text-slate-400">Confidence</p>
                      <p className="text-2xl font-bold">{result.confidence}%</p>
                    </div>
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <p className="text-xs text-slate-400">Position Size</p>
                      <p className="text-2xl font-bold">{result.position_size_pct}%</p>
                    </div>
                    <div className="bg-slate-800/50 rounded-lg p-3">
                      <p className="text-xs text-slate-400">RSI (14)</p>
                      <p className="text-2xl font-bold">{result.rsi_14?.toFixed(1)}</p>
                    </div>
                  </div>

                  {/* Price Levels */}
                  {result.entry_price && (
                    <div className="grid grid-cols-3 gap-4 mb-4">
                      <div className="bg-emerald-900/30 border border-emerald-500/30 rounded-lg p-3 text-center">
                        <p className="text-xs text-emerald-400">Entry</p>
                        <p className="text-xl font-bold text-emerald-300">₹{result.entry_price.toFixed(2)}</p>
                      </div>
                      <div className="bg-red-900/30 border border-red-500/30 rounded-lg p-3 text-center">
                        <p className="text-xs text-red-400">Stop Loss</p>
                        <p className="text-xl font-bold text-red-300">₹{result.stop_loss?.toFixed(2)}</p>
                      </div>
                      <div className="bg-blue-900/30 border border-blue-500/30 rounded-lg p-3 text-center">
                        <p className="text-xs text-blue-400">Target</p>
                        <p className="text-xl font-bold text-blue-300">₹{result.target_price?.toFixed(2)}</p>
                      </div>
                    </div>
                  )}

                  <p className="text-sm text-slate-300 leading-relaxed bg-slate-800/30 rounded-lg p-4">
                    {result.rationale}
                  </p>
                </div>

                {/* Agent Cards */}
                <div className="grid md:grid-cols-2 gap-4">
                  {/* Red Team */}
                  <div className="bg-slate-900 rounded-xl p-5 border border-red-500/20">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-red-400 text-lg">🔴</span>
                      <h3 className="font-semibold text-red-400">Red Team — Governance</h3>
                      <span className={`ml-auto px-2 py-1 rounded text-xs font-bold ${
                        result.red_team_status === "PASS" ? "bg-green-500/20 text-green-400" :
                        result.red_team_status === "WARNING" ? "bg-yellow-500/20 text-yellow-400" :
                        "bg-red-500/20 text-red-400"
                      }`}>
                        {result.red_team_status}
                      </span>
                    </div>
                    <p className="text-sm text-slate-400 mb-2">Score: {result.red_team_score}/100</p>
                    {result.red_team_flags.length > 0 ? (
                      <ul className="space-y-1">
                        {result.red_team_flags.map((f, i) => (
                          <li key={i} className="text-xs text-red-300 bg-red-950/30 rounded px-2 py-1">⚠️ {f}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-green-400">✅ No governance issues detected</p>
                    )}
                  </div>

                  {/* Green Team */}
                  <div className="bg-slate-900 rounded-xl p-5 border border-green-500/20">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-green-400 text-lg">🟢</span>
                      <h3 className="font-semibold text-green-400">Green Team — Fundamentals</h3>
                      <span className="ml-auto px-2 py-1 rounded text-xs font-bold bg-green-500/20 text-green-400">
                        {result.fundamental_verdict}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">ROE</span>
                        <p className="text-green-300 font-bold">{result.roe.toFixed(1)}%</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">D/E</span>
                        <p className="text-green-300 font-bold">{result.debt_equity.toFixed(1)}x</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">PEG</span>
                        <p className="text-green-300 font-bold">{result.peg_ratio.toFixed(2)}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">Score</span>
                        <p className="text-green-300 font-bold">{result.fundamental_score}/100</p>
                      </div>
                    </div>
                  </div>

                  {/* Blue Team */}
                  <div className="bg-slate-900 rounded-xl p-5 border border-blue-500/20">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-blue-400 text-lg">🔵</span>
                      <h3 className="font-semibold text-blue-400">Blue Team — Technicals</h3>
                      <span className="ml-auto px-2 py-1 rounded text-xs font-bold bg-blue-500/20 text-blue-400">
                        {result.technical_signal}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">6M Momentum</span>
                        <p className="text-blue-300 font-bold">{result.momentum_6m.toFixed(1)}%</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">12M Momentum</span>
                        <p className="text-blue-300 font-bold">{result.momentum_12m.toFixed(1)}%</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">EMA Trend</span>
                        <p className="text-blue-300 font-bold">{result.ema_trend}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-2">
                        <span className="text-slate-500">Score</span>
                        <p className="text-blue-300 font-bold">{result.technical_score}/100</p>
                      </div>
                    </div>
                  </div>

                  {/* News Sentinel */}
                  <div className="bg-slate-900 rounded-xl p-5 border border-purple-500/20">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-purple-400 text-lg">📰</span>
                      <h3 className="font-semibold text-purple-400">News Sentinel</h3>
                      <span className={`ml-auto px-2 py-1 rounded text-xs font-bold ${
                        result.news_recommendation === "FAVORABLE" ? "bg-green-500/20 text-green-400" :
                        result.news_recommendation === "NEUTRAL" ? "bg-yellow-500/20 text-yellow-400" :
                        "bg-red-500/20 text-red-400"
                      }`}>
                        {result.news_recommendation}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mb-2">
                      Sentiment: {result.news_sentiment > 0 ? "+" : ""}{result.news_sentiment.toFixed(2)} | Score: {result.news_score}/100
                    </p>
                    {result.news_headlines.length > 0 && (
                      <ul className="space-y-1">
                        {result.news_headlines.slice(0, 3).map((h, i) => (
                          <li key={i} className="text-xs text-slate-300 bg-slate-800 rounded px-2 py-1 truncate">• {h}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TOP PICKS TAB */}
        {activeTab === "top" && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold">🏆 Top BUY Recommendations</h2>
            {loading ? (
              <div className="text-center py-12 text-slate-400">Loading...</div>
            ) : topPicks.length === 0 ? (
              <div className="text-center py-12 text-slate-500">No strong BUY signals found currently</div>
            ) : (
              topPicks.map((pick) => (
                <div key={pick.symbol} className="bg-slate-900 rounded-xl p-5 border border-emerald-500/20 hover:border-emerald-500/40 transition-colors">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xl font-bold">{pick.symbol}</h3>
                      <p className="text-sm text-slate-400">{pick.rationale.substring(0, 120)}...</p>
                    </div>
                    <div className="text-right">
                      <span className="px-3 py-1 rounded-lg bg-emerald-500 text-white font-bold">
                        {pick.signal}
                      </span>
                      <p className="text-xs text-slate-400 mt-1">Score: {pick.composite_score}/100</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* AVOID LIST TAB */}
        {activeTab === "avoid" && (
          <div className="space-y-4">
            <h2 className="text-xl font-bold">🚫 Stocks to AVOID</h2>
            <p className="text-sm text-slate-400">Filtered by Red Team governance screening</p>
            {loading ? (
              <div className="text-center py-12 text-slate-400">Loading...</div>
            ) : avoidList.length === 0 ? (
              <div className="text-center py-12 text-slate-500">No stocks flagged for avoidance currently</div>
            ) : (
              avoidList.map((stock) => (
                <div key={stock.symbol} className="bg-slate-900 rounded-xl p-5 border border-red-500/20">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-xl font-bold text-red-400">{stock.symbol}</h3>
                      <p className="text-sm text-red-300/70">{stock.rationale}</p>
                      {stock.red_team_flags.length > 0 && (
                        <div className="flex gap-2 mt-2 flex-wrap">
                          {stock.red_team_flags.map((f, i) => (
                            <span key={i} className="text-xs bg-red-950/50 text-red-400 px-2 py-1 rounded">{f}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="text-right">
                      <span className="px-3 py-1 rounded-lg bg-red-600 text-white font-bold">AVOID</span>
                      <p className="text-xs text-slate-400 mt-1">Red Score: {stock.red_team_score}/100</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* FULL INDEX TAB */}
        {activeTab === "index" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold">📊 Nifty200 Momentum 30 — Full Analysis</h2>
              <button
                onClick={analyzeIndex}
                disabled={indexLoading}
                className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {indexLoading ? "Analyzing..." : "Run Full Analysis"}
              </button>
            </div>

            {indexLoading ? (
              <div className="text-center py-12">
                <div className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                <p className="text-slate-400">Running all 4 agents on 30 stocks...</p>
                <p className="text-xs text-slate-500 mt-2">Red Team → Green Team → Blue Team → News Sentinel</p>
              </div>
            ) : indexResults.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400">
                      <th className="text-left py-3 px-2">Rank</th>
                      <th className="text-left py-3 px-2">Symbol</th>
                      <th className="text-left py-3 px-2">Signal</th>
                      <th className="text-left py-3 px-2">Score</th>
                      <th className="text-left py-3 px-2">Red Team</th>
                      <th className="text-left py-3 px-2">Fundamental</th>
                      <th className="text-left py-3 px-2">Technical</th>
                      <th className="text-left py-3 px-2">News</th>
                      <th className="text-left py-3 px-2">Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    {indexResults.map((r, i) => (
                      <tr key={r.symbol} className="border-b border-slate-800 hover:bg-slate-800/50 transition-colors">
                        <td className="py-3 px-2 text-slate-500">#{i + 1}</td>
                        <td className="py-3 px-2 font-bold">{r.symbol}</td>
                        <td className="py-3 px-2">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${signalColors[r.signal]} text-white`}>
                            {r.signal.replace("_", " ")}
                          </span>
                        </td>
                        <td className="py-3 px-2 font-mono">{r.composite_score}</td>
                        <td className="py-3 px-2">
                          <span className={`text-xs ${
                            r.red_team_status === "PASS" ? "text-green-400" :
                            r.red_team_status === "WARNING" ? "text-yellow-400" : "text-red-400"
                          }`}>
                            {r.red_team_status} ({r.red_team_score})
                          </span>
                        </td>
                        <td className="py-3 px-2 text-xs text-green-400">{r.fundamental_verdict} ({r.fundamental_score})</td>
                        <td className="py-3 px-2 text-xs text-blue-400">{r.technical_signal} ({r.technical_score})</td>
                        <td className="py-3 px-2 text-xs text-purple-400">{r.news_recommendation} ({r.news_score})</td>
                        <td className="py-3 px-2 text-xs">{r.position_size_pct > 0 ? `${r.position_size_pct}%` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500">
                Click "Run Full Analysis" to analyze all 30 constituents
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-12 py-6 text-center text-xs text-slate-500">
        <p>Nifty200 Momentum 30 Agentic Trading System | Built with Red Team + Green Team + Blue Team + News Sentinel</p>
        <p className="mt-1">Not financial advice. For educational purposes only.</p>
      </footer>
    </div>
  );
}
