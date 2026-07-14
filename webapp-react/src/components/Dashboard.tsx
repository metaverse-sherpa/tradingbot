import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, ResponsiveContainer, YAxis, XAxis, Tooltip } from 'recharts';
import { Activity, Clock, Settings, Zap, Target, Loader2, RefreshCcw, Share2 } from 'lucide-react';
import { useDashboardStore, useAuthStore } from '../store/useStore';
import api from '../lib/api';
import TradeCard from './TradeCard';
import SharePnLModal from './SharePnLModal';

const Dashboard: React.FC = () => {
  const { activeTab, setTab } = useDashboardStore();
  const { user } = useAuthStore();
  const hideDollars = user?.hide_dollars;

  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [signalsLoading, setSignalsLoading] = useState(true);
  const [cryptoData, setCryptoData] = useState({ bal: 0, open: 0, wins: 0, losses: 0, pnl: 0, pnl_pct: 0, chart: [] as {value: number, x: string}[] });
  const [stockData, setStockData] = useState({ bal: 0, open: 0, wins: 0, losses: 0, pnl: 0, pnl_pct: 0, chart: [] as {value: number, x: string}[] });
  const [cryptoSignalCount, setCryptoSignalCount] = useState(0);
  const [stockSignalCount, setStockSignalCount] = useState(0);
  const [activeSignals, setActiveSignals] = useState<any[]>([]);
  const [freeStats, setFreeStats] = useState<any[]>([]);
  const [openTrades, setOpenTrades] = useState<any[]>([]);
  const [openTradesLoading, setOpenTradesLoading] = useState(true);
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);
  const [shareTrade, setShareTrade] = useState<{trade: any, type: 'crypto'|'stock', roe: number, pnl: number} | null>(null);
  const [shareStat, setShareStat] = useState<{stat: any, type: 'crypto'|'stock'} | null>(null);
  const [isDesktop, setIsDesktop] = useState(window.innerWidth >= 768);

  useEffect(() => {
    const handleResize = () => setIsDesktop(window.innerWidth >= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    fetchData();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => fetchData(false), 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchOpenTrades = async (bypassCache = false) => {
    if (bypassCache || openTrades.length === 0) setOpenTradesLoading(true);
    try {
      const openRes = await api.get(`/trades/open${bypassCache ? '?bypass_cache=true' : ''}`);
      const validOpenTrades = (openRes.data || []).filter((t: any) => !t.id?.startsWith('local-'));
      setOpenTrades(validOpenTrades);
    } catch (err) {
      console.error(err);
    } finally {
      setOpenTradesLoading(false);
    }
  };

  const fetchData = async (bypassCache = false) => {
    setLoading(true);
    setSignalsLoading(true);

    fetchOpenTrades(bypassCache);

    try {
      const res = await api.get(`/user/dashboard-summary${bypassCache ? '?bypass_cache=true' : ''}`);
      const data = res.data || {};

      const cBal = { data: data.crypto_balance || { crypto_balance: 0 } };
      const sBal = { data: data.stock_balance || { stock_balance: 0 } };
      const cStats = { data: data.crypto_stats || { crypto: { open_positions: 0, wins: 0, losses: 0 } } };
      const sStats = { data: data.stock_stats || { stock: { open_positions: 0, wins: 0, losses: 0 } } };
      const histRes = { data: data.balance_history || [] };
      const freeStatsRes = { data: data.free_stats || { strategies: [] } };
      const signals = data.active_signals || [];

      const balHist = histRes.data;
      
      setFreeStats(freeStatsRes.data?.strategies || []);

      const buildChartData = (type: 'crypto' | 'stock', bal: number) => {
        const rawPoints = balHist
            .map((item: any) => ({ x: item.timestamp, y: type === 'crypto' ? item.crypto : item.stock }))
            .filter((p: any) => p.y && p.y > 0);
            
        const actualPoints = rawPoints.map((p: any) => ({ 
            value: p.y, 
            x: new Date(p.x * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) 
        }));
        
        if (actualPoints.length >= 5) return actualPoints;
        
        const numDummyPoints = 5 - actualPoints.length;
        const firstRealPointValue = actualPoints.length > 0 ? actualPoints[0].value : (bal || 5000);
        const firstRealPointTime = rawPoints.length > 0 ? rawPoints[0].x : Math.floor(Date.now() / 1000);
        const daySec = 86400;
        
        const dummyPoints = [];
        const volatility = [0.97, 1.02, 0.98, 0.99, 0.96]; // Random looking factors
        
        for (let i = numDummyPoints; i > 0; i--) {
            const time = firstRealPointTime - (i * daySec);
            const factor = volatility[i - 1] || 0.95;
            dummyPoints.push({
                value: firstRealPointValue * factor,
                x: new Date(time * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            });
        }
        
        return [...dummyPoints, ...actualPoints];
      };

      const cBalAmount = cBal.data?.crypto_balance || 0;
      const sBalAmount = sBal.data?.stock_balance || 0;
      
      const cChart = buildChartData('crypto', cBalAmount);
      const sChart = buildChartData('stock', sBalAmount);

      setCryptoData({
        bal: cBalAmount,
        open: cStats.data?.crypto?.open_positions || 0,
        wins: cStats.data?.crypto?.wins || 0,
        losses: cStats.data?.crypto?.losses || 0,
        pnl: cStats.data?.crypto?.overall_pnl || 0,
        pnl_pct: cStats.data?.crypto?.overall_pnl_pct || 0,
        chart: cChart
      });

      setStockData({
        bal: sBalAmount,
        open: sStats.data?.stock?.open_positions || 0,
        wins: sStats.data?.stock?.wins || 0,
        losses: sStats.data?.stock?.losses || 0,
        pnl: sStats.data?.stock?.overall_pnl || 0,
        pnl_pct: sStats.data?.stock?.overall_pnl_pct || 0,
        chart: sChart
      });
      
      setActiveSignals(signals);
      setCryptoSignalCount(signals.filter((s: any) => s.symbol && s.symbol.includes('/')).length);
      setStockSignalCount(signals.filter((s: any) => s.symbol && !s.symbol.includes('/')).length);
      
    } catch (e) {
      console.error('Error fetching dashboard data', e);
    } finally {
      setLoading(false);
      setSignalsLoading(false);
    }
  };

  const renderColumn = (type: 'crypto' | 'stock', data: typeof cryptoData, signalCount: number) => {
    const isCrypto = type === 'crypto';
    const accentColor = isCrypto ? 'text-cyan-400' : 'text-amber-400';
    const totalTrades = data.wins + data.losses;
    const winRate = totalTrades > 0 ? ((data.wins / totalTrades) * 100).toFixed(1) : '0.0';

    return (
      <div className="space-y-4">
        {/* Equity Card */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-2xl px-4 pt-4 pb-0 shadow-lg relative overflow-hidden group hover:border-white/20 transition-all">
          <div className="flex justify-between items-center mb-2">
            <h3 className="text-sm text-gray-400 uppercase tracking-widest font-bold flex items-center gap-2">
              {isCrypto ? <Activity size={16} className={accentColor} /> : <Target size={16} className={accentColor} />}
              {isCrypto ? 'Crypto Equity' : 'Stock Equity'}
            </h3>
            <button
              onClick={() => fetchData(true)}
              className="text-gray-400 hover:text-white transition-colors"
              title="Refresh Dashboard"
            >
              <RefreshCcw size={14} className={loading ? "animate-spin text-white" : ""} />
            </button>
          </div>
          <div className="flex items-baseline gap-3 mb-2 flex-wrap">
            <p className="text-2xl font-mono text-white">
              {loading ? <Loader2 className="animate-spin text-gray-500 size-6" /> : hideDollars ? <span className="blur-md opacity-70 select-none pointer-events-none">$***,***.**</span> : `$${data.bal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </p>
            {!loading && (
              <p className={`font-mono font-bold ${data.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {data.pnl >= 0 ? '+' : ''}{data.pnl_pct}% 
                {hideDollars ? (
                  <span className="text-sm text-gray-500 font-normal ml-1 blur-sm opacity-70 select-none pointer-events-none">(+***,***.**)</span>
                ) : (
                  <span className="text-sm text-gray-500 font-normal ml-1">({data.pnl >= 0 ? '+' : ''}${(Math.abs(data.pnl) || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})</span>
                )}
              </p>
            )}
          </div>
          <div className="h-36 mt-1 w-full opacity-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.chart} margin={{ top: 5, right: hideDollars ? 5 : 20, left: 5, bottom: 0 }}>
                <XAxis dataKey="x" tick={{ fontSize: 10, fill: '#ffffff' }} tickLine={false} axisLine={false} />
                <YAxis orientation="right" domain={['dataMin', 'dataMax']} hide={hideDollars} tick={{ fontSize: 10, fill: '#ffffff' }} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value.toLocaleString()}`} />
                {!hideDollars && (
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1b1f2c', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px', fontSize: '12px' }}
                    itemStyle={{ color: isCrypto ? '#3cd7ff' : '#ffdb3c' }}
                    formatter={(value: any) => [`$${Number(value).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`, 'Balance']}
                  />
                )}
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke={isCrypto ? '#3cd7ff' : '#ffdb3c'} 
                  strokeWidth={2} 
                  strokeDasharray="4 4"
                  dot={false} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="mt-3">
          <button 
            onClick={() => {
              const statObj = {
                name: isCrypto ? 'Crypto Portfolio' : 'Stock Portfolio',
                realized_pct: data.pnl_pct,
                unrealized_pct: 0,
                win_rate: parseFloat(winRate),
                wins: data.wins,
                losses: data.losses
              };
              setShareStat({ stat: statObj, type });
            }}
            className="w-full py-2.5 rounded-xl border border-white/10 text-gray-300 font-medium text-sm hover:bg-white/5 transition-colors flex items-center justify-center gap-2">
            <Share2 size={16} /> SHARE & EARN
          </button>
        </div>

        {/* Action Grid */}
        <div className="grid grid-cols-2 gap-3 mt-4">
          <button 
            onClick={() => { setTab(type); navigate('/trades'); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Activity className="text-gray-400 group-hover:text-white transition-colors" size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white flex items-center gap-1">
              Live Trades {loading ? <Loader2 className="animate-spin text-gray-500 size-3" /> : <span className="text-gray-400 font-normal">({data.open})</span>}
            </span>
          </button>

          <button 
            onClick={() => { setTab(type); navigate('/trades'); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Clock className="text-gray-400 group-hover:text-white transition-colors" size={18} />
            <div className="flex flex-col items-start">
              <span className="text-sm font-semibold text-gray-300 group-hover:text-white">Trade History</span>
              {!loading && (
                <span className="text-[10px] text-white mt-0.5 leading-none">
                  <span className="font-bold text-xs">{winRate}%</span> ({data.wins}W / {data.losses}L)
                </span>
              )}
            </div>
          </button>

          <button 
            onClick={() => { setTab(type); navigate('/signals'); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Zap className={`${accentColor} group-hover:text-white transition-colors`} size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white flex items-center gap-1">
              Alpha Signals {signalsLoading ? <Loader2 className="animate-spin text-gray-500 size-3" /> : <span className="text-gray-400 font-normal">({signalCount})</span>}
            </span>
          </button>
          <button 
            onClick={() => { setTab(type); navigate(`/backtests?run=true&strategy=${encodeURIComponent(type === 'crypto' ? 'Valkyrie Elite Scalper' : 'Sherpa Velocity Pullback')}`); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Settings className="text-gray-400 group-hover:text-white transition-colors" size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white">Backtest</span>
          </button>
        </div>

        {/* Active Trades (Top 5) */}
        {(() => {
          if (openTradesLoading) {
            return (
              <div className="mt-8 space-y-4">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                   ⚡ Live Active Trades <Loader2 className="animate-spin text-gray-500 size-4 ml-2" />
                </h3>
              </div>
            );
          }

          const typeTrades = openTrades
            .filter((t: any) => t.type === type)
            .sort((a, b) => (b.roe || b.pnl_pct || 0) - (a.roe || a.pnl_pct || 0))
            .slice(0, 5);

          if (typeTrades.length === 0) return null;

          return (
            <div className="mt-8 space-y-4">
              <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                 ⚡ Live Active Trades <span className="text-sm text-gray-500 font-normal">({typeTrades.length})</span>
              </h3>
              {typeTrades.map((trade: any, idx: number) => (
                <TradeCard 
                  key={`${type}-active-${trade.id || 'trade'}-${idx}`}
                  trade={trade}
                  type={type}
                  activeTab="active"
                  hideDollars={hideDollars}
                  isExpanded={expandedTradeId === trade.id}
                  onToggleExpand={() => setExpandedTradeId(expandedTradeId === trade.id ? null : trade.id)}
                  onShare={() => setShareTrade({ trade, type, roe: trade.roe || 0, pnl: trade.unrealized_pnl || 0 })}
                />
              ))}
            </div>
          );
        })()}
      </div>
    );
  };

  const renderFreeColumn = (type: 'crypto' | 'stock') => {
    const isCrypto = type === 'crypto';
    const accentColor = isCrypto ? 'text-cyan-400' : 'text-amber-400';
    const typeSignals = activeSignals.filter((s: any) => isCrypto ? s.symbol && s.symbol.includes('/') : s.symbol && !s.symbol.includes('/'));
    const sortedSignals = [...typeSignals].sort((a, b) => (b.pnl_pct || 0) - (a.pnl_pct || 0));
    const typeStrategies = freeStats.filter((s: any) => isCrypto ? !s.name.toLowerCase().includes('pullback') : s.name.toLowerCase().includes('pullback'));

    return (
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-white flex items-center gap-2 mb-2">
          {isCrypto ? '🪙 Crypto Free Signals' : '📈 Stock Free Signals'}
        </h2>

        {typeStrategies.length > 0 && (
          <div className="space-y-3 mt-4">
            {typeStrategies.map((s: any, idx: number) => (
              <div key={idx} className="bg-[#1b1f2c]/50 border border-white/5 rounded-xl p-4">
                <h3 className="font-bold text-white text-sm mb-2">{s.name}</h3>
                <div className="text-sm space-y-1">
                  <p className="text-gray-400">• Win Rate: <span className={accentColor + " font-medium"}>{(s.win_rate || 0).toFixed(1)}%</span> ({s.wins} W | {s.losses} L)</p>
                  <p className="text-gray-400">• Realized PnL: <span className={`font-medium ${s.realized_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{s.realized_pct >= 0 ? '+' : ''}{(s.realized_pct || 0).toFixed(2)}%</span></p>
                  <p className="text-gray-400">• Unrealized PnL: <span className={`font-medium ${(s.unrealized_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{(s.unrealized_pct || 0) >= 0 ? '+' : ''}{(s.unrealized_pct || 0).toFixed(2)}%</span></p>
                  <p className="text-gray-400">• Active Signals: <span className={accentColor + " font-medium"}>{s.active_count}</span></p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between pt-4">
          <h3 className="font-bold text-white flex items-center gap-2">
             🛰️ Active Signals <span className="text-sm text-gray-500 font-normal">({typeSignals.length})</span>
          </h3>
        </div>

        <div className="space-y-3">
          {signalsLoading ? (
            <div className="text-center py-8 flex flex-col items-center justify-center">
              <Loader2 className="animate-spin text-cyan-400 size-8 mb-3 mx-auto" />
              <p className="text-sm text-gray-400 animate-pulse">Your Sherpa is scouting the market for live signals...</p>
            </div>
          ) : sortedSignals.length === 0 ? (
            <div className="text-center py-8">
               <p className="text-sm text-gray-400">No active {type} signals</p>
            </div>
          ) : (
            sortedSignals.map((s: any, idx: number) => (
               <div key={idx} className="bg-[#1b1f2c]/50 border border-white/5 rounded-xl p-3 flex justify-between items-center">
                 <div>
                   <div className="font-bold text-white text-sm">{s.symbol?.split('/')[0]} <span className="text-xs text-gray-500">{s.side?.toUpperCase()}</span></div>
                   <div className="text-xs text-gray-400">{s.strategy}</div>
                 </div>
                 <div className={`text-sm font-bold ${s.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                   {s.pnl_pct >= 0 ? '+' : ''}{(s.pnl_pct || 0).toFixed(2)}%
                 </div>
               </div>
            ))
          )}
        </div>

        <div className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-2xl px-5 py-5 shadow-lg relative overflow-hidden group mt-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2 mb-2">
            <Settings size={18} className="text-gray-400" /> Exchange Not Connected
          </h3>
          <p className="text-sm text-gray-400 mb-4 leading-relaxed">
            Connect your {type} exchange API to get automated trading and personalized portfolio tracking. Until then, you can view the free Alpha Signals.
          </p>
          <button 
            onClick={() => {
              const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
              navigate(isPremium ? '/settings' : '/premium');
              window.scrollTo(0, 0);
            }}
            className="w-full py-2.5 bg-white/5 border border-white/10 text-white font-bold text-xs tracking-wider rounded-xl hover:bg-white/10 transition-colors"
          >
            CONNECT {isCrypto ? 'CRYPTO' : 'STOCK'} EXCHANGE
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="flex-1 w-full flex flex-col">
      {/* Mobile Tab Toggle */}
      <div className="flex justify-center md:hidden mb-4">
        <div className="bg-[#1b1f2c]/80 backdrop-blur-md p-1 rounded-xl border border-white/5 inline-flex shadow-xl">
          <button
            onClick={() => setTab('crypto')}
            className={`px-5 py-1.5 rounded-lg text-sm font-bold transition-all ${activeTab === 'crypto' ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/20' : 'text-gray-400 hover:text-white'}`}
          >
            Crypto
          </button>
          <button
            onClick={() => setTab('stock')}
            className={`px-5 py-1.5 rounded-lg text-sm font-bold transition-all ${activeTab === 'stock' ? 'bg-amber-500 text-white shadow-lg shadow-amber-500/20' : 'text-gray-400 hover:text-white'}`}
          >
            Stocks
          </button>
        </div>
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in w-full max-w-7xl mx-auto">
        {(isDesktop || activeTab === 'crypto') && (
          <div className="w-full">
            {(!user?.has_exchange_keys) ? renderFreeColumn('crypto') : renderColumn('crypto', cryptoData, cryptoSignalCount)}
          </div>
        )}
        {(isDesktop || activeTab === 'stock') && (
          <div className="w-full">
            {(!user?.has_alpaca_keys) ? renderFreeColumn('stock') : renderColumn('stock', stockData, stockSignalCount)}
          </div>
        )}
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
          type={shareStat.type}
          roe={shareStat.stat.realized_pct}
          pnl={shareStat.stat.realized_pct}
          onClose={() => setShareStat(null)}
        />
      )}
    </div>
  );
};

export default Dashboard;
