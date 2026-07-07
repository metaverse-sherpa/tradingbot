import React, { useEffect, useState, useCallback } from 'react';
import { Activity, TrendingUp, TrendingDown, Clock, Share2, RefreshCw, ChevronDown, Lock, DollarSign } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useAuthStore, useDashboardStore } from '../store/useStore';
import SharePnLModal from './SharePnLModal';
import LoadingDisplay from './LoadingDisplay';


const SignalsPage: React.FC = () => {
  const { user } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const navigate = useNavigate();
  
  const [activeSignals, setActiveSignals] = useState<any[]>([]);
  const [closedSignals, setClosedSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<'active' | 'closed'>('active');
  const [activeSortBy, setActiveSortBy] = useState<'pnl' | 'date'>('pnl');
  const [closedSortBy, setClosedSortBy] = useState<'pnl' | 'date'>('date');
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'crypto'|'stock', roe: number, pnl: number} | null>(null);

  const fetchSignals = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const [activeRes, closedRes] = await Promise.all([
        api.get(`/signals/active${showRefresh ? '?force=true' : ''}`),
        api.get('/signals/closed')
      ]);
      setActiveSignals(activeRes.data || []);
      setClosedSignals(closedRes.data || []);
    } catch (err) {
      console.error("Error fetching signals:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(() => fetchSignals(), 60000);
    return () => clearInterval(interval);
  }, [fetchSignals]);

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

  const isCryptoSymbol = (symbol: string) => symbol && symbol.includes('/');

  const sortBy = tab === 'active' ? activeSortBy : closedSortBy;

  const sortSignals = (signals: any[]) => {
    return [...signals].sort((a, b) => {
      if (sortBy === 'date') {
        const timeA = tab === 'closed' ? (a.close_time || a.close_timestamp || a.timestamp || a.open_time || 0) : (a.open_time || 0);
        const timeB = tab === 'closed' ? (b.close_time || b.close_timestamp || b.timestamp || b.open_time || 0) : (b.open_time || 0);
        return timeB - timeA;
      }
      return (b.pnl_pct || 0) - (a.pnl_pct || 0);
    });
  };

  const currentSignals = tab === 'active' ? activeSignals : closedSignals;
  const cryptoSignals = sortSignals(currentSignals.filter(s => isCryptoSymbol(s.symbol)));
  const stockSignals = sortSignals(currentSignals.filter(s => !isCryptoSymbol(s.symbol)));

  const renderSignalCard = (signal: any, type: 'crypto' | 'stock') => {
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
    const isClosed = tab === 'closed';

    const markPrice = signal.current_price || signal.mark_price || signal.exit_price || 0;
    const chartUrl = `/api/trades/chart?symbol=${encodeURIComponent(signal.symbol || '')}&entry=${signal.entry_price || 0}&tp=${signal.tp_price || 0}&sl=${signal.sl_price || 0}&side=${signal.side || ''}&open_ts=${signal.open_time || signal.close_time || 0}&type=${type}&current_price=${markPrice}&strategy=${encodeURIComponent(signal.strategy || '')}`;

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
        {/* Top Row: Symbol + PnL */}
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            <div>
              <h4 className="font-bold text-white text-lg leading-tight flex items-center gap-2">
                {(() => {
                  const isCryptoSignal = type === 'crypto';
                  let linkUrl = '';
                  if (isCryptoSignal) {
                    const baseSymbol = (signal.symbol || '').replace(/:.*$/, '').replace(/[\/-]/g, '').replace(/USDT?$/i, '').replace(/USD$/i, '');
                    linkUrl = `https://marketmasters.ai/currency/${baseSymbol}USDT`;
                  } else {
                    linkUrl = `https://marketmasters.ai/stocks/${signal.symbol || ''}`;
                  }
                  return (
                    <a href={linkUrl} target="_blank" rel="noopener noreferrer" className="hover:text-[#3cd7ff] transition-colors underline decoration-white/30 underline-offset-2" onClick={(e) => e.stopPropagation()}>
                      {(signal.symbol || '').split('/')[0]}
                    </a>
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
              {tab === 'active' && (
                <p className="text-xs text-gray-500 mt-0.5">
                  TARGET: {isPremium ? `${tp_pct.toFixed(0)}%` : <span className="blur-sm select-none">00%</span>}
                </p>
              )}
            </div>
            {!isClosed && <ChevronDown size={20} className={`text-gray-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />}
          </div>
        </div>

        {/* SL / TP Row */}
        <div className="flex justify-between items-center mt-4 text-xs text-gray-400 font-mono">
          {isPremium ? (
            <>
              <div>SL: ${(signal.sl_price || 0).toFixed(2)} (-{sl_pct.toFixed(0)}%)</div>
              <div>TP: ${(signal.tp_price || 0).toFixed(2)} (+{tp_pct.toFixed(0)}%)</div>
            </>
          ) : (
            <>
              <div className="blur-sm select-none opacity-50">SL: $0.00 (-0%)</div>
              <div className="blur-sm select-none opacity-50">TP: $0.00 (+0%)</div>
            </>
          )}
        </div>

        {/* Expanded Chart */}
        {isExpanded && (
          <div className="mt-6 pt-6 border-t border-white/5 space-y-4 cursor-default" onClick={e => e.stopPropagation()}>
            <div className="font-bold text-white mb-2">{(signal.symbol || '').split('/')[0]} ({signal.side?.toUpperCase()}) - 1D Setup | {signal.strategy}</div>
            <div className="relative w-full bg-[#0b0f19]/50 rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
              <img src={chartUrl} className="w-full h-auto block" alt="Signal Chart" />
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderColumn = (type: 'crypto' | 'stock', signals: any[]) => {
    const icon = type === 'crypto' ? '🪙' : '🦙';
    const label = type === 'crypto' ? 'Crypto' : 'Stocks';

    return (
      <div>
        <h3 className="hidden md:flex text-lg font-bold text-white mb-4 items-center justify-center gap-2">
          <span>{icon}</span> {label} ({signals.length})
        </h3>
        {signals.length === 0 ? (
          <div className="text-center py-12">
            <Activity size={48} className="mx-auto text-gray-600 mb-4 opacity-50" />
            <p className="text-gray-400 font-medium">No {tab === 'active' ? 'active' : 'closed'} {label.toLowerCase()} signals</p>
          </div>
        ) : (
          <div className="space-y-4">
            {signals.map(s => renderSignalCard(s, type))}
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

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto pt-4">

      {/* Header Row */}
      <div className="flex justify-between items-center mb-6 px-2">
        <h2 className="text-2xl font-bold text-white flex items-center gap-3">
          🛰️ Alpha Signals
          <div className="flex items-center gap-2">
            {currentSignals.length > 0 && (
              <button
                onClick={() => {
                  if (tab === 'active') setActiveSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
                  else setClosedSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
                }}
                className="w-8 h-8 flex items-center justify-center rounded-lg border border-white/10 hover:bg-white/5 hover:border-cyan-500/30 transition-all text-xs text-gray-400 hover:text-white"
                title={sortBy === 'pnl' ? "Sort by Date" : "Sort by PnL"}
              >
                {sortBy === 'pnl' ? '📅' : <DollarSign size={16} className="text-white font-bold" />}
              </button>
            )}
            <button
              onClick={() => fetchSignals(true)}
              className={`flex items-center justify-center w-8 h-8 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all text-gray-400 hover:text-white ${refreshing ? 'animate-spin text-cyan-400' : ''}`}
              title="Refresh Signals"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </h2>
      </div>

      {/* Tabs */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-full p-1 flex items-center mb-8 max-w-[500px] mx-auto">
        <button
          onClick={() => setTab('active')}
          className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${tab === 'active' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
        >
          Active ({activeSignals.length})
        </button>
        <button
          onClick={() => setTab('closed')}
          className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${tab === 'closed' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
        >
          Closed ({closedSignals.length})
        </button>
      </div>

      {tab === 'closed' && !isPremium ? (
        <div className="text-center py-16 bg-[#1b1f2c]/50 backdrop-blur-md rounded-3xl border border-white/5 max-w-2xl mx-auto mt-8 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-amber-400 via-yellow-500 to-amber-600"></div>
          <div className="w-20 h-20 bg-amber-500/10 rounded-full flex items-center justify-center mx-auto mb-6 border border-amber-500/20 shadow-[0_0_30px_rgba(245,158,11,0.2)]">
            <Lock size={36} className="text-amber-400" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-3">Premium Feature</h2>
          <p className="text-gray-400 mb-8 max-w-md mx-auto leading-relaxed">
            Upgrade to Premium to view closed signals and analyze Sherpa's historical performance.
          </p>
          <Link 
            to="/premium"
            className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-white font-bold rounded-xl transition-all shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:shadow-[0_0_30px_rgba(245,158,11,0.5)] hover:-translate-y-0.5"
          >
            Upgrade to Premium
          </Link>
        </div>
      ) : currentSignals.length === 0 ? (
        <div className="text-center py-12">
          <Activity size={48} className="mx-auto text-gray-600 mb-4 opacity-50" />
          <p className="text-gray-400 font-medium">
            {tab === 'active' ? 'No active signals — Sherpa is analyzing markets...' : 'No closed signals yet.'}
          </p>
        </div>
      ) : (
        <>
          {/* Mobile Category Tab */}
          <div className="md:hidden mb-4">
            <div className="bg-[#1b1f2c]/50 rounded-full p-1 flex border border-white/5">
              <button
                onClick={() => setCategoryTab('crypto')}
                className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'crypto' ? 'bg-cyan-500 text-white shadow-[0_0_12px_rgba(34,211,238,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Crypto ({cryptoSignals.length})
              </button>
              <button
                onClick={() => setCategoryTab('stock')}
                className={`flex-1 py-2 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'stock' ? 'bg-amber-500 text-white shadow-[0_0_12px_rgba(245,158,11,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Stocks ({stockSignals.length})
              </button>
            </div>
          </div>

          {/* Mobile: Single column */}
          <div className="md:hidden space-y-4">
            {categoryTab === 'crypto'
              ? renderColumn('crypto', cryptoSignals)
              : renderColumn('stock', stockSignals)
            }
          </div>

          {/* Desktop: Two columns */}
          <div className="hidden md:grid md:grid-cols-2 md:gap-8">
            {renderColumn('crypto', cryptoSignals)}
            {renderColumn('stock', stockSignals)}
          </div>
        </>
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

      {/* Legal Disclaimer */}
      <p className="text-gray-500 text-[10px] leading-relaxed text-center mt-12 mb-4 px-4 max-w-4xl mx-auto">
        ⚠️ Disclaimer: The information provided by Metaverse Sherpa, including trade signals, strategies, and performance data, is for educational and informational purposes only. It does not constitute financial, investment, or trading advice. Past performance is not indicative of future results. Always do your own research and consult with a qualified financial advisor before making any investment decisions. You are solely responsible for your own trading decisions and any resulting gains or losses.
      </p>
    </div>
  );
};

export default SignalsPage;
