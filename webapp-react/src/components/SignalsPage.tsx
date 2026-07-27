import React, { useEffect, useState, useCallback } from 'react';
import { Activity, TrendingUp, TrendingDown, Clock, Share2, RefreshCw, ChevronDown, Lock, DollarSign, Beaker } from 'lucide-react';
import { formatPrice } from '../utils/formatters';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore, useDashboardStore } from '../store/useStore';
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
  const [cryptoTab, setCryptoTab] = useState<'active' | 'closed'>('active');
  const [stockTab, setStockTab] = useState<'active' | 'closed'>('active');
  const [activeSortBy, setActiveSortBy] = useState<'pnl' | 'date'>('pnl');
  const [closedSortBy, setClosedSortBy] = useState<'pnl' | 'date'>('date');
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'crypto'|'stock', roe: number, pnl: number} | null>(null);
  const [shareStat, setShareStat] = useState<{stat: any, type: string} | null>(null);
  const [userOpenTrades, setUserOpenTrades] = useState<any[]>([]);
  const [executingSignalId, setExecutingSignalId] = useState<string | number | null>(null);
  const [pendingTrades, setPendingTrades] = useState<Record<string, any>>({});
  const [cancellingSignalId, setCancellingSignalId] = useState<string | number | null>(null);

  const [queueModalSignal, setQueueModalSignal] = useState<any | null>(null);
  const [selectedQueueOption, setSelectedQueueOption] = useState<'auto_execute' | 'email_reminder'>('auto_execute');
  const [submittingQueue, setSubmittingQueue] = useState(false);

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
      const [activeRes, closedRes, statsRes, openTradesRes] = await Promise.all([
        api.get(`/signals/active${showRefresh ? '?force=true' : ''}`),
        api.get('/signals/closed'),
        api.get(`/stats/free${showRefresh ? '?bypass_cache=true' : ''}`),
        api.get(`/trades/open`).catch(() => ({ data: [] }))
      ]);
      setActiveSignals(activeRes.data || []);
      setClosedSignals(closedRes.data || []);
      setFreeStats(statsRes.data?.strategies || []);
      setUserOpenTrades((openTradesRes.data || []).filter((t: any) => !t.id?.startsWith('local-')));
      fetchPendingTrades();
    } catch (err) {
      console.error("Error fetching signals/stats:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [fetchPendingTrades]);

  const handleOpenLiveTrade = async (signal: any, e: React.MouseEvent) => {
    e.stopPropagation();
    if (executingSignalId) return;

    if (!isCryptoSymbol(signal.symbol) && !isStockMarketOpen()) {
      setQueueModalSignal(signal);
      setSelectedQueueOption('auto_execute');
      return;
    }

    setExecutingSignalId(signal.id);
    try {
      const res = await api.post('/user/manual-trade', { signal_id: signal.id });
      if (res.data?.success) {
        alert(res.data?.message || '✅ Live trade executed successfully!');
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
    fetchSignalsAndStats();
    const interval = setInterval(() => fetchSignalsAndStats(), 60000);
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

  const formatPercent = (val: number) => {
    return `${(val || 0) > 0 ? '+' : ''}${(val || 0).toFixed(2)}%`;
  };

  const isCryptoSymbol = (symbol: string) => symbol && symbol.includes('/');

  const getSortedSignals = (type: 'crypto' | 'stock', tabState: 'active' | 'closed') => {
    const isCrypto = type === 'crypto';
    const sourceSignals = tabState === 'active' ? activeSignals : closedSignals;
    const filtered = sourceSignals.filter(s => isCryptoSymbol(s.symbol) === isCrypto);
    
    const sortBy = tabState === 'active' ? activeSortBy : closedSortBy;
    return filtered.sort((a, b) => {
      if (sortBy === 'date') {
        const timeA = tabState === 'closed' ? (a.close_time || a.close_timestamp || a.timestamp || a.open_time || 0) : (a.open_time || 0);
        const timeB = tabState === 'closed' ? (b.close_time || b.close_timestamp || b.timestamp || b.open_time || 0) : (b.open_time || 0);
        return timeB - timeA;
      }
      return (b.pnl_pct || 0) - (a.pnl_pct || 0);
    });
  };

  const renderStatCard = (type: 'crypto' | 'stock') => {
    const isCrypto = type === 'crypto';
    const stat = freeStats.find(s => isCrypto ? !s.name.includes('Sherpa') : s.name.includes('Sherpa'));
    if (!stat) return null;

    return (
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg mb-6">
        <div className="flex items-center gap-2 mb-4">
          {stat.name.includes('Sherpa') ? '🦙' : '🛡️'}
          <h3 className="font-bold text-white">{stat.name}</h3>
        </div>
        
        <ul className="space-y-3 mb-6 text-sm">
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Win Rate:&nbsp;
            <span className={`font-bold ${stat.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {typeof stat.win_rate === 'number' ? stat.win_rate.toFixed(2) : stat.win_rate}%
            </span>
            <span className="text-gray-500 ml-1">({stat.wins} W | {stat.losses} L)</span>
          </li>
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Realized PnL:&nbsp;
            <span className={`font-bold ${stat.realized_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {formatPercent(stat.realized_pct)}
            </span>
          </li>
          {stat.unrealized_pct !== undefined && stat.unrealized_pct !== null && (
            <li className="flex items-center text-gray-300">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
              Unrealized PnL:&nbsp;
              <span className={`font-bold ${stat.unrealized_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {formatPercent(stat.unrealized_pct)}
              </span>
            </li>
          )}
          <li className="flex items-center text-gray-300">
            <span className="w-1.5 h-1.5 rounded-full bg-gray-500 mr-2"></span>
            Active Signals:&nbsp;
            <span className="font-bold text-cyan-400">
              {stat.active_count}
            </span>
          </li>
        </ul>

        <div className="space-y-2 mt-auto">
          <button 
            onClick={() => setShareStat({ stat, type })}
            className="w-full py-2.5 rounded-xl border border-white/10 text-gray-300 font-medium text-sm hover:bg-white/5 transition-colors flex items-center justify-center gap-2">
            <Share2 size={16} /> SHARE & EARN
          </button>
          <button 
            onClick={() => navigate(`/backtests?run=true&strategy=${encodeURIComponent(stat.name)}`)}
            className="w-full py-2.5 rounded-xl border border-white/10 text-gray-300 font-medium text-sm hover:bg-white/5 transition-colors flex items-center justify-center gap-2">
            <Beaker size={16} /> BACKTEST
          </button>
        </div>
      </div>
    );
  };

  const renderSignalCard = (signal: any, type: 'crypto' | 'stock', tabState: 'active' | 'closed') => {
    const isLong = signal.side?.toUpperCase() === 'LONG' || signal.side?.toUpperCase() === 'BUY';
    const pnlPct = signal.pnl_pct || 0;
    const isProfit = pnlPct >= 0;
    const pnlColor = isProfit ? 'text-emerald-400' : 'text-rose-400';
    let tp_pct = signal.entry_price > 0 && signal.tp_price > 0 ? Math.abs((signal.tp_price - signal.entry_price) / signal.entry_price * 100) : 0;
    let sl_pct = signal.entry_price > 0 && signal.sl_price > 0 ? Math.abs((signal.sl_price - signal.entry_price) / signal.entry_price * 100) : 0;
    
    if (type === 'crypto') {
      tp_pct *= 20;
      sl_pct *= 20;
    }
    const isExpanded = expandedId === signal.id;
    const isClosed = tabState === 'closed';

    const markPrice = signal.current_price || signal.mark_price || signal.exit_price || 0;
    const chartUrl = `/api/trades/chart?symbol=${encodeURIComponent(signal.symbol || '')}&entry=${signal.entry_price || 0}&tp=${signal.tp_price || 0}&sl=${signal.sl_price || 0}&side=${signal.side || ''}&open_ts=${signal.open_time || signal.close_time || 0}&type=${type}&current_price=${markPrice}&strategy=${encodeURIComponent(signal.strategy || '')}`;

    const cleanSym = (signal.symbol || '').replace('/', '').toUpperCase();
    const hasActiveTrade = userOpenTrades.some((t: any) => (t.symbol || '').replace('/', '').toUpperCase() === cleanSym);

    return (
      <div
        key={signal.id}
        className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg relative overflow-hidden transition-all ${
          isExpanded ? 'ring-1 ring-white/20' : (!isClosed ? 'hover:border-white/20 cursor-pointer' : '')
        }`}
        onClick={() => {
          if (isClosed) return;
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
                {(() => {
                  return (
                    <span className="text-white" onClick={(e) => e.stopPropagation()}>
                      {(signal.symbol || '').split('/')[0]}
                    </span>
                  );
                })()}
                {isLong ? <TrendingUp size={14} className="text-emerald-400"/> : <TrendingDown size={14} className="text-rose-400"/>}
              </h4>
              <p className="text-xs text-gray-400 mt-0.5">{signal.strategy}</p>
              <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                <Clock size={10}/>
                {formatTimeAgo(isClosed ? (signal.close_time || signal.close_timestamp || signal.timestamp || signal.open_time) : signal.open_time)}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 text-right">
            <button
              className="text-gray-400 hover:text-white transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                setShareTrade({ trade: signal, type, roe: pnlPct, pnl: signal.pnl_raw || 0 });
              }}
            >
              <Share2 size={18} />
            </button>
            <div>
              <p className={`font-bold text-lg leading-tight ${pnlColor}`}>
                {isProfit ? '+' : ''}{pnlPct.toFixed(2)}%
              </p>
              {tabState === 'active' && (
                <p className="text-xs text-gray-500 mt-0.5">
                  TARGET: {isPremium ? `${tp_pct.toFixed(0)}%` : <span className="blur-sm select-none">00%</span>}
                </p>
              )}
            </div>
            {!isClosed && <ChevronDown size={20} className={`text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />}
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

        {tabState === 'active' && isPremium && !hasActiveTrade && (
          pendingTrades[String(signal.id)] ? (
            <div className="mt-4 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <button
                disabled
                className="flex-1 py-2.5 px-3 bg-amber-500/10 border border-amber-500/30 text-amber-300 font-medium rounded-xl flex items-center justify-center gap-2 cursor-not-allowed text-xs sm:text-sm"
              >
                <Clock size={15} className="text-amber-400 animate-pulse flex-shrink-0" />
                <span className="truncate">
                  {pendingTrades[String(signal.id)].action_type === 'auto_execute' 
                    ? '⏳ Pending Auto-Execute at Market Open' 
                    : '📧 Pending Email Reminder at Market Open'}
                </span>
              </button>
              <button
                onClick={(e) => handleCancelPendingTrade(signal.id, e)}
                disabled={cancellingSignalId === signal.id}
                className="py-2.5 px-4 bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-400 font-bold rounded-xl transition-all text-xs flex items-center justify-center gap-1.5 shadow-[0_0_10px_rgba(244,63,94,0.15)] flex-shrink-0 disabled:opacity-50"
                title="Cancel pending order"
              >
                {cancellingSignalId === signal.id ? (
                  <RefreshCw size={14} className="animate-spin" />
                ) : (
                  'Cancel'
                )}
              </button>
            </div>
          ) : (
            <button
              onClick={(e) => handleOpenLiveTrade(signal, e)}
              disabled={executingSignalId === signal.id}
              className="mt-4 w-full py-2.5 px-4 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-400 font-bold rounded-xl flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(34,211,238,0.2)] disabled:opacity-50"
            >
              {executingSignalId === signal.id ? (
                <>
                  <RefreshCw size={16} className="animate-spin" /> Opening Live Trade...
                </>
              ) : (
                <>
                  ▶️ Open Live Trade
                </>
              )}
            </button>
          )
        )}

        {isExpanded && (
          <div className="mt-6 pt-6 border-t border-white/5 space-y-4 cursor-default" onClick={e => e.stopPropagation()}>
            {(() => {
              const isAiRec = (signal.strategy || '').toLowerCase().includes('ai') || (signal.strategy || '').toLowerCase().includes('recommendation');
              const timeframeLabel = isAiRec || type === 'stock' ? '1D' : '15M';
              return (
                <div className="font-bold text-white mb-2">
                  {(signal.symbol || '').split('/')[0]} ({signal.side?.toUpperCase()}) - {timeframeLabel} Setup | {signal.strategy}
                </div>
              );
            })()}
            <div className="relative w-full bg-[#0b0f19]/50 rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
              <img src={chartUrl} className="w-full h-auto block" alt="Signal Chart" />
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderColumn = (type: 'crypto' | 'stock') => {
    const icon = type === 'crypto' ? '🪙' : '🦙';
    const label = type === 'crypto' ? 'Crypto' : 'Stocks';
    const tabState = type === 'crypto' ? cryptoTab : stockTab;
    const setTabState = type === 'crypto' ? setCryptoTab : setStockTab;
    
    const signals = getSortedSignals(type, tabState);
    const activeLength = getSortedSignals(type, 'active').length;
    const closedLength = getSortedSignals(type, 'closed').length;

    return (
      <div className="flex flex-col">
        <h3 className="hidden md:flex text-xl font-bold text-white mb-6 items-center justify-center gap-2">
          <span>{icon}</span> {label} Alpha Signals
        </h3>

        {/* Stats Table */}
        {renderStatCard(type)}

        {/* Column Tabs */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-full p-1 flex items-center mb-6">
          <button
            onClick={() => setTabState('active')}
            className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${tabState === 'active' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
          >
            Active ({activeLength})
          </button>
          <button
            onClick={() => setTabState('closed')}
            className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${tabState === 'closed' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
          >
            Closed ({closedLength})
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
            <p className="text-gray-400 font-medium">No {tabState} {label.toLowerCase()} signals</p>
          </div>
        ) : (
          <div className="space-y-4">
            {signals.map(s => renderSignalCard(s, type, tabState))}
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

  const currentTabState = categoryTab === 'crypto' ? cryptoTab : stockTab;
  const currentSortBy = currentTabState === 'active' ? activeSortBy : closedSortBy;

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto pt-4">

      {/* Header Row */}
      <div className="flex justify-between items-center mb-6 px-2">
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          🛰️ Alpha Signals
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (currentTabState === 'active') setActiveSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
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

      {/* Mobile Category Tab */}
      <div className="md:hidden mb-6">
        <div className="bg-[#1b1f2c]/50 rounded-full p-1 flex border border-white/5">
          <button
            onClick={() => setCategoryTab('crypto')}
            className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'crypto' ? 'bg-cyan-500 text-white shadow-[0_0_12px_rgba(34,211,238,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Crypto 
          </button>
          <button
            onClick={() => setCategoryTab('stock')}
            className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'stock' ? 'bg-amber-500 text-white shadow-[0_0_12px_rgba(245,158,11,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Stocks 
          </button>
        </div>
      </div>

      {/* Mobile: Single column */}
      <div className="md:hidden space-y-4">
        {categoryTab === 'crypto'
          ? renderColumn('crypto')
          : renderColumn('stock')
        }
      </div>

      {/* Desktop: Two columns */}
      <div className="hidden md:grid md:grid-cols-2 md:gap-8">
        {renderColumn('crypto')}
        {renderColumn('stock')}
      </div>

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
          type={shareStat.type as 'crypto'|'stock'}
          roe={shareStat.stat.realized_pct}
          pnl={shareStat.stat.realized_pct}
          onClose={() => setShareStat(null)}
        />
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

      {/* Legal Disclaimer */}
      <p className="text-gray-500 text-[10px] leading-relaxed text-center mt-12 mb-4 px-4 max-w-4xl mx-auto">
        ⚠️ Disclaimer: The information provided by Metaverse Sherpa, including trade signals, strategies, and performance data, is for educational and informational purposes only. It does not constitute financial, investment, or trading advice. Past performance is not indicative of future results. Always do your own research and consult with a qualified financial advisor before making any investment decisions. You are solely responsible for your own trading decisions and any resulting gains or losses.
      </p>
    </div>
  );
};

export default SignalsPage;
