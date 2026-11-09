import React, { useState } from 'react';
import { History, ZoomIn, ChevronDown, ChevronUp, Activity } from 'lucide-react';

const ActiveStrategiesCatalog: React.FC = () => {
  const [guideExpanded, setGuideExpanded] = useState(false);

  return (
    <section className="space-y-4 w-full mt-4 lg:mt-8">
      <h3 className="text-lg text-white font-bold flex items-center justify-center lg:justify-start gap-2">
        🧪 Flagship Algorithmic Strategy
      </h3>
      
      <div className="w-full max-w-2xl mx-auto flex flex-col h-full">
        {/* Sherpa Velocity Pullback Flagship Card */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-2xl p-6 border border-white/10 transition-all duration-300 shadow-xl flex flex-col h-full">
          <div className="flex justify-between items-center mb-4">
            <h4 className="text-white text-xl font-bold flex items-center gap-2">
              📈 Sherpa Velocity Pullback
            </h4>
            <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/30 px-3 py-1 rounded-full font-bold">
              US Equities Megacap
            </span>
          </div>
          
          <div>
            <div className="flex items-center gap-2 mb-2">
              <History size={16} className="text-[#3cd7ff]" />
              <h5 className="text-xs font-bold text-[#3cd7ff] uppercase tracking-wider">5-Year Historical Backtest</h5>
            </div>
            <p className="text-xs text-gray-400 mb-4 leading-relaxed">
              These performance metrics are based on <strong>5 years of rigorous historical tick data</strong> across 37 megacap US equities via Alpaca Markets.
            </p>
            
            <div 
              className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video mb-4 flex items-center justify-center cursor-zoom-in group/chart shadow-lg"
              onClick={() => window.open('/api/charts/sherpa_equity.webp', '_blank')}
            >
              <img src="/api/charts/sherpa_equity.webp" alt="Backtest Equity Curve" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/chart:opacity-100 transition-opacity flex items-center justify-center gap-2">
                <ZoomIn size={24} className="text-white" />
                <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-[#0b0e14]/40 rounded-lg p-2.5 text-center border border-white/5">
                <div className="text-[10px] text-gray-500 uppercase">Win Rate</div>
                <div className="text-[#00e676] font-bold text-base">68.4%</div>
              </div>
              <div className="bg-[#0b0e14]/40 rounded-lg p-2.5 text-center border border-white/5">
                <div className="text-[10px] text-gray-500 uppercase">Sharpe Ratio</div>
                <div className="text-[#ffdb3c] font-bold text-base">2.14</div>
              </div>
              <div className="bg-[#0b0e14]/40 rounded-lg p-2.5 text-center border border-white/5">
                <div className="text-[10px] text-gray-500 uppercase">Total Trades</div>
                <div className="text-white font-bold text-base">766</div>
              </div>
              <div className="bg-[#0b0e14]/40 rounded-lg p-2.5 text-center border border-white/5">
                <div className="text-[10px] text-gray-500 uppercase">Max Drawdown</div>
                <div className="text-rose-500 font-bold text-base">-22.7%</div>
              </div>
            </div>
          </div>
          
          <div className="mt-4 pt-2 flex justify-center border-t border-white/5">
            <button 
              onClick={() => setGuideExpanded(!guideExpanded)}
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-xs font-bold uppercase tracking-wider py-2"
            >
              Strategy Guide & Parameters
              {guideExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>

          {guideExpanded && (
            <div className="pt-4 mt-2 border-t border-white/5 space-y-4 text-left animate-fade-in">
              <div className="rounded-xl overflow-hidden mb-4 border border-white/10 shadow-lg">
                  <img src="/api/charts/sherpa_velocity_infographic_ai.webp" alt="Sherpa Velocity Infographic" width={1024} height={1024} className="w-full aspect-square object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
              </div>
              <div className="space-y-1">
                <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Philosophy</h6>
                <p className="text-xs text-gray-300 leading-relaxed">
                  Targets short-term oversold pullback cycles on megacap US equities during robust, verified uptrends. Positions are executed with tight stop-losses and multi-day profit targets.
                </p>
              </div>
              <div className="space-y-1">
                <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Universe</h6>
                <p className="text-xs text-gray-300 leading-relaxed">
                  37 high-liquidity, large-cap US equities (AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, and select S&P leaders).
                </p>
              </div>
              
              <div className="mt-4 pt-4 border-t border-white/5">
                <div className="flex items-center gap-2 mb-3">
                  <Activity size={16} className="text-[#00e676]" />
                  <h5 className="text-xs font-bold text-[#00e676] uppercase tracking-wider">Targeted Performance</h5>
                </div>
                <div className="text-sm space-y-2 bg-[#00e676]/10 border border-[#00e676]/20 rounded-xl p-4">
                  <p className="text-gray-400">• Win Rate: <span className="text-white font-medium">68.4%</span></p>
                  <p className="text-gray-400">• Sharpe Ratio: <span className="text-white font-medium">2.14</span></p>
                  <p className="text-gray-400">• Execution Broker: <span className="text-cyan-400 font-medium">Alpaca Securities</span></p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default ActiveStrategiesCatalog;
