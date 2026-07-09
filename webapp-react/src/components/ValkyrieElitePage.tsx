import React, { useState, useEffect } from 'react';
import { Shield, History, ZoomIn, Activity, BookOpen } from 'lucide-react';
import { Link } from 'react-router-dom';
import api from '../lib/api';

const ValkyrieElitePage: React.FC = () => {
  const [stat, setStat] = useState<any>(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await api.get('/stats/free');
        const s = (res.data?.strategies || []).find((s: any) => s.name === "Valkyrie Elite Scalper");
        setStat(s);
      } catch (e) {
        console.error('Failed to fetch stats', e);
      }
    };
    fetchStats();
  }, []);

  const schemaData = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Valkyrie Elite Scalper",
    "applicationCategory": "FinanceApplication",
    "operatingSystem": "Web",
    "offers": {
      "@type": "Offer",
      "price": "149.00",
      "priceCurrency": "USD"
    }
  };

  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8 p-4 md:p-8">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaData) }} />
      <div className="mb-8">
        <Link to="/strategies" className="text-[#3cd7ff] hover:underline mb-4 inline-block">&larr; Back to Strategies</Link>
        <h2 className="text-3xl font-bold text-[#f3f4f6] flex items-center gap-3">
          <Shield className="text-emerald-400" size={32} />
          Valkyrie Elite Scalper
        </h2>
        <p className="text-gray-400 mt-2">Targets high-integrity trend continuation pullbacks on high-volume assets.</p>
      </div>

      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-8 shadow-lg">
        <h3 className="text-2xl font-bold text-white mb-6">How does the Valkyrie Elite Scalper strategy minimize drawdown?</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
          <div>
            <h4 className="text-xs text-gray-400 uppercase tracking-widest font-bold mb-2 flex items-center gap-2">
              <BookOpen size={14}/> Philosophy
            </h4>
            <p className="text-gray-300 text-sm">Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.</p>
          </div>
          <div>
            <h4 className="text-xs text-gray-400 uppercase tracking-widest font-bold mb-2">Indicators Used</h4>
            <p className="text-gray-300 text-sm">Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.</p>
          </div>
          <div>
            <h4 className="text-xs text-cyan-400 uppercase tracking-widest font-bold mb-2">Execution Pace</h4>
            <p className="text-gray-300 text-sm">Patient and calculated. Averages ~0.68 trades/day.</p>
          </div>
          <div>
            <h4 className="text-xs text-emerald-400 uppercase tracking-widest font-bold mb-2">Drawdown Profile</h4>
            <p className="text-gray-300 text-sm">Highly protected; ultra-low peak drawdown ceiling (~16.2% to 19.5% on expanded basket).</p>
          </div>
        </div>

        <img src="/api/charts/valkyrie_elite_infographic_ai.png" alt="Valkyrie Elite Infographic" className="w-full rounded-xl border border-white/10 mb-8" onError={(e) => e.currentTarget.style.display = 'none'} />

        <div className="bg-[#0b0e14]/40 p-6 rounded-xl border border-white/5">
          <div className="flex items-center gap-2 mb-2">
            <History size={18} className="text-[#3cd7ff]" />
            <h3 className="text-xl font-bold text-white">What is the win rate of the Valkyrie Elite Scalper strategy?</h3>
          </div>
          <p className="text-xs text-gray-400 mb-6">These performance metrics and equity curves are based on 3 years of rigorous historical data. (Simulated with $10k starting capital and a strict 1.5% risk management per trade for crypto).</p>
          
          <div 
            className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video mb-6 flex items-center justify-center cursor-zoom-in group/chart shadow-lg"
            onClick={() => window.open("/api/charts/valkyrie_equity.png", '_blank')}
          >
            <img src="/api/charts/valkyrie_equity.png" alt="Backtest Equity Curve" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/chart:opacity-100 transition-opacity flex items-center justify-center gap-2">
              <ZoomIn size={24} className="text-white" />
              <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
            </div>
          </div>
          
          <div className="overflow-x-auto mb-6">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="py-3 px-4 text-xs text-gray-500 uppercase font-bold">Metric</th>
                  <th className="py-3 px-4 text-xs text-gray-500 uppercase font-bold">Performance Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Win Rate</td>
                  <td className="py-3 px-4 text-[#00e676] font-bold">58%</td>
                </tr>
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Total Trades</td>
                  <td className="py-3 px-4 text-white font-bold">747</td>
                </tr>
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Sharpe Ratio</td>
                  <td className="py-3 px-4 text-[#ffdb3c] font-bold">3.86</td>
                </tr>
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Max Drawdown</td>
                  <td className="py-3 px-4 text-rose-500 font-bold">-19.5%</td>
                </tr>
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Net PnL</td>
                  <td className="py-3 px-4 text-[#00e676] font-bold">+240.1%</td>
                </tr>
                <tr className="bg-[#1b1f2c]/30 hover:bg-[#1b1f2c]/50 transition-colors">
                  <td className="py-3 px-4 text-sm text-gray-300 font-medium">Final Balance</td>
                  <td className="py-3 px-4 text-white font-bold">$34,010.00</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          {stat && (
            <div className="bg-[#1b1f2c]/50 rounded-xl p-5 mt-6 border border-white/5">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={18} className="text-cyan-400" />
                <h5 className="text-sm font-bold text-cyan-400 uppercase tracking-wider">Live Alpha Stats</h5>
              </div>
              <div className="text-sm space-y-1.5">
                <p className="text-gray-400">• Win Rate: <span className="text-cyan-400 font-medium">{(stat.win_rate || 0).toFixed(1)}%</span> ({stat.wins} W | {stat.losses} L)</p>
                <p className="text-gray-400">• Realized PnL: <span className={`font-medium ${stat.realized_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{stat.realized_pct >= 0 ? '+' : ''}{(stat.realized_pct || 0).toFixed(2)}%</span></p>
                <p className="text-gray-400">• Unrealized PnL: <span className={`font-medium ${(stat.unrealized_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{(stat.unrealized_pct || 0) >= 0 ? '+' : ''}{(stat.unrealized_pct || 0).toFixed(2)}%</span></p>
                <p className="text-gray-400">• Active Signals: <span className="text-cyan-400 font-medium">{stat.active_count}</span></p>
              </div>
            </div>
          )}

          <div className="mt-8 pt-6 border-t border-white/10 text-center">
            <Link 
              to="/premium"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-gradient-to-r from-[#3cd7ff] to-[#0099ff] text-white font-bold rounded-xl shadow-lg hover:shadow-cyan-500/25 transition-all hover:-translate-y-0.5 w-full md:w-auto"
            >
              Unlock Strategy with Premium
            </Link>
            <p className="text-xs text-gray-500 mt-3">Full access to Valkyrie Elite Scalper is included in the Premium subscription.</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ValkyrieElitePage;
