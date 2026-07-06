import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, Share2, TrendingUp, TrendingDown, ChevronDown, DollarSign, RefreshCcw } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import api from '../lib/api';
import SharePnLModal from './SharePnLModal';
import LoadingDisplay from './LoadingDisplay';
import { useAuthStore, useDashboardStore } from '../store/useStore';

const TradesPage: React.FC = () => {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const initialStatus = searchParams.get('status') as 'active' | 'closed' | null;
  const initialCategory = searchParams.get('category') as 'crypto' | 'stock' | null;

  const { user } = useAuthStore();
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
  
  const showCryptoColumn = user?.has_exchange_keys || (!user?.has_exchange_keys && !user?.has_alpaca_keys);
  const showStockColumn = user?.has_alpaca_keys || (!user?.has_exchange_keys && !user?.has_alpaca_keys);

  useEffect(() => {
    if (initialCategory && initialCategory !== categoryTab) {
      setCategoryTab(initialCategory);
    }
  }, [initialCategory]);

  const hideDollars = user?.hide_dollars;
  const [openTrades, setOpenTrades] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'active' | 'closed'>(initialStatus || (location.pathname === '/history' ? 'closed' : 'active'));
  const [activeSortBy, setActiveSortBy] = useState<'pnl' | 'date'>('pnl');
  const [closedSortBy, setClosedSortBy] = useState<'pnl' | 'date'>('date');
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'crypto'|'stock', roe: number, pnl: number} | null>(null);

  const handlePanic = async (type: 'crypto' | 'stock') => {
    const tradesToClose = openTrades.filter(t => t.type === type);
    if (tradesToClose.length === 0) return;

    if (!window.confirm(`🚨 PANIC 🚨\n\nAre you sure you want to market close ALL active ${type === 'stock' ? 'Stocks' : 'Crypto'} positions? This action cannot be undone.`)) {
      return;
    }

    setLoading(true);
    let successCount = 0;
    for (const trade of tradesToClose) {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/trades/close', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}` 
          },
          body: JSON.stringify({ id: trade.id || trade.trade_id, type: type, symbol: trade.symbol })
        });
        if (res.ok) successCount++;
      } catch (e) {
        console.error("Failed to close trade", trade.symbol, e);
      }
    }
    
    await fetchTrades(true);
    setLoading(false);
    alert(`Panic complete. Successfully closed ${successCount}/${tradesToClose.length} positions.`);
  };

  const fetchTrades = async (bypassCache = false) => {
    if (bypassCache) setLoading(true);
    try {
      const qs = bypassCache ? '?bypass_cache=true' : '';
      const [openRes, histRes] = await Promise.all([
        api.get(`/trades/open${qs}`),
        api.get(`/trades/history${qs}`)
      ]);
      
      // Filter out ghost trades (local-) from open trades
      const validOpenTrades = (openRes.data || []).filter((t: any) => !t.id?.startsWith('local-'));
      setOpenTrades(validOpenTrades);
      setHistory(histRes.data || []);
    } catch (err) {
      console.error("Error fetching trades:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(() => fetchTrades(false), 30000);
    return () => clearInterval(interval);
  }, []);

  const formatTimeAgo = (timestamp: number) => {
    if (!timestamp) return 'Recent';
    const timeInSeconds = timestamp > 10000000000 ? Math.floor(timestamp / 1000) : timestamp;
    const seconds = Math.floor(Date.now() / 1000 - timeInSeconds);
    if (seconds < 60) return `${Math.max(0, seconds)}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const sortBy = activeTab === 'active' ? activeSortBy : closedSortBy;

  const sortTrades = (trades: any[]) => {
    return [...trades].sort((a, b) => {
      if (sortBy === 'date') {
        const timeA = activeTab === 'closed' ? (a.close_time || a.close_timestamp || a.timestamp || a.open_time || 0) : (a.open_time || 0);
        const timeB = activeTab === 'closed' ? (b.close_time || b.close_timestamp || b.timestamp || b.open_time || 0) : (b.open_time || 0);
        return timeB - timeA;
      }
      const pnlA = activeTab === 'active' ? (a.roe || a.pnl_pct || 0) : (a.pnl_pct || 0);
      const pnlB = activeTab === 'active' ? (b.roe || b.pnl_pct || 0) : (b.pnl_pct || 0);
      return pnlB - pnlA;
    });
  };

  const renderTradeList = (type: 'crypto' | 'stock', trades: any[]) => {
    const typeTrades = sortTrades(trades.filter(t => t.type === type));
    if (typeTrades.length === 0) return null;

    return (
      <div className="mb-8 w-full max-w-3xl mx-auto">
        <div className="flex items-center justify-center mb-4">
          <h3 className="hidden md:flex font-bold text-lg text-white items-center gap-2">
            {type === 'stock' ? '🦙 Stocks' : '🪙 Crypto'} ({typeTrades.length})
          </h3>
        </div>
        
        <div className="space-y-4">
          {typeTrades.map((trade: any, idx: number) => {
            const isLong = trade.side?.toUpperCase() === 'LONG' || trade.side?.toUpperCase() === 'BUY';
            const isProfit = (trade.unrealized_pnl >= 0 || trade.pnl_raw >= 0);
            const pnlColor = isProfit ? 'text-emerald-400' : 'text-rose-400';
            
            const roe = activeTab === 'active' ? trade.roe : trade.pnl_pct;
            const pnlRaw = activeTab === 'active' ? trade.unrealized_pnl : trade.pnl_raw;
            
            // Calculate mock % for target if we don't have the exact risk ratio 
            const leverage = type === 'crypto' ? 20.0 : 1.0;
            const tp_pct = trade.entry_price > 0 && trade.tp_price > 0 ? Math.abs((trade.tp_price - trade.entry_price) / trade.entry_price * 100) * leverage : 0;
            const sl_pct = trade.entry_price > 0 && trade.sl_price > 0 ? Math.abs((trade.sl_price - trade.entry_price) / trade.entry_price * 100) * leverage : 0;
            const targetDollar = trade.qty && trade.tp_price ? Math.abs(trade.tp_price - trade.entry_price) * trade.qty : 0;
            const isExpanded = expandedTradeId === trade.id;
            
            const markPrice = trade.current_price || trade.mark_price || trade.exit_price || 0;
            const chartUrl = `/api/trades/chart?symbol=${encodeURIComponent(trade.symbol || '')}&entry=${trade.entry_price || 0}&tp=${trade.tp_price || 0}&sl=${trade.sl_price || 0}&side=${trade.side || ''}&open_ts=${trade.open_time || trade.close_time || 0}&type=${type}&current_price=${markPrice}&strategy=${encodeURIComponent(trade.strategy || '')}`;
            
            const isClickable = activeTab === 'active';

            return (
              <div key={`${type}-${activeTab}-${trade.id || 'trade'}-${idx}`} className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg relative overflow-hidden transition-all ${isExpanded ? 'ring-1 ring-white/20' : (isClickable ? 'hover:border-white/20 cursor-pointer' : '')}`} onClick={() => isClickable && setExpandedTradeId(isExpanded ? null : trade.id)}>
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center text-sm">
                      {type === 'stock' ? '🦙' : '🪙'}
                    </div>
                    <div>
                      <h4 className="font-bold text-white text-lg leading-tight">
                        {(() => {
                          const isCryptoTrade = type === 'crypto';
                          let linkUrl = '';
                          if (isCryptoTrade) {
                            const baseSymbol = (trade.symbol || '').replace(/:.*$/, '').replace(/[\/-]/g, '').replace(/USDT?$/i, '').replace(/USD$/i, '');
                            linkUrl = `https://marketmasters.ai/currency/${baseSymbol}USDT`;
                          } else {
                            linkUrl = `https://marketmasters.ai/stocks/${trade.symbol || ''}`;
                          }
                          return (
                            <a href={linkUrl} target="_blank" rel="noopener noreferrer" className="hover:text-[#3cd7ff] transition-colors underline decoration-white/30 underline-offset-2" onClick={(e) => e.stopPropagation()}>
                              {(trade.symbol || '').split('/')[0]}
                            </a>
                          );
                        })()}
                      </h4>
                      <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
                        {isLong ? <TrendingUp size={12} className="text-emerald-400"/> : <TrendingDown size={12} className="text-rose-400"/>}
                        {formatTimeAgo(activeTab === 'closed' ? (trade.close_time || trade.close_timestamp || trade.timestamp || trade.open_time) : (trade.open_time || trade.close_time))}
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4 text-right">
                    <button 
                      className="text-gray-400 hover:text-white transition-colors"
                      onClick={(e) => {
                        e.stopPropagation();
                        setShareTrade({ trade, type, roe: roe || 0, pnl: pnlRaw || 0 });
                      }}
                    >
                      <Share2 size={18} />
                    </button>
                    <div>
                      <p className={`font-bold text-lg leading-tight flex items-center justify-end gap-1 ${pnlColor}`}>
                        {isProfit ? '+' : ''}{roe?.toFixed(2)}% <span className="text-xs text-gray-500 font-normal">of {tp_pct.toFixed(0)}%</span>
                      </p>
                      {hideDollars ? (
                        <p className={`text-xs text-gray-500 mt-1 blur-sm opacity-70 select-none pointer-events-none`}>
                          +***.** <span className="text-gray-500">/ +***.**</span>
                        </p>
                      ) : (
                        <p className={`text-xs ${pnlColor} mt-1`}>
                          {isProfit ? '+' : ''}${pnlRaw?.toFixed(2)} <span className="text-gray-500">/ +${targetDollar.toFixed(2)}</span>
                        </p>
                      )}
                    </div>
                    {isClickable && <ChevronDown size={20} className={`text-gray-500 ml-2 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />}
                  </div>
                </div>

                <div className="flex justify-between items-center mt-6 text-xs text-gray-400 font-mono">
                  <div>SL: ${(trade.sl_price || 0).toFixed(2)} (-{sl_pct.toFixed(0)}%)</div>
                  <div>TP: ${(trade.tp_price || 0).toFixed(2)} ({tp_pct.toFixed(0)}%)</div>
                </div>
                
                {isExpanded && (
                  <div className="mt-6 pt-6 border-t border-white/5 space-y-4 cursor-default" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-between">
                      <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Market Analysis & Setup</h4>
                    </div>
                    <div className="font-bold text-white mb-2">{(trade.symbol || '').split('/')[0]} ({trade.side?.toUpperCase()}) - 1D Setup | {trade.strategy}</div>
                    <div className="relative w-full bg-[#0b0f19]/50 rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
                      <img src={chartUrl} className="w-full h-auto block" alt="Signal Chart" />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        
        {/* Panic Button for this specific type */}
        {activeTab === 'active' && typeTrades.length > 0 && (
          <button 
             onClick={() => handlePanic(type)}
             className="mt-6 w-full justify-center bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-500 font-bold py-3 px-8 rounded-xl flex items-center gap-2 transition-colors">
            <AlertTriangle size={18} /> PANIC - Close All {type === 'stock' ? 'Stocks' : 'Crypto'}
          </button>
        )}
      </div>
    );
  };

  const displayedTrades = activeTab === 'active' ? openTrades : history;

  if (loading) {
    return (
      <div className="flex-1 w-full flex items-center justify-center min-h-[400px]">
        <LoadingDisplay />
      </div>
    );
  }

  return (
    <div className="flex-1 w-full max-w-7xl mx-auto flex flex-col items-center pt-4">
      
      {/* Header Controls */}
      <div className="flex flex-col items-center w-full mb-6 gap-4">
        <div className="flex items-center justify-center gap-2">
          {/* Tab Selector */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-full p-1 flex items-center inline-flex">
            <button 
              onClick={() => setActiveTab('active')}
              className={`px-5 py-1.5 rounded-full text-sm font-bold transition-all ${activeTab === 'active' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
            >
              Active ({openTrades.length})
            </button>
            <button 
              onClick={() => setActiveTab('closed')}
              className={`px-5 py-1.5 rounded-full text-sm font-bold transition-all ${activeTab === 'closed' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
            >
              Closed ({history.length})
            </button>
          </div>
          
          <button
            onClick={() => {
              if (activeTab === 'active') setActiveSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
              else setClosedSortBy(prev => prev === 'pnl' ? 'date' : 'pnl');
            }}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-white/10 hover:bg-white/5 hover:border-cyan-500/30 transition-all text-xs text-gray-400 hover:text-white"
            title={sortBy === 'pnl' ? "Sort by Date" : "Sort by PnL"}
          >
            {sortBy === 'pnl' ? '📅' : <DollarSign size={16} className="text-white font-bold" />}
          </button>
          
          <button
            onClick={() => fetchTrades(true)}
            className={`w-8 h-8 flex items-center justify-center rounded-lg border border-white/10 hover:bg-white/5 hover:border-cyan-500/30 transition-all text-gray-400 hover:text-white ${loading ? 'animate-spin text-cyan-400' : ''}`}
            title="Refresh Trades"
          >
            <RefreshCcw size={16} />
          </button>
        </div>

        {/* Mobile Category Tab */}
        {showCryptoColumn && showStockColumn && (
          <div className="md:hidden w-full px-4 max-w-sm">
            <div className="bg-[#1b1f2c]/50 rounded-full p-1 flex border border-white/5">
              <button
                onClick={() => setCategoryTab('crypto')}
                className={`flex-1 py-1.5 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'crypto' ? 'bg-cyan-500 text-white shadow-[0_0_12px_rgba(34,211,238,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Crypto ({displayedTrades.filter(t => t.type === 'crypto').length})
              </button>
              <button
                onClick={() => setCategoryTab('stock')}
                className={`flex-1 py-1.5 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'stock' ? 'bg-amber-500 text-white shadow-[0_0_12px_rgba(245,158,11,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
              >
                Stocks ({displayedTrades.filter(t => t.type === 'stock').length})
              </button>
            </div>
          </div>
        )}
      </div>

      {displayedTrades.length === 0 ? (
        <div className="text-center py-12 w-full">
          <Activity size={48} className="mx-auto text-gray-600 mb-4 opacity-50" />
          <p className="text-gray-400 font-medium">No {activeTab} positions</p>
        </div>
      ) : (
        <>
          {/* Mobile: Single column based on category tab */}
          <div className="md:hidden w-full">
            {!(showCryptoColumn && showStockColumn) ? (
               showCryptoColumn ? renderTradeList('crypto', displayedTrades) : renderTradeList('stock', displayedTrades)
            ) : (
               categoryTab === 'crypto' 
                 ? renderTradeList('crypto', displayedTrades) 
                 : renderTradeList('stock', displayedTrades)
            )}
          </div>

          {/* Desktop: Columns */}
          <div className={`hidden md:grid gap-8 w-full ${showCryptoColumn && showStockColumn ? 'md:grid-cols-2' : 'md:grid-cols-1 max-w-3xl mx-auto'}`}>
            {showCryptoColumn && <div>{renderTradeList('crypto', displayedTrades)}</div>}
            {showStockColumn && <div>{renderTradeList('stock', displayedTrades)}</div>}
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
    </div>
  );
};

export default TradesPage;
