import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart2, Share2, Beaker, RefreshCcw } from 'lucide-react';
import api from '../lib/api';
import LoadingDisplay from './LoadingDisplay';
import SharePnLModal from './SharePnLModal';
import { useDashboardStore } from '../store/useStore';

const StatsPage: React.FC = () => {
  const navigate = useNavigate();

  const [shareStat, setShareStat] = useState<{stat: any, type: string} | null>(null);
  const { activeTab: categoryTab, setTab: setCategoryTab } = useDashboardStore();
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





  // Removed performance rendering logic to simplify the page

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
            Alpha Signal Stats
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
