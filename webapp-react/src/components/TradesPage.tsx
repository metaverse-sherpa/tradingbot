import React, { useEffect, useState } from 'react';
import { Activity, AlertTriangle, DollarSign, RefreshCcw } from 'lucide-react';
import TradeCard from './TradeCard';
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
  

  useEffect(() => {
    if (initialCategory && initialCategory !== categoryTab) {
      setCategoryTab(initialCategory);
    }
  }, [initialCategory]);

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

  const initialLoadDone = React.useRef(false);

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
    const interval = setInterval(() => fetchTrades(false), 30000);
    return () => clearInterval(interval);
  }, []);

  // formatTimeAgo moved to TradeCard.tsx

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
            return (
              <TradeCard 
                key={`${type}-${activeTab}-${trade.id || 'trade'}-${idx}`}
                trade={trade}
                type={type}
                activeTab={activeTab}
                hideDollars={hideDollars}
                isExpanded={expandedTradeId === trade.id}
                onToggleExpand={() => activeTab === 'active' && setExpandedTradeId(expandedTradeId === trade.id ? null : trade.id)}
                onShare={() => setShareTrade({ trade, type, roe: activeTab === 'active' ? trade.roe : trade.pnl_pct || 0, pnl: activeTab === 'active' ? trade.unrealized_pnl : trade.pnl_raw || 0 })}
                onTogglePrivacy={togglePrivacy}
              />
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

  const userHasCrypto = user?.has_exchange_keys || (!user?.has_exchange_keys && !user?.has_alpaca_keys);
  const userHasStock = user?.has_alpaca_keys || (!user?.has_exchange_keys && !user?.has_alpaca_keys);
  
  const showCryptoColumn = userHasCrypto && displayedTrades.some(t => t.type === 'crypto');
  const showStockColumn = userHasStock && displayedTrades.some(t => t.type === 'stock');

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
