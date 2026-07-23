import React, { useState, useEffect, useRef } from 'react';
import { Paperclip, Send } from 'lucide-react';
import api from '../lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  strategyConfig?: any;
  metrics?: any;
  showSaveButton?: boolean;
}

const StrategyBuilderPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('Create a strategy for me that scalps crypto on the 1h timeframe using your most advanced indicators to generate a win rate >55%, drawdown<25%, average trades/day > 0.5 and pnl>100% using 20x leverage and 2% of my account balance.');
  const [isLoading, setIsLoading] = useState(false);
  const [backtestStatus, setBacktestStatus] = useState<any>(null);
  const [lastStrategyConfig, setLastStrategyConfig] = useState<any>(null);
  const [lastMetrics, setLastMetrics] = useState<any>(null);
  const [savedStrategyNames, setSavedStrategyNames] = useState<Set<string>>(new Set());
  const [file, setFile] = useState<File | null>(null);
  const [isAutoOptimizeEnabled, setIsAutoOptimizeEnabled] = useState(false);
  const optimizationAttempts = useRef<number>(0);
  const MAX_ATTEMPTS = 5;
  const messagesRef = useRef<Message[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollIntervalRef = useRef<any>(null);

  useEffect(() => {
    messagesRef.current = messages;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSaveStrategy = async (configToSave?: any, metricsToSave?: any) => {
    const targetConfig = configToSave || lastStrategyConfig;
    const targetMetrics = metricsToSave || lastMetrics;
    if (!targetConfig) {
      alert("No active strategy configuration found to save.");
      return;
    }
    const stratName = targetConfig?.name || 'Custom Strategy';
    try {
      await api.post('/custom-strategies/save', {
        name: stratName,
        asset_type: targetConfig?.asset_type || 'crypto',
        timeframe: targetConfig?.timeframe || '1h',
        config: targetConfig,
        metrics: targetMetrics
      });
      setSavedStrategyNames((prev) => new Set(prev).add(stratName));
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `✅ Strategy "${stratName}" has been successfully saved to your profile!`
      }]);
    } catch (e) {
      console.error('Failed to save strategy', e);
      alert('Failed to save strategy.');
    }
  };

  const handleSend = async (customPrompt?: string | React.MouseEvent | React.KeyboardEvent) => {
    const isCustom = typeof customPrompt === 'string';
    if (!isCustom && !input.trim() && !file) return;

    let userMsg = isCustom ? (customPrompt as string) : input;
    if (!isCustom && file) userMsg += ` [Attached: ${file.name}]`;

    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    if (!isCustom) setInput('');
    setIsLoading(true);

    // Auto-detect user save request in chat
    const isSaveQuery = /\b(save|add to profile|store strategy|save strategy)\b/i.test(userMsg);
    if (!isCustom && isSaveQuery && lastStrategyConfig) {
      handleSaveStrategy(lastStrategyConfig, lastMetrics);
    }

    try {
      const formData = new FormData();
      formData.append('prompt', userMsg);
      formData.append('history', JSON.stringify(messagesRef.current.map(m => ({ role: m.role, content: m.content })))); 
      if (!isCustom && file) formData.append('file', file);

      const res = await api.post('/custom-strategies/chat', formData);

      const currentConfig = res.data.strategy_config || lastStrategyConfig;
      setMessages((prev) => [...prev, { 
        role: 'assistant', 
        content: res.data.reply,
        strategyConfig: currentConfig,
        metrics: lastMetrics,
        showSaveButton: Boolean(currentConfig && currentConfig.name)
      }]);
      
      if (res.data.strategy_config) {
        setLastStrategyConfig(res.data.strategy_config);
      }

      // If AI recommends a backtest, trigger it
      if (res.data.requires_backtest && res.data.strategy_config) {
        triggerBacktest(res.data.strategy_config, res.data.asset_type);
      }
    } catch (e) {
      console.error(e);
      optimizationAttempts.current = 0; // Stop auto-optimize loop on error
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Sorry, something went wrong. Auto-optimize stopped.' }]);
    } finally {
      setIsLoading(false);
      setFile(null);
    }
  };

  const triggerBacktest = async (strategy_config: any, asset_type: string) => {
    try {
      const res = await api.post('/custom-strategies/backtest/trigger', { strategy_config, asset_type });
      if (res.data.task_id) {
        setLastStrategyConfig(strategy_config);
        setBacktestStatus({ task_id: res.data.task_id, status: 'pending' });
        startPolling(res.data.task_id);
      }
    } catch (e) {
      console.error("Failed to trigger backtest", e);
    }
  };

  const startPolling = (taskId: string) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await api.get(`/custom-strategies/backtest/status/${taskId}`);
        if (res.data.status === 'completed' || res.data.status === 'error' || res.data.status === 'failed') {
          clearInterval(pollIntervalRef.current);
          setBacktestStatus(res.data);
          
          if (res.data.status === 'completed') {
             const currentConfig = res.data.result?.config || lastStrategyConfig;
             const currentMetrics = res.data.result?.metrics;
             setLastStrategyConfig(currentConfig); 
             setLastMetrics(currentMetrics);

             const winRate = currentMetrics?.win_rate ?? 0;
             const totalTrades = currentMetrics?.total_trades ?? 0;
             const pnlPct = currentMetrics?.pnl_pct ?? 0;
             const maxDd = currentMetrics?.max_dd_pct ?? 0;
             const profitFactor = currentMetrics?.profit_factor ?? 0;
             
             const isTargetMet = winRate >= 60 && totalTrades >= 5;

             const newMsgs: Message[] = [
                 { 
                     role: 'assistant', 
                     content: `Backtest completed! Results: Win Rate ${winRate.toFixed(2)}%, PnL ${pnlPct.toFixed(2)}%, Trades: ${totalTrades}, Max DD: ${maxDd.toFixed(2)}%, PF: ${profitFactor.toFixed(2)}`,
                     strategyConfig: currentConfig,
                     metrics: currentMetrics,
                     showSaveButton: true
                 }
             ];

             if (isTargetMet) {
                 newMsgs.push({
                     role: 'assistant',
                     content: `🎯 Target metrics achieved! Win Rate: ${winRate.toFixed(2)}% (${totalTrades} trades). Would you like to save "${currentConfig?.name || 'Custom Strategy'}" to your profile?`,
                     strategyConfig: currentConfig,
                     metrics: currentMetrics,
                     showSaveButton: true
                 });
             }

             setMessages((prev) => [...prev, ...newMsgs]);

             if (isAutoOptimizeEnabled && optimizationAttempts.current < MAX_ATTEMPTS) {
                 if (!isTargetMet) {
                     optimizationAttempts.current += 1;
                     const hiddenPrompt = `System Note: Optimization iteration ${optimizationAttempts.current}/${MAX_ATTEMPTS}. Backtest results: Win Rate: ${winRate.toFixed(2)}%, PnL: ${pnlPct.toFixed(2)}%, Total Trades: ${totalTrades}, Max Drawdown: ${maxDd.toFixed(2)}%, Profit Factor: ${profitFactor.toFixed(2)}. Target: > 60% win rate, > 5 trades. You MUST change at least 2 parameters. Consider: ${winRate < 45 ? 'widening SL to give trades more room' : 'increasing TP for better risk/reward'}, ${totalTrades < 5 ? 'removing a condition or switching from crossover to simple comparison' : 'trying a different strategy archetype entirely'}. Generate the improved strategy_config and set requires_backtest to true.`;
                     setTimeout(() => handleSend(hiddenPrompt), 1000);
                 } else {
                     optimizationAttempts.current = 0; // Success!
                 }
             } else {
                 optimizationAttempts.current = 0; // Stop tracking if disabled or max reached
             }
          } else if (res.data.status === 'failed' || res.data.status === 'error') {
             setMessages((prev) => [...prev, { 
                 role: 'assistant', 
                 content: `Backtest failed to complete: ${res.data.error || 'Unknown error'}` 
             }]);
             if (isAutoOptimizeEnabled && optimizationAttempts.current < MAX_ATTEMPTS) {
                 optimizationAttempts.current += 1;
                 const hiddenPrompt = `System Note: Backtest failed with error: ${res.data.error}. Please fix the strategy and try again.`;
                 setTimeout(() => handleSend(hiddenPrompt), 1000);
             }
          }
        } else if (res.data.status === 'running') {
          setBacktestStatus(res.data);
        }
      } catch (e) {
        console.error(e);
        clearInterval(pollIntervalRef.current);
      }
    }, 5000);
  };

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col h-[70vh] md:h-[75vh] bg-gray-900 rounded-lg p-4 border border-gray-700">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-2xl font-bold text-white">AI Strategy Builder</h2>
        {lastStrategyConfig && (
          <button 
            onClick={() => handleSaveStrategy(lastStrategyConfig, lastMetrics)} 
            disabled={savedStrategyNames.has(lastStrategyConfig?.name || 'Custom Strategy')}
            className={`px-4 py-2 rounded font-semibold shadow-lg transition-transform hover:scale-105 ${
              savedStrategyNames.has(lastStrategyConfig?.name || 'Custom Strategy')
                ? 'bg-gray-700 text-gray-300 cursor-default'
                : 'bg-green-500 hover:bg-green-400 text-white'
            }`}
          >
            {savedStrategyNames.has(lastStrategyConfig?.name || 'Custom Strategy') 
              ? '✅ Saved to Profile' 
              : `💾 Save Strategy (${lastStrategyConfig.name || 'Custom'})`}
          </button>
        )}
      </div>
      
      <div className="flex-1 overflow-y-auto mb-4 p-4 bg-gray-800 rounded-lg shadow-inner">
        {messages.map((msg, idx) => (
          <div key={idx} className={`mb-4 flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`p-3 rounded-lg max-w-[80%] ${msg.role === 'user' ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-200'}`}>
              <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
              {msg.showSaveButton && msg.strategyConfig && (
                <div className="mt-3 pt-2 border-t border-gray-600 flex items-center justify-between gap-4">
                  <span className="text-xs text-gray-400 font-mono">Strategy: {msg.strategyConfig?.name || 'Custom Strategy'}</span>
                  <button
                    onClick={() => handleSaveStrategy(msg.strategyConfig, msg.metrics)}
                    disabled={savedStrategyNames.has(msg.strategyConfig?.name || 'Custom Strategy')}
                    className={`px-3 py-1.5 rounded font-bold text-xs shadow-md transition-transform hover:scale-105 ${
                      savedStrategyNames.has(msg.strategyConfig?.name || 'Custom Strategy')
                        ? 'bg-gray-600 text-gray-300 cursor-default'
                        : 'bg-green-500 hover:bg-green-400 text-white'
                    }`}
                  >
                    {savedStrategyNames.has(msg.strategyConfig?.name || 'Custom Strategy')
                      ? '✅ Saved to Profile'
                      : '💾 Save Strategy to Profile'}
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="text-cyan-400 animate-pulse">AI is thinking...</div>
        )}
        {backtestStatus?.status === 'pending' && (
          <div className="text-yellow-400 animate-pulse mt-2">Queueing Backtest...</div>
        )}
        {backtestStatus?.status === 'running' && (
          <div className="text-cyan-400 animate-pulse mt-2">
            Running Backtest on Historical Data...
            {isAutoOptimizeEnabled && optimizationAttempts.current > 0 && ` (Optimization Attempt ${optimizationAttempts.current} of ${MAX_ATTEMPTS})`}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="flex gap-2 mb-2 items-center">
        <input 
            type="checkbox" 
            id="auto-optimize" 
            checked={isAutoOptimizeEnabled} 
            onChange={(e) => setIsAutoOptimizeEnabled(e.target.checked)}
            className="w-4 h-4 text-cyan-600 bg-gray-700 border-gray-600 rounded focus:ring-cyan-500"
        />
        <label htmlFor="auto-optimize" className="text-gray-300 text-sm font-semibold cursor-pointer">
            Auto-Optimize Strategy (Target: &gt; 60% Win Rate)
        </label>
      </div>

      <div className="flex gap-2 items-end">
        <input
          type="file"
          id="file-upload"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          accept="image/*,.txt,.pine"
        />
        <label htmlFor="file-upload" className="bg-gray-700 hover:bg-gray-600 text-white p-2 rounded cursor-pointer flex items-center justify-center shrink-0 h-[40px] w-[40px]">
          <Paperclip size={20} />
        </label>
        <textarea
          className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 sm:px-4 py-2 text-white focus:outline-none focus:border-cyan-500 text-sm sm:text-base min-w-0 resize-none"
          placeholder="Describe strategy or upload PineScript..."
          value={input}
          rows={8}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          onClick={handleSend}
          disabled={isLoading || (!input.trim() && !file)}
          className="bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-white p-2 rounded transition-colors shrink-0 flex items-center justify-center h-[40px] w-[40px]"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};

export default StrategyBuilderPage;
