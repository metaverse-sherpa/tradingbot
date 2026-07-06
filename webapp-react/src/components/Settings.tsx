import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  MessageCircle, Save, Terminal, 
  Activity, Star, LogOut, Bell, Mail, RefreshCw,
  Gift, Code, EyeOff, Trash2, Cpu, ChevronDown, PlayCircle, Copy, ExternalLink, Key
} from 'lucide-react';
import { useAuthStore } from '../store/useStore';
import { useToast } from './Toast';
import api from '../lib/api';
import { auth } from '../lib/firebase';

const CustomSelect = ({ value, onChange, options }: { value: string, onChange: (v: string) => void, options: {label: string, value: string, disabled?: boolean}[] }) => {
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
    <div className="relative w-full" ref={ref}>
      <button 
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-white text-sm flex justify-between items-center focus:outline-none focus:border-emerald-500 transition-colors"
      >
        {options.find(o => o.value === value)?.label || value}
        <ChevronDown size={16} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 w-full mt-2 bg-[#1f2028] border border-[#2e303a] rounded-xl shadow-xl overflow-y-auto max-h-48">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              disabled={opt.disabled}
              onClick={() => { onChange(opt.value); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs transition-colors ${opt.disabled ? 'text-gray-600 cursor-not-allowed' : 'hover:bg-white/5'} ${value === opt.value ? 'text-emerald-400 font-bold bg-white/5' : (opt.disabled ? 'text-gray-600' : 'text-gray-300')}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const Settings: React.FC = () => {
  const { user, setUser } = useAuthStore();
  const navigate = useNavigate();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const { showToast } = useToast();

  // Exchange state
  const [exchangePlatform, setExchangePlatform] = useState('blofin');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [apiPassword, setApiPassword] = useState('');
  const [alpacaEndpoint, setAlpacaEndpoint] = useState('https://paper-api.alpaca.markets');
  const [isSavingExchange, setIsSavingExchange] = useState(false);
  const [isTestingExchange, setIsTestingExchange] = useState(false);

  // Telegram state
  const [telegramId, setTelegramId] = useState(user?.telegram_chat_id?.toString() || '');
  const [isLinkingTelegram, setIsLinkingTelegram] = useState(false);

  // Preferences state
  const [riskPct, setRiskPct] = useState(user?.risk_pct ?? 1.0);
  const [stockRiskPct, setStockRiskPct] = useState(user?.stock_risk_pct ?? 2.0);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);

  // Admin gift
  const [giftMonths, setGiftMonths] = useState(1);
  const [giftResult, setGiftResult] = useState<any>(null);
  const [isGeneratingGift, setIsGeneratingGift] = useState(false);

  // Sync state if user changes
  useEffect(() => {
    if (user?.telegram_chat_id) {
      setTelegramId(user.telegram_chat_id.toString());
    }
    setRiskPct(user?.risk_pct ?? 1.0);
    setStockRiskPct(user?.stock_risk_pct ?? 2.0);
  }, [user]);

  // Handle Exchange Save
  const handleSaveApiKeys = async (e: React.FormEvent, type: 'crypto' | 'stock') => {
    e.preventDefault();
    setIsSavingExchange(true);
    
    try {
      if (type === 'crypto') {
        await api.post('/settings/exchange', {
          exchange_id: exchangePlatform,
          api_key: apiKey,
          api_secret: apiSecret,
          api_password: apiPassword,
          bingx_futures_type: 'perpetual',
          coinbase_sandbox: false
        });
      } else {
        await api.post('/settings/alpaca', {
          api_key: apiKey,
          api_secret: apiSecret,
          endpoint: alpacaEndpoint
        });
      }

      showToast("Saving keys and testing connection...");
      
      // Auto-test
      const testRes = await api.get(`/settings/test-connection?segment=${type}`);
      if (testRes.data.success) {
        showToast(`✅ ${type === 'crypto' ? testRes.data.exchange : 'Alpaca'} connection successful!`, 'success');
        if (testRes.data.note) {
          setTimeout(() => showToast(`ℹ️ ${testRes.data.note}`, 'info'), 1500);
        }
        
        // Refresh user object to show connected state
        const profileRes = await api.get('/user/profile');
        setUser({ ...user, ...profileRes.data });
        
        // Reset form
        setApiKey('');
        setApiSecret('');
        setApiPassword('');
      } else {
        showToast(`❌ Connection failed: ${testRes.data.error || 'Unknown error'}`, 'error');
        if (testRes.data.hint) {
          setTimeout(() => showToast(`💡 ${testRes.data.hint}`, 'info'), 1500);
        }
        // Rollback on failure
        await api.delete(type === 'crypto' ? '/settings/exchange' : '/settings/alpaca');
      }
    } catch (err: any) {
      showToast(err.response?.data?.error || "Failed to save keys", 'error');
    } finally {
      setIsSavingExchange(false);
    }
  };

  const handleDeleteExchange = async (type: 'crypto' | 'stock') => {
    if (!window.confirm(`Are you sure you want to delete your ${type} API keys?`)) return;
    
    try {
      await api.delete(type === 'crypto' ? '/settings/exchange' : '/settings/alpaca');
      showToast(`${type} API keys deleted`, 'success');
      
      const profileRes = await api.get('/user/profile');
      setUser({ ...user, ...profileRes.data });
    } catch (err) {
      showToast("Failed to delete keys", 'error');
    }
  };

  const handleTestConnection = async (type: 'crypto' | 'stock') => {
    setIsTestingExchange(true);
    try {
      const testRes = await api.get(`/settings/test-connection?segment=${type}`);
      if (testRes.data.success) {
        showToast(`✅ ${type === 'crypto' ? testRes.data.exchange : 'Alpaca'} connection successful!`, 'success');
      } else {
        showToast(`❌ Connection failed: ${testRes.data.error || 'Unknown error'}`, 'error');
      }
    } catch (err) {
      showToast("Failed to test connection", 'error');
    } finally {
      setIsTestingExchange(false);
    }
  };

  const handleLinkTelegram = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLinkingTelegram(true);
    try {
      const res = await api.post('/settings/telegram', { telegram_chat_id: telegramId });
      showToast(res.data.message || "Telegram linked", 'success');
      setUser({ ...user, telegram_chat_id: parseInt(telegramId) } as any);
    } catch (err: any) {
      showToast(err.response?.data?.error || "Failed to link Telegram", 'error');
    } finally {
      setIsLinkingTelegram(false);
    }
  };

  const toggleBotStatus = async () => {
    try {
      const newStatus = !user?.is_active;
      const res = await api.post('/settings/status', { is_active: newStatus });
      showToast(res.data.message, 'success');
      setUser({ ...user, is_active: newStatus } as any);
    } catch (err) {
      showToast("Failed to toggle bot status", 'error');
    }
  };

  const togglePreference = async (key: string, currentValue: any) => {
    const newValue = !currentValue;
    const originalUser = { ...user };
    setUser({ ...user, [key]: newValue } as any);

    try {
      await api.post('/settings/preferences', { [key]: newValue });
      
      if (key === 'browser_notifications' && newValue) {
        if ('Notification' in window && Notification.permission !== 'granted') {
          Notification.requestPermission();
        }
      }
    } catch (err) {
      setUser(originalUser as any);
      showToast(`Failed to update ${key}`, 'error');
    }
  };

  const setEmailFrequency = async (freq: string) => {
    try {
      await api.post('/settings/preferences', { email_frequency: freq });
      setUser({ ...user, email_frequency: freq } as any);
    } catch (err) {
      showToast("Failed to update email frequency", 'error');
    }
  };

  const saveRiskPreferences = async () => {
    setIsSavingPreferences(true);
    try {
      await api.post('/settings/preferences', { risk_pct: riskPct, stock_risk_pct: stockRiskPct });
      showToast("Risk configuration updated", 'success');
      setUser({ ...user, risk_pct: riskPct, stock_risk_pct: stockRiskPct } as any);
    } catch (err) {
      showToast("Failed to update risk settings", 'error');
    } finally {
      setIsSavingPreferences(false);
    }
  };

  const handleStrategyChange = async (type: 'crypto' | 'stock', strategyName: string) => {
    try {
      const res = await api.post('/settings/strategy', { type, strategy: strategyName });
      showToast(res.data.message, 'success');
      const key = type === 'crypto' ? 'active_crypto_strategy' : 'active_stock_strategy';
      setUser({ ...user, [key]: strategyName } as any);
    } catch (err: any) {
      showToast(err.response?.data?.error || "Failed to change strategy", 'error');
    }
  };

  const handleGenerateGift = async () => {
    setIsGeneratingGift(true);
    try {
      const res = await api.post('/admin/generate-gift', { months: giftMonths });
      setGiftResult(res.data);
      showToast("Universal Gift links generated!", 'success');
    } catch (err) {
      showToast("Failed to generate gift code", 'error');
    } finally {
      setIsGeneratingGift(false);
    }
  };

  const generateDeveloperKey = async () => {
    if (!window.confirm("This will replace your existing API key if you have one. Continue?")) return;
    try {
      const res = await api.post('/settings/developer-api-key/generate');
      setUser({ ...user, developer_api_key: res.data.developer_api_key } as any);
      showToast("Developer API Key generated", 'success');
    } catch (err) {
      showToast("Failed to generate API key", 'error');
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    showToast(`${label} copied!`, 'info');
  };

  const handleLogout = async () => {
    await auth.signOut();
    window.location.href = '/';
  };

  return (
    <div className="flex-1 w-full max-w-5xl mx-auto space-y-6 pb-20">
      
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-[#f3f4f6]">Settings</h2>
        <p className="text-gray-400 mt-2">Manage your preferences, connections, and security.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* LEFT COLUMN */}
        <div className="space-y-6">
          
          {/* Premium Membership */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-purple-500/20 rounded-xl">
                <Star className="text-purple-400" size={20} />
              </div>
              <h3 className="text-lg font-bold text-white">Membership Status</h3>
            </div>
            
            {user?.is_admin ? (
              <div className="flex justify-between items-center bg-[#1f2028] p-4 rounded-xl border border-white/5">
                <div className="text-sm font-bold text-white">Universal Admin</div>
                <div className="text-xs text-purple-400 font-bold tracking-wider uppercase">Lifetime Active</div>
              </div>
            ) : (
              <div className="flex items-center justify-between p-4 bg-[#1f2028] rounded-xl border border-white/5">
                <div>
                  <div className="font-bold text-white">
                    {isPremium ? "Premium Member" : "Free Tier"}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {isPremium ? `Expires: ${new Date((user?.premium_expiry || 0) * 1000).toLocaleDateString()}` : "Upgrade to unlock automation"}
                  </div>
                </div>
                <Link to="/premium" className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold rounded-lg transition-colors">
                  {isPremium ? "Renew" : "Upgrade Now"}
                </Link>
              </div>
            )}
          </div>

          {/* Connected Exchanges */}
          {isPremium && (
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg animate-fade-in">
              <details className="group" open>
                <summary className="text-lg font-bold text-white flex justify-between items-center cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none">
                  <div className="flex items-center gap-2">
                    🔌 Connected Exchanges
                  </div>
                  <ChevronDown className="text-gray-400 group-open:rotate-180 transition-transform duration-300" />
                </summary>
                <div className="space-y-4 mt-4">
                  {user?.has_exchange_keys ? (
                    <form className="bg-[#1f2028] p-4 rounded-xl border border-white/5 space-y-3" onSubmit={e => e.preventDefault()}>
                      <div className="flex justify-between items-center">
                        <span className="font-bold text-sm text-white flex items-center gap-1.5">
                          🪙 Crypto: <span className="capitalize text-cyan-400 font-mono">{user.exchange_id || 'Blofin'}{user.exchange_id === 'bingx' ? ' (Perpetual Futures)' : ''}</span>
                        </span>
                        <div className="flex items-center gap-2">
                          <button onClick={() => handleTestConnection('crypto')} disabled={isTestingExchange} className="text-xs text-cyan-400 font-bold hover:underline flex items-center gap-1 cursor-pointer">
                            <RefreshCw size={14} className={isTestingExchange ? "animate-spin" : ""} /> Test
                          </button>
                          <button onClick={() => handleDeleteExchange('crypto')} className="text-xs text-red-400 font-bold hover:underline flex items-center gap-1 cursor-pointer">
                            <Trash2 size={14} /> Delete
                          </button>
                        </div>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between items-center gap-2">
                          <span className="text-gray-400">API Key:</span>
                          <input type="password" value="••••••••••••" readOnly className="bg-transparent text-right text-white font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" />
                        </div>
                        <div className="flex justify-between items-center gap-2">
                          <span className="text-gray-400">API Secret:</span>
                          <input type="password" value="••••••••••••" readOnly className="bg-transparent text-right text-white font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" />
                        </div>
                        {['blofin', 'bitget'].includes(user.exchange_id || '') && (
                          <div className="flex justify-between items-center gap-2">
                            <span className="text-gray-400">Passphrase:</span>
                            <input type="password" value="••••••••••••" readOnly className="bg-transparent text-right text-white font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" />
                          </div>
                        )}
                      </div>
                    </form>
                  ) : null}

                  {user?.has_alpaca_keys ? (
                    <form className="bg-[#1f2028] p-4 rounded-xl border border-white/5 space-y-3" onSubmit={e => e.preventDefault()}>
                      <div className="flex justify-between items-center">
                        <span className="font-bold text-sm text-white flex items-center gap-1.5">
                          🦙 Stocks: <span className="text-cyan-400 font-mono">Alpaca</span>
                        </span>
                        <div className="flex items-center gap-2">
                          <button onClick={() => handleDeleteExchange('stock')} className="text-xs text-red-400 font-bold hover:underline flex items-center gap-1 cursor-pointer">
                            <Trash2 size={14} /> Delete
                          </button>
                        </div>
                      </div>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between items-center gap-2">
                          <span className="text-gray-400">API Key:</span>
                          <input type="password" value="••••••••••••" readOnly className="bg-transparent text-right text-white font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" />
                        </div>
                        <div className="flex justify-between items-center gap-2">
                          <span className="text-gray-400">API Secret:</span>
                          <input type="password" value="••••••••••••" readOnly className="bg-transparent text-right text-white font-mono border-none outline-none focus:ring-0 p-0 text-xs w-36" />
                        </div>
                        <div className="flex justify-between items-center gap-2">
                          <span className="text-gray-400">Endpoint URL:</span>
                          <span className="text-white font-mono text-xs">{user.alpaca_endpoint || 'https://api.alpaca.markets'}</span>
                        </div>
                      </div>
                    </form>
                  ) : null}

                  {!user?.has_exchange_keys && !user?.has_alpaca_keys && (
                    <div className="bg-[#1f2028] p-4 rounded-xl border border-white/5 text-xs text-gray-400 leading-relaxed">
                      No exchanges connected. Connect your Crypto Exchange or Alpaca Stocks API credentials below to unlock autonomous copy-trading.
                    </div>
                  )}

                  {(!user?.has_exchange_keys || !user?.has_alpaca_keys) && (
                    <div className="pt-4 border-t border-white/10 space-y-4 animate-fade-in">
                      <h4 className="text-md font-bold text-white">
                        🔌 Connect {(!user?.has_exchange_keys && !user?.has_alpaca_keys) ? 'Exchange' : (user?.has_exchange_keys ? 'Stocks Platform' : 'Crypto Exchange')}
                      </h4>
                      <div className="space-y-2">
                        <label className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">Select Platform</label>
                        <CustomSelect 
                          value={exchangePlatform} 
                          onChange={(v) => setExchangePlatform(v)}
                          options={[
                            ...(!user?.has_exchange_keys ? [
                              { value: 'blofin', label: 'Blofin' },
                              { value: 'binance', label: 'Binance' },
                              { value: 'mexc', label: 'MEXC' },
                              { value: 'bitget', label: 'Bitget' },
                              { value: 'bingx', label: 'BingX' },
                              { value: 'coinbase', label: 'Coinbase Advanced' }
                            ] : []),
                            ...(!user?.has_alpaca_keys ? [
                              { value: 'alpaca', label: 'Alpaca Stocks' }
                            ] : [])
                          ]}
                        />
                      </div>

                      <div className="space-y-3">
                        {exchangePlatform === 'alpaca' ? (
                          <div className="space-y-1">
                            <label className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">Environment</label>
                            <CustomSelect 
                              value={alpacaEndpoint} 
                              onChange={(v) => setAlpacaEndpoint(v)}
                              options={[
                                { value: 'https://paper-api.alpaca.markets', label: 'Paper Trading (Recommended)' },
                                { value: 'https://api.alpaca.markets', label: 'Live Trading' }
                              ]}
                            />
                          </div>
                        ) : null}

                        <div className="space-y-1">
                          <label className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">API Key</label>
                          <input type="text" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="API Key" autoComplete="off" className="w-full h-11 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:outline-none focus:border-cyan-500" />
                        </div>
                        
                        <div className="space-y-1">
                          <label className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">API Secret</label>
                          {exchangePlatform === 'coinbase' ? (
                            <textarea value={apiSecret} onChange={e => setApiSecret(e.target.value)} rows={4} autoComplete="off" className="w-full bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 py-2 focus:outline-none focus:border-cyan-500 font-mono text-[10px]" />
                          ) : (
                            <input type="password" value={apiSecret} onChange={e => setApiSecret(e.target.value)} placeholder="API Secret" autoComplete="new-password" className="w-full h-11 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:outline-none focus:border-cyan-500" />
                          )}
                        </div>

                        {['blofin', 'bitget'].includes(exchangePlatform) && (
                          <div className="space-y-1">
                            <label className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">Passphrase</label>
                            <input type="password" value={apiPassword} onChange={e => setApiPassword(e.target.value)} placeholder="Passphrase" className="w-full h-11 bg-[#1f2028] text-white text-sm border border-white/10 rounded-lg px-4 focus:outline-none focus:border-cyan-500" />
                          </div>
                        )}

                        {exchangePlatform === 'bingx' && (
                          <div className="p-3 bg-cyan-900/20 border border-cyan-500/30 rounded-lg text-xs text-gray-300 space-y-1">
                            <span className="font-bold text-cyan-400 flex items-center gap-1">
                                BingX Requirement
                            </span>
                            <p>Metaverse Sherpa connects to BingX using <strong>Perpetual Futures</strong>. Please make sure your API key has <strong>Read</strong> and <strong>Perpetual Futures Trading</strong> permissions enabled, and your funds are in your Perpetual Futures account.</p>
                          </div>
                        )}

                        {exchangePlatform === 'coinbase' && (
                          <div className="p-3 bg-cyan-900/20 border border-cyan-500/30 rounded-lg text-xs text-gray-300 space-y-1">
                            <span className="font-bold text-cyan-400 flex items-center gap-1">
                                Coinbase Advanced Key Format
                            </span>
                            <p>Your API Key must be the <strong>full resource name</strong> provided by Coinbase, formatted like: <code>organizations/{'{org_id}'}/apiKeys/{'{key_id}'}</code>. If you downloaded the JSON file, copy the full <code>name</code> property for the API Key.</p>
                          </div>
                        )}

                        <button onClick={(e) => handleSaveApiKeys(e, exchangePlatform === 'alpaca' ? 'stock' : 'crypto')} disabled={isSavingExchange || !apiKey || !apiSecret} className="w-full h-11 bg-cyan-600 hover:bg-cyan-500 text-white font-bold rounded-lg transition-colors flex items-center justify-center gap-2 mt-2">
                          {isSavingExchange ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />} Save Keys
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </details>
            </div>
          )}

          {/* Autopilot Status */}
          {isPremium && user?.has_exchange_keys && (
            <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-500/20 rounded-xl">
                  <Activity className="text-blue-400" size={20} />
                </div>
                <h3 className="text-lg font-bold text-white">Autopilot Execution</h3>
              </div>
              <div className="flex items-center justify-between p-4 bg-[#1f2028] rounded-xl border border-white/5">
                <div>
                  <div className="font-bold text-white">Trading Bot is {user?.is_active ? 'Active' : 'Paused'}</div>
                  <div className="text-xs text-gray-400 mt-1">{user?.is_active ? 'Executing signals securely' : 'Not executing trades'}</div>
                </div>
                <button 
                  onClick={toggleBotStatus}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${user?.is_active ? 'bg-cyan-500' : 'bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${user?.is_active ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
            </div>
          )}

          {/* Telegram Sync */}
          <div className={`bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl shadow-lg transition-all duration-300 ${user?.telegram_chat_id ? 'p-4' : 'p-6'}`}>
            <div className={`flex items-center gap-3 ${user?.telegram_chat_id ? '' : 'mb-4'}`}>
              <div className={`p-2 rounded-xl ${user?.telegram_chat_id ? 'bg-emerald-500/20' : 'bg-blue-500/20'}`}>
                <MessageCircle className={`${user?.telegram_chat_id ? 'text-emerald-400' : 'text-blue-400'}`} size={20} />
              </div>
              <h3 className="text-lg font-bold text-white flex-1">Telegram Alerts</h3>
              
              {user?.telegram_chat_id && (
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-bold text-emerald-400">Linked</div>
                    <div className="text-xs text-emerald-200/50 hidden sm:block">({user.telegram_chat_id})</div>
                  </div>
                  <button onClick={() => setUser({...user, telegram_chat_id: null} as any)} className="text-xs px-3 py-1 bg-white/10 rounded hover:bg-white/20 text-white transition-colors">
                    Edit
                  </button>
                </div>
              )}
            </div>
            
            {!user?.telegram_chat_id && (
              <>
                <form onSubmit={handleLinkTelegram} className="flex gap-2">
                  <input 
                    type="text" 
                    value={telegramId}
                    onChange={(e) => setTelegramId(e.target.value)}
                    placeholder="Enter Telegram Chat ID"
                    className="flex-1 bg-black/30 border border-white/10 rounded-xl px-4 py-2 text-white text-sm focus:border-blue-500 outline-none"
                  />
                  <button type="submit" disabled={isLinkingTelegram || !telegramId} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-xl transition-colors">
                    Link
                  </button>
                </form>
                <p className="text-xs text-gray-400 mt-4 leading-relaxed">
                  Get your Chat ID by messaging the <a href="https://t.me/metaversesherpa_trading_bot" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline font-bold">@metaversesherpa_trading_bot</a> on Telegram and typing <code className="bg-white/10 px-1 py-0.5 rounded text-white font-mono">/start</code>.
                </p>
              </>
            )}
          </div>

        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-6">

          {/* Privacy & UI Settings */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-yellow-500/20 rounded-xl">
                <EyeOff className="text-yellow-400" size={20} />
              </div>
              <h3 className="text-lg font-bold text-white">Privacy Mode</h3>
            </div>
            <div className="flex items-center justify-between p-4 bg-[#1f2028] rounded-xl border border-white/5">
              <div>
                <div className="font-bold text-white">Hide Balances</div>
                <div className="text-xs text-gray-400 mt-1">Mask dollar amounts with asterisks</div>
              </div>
              <button 
                onClick={() => togglePreference('hide_dollars', user?.hide_dollars)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${user?.hide_dollars ? 'bg-yellow-500' : 'bg-gray-600'}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${user?.hide_dollars ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
          </div>

          {/* Notifications */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-orange-500/20 rounded-xl">
                <Bell className="text-orange-400" size={20} />
              </div>
              <h3 className="text-lg font-bold text-white">Notifications</h3>
            </div>
            
            <div className="space-y-3">
              <div className="flex items-center justify-between p-4 bg-[#1f2028] rounded-xl border border-white/5">
                <div className="flex items-center gap-3">
                  <Mail className="text-gray-400" size={18} />
                  <div>
                    <div className="font-bold text-white text-sm">Email Alerts</div>
                    <div className="text-xs text-gray-400 mt-1">Trade signals and account updates</div>
                  </div>
                </div>
                <button 
                  onClick={() => togglePreference('email_notifications', user?.email_notifications)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${user?.email_notifications ? 'bg-orange-500' : 'bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${user?.email_notifications ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>

              {user?.email_notifications && (
                <div className="flex gap-2 p-2 bg-[#1f2028] rounded-xl border border-white/5">
                  <button onClick={() => setEmailFrequency('realtime')} className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors ${user.email_frequency === 'realtime' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'text-gray-400 hover:text-white border border-transparent'}`}>Real-time</button>
                  <button onClick={() => setEmailFrequency('daily')} className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors ${user.email_frequency === 'daily' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'text-gray-400 hover:text-white border border-transparent'}`}>Daily Summary</button>
                </div>
              )}

              <div className="flex items-center justify-between p-4 bg-[#1f2028] rounded-xl border border-white/5">
                <div className="flex items-center gap-3">
                  <Terminal className="text-gray-400" size={18} />
                  <div>
                    <div className="font-bold text-white text-sm">Browser Push</div>
                    <div className="text-xs text-gray-400 mt-1">Desktop notifications</div>
                  </div>
                </div>
                <button 
                  onClick={() => togglePreference('browser_notifications', user?.browser_notifications)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${user?.browser_notifications ? 'bg-orange-500' : 'bg-gray-600'}`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${user?.browser_notifications ? 'translate-x-6' : 'translate-x-1'}`} />
                </button>
              </div>
            </div>
          </div>

          {/* Strategy & Risk */}
          <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-emerald-500/20 rounded-xl">
                <Cpu className="text-emerald-400" size={20} />
              </div>
              <h3 className="text-lg font-bold text-white">Algorithms & Risk</h3>
            </div>

            <div className="space-y-4">
              {/* Crypto Strategy */}
              <div className="space-y-2">
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest">Crypto Strategy</label>
                <div className="flex gap-2">
                  <CustomSelect 
                    value={user?.active_crypto_strategy || 'None'} 
                    onChange={(v) => handleStrategyChange('crypto', v)}
                    options={[
                      { value: "None", label: "None (Paused)" },
                      { value: "Mean Reversion Scalper", label: "Mean Reversion Scalper", disabled: user?.disabled_strategies?.includes("Mean Reversion Scalper") },
                      { value: "Valkyrie Elite Scalper", label: "Valkyrie Elite Scalper", disabled: user?.disabled_strategies?.includes("Valkyrie Elite Scalper") }
                    ]}
                  />
                  <button 
                    onClick={() => navigate(`/backtests?strategy=${encodeURIComponent(user?.active_crypto_strategy || 'Valkyrie Elite Scalper')}&risk=${riskPct}`)}
                    className="px-4 bg-[#1f2028] border border-[#2e303a] rounded-xl text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition-colors flex items-center justify-center"
                    title="Run Backtest"
                  >
                    <PlayCircle size={20} />
                  </button>
                </div>
              </div>

              {/* Stock Strategy */}
              <div className="space-y-2">
                <label className="block text-xs font-bold text-gray-400 uppercase tracking-widest">Stock Strategy</label>
                <div className="flex gap-2">
                  <CustomSelect 
                    value={user?.active_stock_strategy || 'None'} 
                    onChange={(v) => handleStrategyChange('stock', v)}
                    options={[
                      { value: "None", label: "None (Paused)" },
                      { value: "Sherpa Velocity Pullback", label: "Sherpa Velocity Pullback", disabled: user?.disabled_strategies?.includes("Sherpa Velocity Pullback") }
                    ]}
                  />
                  <button 
                    onClick={() => navigate(`/backtests?strategy=${encodeURIComponent(user?.active_stock_strategy || 'Sherpa Velocity Pullback')}&risk=${stockRiskPct}`)}
                    className="px-4 bg-[#1f2028] border border-[#2e303a] rounded-xl text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition-colors flex items-center justify-center"
                    title="Run Backtest"
                  >
                    <PlayCircle size={20} />
                  </button>
                </div>
              </div>

              <div className="my-4 border-t border-white/5"></div>

              {/* Risk Sliders */}
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between text-xs font-bold mb-2">
                    <span className="text-gray-400 uppercase tracking-widest">Crypto Risk Per Trade</span>
                    <span className="text-emerald-400">{riskPct}% of balance</span>
                  </div>
                  <input type="range" min="0.5" max="5.0" step="0.5" value={riskPct} onChange={e => setRiskPct(parseFloat(e.target.value))} className="w-full accent-emerald-500" />
                </div>
                
                <div>
                  <div className="flex justify-between text-xs font-bold mb-2">
                    <span className="text-gray-400 uppercase tracking-widest">Stock Risk Per Trade</span>
                    <span className="text-emerald-400">{stockRiskPct}% of balance</span>
                  </div>
                  <input type="range" min="0.5" max="5.0" step="0.5" value={stockRiskPct} onChange={e => setStockRiskPct(parseFloat(e.target.value))} className="w-full accent-emerald-500" />
                </div>

                <button onClick={saveRiskPreferences} disabled={isSavingPreferences} className="w-full py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 font-bold border border-emerald-500/30 rounded-lg transition-colors flex items-center justify-center gap-2">
                  {isSavingPreferences ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />} Apply Position Sizing
                </button>
              </div>
            </div>
          </div>

          {/* Admin Gift Center */}
          {user?.is_admin && (
            <div className="bg-gradient-to-br from-[#2a2411] to-[#1b1f2c] border border-[#ffdb3c]/30 rounded-2xl p-6 shadow-lg relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10">
                <Gift size={100} />
              </div>
              <div className="relative z-10">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-[#ffdb3c]/20 rounded-xl">
                    <Gift className="text-[#ffdb3c]" size={20} />
                  </div>
                  <h3 className="text-lg font-bold text-white">Admin Gifting Center</h3>
                </div>
                <p className="text-xs text-gray-400 mb-4">Generate 100% discount codes for new members.</p>
                
                {!giftResult ? (
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-xs font-bold mb-2 text-gray-300">
                        <span>Duration</span>
                        <span className="text-[#ffdb3c]">{giftMonths} Months</span>
                      </div>
                      <input type="range" min="1" max="12" step="1" value={giftMonths} onChange={e => setGiftMonths(parseInt(e.target.value))} className="w-full accent-[#ffdb3c]" />
                    </div>
                    <button onClick={handleGenerateGift} disabled={isGeneratingGift} className="w-full py-3 bg-gradient-to-r from-yellow-500 to-yellow-600 hover:from-yellow-400 hover:to-yellow-500 text-black font-bold rounded-xl shadow-lg transition-all flex justify-center items-center gap-2">
                      {isGeneratingGift ? <RefreshCw size={16} className="animate-spin" /> : <Gift size={16} />} Generate Universal Gift Link
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3 animate-fade-in text-left">
                    <div className="bg-black/30 p-3 rounded-lg border border-white/10 space-y-1">
                      <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider block">Gift Code</span>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm text-[#ffdb3c] font-bold select-all">{giftResult.code}</span>
                        <button onClick={() => copyToClipboard(giftResult.code, "Code")} className="text-xs text-cyan-400 hover:underline">Copy</button>
                      </div>
                    </div>
                    <div className="bg-black/30 p-3 rounded-lg border border-white/10 space-y-1">
                      <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider block">🌐 Web App Link</span>
                      <div className="flex items-center justify-between gap-2">
                        <input type="text" readOnly value={giftResult.web_gift_url} className="bg-transparent text-xs text-gray-400 font-mono border-none outline-none focus:ring-0 p-0 w-full select-all" />
                        <button onClick={() => copyToClipboard(giftResult.web_gift_url, "Web link")} className="text-xs text-cyan-400 hover:underline">Copy</button>
                      </div>
                    </div>
                    <button onClick={() => setGiftResult(null)} className="w-full py-2 bg-white/5 hover:bg-white/10 text-white text-xs font-bold rounded-lg transition-colors border border-white/10">
                      Create Another
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* FULL WIDTH BOTTOM SECTIONS */}
      
      {/* Developer API */}
      {isPremium && (
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg relative overflow-hidden mt-6">
          <div className="absolute -top-10 -right-10 w-32 h-32 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="relative z-10">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex flex-col flex-1 w-full sm:w-auto min-w-[250px]">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-cyan-500/20 rounded-full flex items-center justify-center shrink-0">
                    <Code className="text-cyan-400" size={20} />
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-white tracking-wide">Developer API Key</h3>
                    <p className="text-[10px] text-gray-400 uppercase tracking-wider font-bold mt-0.5">External Bot Access</p>
                  </div>
                </div>
                
                <p className="text-xs text-gray-400 leading-relaxed mb-4 sm:mb-0">
                  Authenticate external scripts and bots against our REST API. Keep this key secret. 
                  <a href="https://bot.metaversesherpa.io/api" target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline font-bold ml-1 inline-flex items-center gap-1">
                    View API Docs <ExternalLink size={12} />
                  </a>
                </p>
              </div>
              
              <div className="flex items-center gap-2 flex-1 w-full sm:w-auto sm:flex-initial">
                {user?.developer_api_key ? (
                  <>
                    <input 
                      type="text" 
                      readOnly 
                      value={user?.developer_api_key} 
                      onClick={() => copyToClipboard(user?.developer_api_key || "", "API Key")}
                      className="flex-1 min-w-0 bg-black/30 border border-white/10 rounded-xl px-4 py-2.5 text-white font-mono text-xs text-center tracking-wider outline-none cursor-pointer hover:bg-black/40 transition-colors" 
                      title="Click to copy API Key"
                    />
                    <button onClick={() => copyToClipboard(user?.developer_api_key || "", "API Key")} className="w-10 h-10 flex items-center justify-center bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 hover:text-cyan-400 rounded-xl transition-colors shrink-0" title="Copy API Key">
                      <Copy size={16} />
                    </button>
                    <button onClick={generateDeveloperKey} className="w-10 h-10 flex items-center justify-center bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 hover:text-cyan-400 rounded-xl transition-colors shrink-0" title="Regenerate API Key">
                      <RefreshCw size={16} />
                    </button>
                  </>
                ) : (
                  <button onClick={generateDeveloperKey} className="w-full h-11 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-bold rounded-xl hover:opacity-90 active:scale-95 transition-all shadow-lg flex items-center justify-center gap-2 px-6">
                    <Key size={18} />
                    <span className="whitespace-nowrap">Generate API Key</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* System Logs */}
      {user?.is_admin && (
        <div className="bg-[#1b1f2c]/70 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-lg flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gray-500/20 rounded-xl">
              <Terminal className="text-gray-400" size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">System Logs</h3>
              <p className="text-xs text-gray-400">View real-time engine output.</p>
            </div>
          </div>
          <Link to="/logs" className="px-6 py-2 bg-white/10 hover:bg-white/20 text-white font-bold rounded-xl transition-colors flex items-center gap-2">
            Open Dashboard
          </Link>
        </div>
      )}

      {/* Logout */}
      <button 
        onClick={handleLogout}
        className="w-full py-4 bg-red-900/20 hover:bg-red-900/40 border border-red-500/30 text-red-400 font-bold rounded-2xl transition-colors flex items-center justify-center gap-2"
      >
        <LogOut size={18} /> Logout of session securely
      </button>

    </div>
  );
};

export default Settings;
