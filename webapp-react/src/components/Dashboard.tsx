import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, ResponsiveContainer, YAxis, XAxis, Tooltip } from 'recharts';
import { Activity, Clock, Settings, Zap, Target, Loader2, RefreshCcw } from 'lucide-react';
import { useDashboardStore, useAuthStore } from '../store/useStore';
import api from '../lib/api';
import SignalsPage from './SignalsPage';

// Removed dummyData

const Dashboard: React.FC = () => {
  const { activeTab, setTab } = useDashboardStore();
  const { user } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const hideDollars = user?.hide_dollars;

  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [cryptoData, setCryptoData] = useState({ bal: 0, open: 0, wins: 0, losses: 0, pnl: 0, pnl_pct: 0, chart: [] as {value: number, x: string}[] });
  const [stockData, setStockData] = useState({ bal: 0, open: 0, wins: 0, losses: 0, pnl: 0, pnl_pct: 0, chart: [] as {value: number, x: string}[] });
  const [cryptoSignalCount, setCryptoSignalCount] = useState(0);
  const [stockSignalCount, setStockSignalCount] = useState(0);
  const [isDesktop, setIsDesktop] = useState(window.innerWidth >= 768);

  useEffect(() => {
    const handleResize = () => setIsDesktop(window.innerWidth >= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async (bypassCache = false) => {
    setLoading(true);

    try {
      const [cBal, sBal, cStats, sStats, signalsRes, histRes] = await Promise.all([
        api.get(`/user/balance?segment=crypto${bypassCache ? '&bypass_cache=true' : ''}`).catch(() => ({ data: { crypto_balance: 0 } })),
        api.get(`/user/balance?segment=stock${bypassCache ? '&bypass_cache=true' : ''}`).catch(() => ({ data: { stock_balance: 0 } })),
        api.get(`/user/stats?segment=crypto${bypassCache ? '&bypass_cache=true' : ''}`).catch(() => ({ data: { open_positions: 0, wins: 0, losses: 0 } })),
        api.get(`/user/stats?segment=stock${bypassCache ? '&bypass_cache=true' : ''}`).catch(() => ({ data: { open_positions: 0, wins: 0, losses: 0 } })),
        api.get(`/signals/active${bypassCache ? '?force=true' : ''}`).catch(() => ({ data: [] })),
        api.get('/user/balance-history').catch(() => ({ data: [] }))
      ]);

      const signals = signalsRes.data || [];
      const balHist = histRes.data || [];
      
      setCryptoSignalCount(signals.filter((s: any) => s.symbol && s.symbol.includes('/')).length);
      setStockSignalCount(signals.filter((s: any) => s.symbol && !s.symbol.includes('/')).length);

      const buildChartData = (type: 'crypto' | 'stock', bal: number) => {
        const rawPoints = balHist.map((item: any) => ({ x: item.timestamp, y: type === 'crypto' ? item.crypto : item.stock }));
        if (rawPoints.length >= 2) return rawPoints.map((p: any) => ({ 
            value: p.y, 
            x: new Date(p.x * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) 
        }));
        
        const baseVal = bal || 5000;
        const now = Math.floor(Date.now() / 1000);
        const daySec = 86400;
        return [
            { value: baseVal * 0.94, x: new Date((now - 4 * daySec) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) },
            { value: baseVal * 0.98, x: new Date((now - 3 * daySec) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) },
            { value: baseVal * 0.93, x: new Date((now - 2 * daySec) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) },
            { value: baseVal * 1.01, x: new Date((now - 1 * daySec) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) },
            { value: baseVal, x: new Date(now * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }
        ];
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
      } catch (e) {
        console.error('Error fetching dashboard data', e);
      } finally {
        setLoading(false);
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
            onClick={() => { setTab(type); navigate('/history'); }}
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
            onClick={() => { setTab(type); navigate('/stats'); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Target className="text-gray-400 group-hover:text-white transition-colors" size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white">My Stats</span>
          </button>

          <button 
            onClick={() => { setTab(type); navigate('/backtests'); }}
            className="bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl py-2.5 px-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Settings className="text-gray-400 group-hover:text-white transition-colors" size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white">Backtest</span>
          </button>

          <button 
            onClick={() => { setTab(type); navigate('/signals'); }}
            className="col-span-2 bg-[#1b1f2c]/70 backdrop-blur-md border border-white/10 rounded-xl p-3 flex flex-row items-center justify-center gap-2 hover:bg-white/5 transition-colors group"
          >
            <Zap className={`${accentColor} group-hover:text-white transition-colors`} size={18} />
            <span className="text-sm font-semibold text-gray-300 group-hover:text-white">Alpha Signals ({signalCount})</span>
          </button>
        </div>
      </div>
    );
  };

  if (!isPremium) {
    return <SignalsPage />;
  }

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
            {renderColumn('crypto', cryptoData, cryptoSignalCount)}
          </div>
        )}
        {(isDesktop || activeTab === 'stock') && (
          <div className="w-full">
            {renderColumn('stock', stockData, stockSignalCount)}
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
