import React, { useState, useEffect } from 'react';
import { Diamond, Copy, CheckCircle2 } from 'lucide-react';
import { useAuthStore } from '../store/useStore';
import { useToast } from './Toast';
import api from '../lib/api';

const PremiumPage: React.FC = () => {
  const { user } = useAuthStore();
  const { showToast } = useToast();
  const [sourceWallet, setSourceWallet] = useState('');

  useEffect(() => {
    document.title = "Unlock Premium Automated Trading Autopilot | Metaverse Sherpa";
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute('content', "Upgrade to Premium for $20/month. Unlock full automated execution, exchange integration with Binance and Alpaca, and AI-powered portfolio audits.");
    }
  }, []);

  const schemaData = {
    "@context": "https://schema.org",
    "@type": "Product",
    "@id": "https://bot.metaversesherpa.io/#product",
    "name": "Metaversesherpa Automated Trading Subscription",
    "description": "Hands-free automated stock and cryptocurrency trading bot strategy access.",
    "brand": {
      "@type": "Brand",
      "name": "Metaversesherpa"
    },
    "offers": {
      "@type": "Offer",
      "url": "https://bot.metaversesherpa.io/premium",
      "price": "20.00",
      "priceCurrency": "USD"
    }
  };

  const treasuryAddress = 'TUhiPWBbrJKV7cyrnSawZ7JUdLN8Qcg6u3';

  const handleCopy = () => {
    navigator.clipboard.writeText(treasuryAddress);
    showToast('Treasury address copied to clipboard!', 'success');
  };

  const handleSaveWallet = async () => {
    if (!sourceWallet) {
      showToast('Please enter your source wallet address', 'error');
      return;
    }
    if (sourceWallet.trim() === treasuryAddress) {
      showToast('You cannot use the Treasury address as your source wallet', 'error');
      setSourceWallet('');
      return;
    }
    try {
      await api.post('/premium/wallet', { source_wallet: sourceWallet });
      showToast('Source wallet saved. Please proceed to verify payment.', 'success');
    } catch (error) {
      showToast('Failed to save source wallet', 'error');
    }
  };

  const handleVerify = async () => {
    try {
      const res = await api.post('/premium/check-payment');
      
      // GA4 Conversion Tracking
      if (typeof window !== 'undefined' && (window as any).dataLayer) {
        (window as any).dataLayer.push({
          event: 'premium_subscription_purchased',
          value: 20.00,
          currency: 'USD',
          method: 'TRON_USDT'
        });
      }

      showToast(res.data.message || 'Verification request submitted. Please allow up to 15 minutes for blockchain confirmation.', 'info');
    } catch (error: any) {
      showToast(error.response?.data?.error || 'Verification failed.  Most likely cause is your source wallet address.', 'error');
    }
  };

  return (
    <div className="flex-1 w-full max-w-2xl mx-auto space-y-6 pb-20">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schemaData) }} />
      
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-white flex items-center justify-center gap-2">
          <Diamond className="text-blue-400" size={24} /> Premium Upgrade
        </h1>
      </div>

      {/* Benefits Box */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-blue-500/20 rounded-2xl p-6 shadow-lg shadow-blue-900/10 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-6 opacity-5">
          <Diamond size={120} />
        </div>
        
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-4">
            <Diamond className="text-blue-400" size={24} fill="currentColor" />
            <h2 className="text-xl font-bold text-white tracking-wide">Premium Autopilot</h2>
          </div>
          
          <div className="space-y-4 mb-8 mt-6">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={18} />
              <p className="text-sm text-gray-300"><strong className="text-white">Enhanced Alpha Signals:</strong> Receive highly precise signals that include specific Entry Prices, Take Profit (TP), and Stop Loss (SL) targets.</p>
            </div>
            
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={18} />
              <p className="text-sm text-gray-300"><strong className="text-white">Exchange Integration:</strong> Connect directly to top crypto exchanges (Blofin, Binance, MexC) and stock brokerages (Alpaca).</p>
            </div>
            
            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={18} />
              <p className="text-sm text-gray-300"><strong className="text-white">Hands-Free Automation:</strong> Unlock 24/7 autonomous trade execution. Let our algorithms manage your positions while you sleep.</p>
            </div>

            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={18} />
              <p className="text-sm text-gray-300"><strong className="text-white">Priority Support:</strong> Direct access to the Metaverse Sherpa team for technical assistance and algorithmic guidance.</p>
            </div>

            <div className="flex items-start gap-3">
              <CheckCircle2 className="text-emerald-400 mt-0.5 shrink-0" size={18} />
              <p className="text-sm text-gray-300"><strong className="text-white">AI-Powered Portfolio Audits:</strong> Import your existing stock and crypto holdings and let our advanced Gemini AI instantly audit your portfolio. Get a comprehensive health score, real-time sentiment analysis from the latest news, and a personalized step-by-step action plan.</p>
            </div>
          </div>

          <div className="text-center pt-6 border-t border-white/5 bg-black/20 -mx-6 -mb-6 p-6">
            <div className="text-[10px] text-gray-400 uppercase tracking-widest mb-1">Membership Status</div>
            <div className="text-lg font-bold text-gray-300 tracking-wider">
              {user?.is_premium || user?.is_admin ? 'PREMIUM (ACTIVE)' : 'STANDARD TIER (READ ONLY)'}
            </div>
          </div>
        </div>
      </div>

      {/* Upgrade Box */}
      <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
        <h2 className="text-sm font-bold text-white mb-6 border-b border-white/5 pb-4">
          Upgrade / Renew via TRON USDT
        </h2>

        <div className="space-y-6">
          <div className="text-xs text-gray-300 space-y-2 bg-[#1f2028] p-4 rounded-xl border border-white/5">
            <p><strong>1.</strong> Send <strong className="text-yellow-400">20 USDT</strong> (TRC-20) to the Treasury wallet below.</p>
            <p><strong>2.</strong> Enter your sending wallet address and click <strong>Save Source Wallet</strong>.</p>
            <p><strong>3.</strong> Click <strong>Verify Blockchain Payment</strong>.</p>
          </div>

          {/* QR Code */}
          <div className="flex justify-center my-6">
            <div className="w-32 h-32 bg-white rounded-lg p-2 flex items-center justify-center">
               <img src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${treasuryAddress}`} alt="QR Code" className="w-full h-full" />
            </div>
          </div>

          <div className="space-y-4">
            <div className="bg-[#1f2028] border border-white/10 rounded-xl p-3">
              <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">USDT TRC 20 Treasury</span>
                <button onClick={handleCopy} className="text-gray-400 hover:text-white transition-colors">
                  <Copy size={14} />
                </button>
              </div>
              <div className="font-mono text-xs text-gray-300 select-all overflow-hidden text-ellipsis">
                {treasuryAddress}
              </div>
            </div>

            <div>
              <input 
                type="text" 
                value={sourceWallet}
                onChange={(e) => setSourceWallet(e.target.value)}
                placeholder="Your source USDT TRC20 Wallet"
                className="w-full bg-[#1f2028] border border-white/10 rounded-xl px-4 py-3 text-white text-xs focus:outline-none focus:border-cyan-500"
              />
            </div>

            <button 
              onClick={handleSaveWallet}
              className="w-full py-3 bg-[#2a2438] hover:bg-[#342b47] border border-pink-500/20 text-pink-100 text-xs font-bold rounded-xl transition-colors flex justify-center items-center gap-2"
            >
              👛 Save Source Wallet
            </button>

            <button 
              onClick={handleVerify}
              className="w-full py-3 bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 text-white text-xs font-bold rounded-xl transition-colors flex justify-center items-center gap-2 shadow-[0_0_15px_rgba(6,182,212,0.3)]"
            >
              🔎 Verify Blockchain Payment
            </button>

            <div className="text-[10px] text-gray-500 text-center mt-2 px-2">
              Payments are non-refundable. Metaverse Sherpa is not responsible for lost payments or payments sent to incorrect wallets.
            </div>
          </div>
        </div>
      </div>

    </div>
  );
};

export default PremiumPage;
