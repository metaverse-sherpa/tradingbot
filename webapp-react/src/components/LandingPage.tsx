import React from 'react';
import { ArrowRight, Clock, Shield, BarChart3, Gift, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] text-center space-y-10 md:space-y-12 px-6 md:px-0">
      
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
          <h3 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Set It & Forget It</h3>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Connect your exchange once, pick your risk level, and walk away. Sherpa monitors the markets around the clock and trades for you automatically.</p>
        </div>
        
        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <Shield size={28} className="text-emerald-400 mb-3 md:mb-4" />
          <h3 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Built-In Risk Management</h3>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Every trade has a pre-set take-profit and stop-loss. Your downside is capped before you ever enter a position — so one bad trade can't wipe out your wins.</p>
        </div>

        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <BarChart3 size={28} className="text-emerald-400 mb-3 md:mb-4" />
          <h3 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Daily Performance Updates</h3>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Get daily and weekly reports delivered straight to your inbox and Telegram. See exactly what Sherpa traded, how much you gained, and what's still open.</p>
        </div>

        <div className="bg-[#1b1f2c]/50 p-5 md:p-6 rounded-2xl border border-white/5">
          <Gift size={28} className="text-purple-400 mb-3 md:mb-4" />
          <h3 className="text-lg md:text-xl font-bold text-white mb-1.5 md:mb-2">Free Signals, Zero Commitment</h3>
          <p className="text-sm md:text-base text-gray-400 leading-relaxed">Not ready to go full autopilot? Our free tier gives you every signal — entry, direction, and strategy — so you can trade manually and see the results before upgrading.</p>
        </div>
      </div>

      <div className="bg-gradient-to-r from-purple-500/10 to-indigo-500/10 p-6 md:p-8 rounded-2xl border border-purple-500/20">
        <Sparkles size={32} className="text-purple-400 mb-3 md:mb-4" />
        <h3 className="text-xl md:text-2xl font-black text-white mb-2 uppercase tracking-wide">AI-Powered Portfolio Audits</h3>
        <p className="text-sm md:text-lg text-gray-300 leading-relaxed max-w-4xl">
          Import your existing stock and crypto holdings and let our advanced Gemini AI instantly audit your portfolio. 
          Get a comprehensive health score, real-time sentiment analysis from the latest news, and a personalized 
          step-by-step action plan to optimize your investments.
        </p>
      </div>
      </div>

    </div>
  );
};

export default LandingPage;
