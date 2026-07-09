import React from 'react';
import { Map, ZoomIn } from 'lucide-react';
import architectureInfographic from '/architecture_infographic.webp';

const LoginMarketingContent: React.FC = () => {


  return (
    <div className="w-full max-w-md lg:max-w-none lg:flex-1 mx-auto flex flex-col gap-6 h-full justify-between">
      {/* System Architecture */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 space-y-3 relative overflow-hidden group hover:border-[#3cd7ff]/20 transition-all shadow-lg flex-1 flex flex-col justify-center">
        <h3 className="font-bold text-white text-base flex items-center gap-2">
          <Map size={20} className="text-[#3cd7ff]" />
          System Architecture
        </h3>
        <div 
          className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-square flex items-center justify-center cursor-zoom-in group/img shadow-lg"
          onClick={() => window.open(architectureInfographic, '_blank')}
        >
          <img src={architectureInfographic} alt="System Architecture Infographic" width={1024} height={1024} className="w-full h-full object-cover aspect-square" />
          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/img:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <ZoomIn size={24} className="text-white" />
            <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Infographic</span>
          </div>
        </div>
        <p className="text-[11px] text-gray-300 leading-relaxed text-center">
          Click the image to view the high-resolution architecture diagram.
        </p>
      </div>

      {/* Tiers */}
      <section className="grid grid-cols-1 gap-4">
        {/* Standard Tier Card */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 space-y-2.5 relative overflow-hidden group hover:border-[#3cd7ff]/20 transition-all shadow-lg">
          <div className="flex justify-between items-center">
            <span className="text-xs px-2.5 py-1 rounded-full bg-white/5 text-gray-300 font-bold border border-white/10">🥈 Standard Tier</span>
            <span className="text-xs text-[#3cd7ff] font-bold">100% Free</span>
          </div>
          <h3 className="font-bold text-white text-base flex items-center gap-2">📡 Real-Time Alpha Signals</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            Receive institutional setups via our Webapp dashboard or instantly in our Telegram alerts. Learn strategies, audit results, and execute manually with zero cost.
          </p>
        </div>
        
        {/* Premium Tier Card */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border-t-2 border-t-[#3cd7ff]/40 border-l border-r border-b border-white/5 space-y-2.5 relative overflow-hidden group hover:shadow-[0_0_20px_rgba(60,215,255,0.15)] transition-all shadow-lg">
          <div className="flex justify-between items-center">
            <span className="text-xs px-2.5 py-1 rounded-full bg-[#3cd7ff]/15 text-[#3cd7ff] font-bold border border-[#3cd7ff]/20">💎 Premium Tier</span>
            <span className="text-xs text-[#ffdb3c] font-bold">Automated Autopilot</span>
          </div>
          <h3 className="font-bold text-white text-base flex items-center gap-2">🤖 Hands-Free Autopilot</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            Connect your exchange (Blofin, Bitget, MEXC, BingX, Binance, Alpaca) to automatically execute every signal. Features dynamic risk controls and optional leverage up to 20x.
          </p>
        </div>
      </section>



    </div>
  );
};

export default LoginMarketingContent;
