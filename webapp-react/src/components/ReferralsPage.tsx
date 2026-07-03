import React from 'react';
import { useAuthStore } from '../store/useStore';
import { useToast } from './Toast';

const ReferralsPage: React.FC = () => {
  const { user } = useAuthStore();
  const { showToast } = useToast();
  
  const refId = user?.telegram_chat_id || user?.id || '';
  const inviteLink = user?.invite_link || `https://bot.metaversesherpa.io/#/register?ref=${refId}`;
  const telegramInviteLink = `https://t.me/metaversesherpa_trading_bot?start=ref_${refId}`;
  
  // Fetch counts/credits from the user object if they exist, otherwise default to 0
  const refCount = user?.referral_count || 0;
  const credits = user?.referral_credits || 0.00;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => showToast('Invite link copied!', 'success'));
  };

  return (
    <div className="flex-1 w-full max-w-[500px] mx-auto space-y-4 pb-24">
      
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🤝</span>
        <h2 className="text-2xl font-bold text-[#f3f4f6]">Refer & Earn</h2>
      </div>

      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border-t-2 border-emerald-500/40 border-x border-b border-white/10 rounded-2xl p-5 shadow-lg">
        <h3 className="text-xl font-bold text-emerald-400">Recruit & Unlock</h3>
        <p className="text-sm text-gray-400 mt-1 leading-relaxed">
          Earn 30 Days Free Premium for every 3 active members you refer to Metaverse Sherpa.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-4 shadow-lg text-center">
          <p className="text-sm text-gray-400">Recruits</p>
          <p className="text-2xl font-bold text-white mt-1">{refCount}</p>
        </div>
        
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-4 shadow-lg text-center">
          <p className="text-sm text-gray-400">Reward Credits</p>
          <p className="text-2xl font-bold text-emerald-400 mt-1">${credits.toFixed(2)}</p>
        </div>
      </div>

      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-5 shadow-lg space-y-4 mt-4">
        <div>
          <h4 className="font-semibold text-white text-sm mb-2">Your Institutional Invite Link (Web)</h4>
          <div className="flex gap-2">
            <input 
              className="flex-1 min-w-0 h-10 bg-black/30 text-gray-300 text-xs sm:text-sm font-mono border border-white/10 rounded-xl px-4 focus:outline-none" 
              type="text" 
              readOnly 
              value={inviteLink}
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <button 
              onClick={() => copyToClipboard(inviteLink)} 
              className="h-10 px-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-cyan-400 transition-colors text-sm font-bold shrink-0"
            >
              Copy
            </button>
          </div>
        </div>
        
        <div className="pt-4 border-t border-white/10">
          <h4 className="font-semibold text-white text-sm mb-2">Your Institutional Invite Link (Telegram)</h4>
          <div className="flex gap-2">
            <input 
              className="flex-1 min-w-0 h-10 bg-black/30 text-gray-300 text-xs sm:text-sm font-mono border border-white/10 rounded-xl px-4 focus:outline-none" 
              type="text" 
              readOnly 
              value={telegramInviteLink}
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <button 
              onClick={() => copyToClipboard(telegramInviteLink)} 
              className="h-10 px-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-cyan-400 transition-colors text-sm font-bold shrink-0"
            >
              Copy
            </button>
          </div>
        </div>
      </div>

    </div>
  );
};

export default ReferralsPage;
