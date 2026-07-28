import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Lightbulb, Clock, RefreshCw, ChevronDown, Lock, Trash2, AlertTriangle } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore, useDashboardStore } from '../store/useStore';
import LoadingDisplay from './LoadingDisplay';
import { isStockMarketOpen } from '../utils/market';
import { formatPrice } from '../utils/formatters';

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
    <div className="relative inline-block" ref={ref}>
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
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
  const activeTab: 'stocks' | 'crypto' = categoryTab === 'stock' ? 'stocks' : 'crypto';
  const setActiveTab = (tab: 'stocks' | 'crypto') => {
    setCategoryTab(tab === 'stocks' ? 'stock' : 'crypto');
  };

  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);

  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusTab, setStatusTab] = useState<'active' | 'closed'>('active');
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
  const [sortBy, setSortBy] = useState<string>('actual_pnl');

  useEffect(() => {
    if (user) {
      if (user.risk_profile) setRiskProfile(user.risk_profile);
      if (user.investment_goal) setInvestmentGoal(user.investment_goal);
    }
  }, [user]);

  const handleDeleteRecommendation = async (id: number) => {
    if (!window.confirm("Are you sure you want to delete this recommendation record?")) return;
    try {
      await api.delete(`/portfolio/recommendations/${id}`);
      setRecommendations(prev => prev.filter(r => r.id !== id));
    } catch (err) {
      console.error("Failed to delete recommendation:", err);
      alert("Failed to delete recommendation.");
    }
  };

  const [executingSignalId, setExecutingSignalId] = useState<string | number | null>(null);
  const [pendingTrades, setPendingTrades] = useState<Record<string, any>>({});
  const [cancellingSignalId, setCancellingSignalId] = useState<string | number | null>(null);
  const [openTrades, setOpenTrades] = useState<any[]>([]);
  const [closingTradeId, setClosingTradeId] = useState<string | null>(null);

  const [queueModalSignal, setQueueModalSignal] = useState<any | null>(null);
  const [selectedQueueOption, setSelectedQueueOption] = useState<'auto_execute' | 'email_reminder'>('auto_execute');
  const [submittingQueue, setSubmittingQueue] = useState(false);

  const fetchOpenTrades = useCallback(async (bypassCache = false) => {
    try {
      const url = bypassCache ? '/trades/open?bypass_cache=true' : '/trades/open';
      const res = await api.get(url);
      setOpenTrades(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error('Error fetching open trades:', err);
    }
  }, []);

  const fetchPendingTrades = useCallback(async () => {
    try {
      const res = await api.get('/user/pending-trades');
      if (res.data?.success && Array.isArray(res.data?.pending_trades)) {
        const map: Record<string, any> = {};
        res.data.pending_trades.forEach((p: any) => {
          map[String(p.signal_id)] = p;
        });
        setPendingTrades(map);
      }
    } catch (err) {
      console.error('Error fetching pending trades:', err);
    }
  }, []);

  const fetchRecommendations = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const url = showRefresh ? '/portfolio/recommendations?force=true' : '/portfolio/recommendations';
      const res = await api.get(url);
      setRecommendations(res.data?.recommendations || []);
      fetchPendingTrades();
      fetchOpenTrades();
    } catch (err) {
      console.error("Error fetching recommendations:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchPendingTrades, fetchOpenTrades]);

  const handleCloseLiveTrade = async (rec: any, activePos: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const confirmed = window.confirm(`⚠️ Are you sure you want to market close your open position for ${rec.symbol}?`);
    if (!confirmed) return;

    const posId = activePos.id || activePos.trade_id || rec.id;
    setClosingTradeId(String(posId));
    try {
      const res = await api.post('/trades/close', {
        id: posId,
        type: activePos.type || rec.category || 'crypto',
        symbol: activePos.symbol || rec.symbol
      });
      if (res.data?.message) {
        setOpenTrades(prev => prev.filter((p: any) => p.symbol !== rec.symbol && p.symbol !== activePos.symbol));
        alert(`✅ Position for ${rec.symbol} closed successfully!`);
      } else {
        alert(res.data?.error || 'Failed to close position.');
      }
    } catch (err: any) {
      console.error('Error closing trade:', err);
      const errMsg = err.response?.data?.error || err.response?.data?.message || err.message || 'Failed to close position.';
      alert(`❌ ${errMsg}`);
    } finally {
      setClosingTradeId(null);
      fetchRecommendations(true);
      fetchOpenTrades(true);
    }
  };

  const [riskModalData, setRiskModalData] = useState<{ signalId: string; message: string } | null>(null);
  const [acknowledgedRisk, setAcknowledgedRisk] = useState(false);
  const [submittingRiskOverride, setSubmittingRiskOverride] = useState(false);

  const handleOpenLiveTrade = async (rec: any, e: React.MouseEvent, allowRisk = false) => {
    e.stopPropagation();
    
    const isStock = rec.category?.toLowerCase() === 'stock';
    const hasKeys = isStock ? Boolean(user?.has_alpaca_keys) : Boolean(user?.has_exchange_keys);
    
    if (!hasKeys) {
      if (window.confirm(`To execute live ${isStock ? 'stock' : 'crypto'} trades, you need to link your exchange account first. Would you like to go to Settings to set this up?`)) {
        navigate('/settings');
      }
      return;
    }

    const signalId = rec.id && String(rec.id).startsWith('rec_') ? rec.id : `rec_${rec.id}`;
    if (executingSignalId && !allowRisk) return;

    if (rec.category?.toLowerCase() === 'stock' && !isStockMarketOpen()) {
      setQueueModalSignal({ id: signalId, symbol: rec.symbol });
      setSelectedQueueOption('auto_execute');
      return;
    }

    setExecutingSignalId(signalId);
    try {
      const res = await api.post('/user/manual-trade', { 
        signal_id: signalId,
        allow_liquidation_risk: allowRisk
      });
      if (res.data?.success) {
        setOpenTrades(prev => [...prev, { symbol: rec.symbol }]);
        alert(res.data?.message || '✅ Live trade executed successfully!');
        if (riskModalData) setRiskModalData(null);
      } else {
        const errMsg = res.data?.error || res.data?.message || 'Failed to execute trade.';
        if (!allowRisk && (errMsg.includes('Liquidation Risk') || errMsg.includes('Unable to automatically set leverage'))) {
          setRiskModalData({ signalId, message: errMsg });
          setAcknowledgedRisk(false);
        } else {
          alert(`❌ ${errMsg}`);
        }
      }
    } catch (err: any) {
      console.error('Manual trade execution error:', err);
      const errMsg = err.response?.data?.error || err.response?.data?.message || err.message || 'Failed to execute live trade.';
      if (!allowRisk && (errMsg.includes('Liquidation Risk') || errMsg.includes('Unable to automatically set leverage'))) {
        setRiskModalData({ signalId, message: errMsg });
        setAcknowledgedRisk(false);
      } else {
        alert(`❌ ${errMsg}`);
      }
    } finally {
      setExecutingSignalId(null);
      fetchRecommendations(true);
      fetchOpenTrades(true);
    }
  };

  const handleConfirmQueueOrder = async () => {
    if (!queueModalSignal || submittingQueue) return;
    setSubmittingQueue(true);
    try {
      const res = await api.post('/user/queue-trade', {
        signal_id: queueModalSignal.id,
        action_type: selectedQueueOption
      });
      if (res.data?.success) {
        alert(res.data?.message || '✅ Trade queued successfully!');
      } else {
        alert(res.data?.error || 'Failed to queue trade.');
      }
    } catch (err: any) {
      console.error('Queue trade error:', err);
      const errMsg = err.response?.data?.error || err.response?.data?.message || err.message || 'Failed to queue trade.';
      alert(`❌ ${errMsg}`);
    } finally {
      setSubmittingQueue(false);
      setQueueModalSignal(null);
      fetchPendingTrades();
    }
  };

  const handleCancelPendingTrade = async (signalId: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (cancellingSignalId) return;
    setCancellingSignalId(signalId);
    try {
      const res = await api.post('/user/cancel-pending-trade', { signal_id: String(signalId) });
      if (res.data?.success) {
        alert('✅ Pending trade request cancelled.');
      } else {
        alert(res.data?.error || 'Failed to cancel pending trade.');
      }
    } catch (err: any) {
      console.error('Cancel pending trade error:', err);
      alert('❌ Failed to cancel pending trade.');
    } finally {
      setCancellingSignalId(null);
      fetchPendingTrades();
    }
  };

  useEffect(() => {
    if (isPremium) {
      fetchRecommendations();
    } else {
      setLoading(false);
    }
  }, [fetchRecommendations, isPremium]);

  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState(1);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [genNotification, setGenNotification] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  const stepMessages = [
    "📡 Step 1/4: Fetching market snapshots & technical metrics...",
    "🧠 Step 2/4: Evaluating macro regime & candidate universe with Gemini AI...",
    "📐 Step 3/4: Calculating support stop-losses & >= 2:1 R:R targets...",
    "💾 Step 4/4: Finalizing recommendations & updating database records..."
  ];

  const handleGenerateBuys = async () => {
    setGenerating(true);
    setGenStep(1);
    setElapsedSeconds(0);
    setGenNotification(null);

    // Timer interval for elapsed time
    const timerInterval = setInterval(() => {
      setElapsedSeconds(prev => prev + 1);
    }, 1000);

    // Step transitions based on typical timing
    const step2Timeout = setTimeout(() => setGenStep(2), 4000);
    const step3Timeout = setTimeout(() => setGenStep(3), 11000);
    const step4Timeout = setTimeout(() => setGenStep(4), 17000);

    try {
      const res = await api.post('/portfolio/good-buys', {
        risk_profile: riskProfile,
        investment_goal: investmentGoal,
        force_regenerate: true
      });
      await fetchRecommendations(true);

      const returnedRecs = res.data?.recommendations?.stocks || [];
      const cryptoRecs = res.data?.recommendations?.crypto || [];
      const totalFound = returnedRecs.length + cryptoRecs.length;

      setGenNotification({
        type: 'success',
        text: `✅ AI Recommendations updated successfully! Generated ${totalFound} fresh buy ideas for ${riskProfile} / ${investmentGoal}.`
      });
    } catch (err: any) {
      console.error("Failed to generate good buys", err);
      setGenNotification({
        type: 'error',
        text: "❌ Failed to generate AI recommendations. Please check server logs or try again."
      });
    } finally {
      clearInterval(timerInterval);
      clearTimeout(step2Timeout);
      clearTimeout(step3Timeout);
      clearTimeout(step4Timeout);
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
    <div className="space-y-6 relative">
      {/* Status Notification Banner */}
      {genNotification && (
        <div className={`p-4 rounded-2xl border flex items-center justify-between shadow-lg animate-in fade-in slide-in-from-top-2 duration-300 ${
          genNotification.type === 'success'
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}>
          <div className="flex items-center gap-2 text-xs md:text-sm font-bold">
            {genNotification.text}
          </div>
          <button
            onClick={() => setGenNotification(null)}
            className="text-gray-400 hover:text-white text-xs font-black uppercase px-2 py-1"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* AI Generation Progress Modal Overlay */}
      {generating && (
        <div className="fixed inset-0 z-[200] bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-[#141620] border border-cyan-500/30 rounded-3xl p-6 md:p-8 max-w-lg w-full shadow-2xl shadow-cyan-500/10 relative overflow-hidden animate-in zoom-in-95 duration-200">
            {/* Header */}
            <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="bg-cyan-500/20 p-2.5 rounded-xl border border-cyan-500/30 text-cyan-400">
                  <RefreshCw size={20} className="animate-spin" />
                </div>
                <div>
                  <h3 className="text-base md:text-lg font-black text-white uppercase tracking-wider">AI Analyst Re-analyzing Market...</h3>
                  <p className="text-xs text-gray-400">Targeting {riskProfile} risk / {investmentGoal} strategy</p>
                </div>
              </div>
              <div className="text-right">
                <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/20">
                  {elapsedSeconds}s elapsed
                </span>
                <p className="text-[10px] text-gray-500 mt-1 font-semibold">⏱️ ~15-25s avg</p>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-black/40 h-2 rounded-full overflow-hidden mb-6 border border-white/5">
              <div
                className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full transition-all duration-700 ease-out shadow-sm shadow-cyan-500/50"
                style={{
                  width: genStep === 1 ? '25%' : genStep === 2 ? '60%' : genStep === 3 ? '85%' : '98%'
                }}
              />
            </div>

            {/* Current Step Display */}
            <div className="bg-[#0c0d12] p-4 rounded-2xl border border-white/5 mb-6">
              <p className="text-xs font-bold text-cyan-400 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
                {stepMessages[genStep - 1]}
              </p>
            </div>

            {/* Step List Breakdown */}
            <div className="space-y-2.5 text-xs">
              <div className={`flex items-center gap-2.5 transition-colors ${genStep >= 1 ? 'text-gray-200' : 'text-gray-600'}`}>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-black ${genStep > 1 ? 'bg-emerald-500 text-black' : genStep === 1 ? 'bg-cyan-500 text-black animate-pulse' : 'bg-white/10 text-gray-500'}`}>
                  {genStep > 1 ? '✓' : '1'}
                </span>
                <span>Fetch real-time stock & crypto market snapshots</span>
              </div>
              <div className={`flex items-center gap-2.5 transition-colors ${genStep >= 2 ? 'text-gray-200' : 'text-gray-600'}`}>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-black ${genStep > 2 ? 'bg-emerald-500 text-black' : genStep === 2 ? 'bg-cyan-500 text-black animate-pulse' : 'bg-white/10 text-gray-500'}`}>
                  {genStep > 2 ? '✓' : '2'}
                </span>
                <span>Evaluate macro market regime & candidate pools with Gemini AI</span>
              </div>
              <div className={`flex items-center gap-2.5 transition-colors ${genStep >= 3 ? 'text-gray-200' : 'text-gray-600'}`}>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-black ${genStep > 3 ? 'bg-emerald-500 text-black' : genStep === 3 ? 'bg-cyan-500 text-black animate-pulse' : 'bg-white/10 text-gray-500'}`}>
                  {genStep > 3 ? '✓' : '3'}
                </span>
                <span>Calculate technical support stop-losses & &ge; 2:1 R:R targets</span>
              </div>
              <div className={`flex items-center gap-2.5 transition-colors ${genStep >= 4 ? 'text-gray-200' : 'text-gray-600'}`}>
                <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-black ${genStep === 4 ? 'bg-cyan-500 text-black animate-pulse' : 'bg-white/10 text-gray-500'}`}>
                  4
                </span>
                <span>Cache recommendations & update database</span>
              </div>
            </div>
          </div>
        </div>
      )}

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
                  { value: "actual_pnl", label: "Actual PnL %" },
                  { value: "target_pnl", label: "Target PnL %" }
                ]}
              />
              {user?.is_admin && (
                <button
                  onClick={handleGenerateBuys}
                  disabled={generating || refreshing}
                  className="flex items-center justify-center p-2 text-gray-400 hover:text-cyan-400 hover:bg-white/5 rounded-lg transition-colors shrink-0 disabled:opacity-50"
                  title="Re-run AI Recommendation Algorithm (Admin Only)"
                >
                  <RefreshCw size={18} className={generating || refreshing ? 'animate-spin text-cyan-400' : ''} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex bg-[#141620]/40 p-1.5 rounded-2xl border border-white/5 backdrop-blur-sm w-full max-w-sm mb-4">
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

      <div className="flex bg-[#141620]/40 p-1.5 rounded-2xl border border-white/5 backdrop-blur-sm w-full max-w-sm mb-6">
        <button
          onClick={() => setStatusTab('active')}
          className={`flex-1 py-2.5 text-xs font-black uppercase tracking-wider rounded-xl transition-all ${
            statusTab === 'active'
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/20'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Active
        </button>
        <button
          onClick={() => setStatusTab('closed')}
          className={`flex-1 py-2.5 text-xs font-black uppercase tracking-wider rounded-xl transition-all ${
            statusTab === 'closed'
              ? 'bg-rose-500/20 text-rose-400 border border-rose-500/20'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Closed ({closedCount})
        </button>
      </div>

      {/* Stats Panels */}
      {statusTab === 'closed' && (hits > 0 || stops > 0) && (
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
      {statusTab === 'active' && (
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

              const isNearTarget = targetPct > 0 && pnl >= targetPct - 3;
              const isNearStop = stopPct < 0 && pnl <= stopPct + 3;

              let cardClass = "bg-[#181a24]/90 border border-white/10 hover:border-white/20 transition-all rounded-3xl p-5 shadow-xl relative overflow-hidden flex flex-col justify-between";
              if (isNearTarget) {
                cardClass = "bg-[#181a24]/90 border border-emerald-500/50 hover:border-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.25)] transition-all rounded-3xl p-5 relative overflow-hidden flex flex-col justify-between";
              } else if (isNearStop) {
                cardClass = "bg-[#181a24]/90 border border-rose-500/50 hover:border-rose-400 shadow-[0_0_20px_rgba(244,63,94,0.25)] transition-all rounded-3xl p-5 relative overflow-hidden flex flex-col justify-between";
              }

              return (
                <div key={rec.id} className={cardClass}>
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
                      <div className="flex items-center gap-2 text-[11px] font-semibold text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock size={12} />
                          {getDurationString(rec.created_at)}
                        </span>
                        {user?.is_admin && (
                          <button
                            onClick={() => handleDeleteRecommendation(rec.id)}
                            className="p-1 text-gray-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-md transition-colors ml-1"
                            title="Delete recommendation (Admin)"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Prices Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[#0c0d12]/50 p-3 rounded-2xl border border-white/5 mb-4">
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Entry Price</p>
                        <p className="text-xs font-black text-white mt-0.5">${formatPrice(rec.entry_price)}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Current Price</p>
                        <p className="text-xs font-black text-white mt-0.5">${formatPrice(rec.current_price)} <span className="text-[10px] font-semibold text-gray-400">({formatPercent(pnl)})</span></p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Target Price</p>
                        <p className="text-xs font-black text-emerald-400 mt-0.5">${formatPrice(rec.target_price)}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Stop Loss</p>
                        <p className="text-xs font-black text-rose-400 mt-0.5">${formatPrice(rec.stop_loss)} <span className="text-[10px] font-semibold text-rose-500/70">({formatPercent(stopPct)})</span></p>
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

                  {/* Create Live Trade / Close Trade / Pending Order Button */}
                  {(() => {
                    const recSignalId = `rec_${rec.id}`;
                    const pendingOrder = pendingTrades[recSignalId];
                    const activePos = openTrades.find((t: any) => {
                      const recBase = String(rec.symbol || '').toUpperCase().replace('/USDT', '').replace('-USDT', '').replace('/USD', '').replace('-USD', '').replace('-', '');
                      const posBase = String(t.symbol || '').toUpperCase().replace('/USDT', '').replace('-USDT', '').replace('/USD', '').replace('-USD', '').replace('-', '').split(':')[0];
                      return recBase === posBase;
                    });

                    if (activePos) {
                      const posId = String(activePos.id || activePos.trade_id || rec.id);
                      return (
                        <button
                          onClick={(e) => handleCloseLiveTrade(rec, activePos, e)}
                          disabled={closingTradeId === posId}
                          className="mt-4 w-full py-2.5 px-4 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-400 font-bold rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(244,63,94,0.2)] disabled:opacity-50 text-xs uppercase tracking-wider"
                        >
                          {closingTradeId === posId ? (
                            <>
                              <RefreshCw size={16} className="animate-spin" /> Closing Position...
                            </>
                          ) : (
                            <>
                              🚨 Close at Market Price
                            </>
                          )}
                        </button>
                      );
                    } else if (pendingOrder) {
                      return (
                        <div className="mt-4 flex items-center gap-2">
                          <button
                            disabled
                            className="flex-1 py-2.5 px-3 bg-amber-500/10 border border-amber-500/30 text-amber-400 font-bold rounded-xl text-xs flex items-center justify-center gap-1.5"
                          >
                            <Clock size={14} className="animate-spin text-amber-400 shrink-0" />
                            <span className="truncate">
                              {pendingOrder.action_type === 'auto_execute'
                                ? '⚡ Pending Auto-Exec at Market Open'
                                : '📧 Pending Email Reminder at Market Open'}
                            </span>
                          </button>
                          <button
                            onClick={(e) => handleCancelPendingTrade(recSignalId, e)}
                            disabled={cancellingSignalId === recSignalId}
                            className="py-2.5 px-4 bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-400 font-bold rounded-xl transition-all text-xs flex items-center justify-center gap-1.5 shrink-0 disabled:opacity-50"
                            title="Cancel pending order"
                          >
                            {cancellingSignalId === recSignalId ? (
                              <RefreshCw size={14} className="animate-spin" />
                            ) : (
                              'Cancel'
                            )}
                          </button>
                        </div>
                      );
                    } else {
                      return (
                        <button
                          onClick={(e) => handleOpenLiveTrade(rec, e)}
                          disabled={executingSignalId === recSignalId}
                          className="mt-4 w-full py-2.5 px-4 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 font-bold rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)] disabled:opacity-50 text-xs uppercase tracking-wider"
                        >
                          {executingSignalId === recSignalId ? (
                            <>
                              <RefreshCw size={16} className="animate-spin" /> Opening Live Trade...
                            </>
                          ) : (
                            <>
                              ▶️ Open Live Trade
                            </>
                          )}
                        </button>
                      );
                    }
                  })()}
                </div>
              );
            })}
          </div>
        )}
      </div>
      )}

      {/* Historical Recommendations Section */}
      {statusTab === 'closed' && (
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
              <table className="w-full text-left text-xs md:text-sm text-gray-300">
                <thead className="bg-[#141620] text-gray-400 uppercase text-[10px] tracking-wider font-bold border-b border-white/10">
                  <tr>
                    <th className="px-6 py-4">Asset</th>
                    <th className="px-6 py-4">Category</th>
                    <th className="px-6 py-4">Entry</th>
                    <th className="px-6 py-4">Final Price</th>
                    <th className="px-6 py-4">Target</th>
                    <th className="px-6 py-4">Stop Loss</th>
                    <th className="px-6 py-4">Realized PnL</th>
                    <th className="px-6 py-4">Duration</th>
                    <th className="px-6 py-4">Outcome</th>
                    {user?.is_admin && <th className="px-6 py-4 text-right">Actions</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-medium">
                  {pastRecs.map((rec) => {
                    const pnl = ((rec.current_price - rec.entry_price) / rec.entry_price) * 100;
                    const isProfit = pnl >= 0;
                    const isTarget = rec.current_price >= rec.target_price;

                    return (
                      <tr key={rec.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="px-6 py-4 font-black text-cyan-400 uppercase">
                          <a
                            href={getYahooFinanceLink(rec.symbol, rec.category)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="hover:underline"
                          >
                            {rec.symbol}
                          </a>
                        </td>
                        <td className="px-6 py-4 uppercase text-[10px] text-gray-400 font-bold">{rec.category}</td>
                        <td className="px-6 py-4 font-semibold">${formatPrice(rec.entry_price)}</td>
                        <td className="px-6 py-4 font-semibold">${formatPrice(rec.current_price)}</td>
                        <td className="px-6 py-4 text-emerald-500/80 font-semibold">${formatPrice(rec.target_price)}</td>
                        <td className="px-6 py-4 text-rose-500/80 font-semibold">${formatPrice(rec.stop_loss)}</td>
                        <td className={`px-6 py-4 font-black ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {formatPercent(pnl)}
                        </td>
                        <td className="px-6 py-4 text-gray-400">{getDurationString(rec.created_at, rec.closed_at)}</td>
                        <td className="px-6 py-4">
                          <span className={`inline-block px-2.5 py-0.5 rounded-full font-bold text-[10px] uppercase border ${isTarget ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border-rose-500/20'}`}>
                            {isTarget ? 'Target Hit' : 'Stopped Out'}
                          </span>
                        </td>
                        {user?.is_admin && (
                          <td className="px-6 py-4 text-right">
                            <button
                              onClick={() => handleDeleteRecommendation(rec.id)}
                              className="p-1.5 text-gray-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors inline-flex items-center gap-1"
                              title="Delete recommendation (Admin Only)"
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
      )}

      {queueModalSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md">
          <div className="bg-[#1b1f2c] border border-cyan-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 relative">
            <div className="flex items-center gap-3 text-cyan-400 font-bold text-lg border-b border-white/10 pb-3">
              <Clock className="size-6 text-cyan-400 shrink-0" />
              <span>STOCK MARKET CLOSED</span>
            </div>
            
            <p className="text-gray-300 text-sm leading-relaxed">
              The US Equities Market is currently closed. How would you like to handle your live trade for <strong className="text-white">{queueModalSignal.symbol}</strong>?
            </p>

            <div className="space-y-3 pt-1">
              <label
                onClick={() => setSelectedQueueOption('auto_execute')}
                className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                  selectedQueueOption === 'auto_execute'
                    ? 'bg-cyan-500/10 border-cyan-500/50 text-white'
                    : 'bg-white/5 border-white/10 text-gray-400 hover:bg-white/10'
                }`}
              >
                <input
                  type="radio"
                  name="queueOption"
                  checked={selectedQueueOption === 'auto_execute'}
                  onChange={() => setSelectedQueueOption('auto_execute')}
                  className="mt-1 accent-cyan-400"
                />
                <div>
                  <div className="font-bold text-sm text-cyan-300 flex items-center gap-1.5">
                    ⚡ Auto-Execute at Market Open
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    Order will automatically be placed on Alpaca at 9:30 AM EST (provided price hasn't opened &gt;1% higher).
                  </div>
                </div>
              </label>

              <label
                onClick={() => setSelectedQueueOption('email_reminder')}
                className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                  selectedQueueOption === 'email_reminder'
                    ? 'bg-cyan-500/10 border-cyan-500/50 text-white'
                    : 'bg-white/5 border-white/10 text-gray-400 hover:bg-white/10'
                }`}
              >
                <input
                  type="radio"
                  name="queueOption"
                  checked={selectedQueueOption === 'email_reminder'}
                  onChange={() => setSelectedQueueOption('email_reminder')}
                  className="mt-1 accent-cyan-400"
                />
                <div>
                  <div className="font-bold text-sm text-cyan-300 flex items-center gap-1.5">
                    📧 Email Reminder at Market Open
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    Receive a Resend email at 9:30 AM EST with signal progress and a 1-click execution button.
                  </div>
                </div>
              </label>
            </div>

            <div className="flex items-center gap-3 pt-3">
              <button
                onClick={() => setQueueModalSignal(null)}
                disabled={submittingQueue}
                className="flex-1 py-2.5 px-4 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 font-bold rounded-xl text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmQueueOrder}
                disabled={submittingQueue}
                className="flex-1 py-2.5 px-4 bg-gradient-to-r from-cyan-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-black font-bold rounded-xl text-sm transition-all shadow-[0_0_15px_rgba(60,215,255,0.3)] flex items-center justify-center gap-2"
              >
                {submittingQueue ? 'Saving...' : 'Confirm Choice'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Liquidation Risk Warning Modal */}
      {riskModalData && (
        <div className="fixed inset-0 z-[200] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#181920] border border-amber-500/40 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-amber-400 font-bold text-lg">
              <AlertTriangle size={24} /> Liquidation Risk Warning
            </div>
            <p className="text-gray-300 text-sm leading-relaxed">
              {riskModalData.message}
            </p>
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3.5 flex items-start gap-3">
              <input
                type="checkbox"
                id="ack_risk"
                checked={acknowledgedRisk}
                onChange={(e) => setAcknowledgedRisk(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-amber-500/40 text-amber-500 focus:ring-amber-500 bg-black/40"
              />
              <label htmlFor="ack_risk" className="text-xs text-amber-200/90 leading-tight cursor-pointer font-medium">
                I acknowledge that this trade carries liquidation risk before hitting Stop Loss, and I want to proceed at existing leverage.
              </label>
            </div>
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={() => setRiskModalData(null)}
                className="flex-1 py-2.5 bg-white/5 hover:bg-white/10 text-gray-300 font-semibold rounded-xl text-xs transition-colors"
              >
                Cancel Trade
              </button>
              <button
                type="button"
                disabled={!acknowledgedRisk || submittingRiskOverride}
                onClick={async (e) => {
                  setSubmittingRiskOverride(true);
                  const recObj = recommendations.find(r => `rec_${r.id}` === riskModalData.signalId);
                  await handleOpenLiveTrade(recObj || { id: riskModalData.signalId.replace('rec_', '') }, e, true);
                  setSubmittingRiskOverride(false);
                }}
                className="flex-1 py-2.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-400 font-bold rounded-xl text-xs transition-all disabled:opacity-40"
              >
                {submittingRiskOverride ? 'Processing...' : 'Proceed Anyway'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecommendationsPage;
