import React, { useState, useEffect } from 'react';
import { X, Download, Link as LinkIcon, Image as ImageIcon } from 'lucide-react';
import api from '../lib/api';

interface SharePnLModalProps {
  trade?: any;
  stat?: any;
  type?: 'crypto' | 'stock' | 'free';
  onClose: () => void;
  roe?: number;
  pnl?: number;
}

const SharePnLModal: React.FC<SharePnLModalProps> = ({ trade, stat, onClose, roe, pnl }) => {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingText, setLoadingText] = useState('Generating your premium card...');
  const [copied, setCopied] = useState(false);

  const symbol = trade?.symbol || '';
  const side = trade?.side || 'LONG';
  const entry = trade?.entry_price || 0;
  const mark = trade?.current_price || trade?.mark_price || trade?.exit_price || 0;
  
  const strategyName = stat?.name || '';

  // Mock user profile or fetch real one for referral
  const refId = localStorage.getItem('user_id') || '8';
  const refLink = `https://bot.metaversesherpa.io/login?ref=${refId}`;

  useEffect(() => {
    const messages = [
      "Generating your premium card...",
      "Refer 3 people for 1 free month of Premium!",
      "Share with friends and family!"
    ];
    let messageIndex = 0;
    const interval = setInterval(() => {
      messageIndex = (messageIndex + 1) % messages.length;
      setLoadingText(messages[messageIndex]);
    }, 2500);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchImage = async () => {
      try {
        let response;
        if (stat) {
          const queryParams = new URLSearchParams({
            type: 'stats',
            tab: 'free',
            strategy: strategyName,
            overall_pnl_pct: (stat.realized_pct || 0).toString(),
            daily_pnl_pct: (stat.unrealized_pct || 0).toString(),
            win_rate: (stat.win_rate || 0).toString(),
            total_trades: ((stat.wins || 0) + (stat.losses || 0)).toString()
          });
          response = await api.get(`/share/card?${queryParams.toString()}`, {
            responseType: 'blob'
          });
        } else {
          const queryParams = new URLSearchParams({
            type: 'trade',
            symbol: symbol.split('/')[0],
            side: side,
            roe: (roe || 0).toString(),
            entry: entry.toString(),
            mark: mark.toString(),
            pnl_usdt: (pnl || 0).toString(),
          });
          response = await api.get(`/share/card?${queryParams.toString()}`, {
            responseType: 'blob'
          });
        }
        
        const url = URL.createObjectURL(response.data);
        setImageUrl(url);
      } catch (err) {
        console.error("Failed to generate PnL card:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchImage();

    return () => {
      if (imageUrl) {
        URL.revokeObjectURL(imageUrl);
      }
    };
  }, []);

  const handleCopy = () => {
    navigator.clipboard.writeText(refLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="bg-[#1b1f2c]/90 rounded-2xl border border-white/10 w-full overflow-hidden flex flex-col gap-3 p-4 sm:p-5 relative max-w-[360px] animate-in zoom-in-95 duration-200">
        <div className="flex justify-between items-center pb-2 border-b border-white/10">
          <h3 className="font-bold text-white text-base flex items-center gap-2">
            <Share2Icon />
            {stat ? `Share PnL Card - ${strategyName}` : `Share PnL Card - ${symbol.split('/')[0]}`}
          </h3>
          <button onClick={onClose} className="p-1.5 hover:bg-white/5 rounded-full text-gray-400 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>
        
        <div className="flex flex-col items-center justify-center min-h-[250px] py-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center w-full h-full">
              <div className="relative w-16 h-16 mb-4">
                <div className="absolute inset-0 border-4 border-white/10 rounded-full"></div>
                <div className="absolute inset-0 border-4 border-cyan-400 rounded-full border-t-transparent animate-spin"></div>
                <div className="absolute inset-0 flex items-center justify-center text-cyan-400">
                  <ImageIcon size={24} className="animate-pulse" />
                </div>
              </div>
              <p className="text-xs text-gray-400 text-center transition-opacity duration-300">
                {loadingText}
              </p>
            </div>
          ) : imageUrl ? (
            <div className="w-full flex flex-col gap-4">
              <div className="w-full rounded-xl overflow-hidden border border-white/10 relative shadow-2xl bg-black/20 flex justify-center items-center">
                <img src={imageUrl} className="w-full h-auto max-h-[40vh] object-contain rounded-xl" alt="PnL Card Preview" />
              </div>
              
              <div className="w-full space-y-3">
                <div className="flex gap-2">
                  <a href={imageUrl} download="sherpa_pnl_card.jpg" className="flex-1 h-11 bg-white/5 border border-white/10 text-white font-semibold rounded-lg hover:bg-white/10 active:scale-95 transition-all text-xs flex items-center justify-center gap-2">
                    <Download size={16} /> Share Image
                  </a>
                  <button onClick={handleCopy} className="flex-1 h-11 bg-white/5 border border-white/10 text-white font-semibold rounded-lg hover:bg-white/10 active:scale-95 transition-all text-xs flex items-center justify-center gap-2">
                    <LinkIcon size={16} /> {copied ? 'Copied!' : 'Copy Invite Link'}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 text-center leading-normal">
                  Scan the QR code on the card or use your referral link to earn 30 days free Premium for every 3 members referred!
                </p>
              </div>
            </div>
          ) : (
            <p className="text-rose-400 text-sm">Failed to generate card.</p>
          )}
        </div>
      </div>
    </div>
  );
};

const Share2Icon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-cyan-400">
    <circle cx="18" cy="5" r="3"></circle>
    <circle cx="6" cy="12" r="3"></circle>
    <circle cx="18" cy="19" r="3"></circle>
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
  </svg>
);

export default SharePnLModal;
