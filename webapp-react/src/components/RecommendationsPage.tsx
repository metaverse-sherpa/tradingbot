import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Lightbulb, Clock, RefreshCw, ChevronDown, Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore } from '../store/useStore';
import LoadingDisplay from './LoadingDisplay';

const SmallCustomSelect = ({ value, onChange, options }: { value: string, onChange: (v: string) => void, options: {value: string, label: string}[] }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentLabel = options.find(o => o.value === value)?.label || value;

  return (
    <div className="relative w-full sm:w-auto" ref={ref}>
      <button 
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full sm:w-56 lg:w-64 bg-[#1f2028] border border-white/10 text-white text-xs md:text-sm font-bold uppercase tracking-wider rounded-xl px-4 py-2.5 flex justify-between items-center outline-none hover:border-white/20 transition-colors"
      >
        <span className="truncate pr-2">{currentLabel}</span>
        <ChevronDown size={14} className={`text-gray-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-[100] w-full mt-1 bg-[#1f2028] border border-white/10 rounded-xl shadow-xl overflow-y-auto max-h-48 left-0">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-4 py-2.5 text-xs hover:bg-white/5 transition-colors ${value === opt.value ? 'text-cyan-400 font-bold bg-white/5' : 'text-gray-300'}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};


const RecommendationsPage: React.FC = () => {
  const { user, setUser } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);

  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState<'stocks' | 'crypto'>('stocks');
  const [expandedCharts, setExpandedCharts] = useState<Record<string | number, boolean>>({});

  const toggleChart = (id: string | number) => {
    setExpandedCharts(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  // Filters initialized from user preference
  const [riskProfile, setRiskProfile] = useState<string>(user?.risk_profile || 'Moderate');
  const [investmentGoal, setInvestmentGoal] = useState<string>(user?.investment_goal || 'Growth');
  const [sortBy, setSortBy] = useState<string>('target_pnl');

  useEffect(() => {
    if (user) {
      if (user.risk_profile) setRiskProfile(user.risk_profile);
      if (user.investment_goal) setInvestmentGoal(user.investment_goal);
    }
  }, [user]);

  const fetchRecommendations = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const url = showRefresh ? '/portfolio/recommendations?force=true' : '/portfolio/recommendations';
      const res = await api.get(url);
      setRecommendations(res.data?.recommendations || []);
    } catch (err) {
      console.error("Error fetching recommendations:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (isPremium) {
      fetchRecommendations();
    } else {
      setLoading(false);
    }
  }, [fetchRecommendations, isPremium]);

  const handleGenerateBuys = async () => {
    setGenerating(true);
    try {
      await api.post('/portfolio/good-buys', {
        risk_profile: riskProfile,
        investment_goal: investmentGoal,
        force_regenerate: true
      });
      await fetchRecommendations(true);
    } catch (err: any) {
      console.error("Failed to generate good buys", err);
    } finally {
      setGenerating(false);
    }
  };

  const getYahooFinanceLink = (symbol: string, category: string) => {
    const isCrypto = category.toLowerCase() === 'crypto';
    const cleanSym = symbol.toUpperCase().replace('/USDT', '').replace('/USD', '');
    const suffix = isCrypto ? '-USD' : '';
    return `https://uk.finance.yahoo.com/quote/${cleanSym}${suffix}`;
  };

  const formatPercent = (val: number) => {
    return `${val > 0 ? '+' : ''}${val.toFixed(2)}%`;
  };

  const getDurationString = (created_at: number, closed_at?: number) => {
    const end = closed_at || Math.floor(Date.now() / 1000);
    const diffSeconds = end - created_at;
    const diffDays = Math.floor(diffSeconds / 86400);
    if (diffDays <= 0) {
      const hours = Math.floor(diffSeconds / 3600);
      return `${hours}h open`;
    }
    return `${diffDays}d open`;
  };

  if (!isPremium) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-6">
        <div className="bg-[#1f2028]/80 border border-yellow-500/30 rounded-3xl p-8 max-w-md shadow-2xl backdrop-blur-xl">
          <div className="bg-yellow-500/10 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-6 text-yellow-500 border border-yellow-500/20">
            <Lock size={32} />
          </div>
          <h2 className="text-2xl font-black text-[#f3f4f6] tracking-wide uppercase mb-3">Premium Feature</h2>
          <p className="text-gray-400 text-sm mb-6 leading-relaxed">
            AI recommendations and portfolio performance tracking are exclusive to premium members. Upgrade your account to view high-conviction signals and start tracking holds.
          </p>
          <Link
            to="/premium"
            className="inline-block w-full bg-gradient-to-r from-yellow-500 to-amber-600 hover:from-yellow-400 hover:to-amber-500 text-black font-extrabold uppercase py-3.5 rounded-xl text-sm transition-all tracking-wider shadow-lg shadow-yellow-500/10"
          >
            Upgrade to Premium
          </Link>
        </div>
      </div>
    );
  }

  if (loading) {
    return <LoadingDisplay />;
  }

  // Count active recs per category (independent of active tab) for tab badges
  const profileFilteredRecs = recommendations.filter(
    (r) =>
      r.risk_profile.toLowerCase() === riskProfile.toLowerCase() &&
      r.investment_goal.toLowerCase() === investmentGoal.toLowerCase()
  );
  const activeCryptoCount = profileFilteredRecs.filter((r) => r.category.toLowerCase() === 'crypto' && r.status === 'active').length;
  const activeStockCount = profileFilteredRecs.filter((r) => r.category.toLowerCase() === 'stock' && r.status === 'active').length;

  // Filter recommendations based on selected drop downs and active tab
  const filteredRecs = recommendations.filter(
    (r) =>
      r.risk_profile.toLowerCase() === riskProfile.toLowerCase() &&
      r.investment_goal.toLowerCase() === investmentGoal.toLowerCase() &&
      r.category.toLowerCase() === (activeTab === 'stocks' ? 'stock' : 'crypto')
  );

  const sortedRecs = [...filteredRecs].sort((a, b) => {
    if (sortBy === 'target_pnl') {
      const targetA = a.entry_price ? Math.abs((a.target_price - a.entry_price) / a.entry_price) : 0;
      const targetB = b.entry_price ? Math.abs((b.target_price - b.entry_price) / b.entry_price) : 0;
      return targetB - targetA;
    } else {
      const pnlA = a.entry_price ? ((a.current_price - a.entry_price) / a.entry_price) * 100 : 0;
      const pnlB = b.entry_price ? ((b.current_price - b.entry_price) / b.entry_price) * 100 : 0;
      return pnlB - pnlA;
    }
  });

  const activeRecs = sortedRecs.filter((r) => r.status === 'active');
  const pastRecs = sortedRecs.filter((r) => r.status !== 'active');

  // Compute stats locally
  const totalRecs = filteredRecs.length;
  const closedCount = pastRecs.length;
  const hits = pastRecs.filter((r) => r.status === 'hit_target').length;
  const stops = pastRecs.filter((r) => r.status === 'hit_stop_loss').length;
  const winRate = closedCount > 0 ? (hits / closedCount) * 100 : 0;
  const avgDays = closedCount > 0
    ? pastRecs.reduce((sum, r) => sum + ((r.closed_at || r.created_at) - r.created_at), 0) / closedCount / 86400
    : 0;


  return (
    <div className="space-y-6">
      {/* Header and Filter Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-[#141620]/40 p-4 sm:p-6 rounded-3xl border border-white/5 backdrop-blur-sm">
        <div>
          <h1 className="text-xl md:text-3xl font-black text-[#f3f4f6] flex items-center gap-3 tracking-wide uppercase">
            <span className="bg-cyan-500/10 p-2.5 rounded-xl border border-cyan-500/20 text-cyan-400">
              <Lightbulb size={22} className="fill-[#131620]" />
            </span>
            RECOMMENDATION TRACKER
          </h1>
          <p className="text-gray-400 text-xs md:text-sm mt-1">
            Track performance, targets, and stop losses of AI-recommended buys.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row sm:flex-wrap items-stretch sm:items-center gap-3 sm:gap-4 relative z-20 w-full lg:w-auto mt-6 lg:mt-0">
          {/* Risk Dropdown */}
          <div className="flex flex-row items-center justify-between sm:justify-start gap-4 bg-white/5 sm:bg-transparent px-4 py-2 sm:p-0 rounded-xl">
            <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider whitespace-nowrap">Risk Profile</span>
            <SmallCustomSelect
              value={riskProfile}
              onChange={async (v) => {
                setRiskProfile(v);
                try {
                  await api.post('/settings/preferences', { risk_profile: v });
                  if (user) setUser({ ...user, risk_profile: v } as any);
                } catch (e) {
                  console.error("Failed to update risk profile:", e);
                }
              }}
              options={[
                { value: "Conservative", label: "Conservative" },
                { value: "Moderate", label: "Moderate" },
                { value: "Aggressive", label: "Aggressive" }
              ]}
            />
          </div>

          {/* Goal Dropdown */}
          <div className="flex flex-row items-center justify-between sm:justify-start gap-4 bg-white/5 sm:bg-transparent px-4 py-2 sm:p-0 rounded-xl">
            <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider whitespace-nowrap">Goal</span>
            <SmallCustomSelect
              value={investmentGoal}
              onChange={async (v) => {
                setInvestmentGoal(v);
                try {
                  await api.post('/settings/preferences', { investment_goal: v });
                  if (user) setUser({ ...user, investment_goal: v } as any);
                } catch (e) {
                  console.error("Failed to update investment goal:", e);
                }
              }}
              options={[
                { value: "Income", label: "Income" },
                { value: "Growth", label: "Growth" },
                { value: "Speculation", label: "Speculation" }
              ]}
            />
          </div>

          {/* Sort By Dropdown */}
          <div className="flex flex-row items-center justify-between sm:justify-start gap-3 sm:gap-4 bg-white/5 sm:bg-transparent px-3 sm:px-4 py-2 sm:p-0 rounded-xl">
            <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider whitespace-nowrap">Sort By</span>
            <div className="flex items-center gap-2">
              <SmallCustomSelect
                value={sortBy}
                onChange={(v) => setSortBy(v)}
                options={[
                  { value: "target_pnl", label: "Target PnL %" },
                  { value: "actual_pnl", label: "Actual PnL %" }
                ]}
              />
              <button
                onClick={() => fetchRecommendations(true)}
                disabled={refreshing}
                className="flex items-center justify-center p-2 text-gray-400 hover:text-cyan-400 hover:bg-white/5 rounded-lg transition-colors shrink-0 disabled:opacity-50"
                title="Refresh Recommendations"
              >
                <RefreshCw size={18} className={refreshing ? 'animate-spin text-cyan-400' : ''} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex bg-[#141620]/40 p-1.5 rounded-2xl border border-white/5 backdrop-blur-sm w-full max-w-sm mb-6">
        <button
          onClick={() => setActiveTab('crypto')}
          className={`flex-1 py-2.5 text-xs font-black uppercase tracking-wider rounded-xl transition-all ${
            activeTab === 'crypto'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/20'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Crypto ({activeCryptoCount})
        </button>
        <button
          onClick={() => setActiveTab('stocks')}
          className={`flex-1 py-2.5 text-xs font-black uppercase tracking-wider rounded-xl transition-all ${
            activeTab === 'stocks'
              ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/20'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Stocks ({activeStockCount})
        </button>
      </div>

      {/* Stats Panels */}
      {(hits > 0 || stops > 0) && (
        <div className="w-full mb-6">
        {/* Stocks Hold Stats */}
        {activeTab === 'stocks' && (
          <div className="bg-gradient-to-br from-[#141724] to-[#0f111a] border border-white/5 rounded-3xl p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/5 rounded-full blur-2xl pointer-events-none"></div>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl">📈</span>
              <h3 className="text-sm font-black text-gray-300 uppercase tracking-wider">Stocks Hold Stats</h3>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Total Recs</p>
                <p className="text-xl font-black text-white mt-1">{totalRecs}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Win Rate</p>
                <p className={`text-xl font-black mt-1 ${winRate >= 50 ? 'text-emerald-400' : winRate > 0 ? 'text-rose-400' : 'text-gray-400'}`}>
                  {winRate.toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Hit Target</p>
                <p className="text-xl font-black text-emerald-400 mt-1">{hits}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Stop Loss</p>
                <p className="text-xl font-black text-rose-400 mt-1">{stops}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Avg Duration</p>
                <p className="text-xl font-black text-cyan-400 mt-1">
                  {closedCount > 0 ? `${avgDays.toFixed(1)}d` : '—'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Crypto Hold Stats */}
        {activeTab === 'crypto' && (
          <div className="bg-gradient-to-br from-[#141724] to-[#0f111a] border border-white/5 rounded-3xl p-6 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-yellow-500/5 rounded-full blur-2xl pointer-events-none"></div>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xl">🪙</span>
              <h3 className="text-sm font-black text-gray-300 uppercase tracking-wider">Crypto Hold Stats</h3>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Total Recs</p>
                <p className="text-xl font-black text-white mt-1">{totalRecs}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Win Rate</p>
                <p className={`text-xl font-black mt-1 ${winRate >= 50 ? 'text-emerald-400' : winRate > 0 ? 'text-rose-400' : 'text-gray-400'}`}>
                  {winRate.toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Hit Target</p>
                <p className="text-xl font-black text-emerald-400 mt-1">{hits}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Stop Loss</p>
                <p className="text-xl font-black text-rose-400 mt-1">{stops}</p>
              </div>
              <div>
                <p className="text-gray-500 text-[10px] uppercase font-bold tracking-wider">Avg Duration</p>
                <p className="text-xl font-black text-cyan-400 mt-1">
                  {closedCount > 0 ? `${avgDays.toFixed(1)}d` : '—'}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Active Recommendations Section */}
      <div>
        <h2 className="text-lg font-black text-[#f3f4f6] uppercase tracking-wider mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          Active recommendations ({activeRecs.length})
        </h2>

        {activeRecs.length === 0 ? (
          <div className="bg-[#141620]/40 p-8 rounded-3xl border border-white/5 text-center flex flex-col items-center gap-5">
            <p className="text-gray-400">
              There aren't currently any active recommendations tracked for {riskProfile} & {investmentGoal}.
            </p>
            <button
              onClick={handleGenerateBuys}
              disabled={generating}
              className="flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white px-6 py-3 rounded-xl text-sm font-black transition-all uppercase tracking-wider shadow-lg shadow-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? (
                <>
                  <RefreshCw size={16} className="animate-spin" />
                  Generating AI Buys...
                </>
              ) : (
                <>
                  <Lightbulb size={16} className="fill-[#131620]" />
                  Generate AI Buys
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {activeRecs.map((rec) => {
              const pnl = ((rec.current_price - rec.entry_price) / rec.entry_price) * 100;
              const isProfit = pnl >= 0;
              const targetPct = ((rec.target_price - rec.entry_price) / rec.entry_price) * 100;
              const stopPct = ((rec.stop_loss - rec.entry_price) / rec.entry_price) * 100;

              return (
                <div key={rec.id} className="bg-[#181a24]/90 border border-white/10 hover:border-white/20 transition-all rounded-3xl p-5 shadow-xl relative overflow-hidden flex flex-col justify-between">
                  <div>
                    {/* Top Row */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div>
                        <a
                          href={getYahooFinanceLink(rec.symbol, rec.category)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-lg font-black text-cyan-400 hover:underline uppercase tracking-wide"
                        >
                          {rec.symbol}
                        </a>
                        <span className="ml-2 text-[10px] font-bold bg-white/5 border border-white/10 text-gray-400 uppercase tracking-widest px-2 py-0.5 rounded-md">
                          {rec.category}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-[11px] font-semibold text-gray-400">
                        <Clock size={12} />
                        {getDurationString(rec.created_at)}
                      </div>
                    </div>

                    {/* Prices Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[#0c0d12]/50 p-3 rounded-2xl border border-white/5 mb-4">
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Entry Price</p>
                        <p className="text-xs font-black text-white mt-0.5">${rec.entry_price.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Current Price</p>
                        <p className="text-xs font-black text-white mt-0.5">${rec.current_price.toLocaleString()} <span className="text-[10px] font-semibold text-gray-400">({formatPercent(pnl)})</span></p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Target Price</p>
                        <p className="text-xs font-black text-emerald-400 mt-0.5">${rec.target_price.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Stop Loss</p>
                        <p className="text-xs font-black text-rose-400 mt-0.5">${rec.stop_loss.toLocaleString()} <span className="text-[10px] font-semibold text-rose-500/70">({formatPercent(stopPct)})</span></p>
                      </div>
                    </div>

                    {/* PnL Indicator */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-gray-400 font-bold uppercase tracking-wider">Performance</span>
                        <span className={`text-sm font-black px-2.5 py-1 rounded-lg border ${
                          sortBy === 'actual_pnl' 
                            ? (isProfit ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 shadow-sm shadow-emerald-500/10' : 'bg-rose-500/20 text-rose-400 border-rose-500/40 shadow-sm shadow-rose-500/10')
                            : (isProfit ? 'bg-emerald-500/5 text-emerald-500/70 border-emerald-500/10' : 'bg-rose-500/5 text-rose-500/70 border-rose-500/10')
                        }`}>
                          {pnl > 0 ? '+' : ''}{pnl.toFixed(2)}%
                        </span>
                        <span className="text-xs text-gray-500 font-bold uppercase tracking-wider mx-1">of</span>
                        <span className={`text-sm font-black px-2.5 py-1 rounded-lg border ${
                          sortBy === 'target_pnl' 
                            ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40 shadow-sm shadow-cyan-500/10'
                            : 'bg-cyan-500/5 text-cyan-500/70 border-cyan-500/10'
                        }`}>
                          {targetPct > 0 ? '+' : ''}{targetPct.toFixed(2)}%
                        </span>
                      </div>
                      <button
                        onClick={() => toggleChart(rec.id)}
                        className="text-gray-400 hover:text-cyan-400 transition-colors p-2 hover:bg-white/5 rounded-xl flex items-center justify-center gap-1.5 text-xs font-bold uppercase tracking-wider border border-white/5 sm:border-0 bg-white/5 sm:bg-transparent w-full sm:w-auto"
                      >
                        {expandedCharts[rec.id] ? 'Hide Chart' : 'Show Chart'}
                        <ChevronDown size={14} className={`transform transition-transform duration-200 ${expandedCharts[rec.id] ? 'rotate-180' : ''}`} />
                      </button>
                    </div>
                  </div>

                  {/* Embedded mini chart using get_trade_chart logic */}
                  {expandedCharts[rec.id] && (
                    <div className="mt-2 bg-[#0c0d12]/40 rounded-xl overflow-hidden border border-white/5 animate-in fade-in slide-in-from-top-2 duration-200">
                      <img
                        src={`/api/trades/chart?symbol=${encodeURIComponent(
                          rec.category === 'stock' ? rec.symbol : `${rec.symbol}/USDT`
                        )}&entry=${rec.entry_price}&tp=${rec.target_price}&sl=${rec.stop_loss}&open_ts=${rec.created_at}&current_price=${rec.current_price}&type=${rec.category}&timeframe=1D&leverage=1`}
                        alt={`${rec.symbol} price action chart`}
                        className="w-full h-auto object-cover opacity-90"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Historical Recommendations Section */}
      <div>
        <h2 className="text-lg font-black text-[#f3f4f6] uppercase tracking-wider mb-4 flex items-center gap-2">
          <Clock size={18} className="text-gray-400" />
          Past recommendations ({pastRecs.length})
        </h2>

        {pastRecs.length === 0 ? (
          <div className="bg-[#141620]/40 p-8 rounded-3xl border border-white/5 text-center text-gray-400">
            No closed holds tracked for this configuration yet.
          </div>
        ) : (
          <div className="bg-[#181a24]/90 rounded-3xl border border-white/10 overflow-hidden shadow-xl">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/10 text-[10px] font-black text-gray-500 uppercase tracking-widest bg-[#13151f]/50">
                    <th className="px-6 py-4">Symbol</th>
                    <th className="px-6 py-4">Category</th>
                    <th className="px-6 py-4">Entry</th>
                    <th className="px-6 py-4">Exit</th>
                    <th className="px-6 py-4">Target</th>
                    <th className="px-6 py-4">Stop Loss</th>
                    <th className="px-6 py-4">PnL</th>
                    <th className="px-6 py-4">Duration</th>
                    <th className="px-6 py-4">Result</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-xs text-gray-300">
                  {pastRecs.map((rec) => {
                    const pnl = ((rec.current_price - rec.entry_price) / rec.entry_price) * 100;
                    const isProfit = pnl >= 0;
                    const isTarget = rec.status === 'hit_target';

                    return (
                      <tr key={rec.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-6 py-4 font-black">
                          <a
                            href={getYahooFinanceLink(rec.symbol, rec.category)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-cyan-400 hover:underline uppercase"
                          >
                            {rec.symbol}
                          </a>
                        </td>
                        <td className="px-6 py-4 uppercase font-semibold text-gray-400 text-[10px]">{rec.category}</td>
                        <td className="px-6 py-4 font-semibold">${rec.entry_price.toLocaleString()}</td>
                        <td className="px-6 py-4 font-semibold">${rec.current_price.toLocaleString()}</td>
                        <td className="px-6 py-4 text-emerald-500/80 font-semibold">${rec.target_price.toLocaleString()}</td>
                        <td className="px-6 py-4 text-rose-500/80 font-semibold">${rec.stop_loss.toLocaleString()}</td>
                        <td className={`px-6 py-4 font-black ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {formatPercent(pnl)}
                        </td>
                        <td className="px-6 py-4 text-gray-400">{getDurationString(rec.created_at, rec.closed_at)}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-block px-2.5 py-0.5 rounded-full font-bold text-[10px] uppercase border ${isTarget ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'}`}>
                            {isTarget ? 'Target Hit' : 'Stopped Out'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default RecommendationsPage;
