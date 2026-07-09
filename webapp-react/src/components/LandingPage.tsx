import React from 'react';
import { ArrowRight, Clock, Shield, BarChart3, Gift, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  const orgSchemaData = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "Metaverse Sherpa",
    "url": "https://tradingbot.metaversesherpa.io",
    "sameAs": [
      "https://x.com/metaversesherpa",
      "https://github.com/metaversesherpa"
    ],
    "founder": {
      "@type": "Person",
      "name": "John Giles",
      "sameAs": [
        "https://www.linkedin.com/in/johngiles"
      ]
    }
  };

  return (
    <div className="flex flex-col items-center min-h-[calc(100vh-8rem)] text-center space-y-10 md:space-y-12 px-6 md:px-0 py-10 pb-24 pt-10 md:pt-20">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(orgSchemaData) }} />
      <div className="space-y-5 md:space-y-6 max-w-3xl">
        <h1 className="text-3xl md:text-7xl font-bold text-white leading-tight">
          Your Money. Working Harder. <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">24/7.</span>
        </h1>
        <p className="text-base md:text-xl text-gray-400 leading-relaxed">
          Sherpa finds high-probability trade setups across crypto and stocks — then executes them automatically while you sleep, travel, or live your life.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 md:gap-4 w-full sm:w-auto">
        <button 
          onClick={() => navigate('/dashboard')}
          className="w-full sm:w-auto bg-[#3cd7ff] hover:bg-white text-black px-6 py-3 md:px-8 md:py-4 rounded-xl font-bold text-sm md:text-lg shadow-[0_0_20px_rgba(60,215,255,0.4)] transition-all flex justify-center items-center gap-2 uppercase tracking-wider"
        >
          Enter App <ArrowRight size={20} />
        </button>
        <button 
          onClick={() => navigate('/strategies')}
          className="w-full sm:w-auto bg-transparent border-2 border-[#3cd7ff] text-[#3cd7ff] hover:bg-[#3cd7ff]/10 px-6 py-3 md:px-8 md:py-4 rounded-xl font-bold text-sm md:text-lg transition-all uppercase tracking-wider flex justify-center items-center"
        >
          View Strategies
        </button>
      </div>

      <div className="w-full max-w-6xl mt-10 md:mt-16 text-left space-y-4 md:space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 w-full">
          <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <Clock size={28} className="text-cyan-400 mb-3 md:mb-4" />
          <h2 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Set It & Forget It</h2>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Connect your exchange once, pick your risk level, and walk away. Sherpa monitors the markets around the clock and trades for you automatically.</p>
        </div>
        
        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <Shield size={28} className="text-emerald-400 mb-3 md:mb-4" />
          <h2 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Built-In Risk Management</h2>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Every trade has a pre-set take-profit and stop-loss. Your downside is capped before you ever enter a position — so one bad trade can't wipe out your wins.</p>
        </div>

        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <BarChart3 size={28} className="text-emerald-400 mb-3 md:mb-4" />
          <h2 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Daily Performance Updates</h2>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Get daily and weekly reports delivered straight to your inbox and Telegram. See exactly what Sherpa traded, how much you gained, and what's still open.</p>
        </div>

        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <Gift size={28} className="text-purple-400 mb-3 md:mb-4" />
          <h2 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Free Signals, Zero Commitment</h2>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Not ready to go full autopilot? Our free tier gives you every signal — entry, direction, and strategy — so you can trade manually and see the results before upgrading.</p>
        </div>
      </div>

      <div className="bg-gradient-to-r from-purple-500/10 to-indigo-500/10 p-6 md:p-8 rounded-2xl border border-purple-500/20">
        <div className="flex flex-col xl:flex-row items-center gap-8">
          <div className="flex-1">
            <Sparkles size={32} className="text-purple-400 mb-3 md:mb-4" />
            <h2 className="text-xl md:text-2xl font-black text-white mb-2 uppercase tracking-wide">AI-Powered Portfolio Audits</h2>
            <p className="text-sm md:text-lg text-gray-300 leading-relaxed max-w-2xl">
              Import your existing stock and crypto holdings and let our advanced Gemini AI instantly audit your portfolio. 
              Get a comprehensive health score, real-time sentiment analysis from the latest news, and a personalized 
              step-by-step action plan to optimize your investments.
            </p>
          </div>
          
          <div className="w-full xl:w-[500px] flex-shrink-0">
            {/* Mock Dashboard UI */}
            <div className="bg-[#131620] border border-white/5 rounded-xl p-4 shadow-2xl relative overflow-hidden transform transition-transform hover:scale-[1.02] duration-300">
              
              {/* Header */}
              <div className="flex items-center justify-between mb-4 pb-3 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-rose-500"></div>
                  <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                  <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                </div>
                <div className="px-3 py-1 bg-purple-500/20 text-purple-400 text-[10px] font-bold rounded-md flex items-center gap-1 uppercase tracking-wider">
                  <Sparkles size={12} /> AI Analysis
                </div>
              </div>

              {/* Health Banner */}
              <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 mb-4 flex items-center gap-3">
                <div className="text-2xl flex-shrink-0">🏆</div>
                <div>
                  <h3 className="text-white font-black text-xs uppercase tracking-wider">Portfolio Health Audited!</h3>
                  <p className="text-[10px] text-gray-400 mt-0.5">Current health score: <span className="text-emerald-400 font-bold">65/100</span> (from 60/100, <span className="text-emerald-400">+5 pts</span>)</p>
                </div>
              </div>
              
              {/* Action Plan */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-black text-gray-400 uppercase tracking-widest">Recommended Action Plan</span>
                </div>
                
                <div className="bg-[#1f2028] border border-[#2e303a] rounded-lg p-2.5 flex items-start gap-2.5">
                  <div className="w-4 h-4 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-[9px] font-bold flex-shrink-0 mt-0.5">1</div>
                  <p className="text-[11px] text-gray-300 leading-tight">Sell all holdings in defensive assets like bonds (AGG) and gold (GLD).</p>
                </div>
                
                <div className="bg-[#1f2028] border border-[#2e303a] rounded-lg p-2.5 flex items-start gap-2.5">
                  <div className="w-4 h-4 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-[9px] font-bold flex-shrink-0 mt-0.5">2</div>
                  <p className="text-[11px] text-gray-300 leading-tight">Reduce exposure to conservative stocks and dividend-focused ETFs (PG, SCHD, VIG).</p>
                </div>
                
                <div className="bg-[#1f2028] border border-[#2e303a] rounded-lg p-2.5 flex items-start gap-2.5 relative">
                  <div className="absolute inset-x-0 bottom-0 h-full bg-gradient-to-t from-[#131620] to-transparent pointer-events-none" />
                  <div className="w-4 h-4 rounded-full bg-cyan-500/20 text-cyan-400 flex items-center justify-center text-[9px] font-bold flex-shrink-0 mt-0.5">3</div>
                  <p className="text-[11px] text-gray-300 leading-tight">Reallocate capital from sales into high-conviction growth stocks or growth-oriented ETFs.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>

    </div>
  );
};

export default LandingPage;
