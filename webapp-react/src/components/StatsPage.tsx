import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart2, Share2, Beaker, RefreshCcw } from 'lucide-react';
import api from '../lib/api';
import LoadingDisplay from './LoadingDisplay';
import SharePnLModal from './SharePnLModal';
import { useAuthStore, useDashboardStore } from '../store/useStore';

const StatsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [shareStat, setShareStat] = useState<{stat: any, type: string} | null>(null);
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
  const hideDollars = user?.hide_dollars;
  const [userStats, setUserStats] = useState<any>(null);
  const [freeStats, setFreeStats] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStats = async (bypassCache = false) => {
    if (bypassCache || !userStats) setIsLoading(true);
    try {
      const qs = bypassCache ? '?bypass_cache=true' : '';
      const [userRes, freeRes] = await Promise.all([
        api.get(`/user/stats${qs}`),
        api.get(`/stats/free${qs}`)
      ]);
      setUserStats(userRes.data);
      setFreeStats(freeRes.data.strategies || []);
    } catch (error) {
      console.error("Failed to fetch stats", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);





  const formatCurrency = (val: number): React.ReactNode => {
    if (hideDollars) return <span className="blur-sm opacity-70 select-none pointer-events-none">$***,***.**</span>;
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val || 0);
  };

  const formatPercent = (val: number) => {
    return `${(val || 0) > 0 ? '+' : ''}${(val || 0).toFixed(2)}%`;
  };

  if (isLoading) {
    return (
      <div className="flex-1 w-full max-w-5xl mx-auto flex items-center justify-center min-h-[400px]">
        <LoadingDisplay />
      </div>
    );
  }





  const crypto = userStats?.crypto || {};
  const stock = userStats?.stock || {};

  const renderCryptoPerformance = () => (
    <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-bold text-white flex items-center gap-2">
          <span className="text-xl">🪙</span> Crypto Performance
        </h3>
        <span className="text-xs px-2.5 py-1 rounded-full bg-cyan-500/20 text-cyan-400 font-bold capitalize">
          Blofin
        </span>
      </div>
      
      <div className="grid grid-cols-3 gap-2 text-center mb-4">
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Portf Value</p>
          <p className="text-sm font-bold text-white">{formatCurrency(crypto.portfolio_value)}</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Win Rate</p>
          <p className={`text-sm font-bold ${crypto.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {(crypto.win_rate || 0).toFixed(2)}%
          </p>
          <p className="text-[10px] text-gray-500 mt-1">({crypto.wins || 0}W / {crypto.losses || 0}L)</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Cum PNL</p>
          <p className={`text-sm font-bold ${crypto.overall_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPercent(crypto.overall_pnl_pct)}
          </p>
          <p className="text-[10px] text-gray-500 mt-1">({formatCurrency(crypto.overall_pnl)})</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div 
          onClick={() => navigate('/trades?status=active&category=crypto')}
          className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center cursor-pointer hover:bg-[#1a1e2a] transition-colors"
        >
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1"># Open</p>
          <p className="text-lg font-bold text-white">{crypto.open_positions || 0}</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Unrealized PNL</p>
          <p className={`text-sm font-bold ${crypto.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatCurrency(crypto.unrealized_pnl)}
          </p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Net PNL</p>
          <p className={`text-sm font-bold ${(crypto.overall_pnl + (crypto.unrealized_pnl || 0)) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatCurrency(crypto.overall_pnl + (crypto.unrealized_pnl || 0))}
          </p>
        </div>
      </div>
    </div>
  );

  const renderStockPerformance = () => (
    <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg flex flex-col justify-between">
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-bold text-white flex items-center gap-2">
          <span className="text-xl">🦙</span> Stocks Performance
        </h3>
        <span className="text-xs px-2.5 py-1 rounded-full bg-yellow-500/20 text-yellow-500 font-bold capitalize">
          Alpaca Live
        </span>
      </div>
      
      <div className="grid grid-cols-3 gap-2 text-center mb-4">
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Portf Value</p>
          <p className="text-sm font-bold text-white">{formatCurrency(stock.portfolio_value)}</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Win Rate</p>
          <p className={`text-sm font-bold ${stock.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {(stock.win_rate || 0).toFixed(2)}%
          </p>
          <p className="text-[10px] text-gray-500 mt-1">({stock.wins || 0}W / {stock.losses || 0}L)</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Cum PNL</p>
          <p className={`text-sm font-bold ${stock.overall_pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatPercent(stock.overall_pnl_pct)}
          </p>
          <p className="text-[10px] text-gray-500 mt-1">({formatCurrency(stock.overall_pnl)})</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div 
          onClick={() => navigate('/trades?status=active&category=stock')}
          className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center cursor-pointer hover:bg-[#1a1e2a] transition-colors"
        >
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1"># Open</p>
          <p className="text-lg font-bold text-white">{stock.open_positions || 0}</p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Unrealized PNL</p>
          <p className={`text-sm font-bold ${stock.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatCurrency(stock.unrealized_pnl)}
          </p>
        </div>
        <div className="bg-[#131620] rounded-xl p-3 flex flex-col justify-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">Net PNL</p>
          <p className={`text-sm font-bold ${(stock.overall_pnl + stock.unrealized_pnl) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {formatCurrency(stock.overall_pnl + stock.unrealized_pnl)}
          </p>
        </div>
      </div>
    </div>
  );

  const cryptoFreeStats = freeStats.filter(s => !s.name.includes('Sherpa'));
  const stockFreeStats = freeStats.filter(s => s.name.includes('Sherpa'));

  const renderFreeStatCard = (stat: any, idx: number) => (
    <div key={idx} className="flex flex-col">
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg flex-1">
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
            onClick={() => setShareStat({ stat, type: categoryTab })}
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
    </div>
  );

  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8">
      
      {/* Institutional Performance Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold text-[#f3f4f6] flex items-center gap-2">
            <BarChart2 className="text-cyan-400" />
            Institutional Performance
          </h2>
          <button
            onClick={() => fetchStats(true)}
            className="text-gray-400 hover:text-white transition-colors"
            title="Refresh Stats"
          >
            <RefreshCcw size={20} className={isLoading ? "animate-spin text-white" : ""} />
          </button>
        </div>

        {/* Mobile Category Tab */}
        <div className="md:hidden w-full mb-6">
          <div className="bg-[#1b1f2c]/50 rounded-full p-1 flex border border-white/5 max-w-sm mx-auto">
            <button
              onClick={() => setCategoryTab('crypto')}
              className={`flex-1 py-1.5 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'crypto' ? 'bg-cyan-500 text-white shadow-[0_0_12px_rgba(34,211,238,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Crypto
            </button>
            <button
              onClick={() => setCategoryTab('stock')}
              className={`flex-1 py-1.5 text-center rounded-full text-sm font-bold transition-all ${categoryTab === 'stock' ? 'bg-amber-500 text-white shadow-[0_0_12px_rgba(245,158,11,0.4)]' : 'text-gray-400 hover:text-gray-200'}`}
            >
              Stocks
            </button>
          </div>
        </div>

        {/* Mobile View */}
        <div className="md:hidden w-full space-y-8">
          {categoryTab === 'crypto' ? (
            <>
              {isPremium && renderCryptoPerformance()}
              {cryptoFreeStats.length > 0 && (
                <div>
                  <h2 className="text-xl font-bold text-[#f3f4f6] flex items-center gap-2 mb-4">
                    <Beaker className="text-emerald-400" />
                    Crypto Alpha Signals
                  </h2>
                  <div className="space-y-6">
                    {cryptoFreeStats.map((stat, idx) => renderFreeStatCard(stat, idx))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {isPremium && renderStockPerformance()}
              {stockFreeStats.length > 0 && (
                <div>
                  <h2 className="text-xl font-bold text-[#f3f4f6] flex items-center gap-2 mb-4">
                    <Beaker className="text-emerald-400" />
                    Stocks Alpha Signals
                  </h2>
                  <div className="space-y-6">
                    {stockFreeStats.map((stat, idx) => renderFreeStatCard(stat, idx))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Desktop View */}
        <div className="hidden md:grid md:grid-cols-2 gap-6">
          <div className="space-y-8">
            {isPremium && renderCryptoPerformance()}
            {cryptoFreeStats.length > 0 && (
              <div>
                <h2 className="text-xl font-bold text-[#f3f4f6] flex items-center gap-2 mb-4">
                  <Beaker className="text-emerald-400" />
                  Crypto Alpha Signals
                </h2>
                <div className="space-y-6">
                  {cryptoFreeStats.map((stat, idx) => renderFreeStatCard(stat, idx))}
                </div>
              </div>
            )}
          </div>
          <div className="space-y-8">
            {isPremium && renderStockPerformance()}
            {stockFreeStats.length > 0 && (
              <div>
                <h2 className="text-xl font-bold text-[#f3f4f6] flex items-center gap-2 mb-4">
                  <Beaker className="text-emerald-400" />
                  Stocks Alpha Signals
                </h2>
                <div className="space-y-6">
                  {stockFreeStats.map((stat, idx) => renderFreeStatCard(stat, idx))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {shareStat && (
        <SharePnLModal
          stat={shareStat.stat}
          type={shareStat.type as any}
          onClose={() => setShareStat(null)}
        />
      )}
    </div>
  );
};

export default StatsPage;
