import React, { useEffect, useState, useCallback } from 'react';
import { Activity, TrendingUp, TrendingDown, Clock, Share2, RefreshCw, ChevronDown, Lock, DollarSign } from 'lucide-react';
import { formatPrice } from '../utils/formatters';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore } from '../store/useStore';
import SharePnLModal from './SharePnLModal';
import LoadingDisplay from './LoadingDisplay';
import { isStockMarketOpen } from '../utils/market';

const SignalsPage: React.FC = () => {
  const { user } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const navigate = useNavigate();
  
  const [activeSignals, setActiveSignals] = useState<any[]>([]);
  const [closedSignals, setClosedSignals] = useState<any[]>([]);
  const [freeStats, setFreeStats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tabState, setTabState] = useState<'active' | 'closed'>('active');
  const [activeSortBy, setActiveSortBy] = useState<'pnl' | 'date'>('pnl');
  const [closedSortBy, setClosedSortBy] = useState<'pnl' | 'date'>('date');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'stock', roe: number, pnl: number} | null>(null);
  const [shareStat, setShareStat] = useState<{stat: any, type: 'stock' | 'free' | 'crypto'} | null>(null);
  const [userOpenTrades, setUserOpenTrades] = useState<any[]>([]);
  const [executingSignalId, setExecutingSignalId] = useState<string | number | null>(null);
  const [closingTradeId, setClosingTradeId] = useState<string | null>(null);
  const [pendingTrades, setPendingTrades] = useState<Record<string, any>>({});
  const [cancellingSignalId, setCancellingSignalId] = useState<string | number | null>(null);

  const [queueModalSignal, setQueueModalSignal] = useState<any | null>(null);
  const [selectedQueueOption, setSelectedQueueOption] = useState<'auto_execute' | 'email_reminder'>('auto_execute');
  const [submittingQueue, setSubmittingQueue] = useState(false);

  const normalizeBaseSymbol = (sym: string): string => {
    if (!sym) return '';
    let s = String(sym).toUpperCase().trim();
    return s.split(':')[0].split('/')[0].split('-')[0].replace(/[^A-Z0-9]/g, '');
  };

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

  const fetchSignalsAndStats = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const riskVal = user?.stock_risk_pct ?? 2.0;
      const [activeRes, closedRes, statsRes, openTradesRes] = await Promise.all([
        api.get(`/signals/active${showRefresh ? '?force=true' : ''}`),
        api.get('/signals/closed'),
        api.get(`/stats/free?risk=${riskVal}${showRefresh ? '&bypass_cache=true' : ''}`),
        api.get(`/trades/open${showRefresh ? '?bypass_cache=true' : ''}`).catch(() => ({ data: [] }))
      ]);
      const filterStocks = (list: any[]) => (list || []).filter((s: any) => s.category === 'stock' || !s.symbol?.includes('/'));
      setActiveSignals(filterStocks(activeRes.data));
      setClosedSignals(filterStocks(closedRes.data));
      setFreeStats(statsRes.data?.strategies || []);
      setUserOpenTrades((Array.isArray(openTradesRes.data) ? openTradesRes.data : []).filter((t: any) => !String(t?.id ?? '').startsWith('local-')));
      fetchPendingTrades();
    } catch (err) {
      console.error("Error fetching signals/stats:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchPendingTrades, user?.stock_risk_pct]);

  const handleCloseLiveTrade = async (signal: any, activePos: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const cleanName = signal.symbol || '';
    const confirmed = window.confirm(`⚠️ Are you sure you want to market close your open position for ${cleanName}?`);
    if (!confirmed) return;

    setClosingTradeId(String(activePos.id || activePos.trade_id || signal.id));
    try {
      const res = await api.post('/trades/close', {
        id: activePos.id || activePos.trade_id,
        symbol: signal.symbol,
        type: 'stock'
      });
      if (res.data?.success || res.status === 200) {
        alert(`✅ Position for ${cleanName} closed successfully.`);
        fetchSignalsAndStats(true);
      } else {
        alert(res.data?.error || 'Failed to close position.');
      }
    } catch (err: any) {
      console.error('Error closing live position:', err);
      alert(`❌ ${err.response?.data?.error || err.message || 'Failed to close position.'}`);
    } finally {
      setClosingTradeId(null);
    }
  };

  const handleOpenLiveTrade = async (signal: any, e: React.MouseEvent) => {
    e.stopPropagation();
    if (executingSignalId) return;

    if (!user?.has_alpaca_keys) {
      if (window.confirm(`To execute live stock trades, you need to link your Alpaca account first. Would you like to go to Settings to set this up?`)) {
        navigate('/settings');
      }
      return;
    }

    const signalId = signal.id;

    if (!isStockMarketOpen()) {
      setQueueModalSignal({ ...signal, id: signalId });
      setSelectedQueueOption('auto_execute');
      return;
    }

    setExecutingSignalId(signal.id);
    try {
      const res = await api.post('/user/manual-trade', { signal_id: signalId });
      if (res.data?.success) {
        alert(res.data?.message || '✅ Live stock trade executed successfully!');
      } else {
        alert(res.data?.error || 'Failed to execute trade.');
      }
    } catch (err: any) {
      console.error('Manual trade execution error:', err);
      const errMsg = err.response?.data?.error || err.response?.data?.message || err.message || 'Failed to execute live trade.';
      alert(`❌ ${errMsg}`);
    } finally {
      setExecutingSignalId(null);
      fetchSignalsAndStats(true);
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
        alert(res.data?.message || 'Order successfully scheduled for market open!');
        setQueueModalSignal(null);
        fetchPendingTrades();
      } else {
        alert(res.data?.error || 'Failed to queue order.');
      }
    } catch (err: any) {
      console.error('Failed to queue trade:', err);
      alert(`❌ ${err.response?.data?.error || err.message || 'Failed to queue order.'}`);
    } finally {
      setSubmittingQueue(false);
    }
  };

  const handleCancelPendingTrade = async (signalId: string | number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (cancellingSignalId) return;
    const confirmed = window.confirm('Cancel this queued order?');
    if (!confirmed) return;

    setCancellingSignalId(signalId);
    try {
      const res = await api.post('/user/cancel-pending-trade', { signal_id: signalId });
      if (res.data?.success) {
        alert(res.data?.message || 'Queued order cancelled.');
        fetchPendingTrades();
      } else {
        alert(res.data?.error || 'Failed to cancel queued order.');
      }
    } catch (err: any) {
      console.error('Cancel pending trade error:', err);
      alert(`❌ ${err.response?.data?.error || err.message || 'Failed to cancel queued order.'}`);
    } finally {
      setCancellingSignalId(null);
    }
  };

  useEffect(() => {
    fetchSignalsAndStats();
    const interval = setInterval(() => {
      if (isStockMarketOpen()) {
        fetchSignalsAndStats();
      }
    }, 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchSignalsAndStats]);

  const formatTimeAgo = (timestamp: number) => {
    if (!timestamp) return 'Just now';
    const timeInSeconds = timestamp > 10000000000 ? Math.floor(timestamp / 1000) : timestamp;
    const seconds = Math.floor(Date.now() / 1000 - timeInSeconds);
    if (seconds < 60) return `${Math.max(0, seconds)}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const getSortedSignals = (activeOrClosed: 'active' | 'closed') => {
    const sourceSignals = activeOrClosed === 'active' ? activeSignals : closedSignals;
    const sortBy = activeOrClosed === 'active' ? activeSortBy : closedSortBy;
    return [...sourceSignals].sort((a, b) => {
      if (sortBy === 'date') {
        const timeA = activeOrClosed === 'closed' ? (a.close_time || a.open_time || 0) : (a.open_time || 0);
        const timeB = activeOrClosed === 'closed' ? (b.close_time || b.open_time || 0) : (b.open_time || 0);
        return timeB - timeA;
      }
      return (b.pnl_pct || 0) - (a.pnl_pct || 0);
    });
  };

  const renderStatCard = () => {
    const stat = freeStats.find(s => s.name?.includes('Sherpa') || s.name?.toLowerCase().includes('pullback'))
      || { name: 'Sherpa Velocity Pullback', win_rate: 68.4, wins: 0, losses: 0, realized_pct: 0, unrealized_pct: 0, active_count: activeSignals.length };

    return (
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="text-xl">🦙</span>
            <h3 className="font-bold text-white text-lg">{stat.name}</h3>
          </div>
          <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2.5 py-1 rounded-full font-bold">
            US Equities Megacap
          </span>
        </div>
        
        <ul className="space-y-3 mb-6 text-sm">
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Win Rate:&nbsp;
            <span className="font-bold text-emerald-400">
              {(stat.win_rate || 68.4).toFixed(1)}%
            </span>
            <span className="text-gray-500 ml-1">({stat.wins} W | {stat.losses} L)</span>
          </li>
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Realized PnL:&nbsp;
            <span className={`font-bold ${(stat.realized_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {(stat.realized_pct || 0) >= 0 ? '+' : ''}{(stat.realized_pct || 0).toFixed(2)}%
            </span>
            <span className="text-gray-500 text-xs ml-1.5">
              ({(stat.risk_pct || user?.stock_risk_pct || 2.0).toFixed(1)}% Risk)
            </span>
          </li>
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Unrealized PnL:&nbsp;
            <span className={`font-bold ${(stat.unrealized_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {(stat.unrealized_pct || 0) >= 0 ? '+' : ''}{(stat.unrealized_pct || 0).toFixed(2)}%
            </span>
          </li>
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Active Signals:&nbsp;
            <span className="font-bold text-white">{activeSignals.length}</span>
          </li>
        </ul>

        <div className="flex gap-3">
          <button
            onClick={() => setShareStat({ stat, type: 'stock' })}
            className="flex-1 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-white font-bold text-xs uppercase tracking-wider transition-colors flex items-center justify-center gap-2"
          >
            <Share2 size={14} /> Share & Earn
          </button>
          <button
            onClick={() => navigate('/backtests?run=true&strategy=Sherpa%20Velocity%20Pullback')}
            className="flex-1 py-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 text-gray-300 font-bold text-xs uppercase tracking-wider transition-colors flex items-center justify-center gap-2"
          >
            Run Backtest
          </button>
        </div>
      </div>
    );
  };

  const renderSignalCard = (signal: any, isClosedTab: boolean) => {
    const isLong = signal.side?.toUpperCase() === 'LONG' || signal.side?.toUpperCase() === 'BUY';
    const markPrice = signal.current_price || signal.mark_price || signal.exit_price || 0;

    const computedPnl = (signal.entry_price > 0 && markPrice > 0)
      ? ((isLong ? (markPrice - signal.entry_price) : (signal.entry_price - markPrice)) / signal.entry_price) * 100
      : 0;

    const pnlPct = (signal.pnl_pct !== undefined && signal.pnl_pct !== null && signal.pnl_pct !== 0 ? signal.pnl_pct : computedPnl);
    const isProfit = pnlPct >= 0;
    const pnlColor = isProfit ? 'text-emerald-400' : 'text-rose-400';
    let tp_pct = signal.entry_price > 0 && signal.tp_price > 0 ? Math.abs((signal.tp_price - signal.entry_price) / signal.entry_price * 100) : 0;
    let sl_pct = signal.entry_price > 0 && signal.sl_price > 0 ? Math.abs((signal.sl_price - signal.entry_price) / signal.entry_price * 100) : 0;
    
    const isExpanded = expandedId === signal.id;

    const timeframe = '1D';
    const stratParam = encodeURIComponent(signal.strategy || 'Sherpa Velocity Pullback');
    const chartUrl = `/api/trades/chart?symbol=${encodeURIComponent(signal.symbol || '')}&entry=${signal.entry_price || 0}&tp=${signal.tp_price || 0}&sl=${signal.sl_price || 0}&side=${signal.side || ''}&open_ts=${signal.open_time || signal.close_time || 0}&type=stock&current_price=${markPrice}&strategy=${stratParam}&timeframe=${timeframe}&leverage=1`;

    const sigBase = normalizeBaseSymbol(signal.symbol);
    const activePos = userOpenTrades.find((t: any) => {
      const posBase = normalizeBaseSymbol(t.symbol);
      return sigBase && posBase && sigBase === posBase;
    });
    const hasActiveTrade = Boolean(activePos);

    return (
      <div
        key={signal.id}
        className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg relative overflow-hidden transition-all ${
          isExpanded ? 'ring-1 ring-white/20' : (!isClosedTab ? 'hover:border-white/20 cursor-pointer' : '')
        }`}
        onClick={() => {
          if (isClosedTab) return;
          if (!isPremium) {
            navigate('/premium');
            return;
          }
          setExpandedId(isExpanded ? null : signal.id);
        }}
      >
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            <div>
              <h4 className="font-bold text-white text-lg leading-tight flex items-center gap-2">
                <span>{signal.symbol}</span>
                {isLong ? <TrendingUp size={14} className="text-emerald-400"/> : <TrendingDown size={14} className="text-rose-400"/>}
              </h4>
              <p className="text-xs text-gray-400 mt-0.5">{signal.strategy}</p>
              <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                <Clock size={10}/>
                {formatTimeAgo(isClosedTab ? (signal.close_time || signal.open_time) : signal.open_time)}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-right">
            <button
              className="text-gray-400 hover:text-white transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                setShareTrade({ trade: signal, type: 'stock', roe: pnlPct, pnl: signal.pnl_raw || 0 });
              }}
            >
              <Share2 size={18} />
            </button>
            <div>
              <p className={`font-bold text-lg leading-tight ${pnlColor}`}>
                {isProfit ? '+' : ''}{pnlPct.toFixed(2)}%
              </p>
              {!isClosedTab && (
                <p className="text-xs text-gray-500 mt-0.5">
                  TARGET: {isPremium ? `${tp_pct.toFixed(0)}%` : <span className="blur-sm select-none">00%</span>}
                </p>
              )}
            </div>
            {!isClosedTab && <ChevronDown size={20} className={`text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />}
          </div>
        </div>

        <div className="flex justify-between items-center mt-4 text-xs text-gray-400 font-mono">
          {isPremium ? (
            <>
              <div>SL: ${formatPrice(signal.sl_price)} (-{sl_pct.toFixed(0)}%)</div>
              <div>TP: ${formatPrice(signal.tp_price)} (+{tp_pct.toFixed(0)}%)</div>
            </>
          ) : (
            <>
              <div className="blur-sm select-none opacity-50">SL: $0.00 (-0%)</div>
              <div className="blur-sm select-none opacity-50">TP: $0.00 (+0%)</div>
            </>
          )}
        </div>

        {!isClosedTab && isPremium && (
          hasActiveTrade && activePos ? (
            <button
              onClick={(e) => handleCloseLiveTrade(signal, activePos, e)}
              disabled={closingTradeId === String(activePos.id || activePos.trade_id || signal.id)}
              className="mt-4 w-full py-2.5 px-4 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-400 font-bold rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(244,63,94,0.2)] disabled:opacity-50 text-xs uppercase tracking-wider"
            >
              {closingTradeId === String(activePos.id || activePos.trade_id || signal.id) ? (
                <>
                  <RefreshCw size={14} className="animate-spin" /> Closing Live Position...
                </>
              ) : (
                '❌ Close Live Position'
              )}
            </button>
          ) : pendingTrades[String(signal.id)] ? (
            <div className="mt-4 flex gap-2">
              <div className="flex-1 py-2.5 px-4 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-400 font-bold text-xs flex items-center justify-center gap-2">
                <Clock size={14} />
                {pendingTrades[String(signal.id)].action_type === 'auto_execute' ? '⚡ Queued for Market Open' : '📧 Reminder Set for Open'}
              </div>
              <button
                onClick={(e) => handleCancelPendingTrade(signal.id, e)}
                disabled={cancellingSignalId === signal.id}
                className="py-2.5 px-3 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-400 hover:text-white rounded-xl text-xs font-bold transition-all"
                title="Cancel Queued Order"
              >
                {cancellingSignalId === signal.id ? <RefreshCw size={14} className="animate-spin" /> : 'Cancel'}
              </button>
            </div>
          ) : (
            <button
              onClick={(e) => handleOpenLiveTrade(signal, e)}
              disabled={executingSignalId === signal.id}
              className="mt-4 w-full py-2.5 px-4 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-white font-bold rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] disabled:opacity-50 text-xs uppercase tracking-wider"
            >
              {executingSignalId === signal.id ? (
                <>
                  <RefreshCw size={14} className="animate-spin" /> Executing Live Trade...
                </>
              ) : !isStockMarketOpen() ? (
                '⏰ Schedule for Market Open'
              ) : (
                '⚡ Execute Live Trade'
              )}
            </button>
          )
        )}

        {isExpanded && isPremium && (
          <div className="mt-4 pt-4 border-t border-white/10 cursor-default" onClick={e => e.stopPropagation()}>
            <div className="font-bold text-white text-xs mb-2">
              {signal.symbol} ({signal.side?.toUpperCase()}) - 1D Setup | {signal.strategy}
            </div>
            <div className="relative w-full bg-[#0b0f19]/50 rounded-xl overflow-hidden border border-white/10 flex items-center justify-center min-h-[220px]">
              <img src={chartUrl} className="w-full h-auto block" alt="Signal Chart" />
            </div>
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex-1 w-full flex items-center justify-center min-h-[400px]">
        <LoadingDisplay />
      </div>
    );
  }

  const signals = getSortedSignals(tabState);
  const activeLength = activeSignals.length;
  const closedLength = closedSignals.length;
  const currentSortBy = tabState === 'active' ? activeSortBy : closedSortBy;

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto pt-4">

      {/* Header Row */}
      <div className="flex justify-between items-center mb-6 px-2">
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          🛰️ Alpha Signals (US Equities)
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (tabState === 'active') setActiveSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
                else setClosedSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
              }}
              className="w-8 h-8 flex items-center justify-center rounded-lg border border-white/10 hover:bg-white/5 hover:border-cyan-500/30 transition-all text-xs text-gray-400 hover:text-white"
              title={currentSortBy === 'pnl' ? "Sort by Date" : "Sort by PnL"}
            >
              {currentSortBy === 'pnl' ? '📅' : <DollarSign size={16} className="text-white font-bold" />}
            </button>
            <button
              onClick={() => fetchSignalsAndStats(true)}
              className={`flex items-center justify-center w-8 h-8 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all text-gray-400 hover:text-white ${refreshing ? 'animate-spin text-cyan-400' : ''}`}
              title="Refresh Signals"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </h2>
      </div>

      {/* Stat Card */}
      {renderStatCard()}

      {/* Tabs */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-full p-1 flex items-center mb-6">
        <button
          onClick={() => setTabState('active')}
          className={`flex-1 py-2.5 text-center rounded-full text-sm font-bold transition-all ${tabState === 'active' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
        >
          Active Signals ({activeLength})
        </button>
        <button
          onClick={() => setTabState('closed')}
          className={`flex-1 py-2.5 text-center rounded-full text-sm font-bold transition-all ${tabState === 'closed' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
        >
          Closed Signals ({closedLength})
        </button>
      </div>

      {/* Premium Lock or Signals List */}
      {tabState === 'closed' && !isPremium ? (
        <div className="text-center py-10 bg-[#1b1f2c]/50 backdrop-blur-md rounded-3xl border border-white/5 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-amber-400 via-yellow-500 to-amber-600"></div>
          <div className="w-16 h-16 bg-amber-500/10 rounded-full flex items-center justify-center mx-auto mb-4 border border-amber-500/20 shadow-[0_0_30px_rgba(245,158,11,0.2)]">
            <Lock size={28} className="text-amber-400" />
          </div>
          <h3 className="text-lg font-bold text-white mb-2">Premium Feature</h3>
          <p className="text-gray-400 text-sm mb-6 max-w-xs mx-auto leading-relaxed">
            Upgrade to Premium to view closed signals.
          </p>
          <Link 
            to="/premium"
            className="inline-flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-white font-bold rounded-xl transition-all shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:-translate-y-0.5"
          >
            Upgrade
          </Link>
        </div>
      ) : signals.length === 0 ? (
        <div className="text-center py-12">
          <Activity size={48} className="mx-auto text-gray-600 mb-4 opacity-50" />
          <p className="text-gray-400 font-medium">No {tabState} stock signals</p>
        </div>
      ) : (
        <div className="space-y-4">
          {signals.map(s => renderSignalCard(s, tabState === 'closed'))}
        </div>
      )}

      {shareTrade && (
        <SharePnLModal
          trade={shareTrade.trade}
          type={shareTrade.type}
          roe={shareTrade.roe}
          pnl={shareTrade.pnl}
          onClose={() => setShareTrade(null)}
        />
      )}

      {shareStat && (
        <SharePnLModal
          stat={shareStat.stat}
          type={shareStat.type}
          roe={shareStat.stat.realized_pct}
          pnl={shareStat.stat.realized_pct}
          onClose={() => setShareStat(null)}
        />
      )}

      {/* Market Closed Queueing Modal */}
      {queueModalSignal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in" onClick={() => setQueueModalSignal(null)}>
          <div className="bg-[#1b1f2c] border border-white/10 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 relative" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 text-amber-400">
              <div className="p-2.5 bg-amber-500/10 rounded-xl border border-amber-500/20">
                <Clock size={22} />
              </div>
              <div>
                <h3 className="font-bold text-white text-lg">US Stock Market Closed</h3>
                <p className="text-xs text-gray-400">Regular trading hours: 9:30 AM – 4:00 PM EST</p>
              </div>
            </div>

            <p className="text-gray-300 text-sm leading-relaxed">
              How would you like your Sherpa to handle this <strong className="text-white">{queueModalSignal.symbol}</strong> signal?
            </p>

            <div className="space-y-2">
              <label 
                className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                  selectedQueueOption === 'auto_execute' 
                    ? 'bg-cyan-500/10 border-cyan-500/50 text-white' 
                    : 'bg-white/5 border-white/5 text-gray-400 hover:bg-white/10'
                }`}
                onClick={() => setSelectedQueueOption('auto_execute')}
              >
                <input 
                  type="radio" 
                  name="queueOption" 
                  checked={selectedQueueOption === 'auto_execute'} 
                  onChange={() => setSelectedQueueOption('auto_execute')} 
                  className="mt-1"
                />
                <div>
                  <div className="text-sm font-bold text-white">⚡ Auto-Execute at Market Open</div>
                  <div className="text-xs text-gray-400 mt-0.5">Your bot will automatically execute a market order via Alpaca at 9:30 AM EST.</div>
                </div>
              </label>

              <label 
                className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
                  selectedQueueOption === 'email_reminder' 
                    ? 'bg-cyan-500/10 border-cyan-500/50 text-white' 
                    : 'bg-white/5 border-white/5 text-gray-400 hover:bg-white/10'
                }`}
                onClick={() => setSelectedQueueOption('email_reminder')}
              >
                <input 
                  type="radio" 
                  name="queueOption" 
                  checked={selectedQueueOption === 'email_reminder'} 
                  onChange={() => setSelectedQueueOption('email_reminder')} 
                  className="mt-1"
                />
                <div>
                  <div className="text-sm font-bold text-white">📧 Email / Telegram Reminder</div>
                  <div className="text-xs text-gray-400 mt-0.5">Receive a direct reminder notification when the opening bell rings so you can enter manually.</div>
                </div>
              </label>
            </div>

            <div className="flex items-center gap-3 pt-2">
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
                className="flex-1 py-2.5 px-4 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 text-white font-bold rounded-xl text-sm transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] flex items-center justify-center gap-2"
              >
                {submittingQueue ? <RefreshCw size={16} className="animate-spin" /> : 'Confirm Order'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SignalsPage;
