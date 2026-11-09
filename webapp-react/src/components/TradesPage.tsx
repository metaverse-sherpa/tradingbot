import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, DollarSign, RefreshCcw } from 'lucide-react';
import TradeCard from './TradeCard';
import { useLocation } from 'react-router-dom';
import api from '../lib/api';
import SharePnLModal from './SharePnLModal';
import LoadingDisplay from './LoadingDisplay';
import { useAuthStore } from '../store/useStore';
import { isStockMarketOpen } from '../utils/market';

const TradesPage: React.FC = () => {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const initialStatus = searchParams.get('status') as 'active' | 'closed' | null;

  const { user } = useAuthStore();
  
  useEffect(() => {
    const tradeOpened = searchParams.get('trade_opened');
    const urlError = searchParams.get('error');
    if (tradeOpened) {
      alert(`✅ Live stock trade for ${tradeOpened} successfully opened!`);
    } else if (urlError) {
      alert(`❌ Execution note: ${urlError}`);
    }
  }, [location.search]);

  const [revealValues, setRevealValues] = useState(false);
  const hideDollars = user?.hide_dollars && !revealValues;

  const togglePrivacy = () => {
    if (user?.hide_dollars) {
      setRevealValues(!revealValues);
    }
  };
  const [openTrades, setOpenTrades] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'active' | 'closed'>(initialStatus || (location.pathname === '/history' ? 'closed' : 'active'));
  const [activeSortBy, setActiveSortBy] = useState<'pnl' | 'date'>('pnl');
  const [closedSortBy, setClosedSortBy] = useState<'pnl' | 'date'>('date');
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'stock', roe: number, pnl: number} | null>(null);
  const [confirmCloseTrade, setConfirmCloseTrade] = useState<any | null>(null);
  const [closingTrade, setClosingTrade] = useState(false);

  const handleExecuteSingleClose = async () => {
    if (!confirmCloseTrade) return;
    setClosingTrade(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/trades/close', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}` 
        },
        body: JSON.stringify({ 
          id: confirmCloseTrade.id || confirmCloseTrade.trade_id, 
          type: 'stock', 
          symbol: confirmCloseTrade.symbol 
        })
      });
      const data = await res.json();
      if (res.ok) {
        alert(`✅ Position for ${confirmCloseTrade.symbol} closed successfully.`);
      } else {
        alert(`❌ Failed to close trade: ${data.error || data.message || 'Unknown error'}`);
      }
    } catch (e: any) {
      console.error("Failed to close trade", confirmCloseTrade.symbol, e);
      alert(`❌ Failed to close position: ${e.message}`);
    } finally {
      setClosingTrade(false);
      setConfirmCloseTrade(null);
      await fetchTrades(true);
    }
  };

  const handlePanic = async () => {
    const tradesToClose = openTrades.filter(t => t.type === 'stock' || !t.type);
    if (tradesToClose.length === 0) return;

    if (!window.confirm(`🚨 PANIC 🚨\n\nAre you sure you want to market close ALL active stock positions? This action cannot be undone.`)) {
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
          body: JSON.stringify({ id: trade.id || trade.trade_id, type: 'stock', symbol: trade.symbol })
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

  const initialLoadDone = React.useRef(false);

  const fetchTrades = async (bypassCache = false) => {
    if (bypassCache) setLoading(true);
    try {
      const qs = bypassCache ? '?bypass_cache=true' : '';
      const [openRes, histRes] = await Promise.all([
        api.get(`/trades/open${qs}`),
        api.get(`/trades/history${qs}`)
      ]);
      
      const filterStocks = (list: any[]) => (Array.isArray(list) ? list : []).filter((t: any) => !String(t?.id ?? '').startsWith('local-') && (t.type === 'stock' || !t.symbol?.includes('/')));
      const validOpenTrades = filterStocks(openRes.data);
      setOpenTrades(validOpenTrades);
      setHistory(filterStocks(histRes.data));

      if (!initialLoadDone.current) {
        if (!initialStatus && location.pathname !== '/history' && validOpenTrades.length === 0) {
          setActiveTab('closed');
        }
        initialLoadDone.current = true;
      }
    } catch (err) {
      console.error("Error fetching trades:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
    const interval = setInterval(() => {
      if (openTrades.length > 0 || isStockMarketOpen()) {
        fetchTrades(false);
      }
    }, 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, [openTrades.length]);

  const sortBy = activeTab === 'active' ? activeSortBy : closedSortBy;

  const sortTrades = (trades: any[]) => {
    return [...trades].sort((a, b) => {
      if (sortBy === 'date') {
        const timeA = activeTab === 'closed' ? (a.close_time || a.open_time || 0) : (a.open_time || 0);
        const timeB = activeTab === 'closed' ? (b.close_time || b.open_time || 0) : (b.open_time || 0);
        return timeB - timeA;
      }
      const pnlA = activeTab === 'active' ? (a.roe || a.pnl_pct || 0) : (a.pnl_pct || 0);
      const pnlB = activeTab === 'active' ? (b.roe || b.pnl_pct || 0) : (b.pnl_pct || 0);
      return pnlB - pnlA;
    });
  };

  const displayedTrades = sortTrades(activeTab === 'active' ? openTrades : history);

  if (loading) {
    return (
      <div className="flex-1 w-full flex items-center justify-center min-h-[400px]">
        <LoadingDisplay />
      </div>
    );
  }

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto flex flex-col items-center pt-4">
      
      {/* Header Controls */}
      <div className="flex flex-col items-center w-full mb-6 gap-4">
        <div className="flex items-center justify-center gap-2">
          {/* Tab Selector */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-full p-1 flex items-center inline-flex">
            <button 
              onClick={() => setActiveTab('active')}
              className={`px-5 py-2 rounded-full text-sm font-bold transition-all ${activeTab === 'active' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
            >
              Active Stock Positions ({openTrades.length})
            </button>
            <button 
              onClick={() => setActiveTab('closed')}
              className={`px-5 py-2 rounded-full text-sm font-bold transition-all ${activeTab === 'closed' ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.3)]' : 'text-gray-400 hover:text-white'}`}
            >
              Closed Stock Trades ({history.length})
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
      </div>

      {displayedTrades.length === 0 ? (
        <div className="text-center py-12 w-full">
          <Activity size={48} className="mx-auto text-gray-600 mb-4 opacity-50" />
          <p className="text-gray-400 font-medium">No {activeTab} stock positions</p>
        </div>
      ) : (
        <div className="w-full space-y-4">
          {displayedTrades.map((trade: any, idx: number) => {
            const tradeId = trade.id || `stock-${trade.symbol || idx}`;
            const isExpanded = Boolean(expandedTradeId) && expandedTradeId === tradeId;
            return (
              <TradeCard 
                key={`stock-${activeTab}-${tradeId}-${idx}`}
                trade={trade}
                type="stock"
                activeTab={activeTab}
                hideDollars={hideDollars}
                isExpanded={isExpanded}
                onToggleExpand={() => activeTab === 'active' && setExpandedTradeId(isExpanded ? null : tradeId)}
                onShare={() => setShareTrade({ trade, type: 'stock', roe: activeTab === 'active' ? trade.roe : trade.pnl_pct || 0, pnl: activeTab === 'active' ? trade.unrealized_pnl : trade.pnl_raw || 0 })}
                onTogglePrivacy={togglePrivacy}
                onClosePosition={(t) => setConfirmCloseTrade(t)}
              />
            );
          })}
          
          {activeTab === 'active' && displayedTrades.length > 0 && (
            <button 
              onClick={handlePanic}
              className="mt-6 w-full justify-center bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-500 font-bold py-3 px-8 rounded-xl flex items-center gap-2 transition-colors">
              <AlertTriangle size={18} /> PANIC - Close All Stock Positions
            </button>
          )}
        </div>
      )}

      {shareTrade && (
        <SharePnLModal 
          trade={shareTrade.trade} 
          type="stock" 
          roe={shareTrade.roe} 
          pnl={shareTrade.pnl} 
          onClose={() => setShareTrade(null)} 
        />
      )}

      {confirmCloseTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md">
          <div className="bg-[#1b1f2c] border border-rose-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 relative">
            <div className="flex items-center gap-3 text-rose-400 font-bold text-lg border-b border-white/10 pb-3">
              <AlertTriangle className="size-6 text-rose-500 shrink-0" />
              <span>CLOSE {confirmCloseTrade.symbol} CONFIRMATION</span>
            </div>
            
            <p className="text-gray-300 text-sm leading-relaxed">
              You are about to close your <strong className="text-white font-bold">{confirmCloseTrade.symbol}</strong> position manually at market price.
            </p>

            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400 text-xs leading-relaxed">
              <strong>❗ Strategic Warning:</strong><br/>
              By closing early, you may miss out on significant profit potential. Your performance statistics will also deviate from the official Sherpa strategy results.
            </div>

            <p className="text-gray-400 text-xs font-medium">Are you absolutely sure you want to exit now?</p>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setConfirmCloseTrade(null)}
                disabled={closingTrade}
                className="flex-1 py-2.5 px-4 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 font-bold rounded-xl text-sm transition-colors"
              >
                ❌ Keep Open
              </button>
              <button
                onClick={handleExecuteSingleClose}
                disabled={closingTrade}
                className="flex-1 py-2.5 px-4 bg-rose-500 hover:bg-rose-600 text-white font-bold rounded-xl text-sm transition-colors shadow-[0_0_15px_rgba(244,63,94,0.3)] flex items-center justify-center gap-2"
              >
                {closingTrade ? <RefreshCcw size={16} className="animate-spin" /> : '✅ Close Now'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TradesPage;
