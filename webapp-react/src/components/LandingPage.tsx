import React from 'react';
import { ArrowRight, Activity, Shield, Zap } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] text-center space-y-12">
      
      <div className="space-y-6 max-w-3xl">
        <h1 className="text-5xl md:text-7xl font-bold text-white leading-tight">
          Next-Gen <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">Automated</span> Trading
        </h1>
        <p className="text-xl text-gray-400 leading-relaxed">
          The MetaVerse Sherpa engine provides institutional-grade trading algorithms for retail traders.
          Connect your exchange, select your strategy, and let the AI do the heavy lifting.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto px-6 sm:px-0">
        <button 
          onClick={() => navigate('/dashboard')}
          className="w-full sm:w-auto bg-[#3cd7ff] hover:bg-white text-black px-6 py-3 md:px-8 md:py-4 rounded-xl font-bold text-base md:text-lg shadow-[0_0_20px_rgba(60,215,255,0.4)] transition-all flex justify-center items-center gap-2 uppercase tracking-wider"
        >
          Enter App <ArrowRight size={20} />
        </button>
        <button 
          onClick={() => navigate('/strategies')}
          className="w-full sm:w-auto bg-transparent border-2 border-[#3cd7ff] text-[#3cd7ff] hover:bg-[#3cd7ff]/10 px-6 py-3 md:px-8 md:py-4 rounded-xl font-bold text-base md:text-lg transition-all uppercase tracking-wider flex justify-center items-center"
        >
          View Strategies
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 w-full max-w-5xl mt-16 text-left">
        <div className="bg-[#1b1f2c]/50 p-6 rounded-2xl border border-white/5">
          <Zap size={32} className="text-yellow-400 mb-4" />
          <h3 className="text-xl font-bold text-white mb-2">Lightning Fast</h3>
          <p className="text-gray-400">Our Rust and Python engines process market data in milliseconds, executing trades before retail indicators even blink.</p>
        </div>
        
        <div className="bg-[#1b1f2c]/50 p-6 rounded-2xl border border-white/5">
          <Shield size={32} className="text-emerald-400 mb-4" />
          <h3 className="text-xl font-bold text-white mb-2">Capital Protection</h3>
          <p className="text-gray-400">Advanced risk management dynamically scales position sizes and stop-losses to protect your principal capital.</p>
        </div>

        <div className="bg-[#1b1f2c]/50 p-6 rounded-2xl border border-white/5">
          <Activity size={32} className="text-cyan-400 mb-4" />
          <h3 className="text-xl font-bold text-white mb-2">Live Insights</h3>
          <p className="text-gray-400">Watch your portfolio grow with real-time updates pushed directly to your dashboard via WebSockets.</p>
        </div>
      </div>

    </div>
  );
};

export default LandingPage;
