import React from 'react';
import { Share2, TrendingUp, TrendingDown, ChevronDown } from 'lucide-react';
import { formatPrice } from '../utils/formatters';

export const formatTimeAgo = (timestamp: number) => {
  if (!timestamp) return 'Recent';
  const timeInSeconds = timestamp > 10000000000 ? Math.floor(timestamp / 1000) : timestamp;
  const seconds = Math.floor(Date.now() / 1000 - timeInSeconds);
  if (seconds < 60) return `${Math.max(0, seconds)}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

interface TradeCardProps {
  trade: any;
  type: 'crypto' | 'stock';
  activeTab: 'active' | 'closed';
  hideDollars?: boolean;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onShare: () => void;
  onTogglePrivacy?: () => void;
  onClosePosition?: (trade: any) => void;
}

const TradeCard: React.FC<TradeCardProps> = ({ trade, type, activeTab, hideDollars, isExpanded, onToggleExpand, onShare, onTogglePrivacy, onClosePosition }) => {
  const isLong = trade.side?.toUpperCase() === 'LONG' || trade.side?.toUpperCase() === 'BUY';
  const isProfit = (trade.unrealized_pnl >= 0 || trade.pnl_raw >= 0);
  const pnlColor = isProfit ? 'text-emerald-400' : 'text-rose-400';
  
  const roe = activeTab === 'active' ? trade.roe : trade.pnl_pct;
  const pnlRaw = activeTab === 'active' ? trade.unrealized_pnl : trade.pnl_raw;
  
  // Calculate mock % for target if we don't have the exact risk ratio 
  const tp_pct = trade.entry_price > 0 && trade.tp_price > 0 ? Math.abs((trade.tp_price - trade.entry_price) / trade.entry_price * 100) : 0;
  const sl_pct = trade.entry_price > 0 && trade.sl_price > 0 ? Math.abs((trade.sl_price - trade.entry_price) / trade.entry_price * 100) : 0;
  const targetDollar = trade.qty && trade.tp_price ? Math.abs(trade.tp_price - trade.entry_price) * trade.qty : 0;
  
  const markPrice = trade.current_price || trade.mark_price || trade.exit_price || 0;
  const chartUrl = `/api/trades/chart?symbol=${encodeURIComponent(trade.symbol || '')}&entry=${trade.entry_price || 0}&tp=${trade.tp_price || 0}&sl=${trade.sl_price || 0}&side=${trade.side || ''}&open_ts=${trade.open_time || trade.close_time || 0}&type=${type}&current_price=${markPrice}&strategy=${encodeURIComponent(trade.strategy || '')}&leverage=${trade.leverage || 1}`;
  
  const isClickable = activeTab === 'active';

  return (
    <div className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg relative overflow-hidden transition-all ${isExpanded ? 'ring-1 ring-white/20' : (isClickable ? 'hover:border-white/20 cursor-pointer' : '')}`} onClick={() => isClickable && onToggleExpand()}>
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center text-sm">
            {type === 'stock' ? '🦙' : '🪙'}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="font-bold text-white text-lg leading-tight">
                {(trade.symbol || '').split('/')[0]}
              </h4>
              {activeTab === 'active' && onClosePosition && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onClosePosition(trade);
                  }}
                  className="px-2.5 py-0.5 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 text-[10px] font-bold rounded-md transition-colors flex items-center gap-1"
                >
                  🚨 Market Close
                </button>
              )}
            </div>
            <div className="flex items-center gap-1 text-xs text-gray-400 mt-1">
              {isLong ? <TrendingUp size={12} className="text-emerald-400"/> : <TrendingDown size={12} className="text-rose-400"/>}
              {formatTimeAgo(activeTab === 'closed' ? (trade.close_time || trade.close_timestamp || trade.timestamp || trade.open_time) : (trade.open_time || trade.close_time))}
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-4 text-right">
          <button 
            className="text-gray-400 hover:text-white transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onShare();
            }}
          >
            <Share2 size={18} />
          </button>
          <div>
            <p className={`font-bold text-lg leading-tight flex items-center justify-end gap-1 ${pnlColor}`}>
              {isProfit ? '+' : ''}{roe?.toFixed(2)}% <span className="text-xs text-gray-500 font-normal">{trade.tp_price > 0 ? `of ${tp_pct.toFixed(0)}%` : 'No Target'}</span>
            </p>
            {hideDollars ? (
              <p 
                onClick={(e) => { if (onTogglePrivacy) { e.stopPropagation(); onTogglePrivacy(); } }} 
                className={`text-xs text-gray-500 mt-1 blur-sm opacity-70 select-none ${onTogglePrivacy ? 'cursor-pointer' : 'pointer-events-none'}`}
              >
                +***.** <span className="text-gray-500">/ +***.**</span>
              </p>
            ) : (
              <p 
                onClick={(e) => { if (onTogglePrivacy) { e.stopPropagation(); onTogglePrivacy(); } }} 
                className={`text-xs ${pnlColor} mt-1 ${onTogglePrivacy ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}`}
              >
                {isProfit ? '+' : ''}${pnlRaw?.toFixed(2)} <span className="text-gray-500">/ {trade.tp_price > 0 ? `+$${targetDollar.toFixed(2)}` : 'No Target'}</span>
              </p>
            )}
          </div>
          {isClickable && <ChevronDown size={20} className={`text-gray-500 ml-2 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />}
        </div>
      </div>

      <div className="flex justify-between items-center mt-6 text-xs text-gray-400 font-mono">
        <div>SL: {trade.sl_price > 0 ? `$${formatPrice(trade.sl_price)} (-${sl_pct.toFixed(0)}%)` : 'Not Set'}</div>
        <div>TP: {trade.tp_price > 0 ? `$${formatPrice(trade.tp_price)} (+${tp_pct.toFixed(0)}%)` : 'Not Set'}</div>
      </div>
      
      {isExpanded && (
        <div className="mt-6 pt-6 border-t border-white/5 space-y-4 cursor-default" onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Market Analysis & Setup</h4>
          </div>
          {(() => {
            const isAiRec = (trade.strategy || '').toLowerCase().includes('ai') || (trade.strategy || '').toLowerCase().includes('recommendation');
            const timeframeLabel = isAiRec || type === 'stock' ? '1D' : '15M';
            return (
              <div className="font-bold text-white mb-2">
                {(trade.symbol || '').split('/')[0]} ({trade.side?.toUpperCase()}) - {timeframeLabel} Setup | {trade.strategy}
              </div>
            );
          })()}
          <div className="relative w-full bg-[#0b0f19]/50 rounded-lg overflow-hidden border border-white/5 flex items-center justify-center min-h-[220px]">
            <img src={chartUrl} className="w-full h-auto block" alt="Signal Chart" />
          </div>
        </div>
      )}
    </div>
  );
};

export default TradeCard;
