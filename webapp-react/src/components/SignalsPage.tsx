import React, { useEffect, useState, useCallback } from 'react';
import { Activity, TrendingUp, TrendingDown, Clock, Share2, RefreshCw, ChevronDown, Lock, DollarSign, Beaker } from 'lucide-react';
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

  const fetchSignalsAndStats = useCallback(async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    try {
      const [activeRes, closedRes, statsRes] = await Promise.all([
        api.get(`/signals/active${showRefresh ? '?force=true' : ''}`),
        api.get('/signals/closed'),
        api.get(`/stats/free${showRefresh ? '?bypass_cache=true' : ''}`)
      ]);
      setActiveSignals(activeRes.data || []);
      setClosedSignals(closedRes.data || []);
      setFreeStats(statsRes.data?.strategies || []);
    } catch (err) {
      console.error("Error fetching signals/stats:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

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
            onClick={() => navigate(`/backtests?strategy=${encodeURIComponent(stat.name)}`)}
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
          trade={shareStat.stat} // sharePnLModal expects trade object, stat object structure might need adaptation but it was like this in StatsPage
          type={shareStat.type as 'crypto'|'stock'}
          roe={shareStat.stat.realized_pct}
          pnl={shareStat.stat.realized_pct} // Dummy PNL
          onClose={() => setShareStat(null)}
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
