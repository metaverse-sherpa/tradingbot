import React from 'react';
import { BookOpen, Shield, TrendingUp, History, ZoomIn } from 'lucide-react';

const strategies = [
  {
    name: "Valkyrie Elite Scalper",
    icon: <Shield className="text-emerald-400" size={24} />,
    philosophy: "Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.",
    indicators: "Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.",
    pace: "Patient and calculated. Averages ~0.68 trades/day.",
    drawdown: "Highly protected; ultra-low peak drawdown ceiling (~16.2% to 19.5% on expanded basket).",
    backtest: {
      period: "3-Year Historical Backtest",
      desc: "These performance metrics and equity curves are based on 3 years of rigorous historical data. (Simulated with $10k starting capital and a strict 1.5% risk management per trade for crypto).",
      winRate: "58%",
      trades: "747",
      sharpe: "3.86",
      maxDrawdown: "-19.5%",
      netPnl: "+240.1%",
      finalBalance: "$34,010.00",
      chart: "/api/charts/valkyrie_equity.png",
      infographic: "/api/charts/valkyrie_elite_infographic_ai.png"
    }
  },
  {
    name: "Sherpa Velocity Pullback",
    icon: <TrendingUp className="text-purple-400" size={24} />,
    philosophy: "Targets short-term oversold pullback cycles on megacap US equities during robust, verified uptrends.",
    indicators: "Daily Close > EMA(200), SuperTrend(10, 3) is UP, 4-period RSI (< 26).",
    pace: "Daily swing. Scans daily at market open (9:31 AM EST). Averages ~0.42 trades/day.",
    drawdown: "Tight 22.7% maximum drawdown with a high 68.4% win rate over a 5-year period.",
    backtest: {
      period: "5-Year Historical Backtest",
      desc: "These performance metrics are based on 5 years of rigorous historical data. (Simulated with $10k starting capital on US Equities).",
      winRate: "68.4%",
      trades: "766",
      sharpe: "-",
      maxDrawdown: "-22.7%",
      netPnl: "-",
      finalBalance: "-",
      chart: "",
      infographic: ""
    }
  }
];

const StrategiesPage: React.FC = () => {
  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8 p-4 md:p-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Strategy Guides</h2>
          <p className="text-gray-400 mt-2">Learn about the logic behind our automated trading engines.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8">
        {strategies.map((strat, idx) => (
          <div key={idx} className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-8 shadow-lg">
            <div className="flex items-center gap-4 mb-6">
              <div className="p-4 bg-[#131620] rounded-xl shadow-inner border border-white/5">
                {strat.icon}
              </div>
              <h3 className="text-2xl font-bold text-white">{strat.name}</h3>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="space-y-6">
                <div>
                  <h4 className="text-xs text-gray-400 uppercase tracking-widest font-bold mb-2 flex items-center gap-2">
                    <BookOpen size={14}/> Philosophy
                  </h4>
                  <p className="text-gray-300 leading-relaxed text-sm">{strat.philosophy}</p>
                </div>
                <div>
                  <h4 className="text-xs text-gray-400 uppercase tracking-widest font-bold mb-2">Indicators Used</h4>
                  <p className="text-gray-300 leading-relaxed text-sm">{strat.indicators}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/5">
                  <div>
                    <h4 className="text-xs text-cyan-400 uppercase tracking-widest font-bold mb-2">Execution Pace</h4>
                    <p className="text-gray-300 text-sm">{strat.pace}</p>
                  </div>
                  <div>
                    <h4 className="text-xs text-emerald-400 uppercase tracking-widest font-bold mb-2">Drawdown Profile</h4>
                    <p className="text-gray-300 text-sm">{strat.drawdown}</p>
                  </div>
                </div>
                
                {strat.backtest.infographic && (
                   <div className="pt-4 border-t border-white/5">
                     <img src={strat.backtest.infographic} alt="Infographic" className="w-full rounded-xl border border-white/10" onError={(e) => e.currentTarget.style.display = 'none'} />
                   </div>
                )}
              </div>
              
              {/* Backtest Section */}
              <div className="bg-[#0b0e14]/40 p-6 rounded-xl border border-white/5">
                <div className="flex items-center gap-2 mb-2">
                  <History size={18} className="text-[#3cd7ff]" />
                  <h5 className="text-sm font-bold text-[#3cd7ff] uppercase tracking-wider">{strat.backtest.period}</h5>
                </div>
                <p className="text-xs text-gray-400 mb-6 leading-relaxed">
                  {strat.backtest.desc}
                </p>
                
                {strat.backtest.chart && (
                  <div 
                    className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-video mb-6 flex items-center justify-center cursor-zoom-in group/chart shadow-lg"
                    onClick={() => window.open(strat.backtest.chart, '_blank')}
                  >
                    <img src={strat.backtest.chart} alt="Backtest Equity Curve" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/chart:opacity-100 transition-opacity flex items-center justify-center gap-2">
                      <ZoomIn size={24} className="text-white" />
                      <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Chart</span>
                    </div>
                  </div>
                )}
                
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase font-bold">Win Rate</div>
                    <div className="text-[#00e676] font-bold text-lg">{strat.backtest.winRate}</div>
                  </div>
                  <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase font-bold">Total Trades</div>
                    <div className="text-white font-bold text-lg">{strat.backtest.trades}</div>
                  </div>
                  {strat.backtest.sharpe !== "-" && (
                    <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                      <div className="text-[10px] text-gray-500 uppercase font-bold">Sharpe Ratio</div>
                      <div className="text-[#ffdb3c] font-bold text-lg">{strat.backtest.sharpe}</div>
                    </div>
                  )}
                  <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase font-bold">Max Drawdown</div>
                    <div className="text-rose-500 font-bold text-lg">{strat.backtest.maxDrawdown}</div>
                  </div>
                  {strat.backtest.netPnl !== "-" && (
                    <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                      <div className="text-[10px] text-gray-500 uppercase font-bold">Net PnL</div>
                      <div className="text-[#00e676] font-bold text-lg">{strat.backtest.netPnl}</div>
                    </div>
                  )}
                  {strat.backtest.finalBalance !== "-" && (
                    <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                      <div className="text-[10px] text-gray-500 uppercase font-bold">Final Balance</div>
                      <div className="text-white font-bold text-lg">{strat.backtest.finalBalance}</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default StrategiesPage;
