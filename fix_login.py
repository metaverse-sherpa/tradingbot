import re

with open("webapp-react/src/components/LoginMarketingContent.tsx", "r") as f:
    content = f.read()

# 1 & 2. Fix Architecture image
content = content.replace("import api from '../lib/api';", "import api from '../lib/api';\nimport architectureImg from '../assets/architecture_infographic.png';")
content = content.replace("window.open('/architecture_infographic.png', '_blank')", "window.open(architectureImg, '_blank')")
content = content.replace('src="/architecture_infographic.png"', 'src={architectureImg}')

# 3. Add Stock Strategy
sherpa_strategy = """

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
"""

content = content.replace("</section>\n\n      {/* Live Active Signals Teaser */}", sherpa_strategy + "\n      </section>\n\n      {/* Live Active Signals Teaser */}")

# 4. Update blur logic for active signals
content = content.replace("const blurLevel = idx === 0 ? 'blur-[2px]' : idx === 1 ? 'blur-[3px]' : 'blur-[4px]';", "")
content = content.replace("const opacity = idx === 0 ? 'opacity-50' : idx === 1 ? 'opacity-30' : 'opacity-20';", "")
content = content.replace("className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 ${opacity} ${blurLevel}`}", "className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/5 rounded-xl p-4 opacity-100`}")
content = content.replace('<div className="text-xs text-gray-400">Entry: Locked</div>', '<div className="text-xs text-gray-400">Entry: <span className="blur-sm select-none text-white/50 font-mono">Locked</span></div>')
content = content.replace('<div className="text-xs text-gray-400">Target: Locked</div>', '<div className="text-xs text-gray-400">Target: <span className="blur-sm select-none text-white/50 font-mono">Locked</span></div>')

with open("webapp-react/src/components/LoginMarketingContent.tsx", "w") as f:
    f.write(content)

