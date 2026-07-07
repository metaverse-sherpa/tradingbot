import React, { useState, useEffect } from 'react';
import { Map, ZoomIn, Lock, ChevronDown, ChevronUp, History, Activity } from 'lucide-react';
import api from '../lib/api';
import architectureImg from '../assets/architecture_infographic.png';

const LoginMarketingContent: React.FC = () => {
  const [guideExpanded, setGuideExpanded] = useState(false);
  const [liveSignals, setLiveSignals] = useState<any[]>([]);

  useEffect(() => {
    const fetchSignals = async () => {
      try {
        const response = await api.get('/signals/active');
        if (response.data && Array.isArray(response.data)) {
          setLiveSignals(response.data.slice(0, 3));
        }
      } catch (err) {
        console.error("Failed to fetch signals for marketing page", err);
      }
    };
    fetchSignals();
  }, []);

  return (
    <div className="w-full max-w-md mx-auto flex flex-col gap-6 mt-8 mb-12">
      {/* System Architecture */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 space-y-3 relative overflow-hidden group hover:border-[#3cd7ff]/20 transition-all shadow-lg">
        <h3 className="font-bold text-white text-base flex items-center gap-2">
          <Map size={20} className="text-[#3cd7ff]" />
          System Architecture
        </h3>
        <div 
          className="relative overflow-hidden rounded-xl border border-white/10 bg-black/40 aspect-square flex items-center justify-center cursor-zoom-in group/img shadow-lg"
          onClick={() => window.open(architectureImg, '_blank')}
        >
          <img src={architectureImg} alt="System Architecture Infographic" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/img:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <ZoomIn size={24} className="text-white" />
            <span className="text-xs text-white font-bold uppercase tracking-wider">Expand Infographic</span>
          </div>
        </div>
        <p className="text-[11px] text-gray-400 leading-relaxed text-center">
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
          <h3 className="font-bold text-white text-base flex items-center gap-2">🤖 Zero-Latency Execution</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            Connect exchange APIs (Blofin, Bitget, MEXC, BingX, Binance, Alpaca) to automatically execute every signal with zero latency. Features advanced risk mitigation, Bollinger Bands, volatility squeezes, and up to 20x leverage.
          </p>
        </div>
      </section>

      {/* Strategies Catalog */}
      <section className="space-y-4">
        <h3 className="text-lg text-white font-bold flex items-center gap-2">🧪 Active Strategies Catalog</h3>
        
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 transition-all duration-300 shadow-lg">
          <div className="flex justify-between items-center mb-4">
            <h4 className="text-white text-lg font-bold flex items-center gap-2">
              🛡️ Valkyrie Elite Scalper
            </h4>
          </div>
          
          {/* Backtest Results */}
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
              onClick={() => window.open('/api/charts/valkyrie_equity.png', '_blank')}
            >
              <img src="/api/charts/valkyrie_equity.png" alt="Backtest Equity Curve" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
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
                 <img src="/api/charts/valkyrie_elite_infographic_ai.png" alt="Valkyrie Infographic" className="w-full h-auto object-cover" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
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
      

        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl rounded-xl p-5 border border-white/5 transition-all duration-300 shadow-lg mt-4">
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
          
          <div className="pt-4 mt-4 border-t border-white/5 space-y-4 text-left">
              <div className="space-y-1">
                <h6 className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Philosophy</h6>
                <p className="text-xs text-gray-300 leading-relaxed">
                  Targets short-term oversold pullback cycles on megacap US equities during robust, verified uptrends.
                </p>
              </div>
          </div>
        </div>

      </section>

      {/* Live Active Signals Teaser */}
      <section className="space-y-4 relative mt-2">
        <h3 className="text-lg text-white font-bold flex items-center gap-2">📡 Live Active Signals</h3>
        <div className="space-y-4 relative">
          {liveSignals.length === 0 ? (
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 opacity-50 blur-[2px] text-center">
              <span className="text-gray-400 text-sm">Loading active market signals...</span>
            </div>
          ) : (
            liveSignals.map((signal, idx) => {
              
              
              const pnlColor = (signal.unrealized_pnl_pct || 0) >= 0 ? 'text-[#00e676]' : 'text-rose-400';
              const sideColor = signal.side === 'BUY' ? 'text-[#00e676] bg-[#00e676]/20' : 'text-rose-400 bg-rose-500/20';
              const sideText = signal.side === 'BUY' ? 'LONG' : 'SHORT';
              const isCrypto = signal.symbol.includes('/');
              let linkUrl = '';
              if (isCrypto) {
                // Ensure it formats to /currency/<symbol>USDT without doubling USDT and removing slashes/hyphens
                const baseSymbol = signal.symbol.replace(/:.*$/, '').replace(/[\/-]/g, '').replace(/USDT?$/i, '').replace(/USD$/i, '');
                linkUrl = `https://marketmasters.ai/currency/${baseSymbol}USDT`;
              } else {
                linkUrl = `https://marketmasters.ai/stocks/${signal.symbol}`;
              }
              
              return (
                <div key={idx} className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 opacity-100`}>
                  <div className="flex justify-between items-center mb-2">
                    <a 
                      href={linkUrl} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="text-white font-bold hover:text-[#3cd7ff] transition-colors underline decoration-white/30 underline-offset-2"
                    >
                      {signal.symbol.split('/')[0]}
                    </a>
                    <span className={`text-xs px-2 py-1 rounded ${sideColor}`}>{sideText}</span>
                  </div>
                  <div className="text-xs text-gray-400">Entry: <span className="blur-sm select-none text-white/50 font-mono">Locked</span></div>
                  <div className="text-xs text-gray-400">Target: <span className="blur-sm select-none text-white/50 font-mono">Locked</span></div>
                  <div className={`${pnlColor} font-bold mt-2`}>
                    {(signal.unrealized_pnl_pct || 0) > 0 ? '+' : ''}{(signal.unrealized_pnl_pct || 0).toFixed(2)}% PnL
                  </div>
                </div>
              );
            })
          )}

          <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#0b0e14] via-[#0b0e14]/90 to-transparent flex flex-col justify-end items-center pb-4 z-20 pointer-events-none">
            <div className="text-center bg-[#1b1f2c]/90 border border-[#3cd7ff]/20 backdrop-blur-md px-5 py-4 rounded-xl max-w-[340px] shadow-lg pointer-events-auto shadow-[0_0_20px_rgba(60,215,255,0.1)]">
              <p className="text-sm text-white font-bold flex items-center justify-center gap-2 mb-2">
                <Lock size={16} className="text-[#3cd7ff]" /> Trade Details Locked
              </p>
              <p className="text-xs text-gray-400 leading-relaxed">
                <span className="text-[#3cd7ff] font-bold">Create a free account</span> or sign in to unlock real-time entry targets, stop losses, and dynamic charts.
              </p>
            </div>
          </div>
        </div>
      </section>

    </div>
  );
};

export default LoginMarketingContent;
