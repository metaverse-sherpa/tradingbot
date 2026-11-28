import React, { useEffect } from 'react';
import { BookOpen, TrendingUp, Lightbulb } from 'lucide-react';
import { Link } from 'react-router-dom';

const strategies = [
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
      sharpe: "2.14",
      maxDrawdown: "-22.7%",
      netPnl: "+1,515.8%",
      finalBalance: "$161,586.43",
      chart: "/api/charts/sherpa_equity.webp",
      infographic: "/api/charts/sherpa_velocity_infographic_ai.webp"
    }
  },
  {
    name: "AI Recommendations Autopilot",
    icon: <Lightbulb className="text-cyan-400" size={24} />,
    philosophy: "Autonomous quantitative multi-factor crypto allocation focused on Conservative & Income. Uses LLM-synthesized macro regime analysis, strict 2:1 risk-reward criteria, and technical support levels.",
    indicators: "Macro Regime Analysis + Support/Resistance Zones + Mathematical 2:1 R:R Filter + 52-Week Range Metrics.",
    pace: "Daily rotation. Recommendations evaluated daily at 01:00 AM EST with immediate market entry.",
    drawdown: "Conservative leverage (2-3x max) with stop losses mathematically placed strictly above liquidation prices.",
    backtest: {
      period: "Forward-Tested Live Performance",
      desc: "Live tracked performance of Conservative & Income AI Crypto recommendations across forward-tested market cycles.",
      winRate: "63.0%",
      trades: "39",
      sharpe: "3.42",
      maxDrawdown: "-12.4%",
      netPnl: "+186.4%",
      finalBalance: "$28,640.00",
      chart: "",
      infographic: ""
    }
  }
];

const StrategiesPage: React.FC = () => {

  useEffect(() => {
    document.title = "Automated Trading Strategy Guides | Metaverse Sherpa";
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute('content', "Explore our proprietary algorithmic trading strategies for crypto and equities. Discover the philosophy, backtests, and performance metrics.");
    }
  }, []);

  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8 p-4 md:p-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-[#f3f4f6]">Strategy Guides</h1>
          <p className="text-gray-400 mt-2">Learn about the logic behind our automated trading engines.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {strategies.map((strat, idx) => {
          const isRecommendations = strat.name === "AI Recommendations Autopilot";

          return (
            <div key={idx} className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-8 shadow-lg flex flex-col h-full">
              <div className="flex items-center gap-4 mb-6">
                <div className="p-4 bg-[#131620] rounded-xl shadow-inner border border-white/5">
                  {strat.icon}
                </div>
                <h2 className="text-2xl font-bold text-white">{strat.name}</h2>
              </div>
              
              <div className="flex-1 space-y-6">
                <div>
                  <h3 className="text-xs text-gray-400 uppercase tracking-widest font-bold mb-2 flex items-center gap-2">
                    <BookOpen size={14}/> Overview
                  </h3>
                  <p className="text-gray-300 leading-relaxed text-sm">{strat.philosophy}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-white/5">
                   <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                     <div className="text-[10px] text-gray-500 uppercase font-bold">Win Rate</div>
                     <div className="text-[#00e676] font-bold text-lg">{strat.backtest.winRate}</div>
                   </div>
                   <div className="bg-[#1b1f2c]/50 rounded-lg p-3 text-center border border-white/5">
                     <div className="text-[10px] text-gray-500 uppercase font-bold">Net PnL</div>
                     <div className="text-[#00e676] font-bold text-lg">{strat.backtest.netPnl}</div>
                   </div>
                </div>
              </div>

              <div className="mt-8 pt-6 border-t border-white/5">
                <Link 
                  to={isRecommendations ? '/recommendations' : '/strategies/sherpa-velocity'} 
                  className={`w-full py-3 rounded-xl flex items-center justify-center font-bold transition-all ${isRecommendations ? 'bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20' : 'bg-purple-500/10 text-purple-400 hover:bg-purple-500/20'}`}
                >
                  {isRecommendations ? "View Recommendations Hub" : "Explore Strategy"}
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default StrategiesPage;
