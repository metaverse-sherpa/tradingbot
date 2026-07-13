import React, { useState, useEffect } from 'react';
import { Lock } from 'lucide-react';
import api from '../lib/api';

const LiveActiveSignals: React.FC = () => {
  const [liveSignals, setLiveSignals] = useState<any[]>([]);

  useEffect(() => {
    const fetchSignals = async () => {
      try {
        const response = await api.get('/signals/active');
        if (response.data && Array.isArray(response.data)) {
          setLiveSignals(response.data);
        }
      } catch (err) {
        console.error("Failed to fetch signals for marketing page", err);
      }
    };
    fetchSignals();
  }, []);

  const cryptoSignals = liveSignals.filter(s => s.symbol.includes('/')).slice(0, 3);
  const stockSignals = liveSignals.filter(s => !s.symbol.includes('/')).slice(0, 3);

  const renderSignalsColumn = (signals: any[], title: string, icon: string) => (
    <div className="flex flex-col gap-4 relative w-full lg:max-w-[500px]">
      <h3 className="text-lg text-white font-bold flex items-center gap-2">{icon} {title}</h3>
      <div className="space-y-4 relative w-full">
        {signals.length === 0 ? (
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 text-center">
            <span className="text-gray-400 text-sm">Loading active market signals...</span>
          </div>
        ) : (
          signals.map((signal, idx) => {
            const pnl = signal.pnl_pct || signal.unrealized_pnl_pct || 0;
            const isLong = signal.side === 'BUY' || signal.side === 'LONG';
            const pnlColor = pnl >= 0 ? 'text-[#00e676]' : 'text-rose-400';
            const sideColor = isLong ? 'text-[#00e676] bg-[#00e676]/20' : 'text-rose-400 bg-rose-500/20';
            const sideText = isLong ? 'LONG' : 'SHORT';
            return (
              <div key={idx} className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 opacity-100 shadow-lg">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-white font-bold">
                    {signal.symbol.split('/')[0]}
                  </span>
                  <span className={`text-xs px-2 py-1 rounded ${sideColor}`}>{sideText}</span>
                </div>
                <div className="text-xs text-gray-400">Entry: <span className="blur-sm select-none text-white/50 font-mono">100.00</span></div>
                <div className="text-xs text-gray-400">Target: <span className="blur-sm select-none text-white/50 font-mono">110.00</span></div>
                <div className={`${pnlColor} font-bold mt-2`}>
                  {pnl > 0 ? '+' : ''}{pnl.toFixed(2)}% PnL
                </div>
              </div>
            );
          })
        )}
        <div className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none">
          <div 
            className="text-center bg-[#1b1f2c]/95 backdrop-blur-md border border-[#3cd7ff]/20 px-5 py-4 rounded-xl max-w-[340px] shadow-[0_0_30px_rgba(60,215,255,0.15)] pointer-events-auto transition-transform hover:scale-105 cursor-pointer"
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          >
            <p className="text-sm text-white font-bold flex items-center justify-center gap-2 mb-2">
              <Lock size={16} className="text-[#3cd7ff]" /> Trade Details Locked
            </p>
            <p className="text-xs text-gray-400 leading-relaxed">
              <span className="text-[#3cd7ff] font-bold">Create a free account</span> or sign in to unlock real-time entry targets, stop losses, and dynamic charts.
            </p>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <section className="space-y-4 w-full mt-4 lg:mt-8 mb-12">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16 w-full lg:justify-center">
        <div className="w-full flex justify-center lg:justify-end">
          {renderSignalsColumn(cryptoSignals, "Live Crypto Signals", "📡")}
        </div>
        <div className="w-full flex justify-center lg:justify-start">
          {renderSignalsColumn(stockSignals, "Live Stock Signals", "📡")}
        </div>
      </div>
    </section>
  );
};

export default LiveActiveSignals;
