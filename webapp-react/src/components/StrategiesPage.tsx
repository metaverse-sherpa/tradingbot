import React from 'react';
import { BookOpen, Shield, TrendingUp, BarChart2 } from 'lucide-react';

const strategies = [
  {
    name: "Mean Reversion Scalper",
    icon: <BarChart2 className="text-cyan-400" size={24} />,
    philosophy: "Assumes that prices that deviate excessively from the 20-period Bollinger Bands will snap back (revert) to the 200 EMA trend-line.",
    indicators: "Bollinger Bands + EMA 200 + ADX trend strength + Wilder RSI.",
    pace: "Highly active. Averages ~0.84 trades/day.",
    drawdown: "Optimized for 1.0% risk, maintaining a safe drawdown of ~21.9%.",
  },
  {
    name: "Valkyrie Elite Scalper",
    icon: <Shield className="text-emerald-400" size={24} />,
    philosophy: "Targets high-integrity trend continuation pullbacks on high-volume assets. It waits for price spikes to pierce the bands and quickly close back inside.",
    indicators: "Bollinger Bands + Volatility Squeeze + Wick piercing verification + ADX + standard RSI.",
    pace: "Patient and calculated. Averages ~0.68 trades/day.",
    drawdown: "Highly protected; ultra-low peak drawdown ceiling (~16.2% to 19.5% on expanded basket).",
  },
  {
    name: "Sherpa Velocity Pullback",
    icon: <TrendingUp className="text-purple-400" size={24} />,
    philosophy: "Targets short-term oversold pullback cycles on megacap US equities during robust, verified uptrends.",
    indicators: "Daily Close > EMA(200), SuperTrend(10, 3) is UP, 4-period RSI (< 26).",
    pace: "Daily swing. Scans daily at market open (9:31 AM EST). Averages ~0.42 trades/day.",
    drawdown: "Tight 22.7% maximum drawdown with a high 68.4% win rate over a 5-year period.",
  }
];

const StrategiesPage: React.FC = () => {
  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Strategy Guides</h2>
          <p className="text-gray-400 mt-2">Learn about the logic behind our automated trading engines.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        {strategies.map((strat, idx) => (
          <div key={idx} className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-8 shadow-lg">
            <div className="flex items-center gap-4 mb-6">
              <div className="p-4 bg-[#131620] rounded-xl shadow-inner border border-white/5">
                {strat.icon}
              </div>
              <h3 className="text-2xl font-bold text-white">{strat.name}</h3>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
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
              </div>
              
              <div className="space-y-6 bg-[#131620]/50 p-6 rounded-xl border border-white/5">
                <div>
                  <h4 className="text-xs text-cyan-400 uppercase tracking-widest font-bold mb-2">Execution Pace</h4>
                  <p className="text-gray-300 text-sm">{strat.pace}</p>
                </div>
                <div>
                  <h4 className="text-xs text-emerald-400 uppercase tracking-widest font-bold mb-2">Drawdown Profile</h4>
                  <p className="text-gray-300 text-sm">{strat.drawdown}</p>
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
