import React, { useEffect } from 'react';
import { BookOpen, Shield, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';

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
      chart: "/api/charts/valkyrie_equity.webp",
      infographic: "/api/charts/valkyrie_elite_infographic_ai.webp"
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
      sharpe: "2.14",
      maxDrawdown: "-22.7%",
      netPnl: "+1,515.8%",
      finalBalance: "$161,586.43",
      chart: "/api/charts/sherpa_equity.webp",
      infographic: "/api/charts/sherpa_velocity_infographic_ai.webp"
    }
  },
  {
    name: "Custom AI Builder",
    icon: <TrendingUp className="text-cyan-400" size={24} />,
    philosophy: "Build your own custom algorithmic trading strategies by chatting with AI, uploading PineScript, or sharing chart screenshots.",
    indicators: "Anything you can imagine. Powered by Gemini AI.",
    pace: "Customizable. Works on 1m to Daily timeframes.",
    drawdown: "Backtest your ideas to see the potential drawdown and optimize with AI.",
    backtest: {
      period: "Custom Backtests",
      desc: "Simulate your strategy over historical data to evaluate its performance before going live.",
      winRate: "N/A",
      trades: "N/A",
      sharpe: "N/A",
      maxDrawdown: "N/A",
      netPnl: "N/A",
      finalBalance: "N/A",
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
          const isCrypto = strat.name.includes("Valkyrie");

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
                <Link to={isCrypto ? '/strategies/valkyrie-elite' : strat.name === "Custom AI Builder" ? '/strategies/builder' : '/strategies/sherpa-velocity'} className={`w-full py-3 rounded-xl flex items-center justify-center font-bold transition-all ${isCrypto ? 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20' : strat.name === "Custom AI Builder" ? 'bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20' : 'bg-purple-500/10 text-purple-400 hover:bg-purple-500/20'}`}>
                  {strat.name === "Custom AI Builder" ? "Build Custom Strategy" : "Explore Strategy"}
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
