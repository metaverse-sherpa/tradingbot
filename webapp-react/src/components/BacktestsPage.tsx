import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PlayCircle, Settings2, BarChart2, Loader2, ArrowUpRight, ArrowDownRight, Target, Activity, ChevronDown } from 'lucide-react';
import api from '../lib/api';
import { useAuthStore } from '../store/useStore';

const CustomSelect = ({ value, onChange, options }: { value: string, onChange: (v: string) => void, options: string[] }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button 
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-[#1f2028] border border-[#2e303a] rounded-xl px-4 py-3 text-white flex justify-between items-center focus:outline-none focus:border-cyan-500 transition-colors"
      >
        {value}
        <ChevronDown size={16} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 w-full mt-2 bg-[#1f2028] border border-[#2e303a] rounded-xl shadow-xl overflow-y-auto max-h-48">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => { onChange(opt); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-white/5 transition-colors ${value === opt ? 'text-cyan-400 font-bold bg-white/5' : 'text-gray-300'}`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const BacktestsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { user } = useAuthStore();
  
  const allStrategies = ["Valkyrie Elite Scalper", "Sherpa Velocity Pullback", "Mean Reversion Scalper"];
  const disabledStrategies = user?.disabled_strategies || [];
  const enabledStrategies = allStrategies.filter(s => !disabledStrategies.includes(s));
  
  const defaultStrategy = searchParams.get('strategy') || enabledStrategies[0] || 'Valkyrie Elite Scalper';
  
  const [strategy, setStrategy] = useState(defaultStrategy);
  const [period, setPeriod] = useState(() => {
    const isStock = defaultStrategy === 'Sherpa Velocity Pullback';
    return isStock ? 'Last 5 Years' : 'Last 3 Years';
  });
  const [capital, setCapital] = useState(10000);
  const [riskPct, setRiskPct] = useState(() => {
    const riskParam = searchParams.get('risk');
    return riskParam ? Number(riskParam) : 1.5;
  });
  
  useEffect(() => {
    if (!user) return;
    const isStock = strategy === 'Sherpa Velocity Pullback';
    const defaultRisk = isStock ? (user.stock_risk_pct ?? 1.5) : (user.risk_pct ?? 1.5);
    
    // If we have a risk param in the URL, prioritize that on first load
    const riskParam = searchParams.get('risk');
    if (riskParam && strategy === defaultStrategy) {
      setRiskPct(Number(riskParam));
    } else {
      setRiskPct(defaultRisk);
    }
    
    // Reset the period when the strategy changes
    setPeriod(isStock ? 'Last 5 Years' : 'Last 3 Years');
  }, [strategy, user, searchParams, defaultStrategy]);
  
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    setResults(null);
    
    try {
      const response = await api.post('/backtest/run', {
        strategy,
        capital,
        risk_pct: riskPct,
        period,
      });
      
      if (response.data?.status === 'success') {
        setResults(response.data.result);
      } else {
        setError(response.data?.error || 'Failed to run backtest');
      }
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || 'Failed to run backtest');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-8">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-[#f3f4f6]">Backtester</h2>
          <p className="text-gray-400 mt-2">Simulate strategy performance over historical market data.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Configuration Panel */}
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg h-fit space-y-6">
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            <Settings2 size={20} className="text-cyan-400" /> Configuration
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Strategy</label>
              <CustomSelect 
                value={strategy}
                onChange={setStrategy}
                options={enabledStrategies}
              />
            </div>
            
            <div>
              <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Time Period</label>
              <CustomSelect 
                value={period}
                onChange={setPeriod}
                options={["Last 1 Year", "Last 3 Years", "Last 5 Years"]}
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Initial Capital ($)</label>
              <input 
                type="number" 
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value))}
                className="w-full bg-[#1f2028] border border-[#2e303a] rounded-xl px-4 py-3 text-white focus:outline-none focus:border-cyan-500 transition-colors" 
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest">Risk % per trade</label>
                <span className="text-sm font-bold text-cyan-400">{riskPct.toFixed(1)}%</span>
              </div>
              <input 
                type="range" 
                min="0.1" 
                max="5" 
                step="0.1"
                value={riskPct}
                onChange={(e) => setRiskPct(Number(e.target.value))}
                className="w-full accent-cyan-500 h-2 bg-[#1f2028] rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {error && (
              <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm p-3 rounded-xl">
                {error}
              </div>
            )}

            <button 
              onClick={runBacktest}
              disabled={loading}
              className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-3 px-4 rounded-xl shadow-lg transition-all flex items-center justify-center gap-2 mt-4">
              {loading ? <Loader2 size={18} className="animate-spin" /> : <PlayCircle size={18} />} 
              {loading ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>

        {/* Results Panel */}
        <div className="lg:col-span-2 space-y-6">
          {loading ? (
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg min-h-[400px] flex flex-col items-center justify-center">
              <div className="relative w-16 h-16 mb-4">
                <div className="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                <div className="absolute inset-0 border-4 border-cyan-400 rounded-full border-t-transparent animate-spin"></div>
              </div>
              <p className="text-gray-400 animate-pulse text-center max-w-md mt-4">
                Simulating strategy over historical data...
              </p>
            </div>
          ) : results ? (
            <div className="space-y-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-gray-400 uppercase mb-1 flex items-center gap-1"><Activity size={14} /> Net PnL</p>
                  <p className={`text-xl font-bold ${results.net_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'} flex items-center`}>
                    {results.net_pnl >= 0 ? <ArrowUpRight size={20} className="mr-1" /> : <ArrowDownRight size={20} className="mr-1" />}
                    {formatCurrency(Math.abs(results.net_pnl))} ({results.net_pnl >= 0 ? '+' : ''}{results.pnl_pct}%)
                  </p>
                </div>
                <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-gray-400 uppercase mb-1 flex items-center gap-1"><Target size={14} /> Win Rate</p>
                  <p className={`text-xl font-bold ${results.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {results.win_rate}%
                  </p>
                </div>
                <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-gray-400 uppercase mb-1">Max Drawdown</p>
                  <p className="text-xl font-bold text-rose-400">
                    -{results.max_drawdown}%
                  </p>
                </div>
                <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-xl p-4">
                  <p className="text-xs text-gray-400 uppercase mb-1">Total Trades</p>
                  <p className="text-xl font-bold text-white">
                    {results.total_trades}
                  </p>
                </div>
              </div>
              
              <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-4 shadow-lg flex justify-center items-center">
                <img src={results.chart_url} alt="Backtest Equity Curve" className="w-full h-auto max-h-[600px] object-contain rounded-lg shadow-md" />
              </div>
            </div>
          ) : (
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg min-h-[400px] flex flex-col items-center justify-center border-dashed">
              <BarChart2 size={48} className="text-gray-600 mb-4" />
              <p className="text-gray-400 text-center max-w-md">
                Configure parameters on the left and click "Run Backtest" to generate performance metrics and equity curves.
              </p>
            </div>
          )}
        </div>

      </div>

    </div>
  );
};

export default BacktestsPage;
