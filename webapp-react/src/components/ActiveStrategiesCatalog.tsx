import React, { useState } from 'react';
import { History, ZoomIn, ChevronDown, ChevronUp, Activity } from 'lucide-react';

const ActiveStrategiesCatalog: React.FC = () => {
  const [guideExpanded, setGuideExpanded] = useState(false);
  const [guideExpanded2, setGuideExpanded2] = useState(false);

  return (
    <section className="space-y-4 w-full mt-4 lg:mt-8">
      <h3 className="text-lg text-white font-bold flex items-center justify-center lg:justify-start gap-2">
        🧪 Active Strategies Catalog
      </h3>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16 w-full lg:justify-center">
        {/* Left Column Strategy: Valkyrie */}
        <div className="w-full max-w-[420px] mx-auto lg:mr-0 flex flex-col h-full">
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 transition-all duration-300 shadow-lg flex flex-col h-full">
            <div className="flex justify-between items-center mb-4">
              <h4 className="text-white text-lg font-bold flex items-center gap-2">
                🛡️ Valkyrie Elite Scalper
              </h4>
            </div>
            
            <div>
              <div className="flex items-center gap-2 mb-2">
                <History size={16} className="text-[#3cd7ff]" />
                <h5 className="text-xs font-bold text-[#3cd7ff] uppercase tracking-wider">3-Year Historical Backtest</h5>
              </div>
              <p className="text-[10px] text-gray-400 mb-4 leading-relaxed">
                These performance metrics and equity curves are based on <strong>3 years of rigorous historical data</strong>. (Simulated with $10k starting capital and a strict 1.5% risk management per trade for crypto).
              </p>
              
              <div 
                className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video mb-4 flex items-center justify-center cursor-zoom-in group/chart shadow-lg"
                onClick={() => window.open('/api/charts/valkyrie_equity.webp', '_blank')}
              >
                <img src="/api/charts/valkyrie_equity.webp" alt="Backtest Equity Curve" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/chart:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  <ZoomIn size={24} className="text-white" />
                  <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
                </div>
              </div>
              
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Win Rate</div>
                  <div className="text-[#00e676] font-bold text-sm">58%</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Total Trades</div>
                  <div className="text-white font-bold text-sm">747</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Sharpe Ratio</div>
                  <div className="text-[#ffdb3c] font-bold text-sm">3.86</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Max Drawdown</div>
                  <div className="text-rose-500 font-bold text-sm">-19.5%</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Net PnL</div>
                  <div className="text-[#00e676] font-bold text-sm">+240.1%</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Final Balance</div>
                  <div className="text-white font-bold text-sm">$34,010.00</div>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-2 flex justify-center border-t border-white/5">
              <button 
                onClick={() => setGuideExpanded(!guideExpanded)}
                className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-xs font-bold uppercase tracking-wider py-2"
              >
                Strategy Guide & Live Stats
                {guideExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>

            {guideExpanded && (
              <div className="pt-4 mt-2 border-t border-white/5 space-y-4 text-left animate-fade-in">
                <div className="rounded-xl overflow-hidden mb-4 border border-white/10 shadow-lg">
                    <img src="/api/charts/valkyrie_elite_infographic_ai.webp" alt="Valkyrie Infographic" width={1024} height={1024} className="w-full aspect-square object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                </div>
                <div className="space-y-1">
                  <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Philosophy</h6>
                  <p className="text-xs text-gray-300 leading-relaxed">
                    Wick Rejection. Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.
                  </p>
                </div>
                <div className="space-y-1">
                  <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Indicators</h6>
                  <p className="text-xs text-gray-300 leading-relaxed">
                    Bollinger Bands + Volatility Squeeze + Wick piercing
                  </p>
                </div>
                
                <div className="mt-4 pt-4 border-t border-white/5">
                  <div className="flex items-center gap-2 mb-3">
                    <Activity size={16} className="text-[#00e676]" />
                    <h5 className="text-xs font-bold text-[#00e676] uppercase tracking-wider">Live Signal Stats</h5>
                  </div>
                  <div className="text-sm space-y-2 bg-[#00e676]/10 border border-[#00e676]/20 rounded-xl p-4">
                    <p className="text-gray-400">• Win Rate: <span className="text-white font-medium">88.4%</span> (14,892 Trades)</p>
                    <p className="text-gray-400">• Realized PnL: <span className="text-[#00e676] font-medium">+15.2%</span></p>
                    <p className="text-gray-400">• Active Signals: <span className="text-white font-medium">12</span></p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Column Strategy: Sherpa */}
        <div className="w-full lg:max-w-[500px] lg:mx-0 flex flex-col h-full">
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 transition-all duration-300 shadow-lg flex flex-col h-full">
            <div className="flex justify-between items-center mb-4">
              <h4 className="text-white text-lg font-bold flex items-center gap-2">
                📈 Sherpa Velocity Pullback
              </h4>
            </div>
            
            <div>
              <div className="flex items-center gap-2 mb-2">
                <History size={16} className="text-[#3cd7ff]" />
                <h5 className="text-xs font-bold text-[#3cd7ff] uppercase tracking-wider">5-Year Historical Backtest</h5>
              </div>
              <p className="text-[10px] text-gray-400 mb-4 leading-relaxed">
                These performance metrics are based on <strong>5 years of rigorous historical data</strong>. (Simulated with $10k starting capital on US Equities).
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

              <div className="grid grid-cols-2 gap-2">
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Win Rate</div>
                  <div className="text-[#00e676] font-bold text-sm">68.4%</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Total Trades</div>
                  <div className="text-white font-bold text-sm">766</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Pace</div>
                  <div className="text-white font-bold text-sm">0.42/day</div>
                </div>
                <div className="bg-[#0b0e14]/40 rounded-lg p-2 text-center border border-white/5">
                  <div className="text-[9px] text-gray-500 uppercase">Max Drawdown</div>
                  <div className="text-rose-500 font-bold text-sm">-22.7%</div>
                </div>
              </div>
            </div>
            
            <div className="mt-4 pt-2 flex justify-center border-t border-white/5">
              <button 
                onClick={() => setGuideExpanded2(!guideExpanded2)}
                className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-xs font-bold uppercase tracking-wider py-2"
              >
                Strategy Guide & Live Stats
                {guideExpanded2 ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
            </div>

            {guideExpanded2 && (
              <div className="pt-4 mt-2 border-t border-white/5 space-y-4 text-left animate-fade-in">
                <div className="rounded-xl overflow-hidden mb-4 border border-white/10 shadow-lg">
                    <img src="/api/charts/sherpa_velocity_infographic_ai.webp" alt="Sherpa Velocity Infographic" width={1024} height={1024} className="w-full aspect-square object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                </div>
                <div className="space-y-1">
                  <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Philosophy</h6>
                  <p className="text-xs text-gray-300 leading-relaxed">
                    Targets short-term oversold pullback cycles on megacap US equities during robust, verified uptrends.
                  </p>
                </div>
                
                <div className="mt-4 pt-4 border-t border-white/5">
                  <div className="flex items-center gap-2 mb-3">
                    <Activity size={16} className="text-[#00e676]" />
                    <h5 className="text-xs font-bold text-[#00e676] uppercase tracking-wider">Live Signal Stats</h5>
                  </div>
                  <div className="text-sm space-y-2 bg-[#00e676]/10 border border-[#00e676]/20 rounded-xl p-4">
                    <p className="text-gray-400">• Win Rate: <span className="text-white font-medium">71.0%</span> (766 Trades)</p>
                    <p className="text-gray-400">• Realized PnL: <span className="text-[#00e676] font-medium">+24.9%</span></p>
                    <p className="text-gray-400">• Active Signals: <span className="text-white font-medium">5</span></p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};

export default ActiveStrategiesCatalog;
