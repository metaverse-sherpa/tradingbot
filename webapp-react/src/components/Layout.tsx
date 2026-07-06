import React, { useState, useRef, useEffect } from 'react';
import ParticlesBackground from './ParticlesBackground';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { Settings, LayoutDashboard, Activity, BarChart2, Crown, Users, Power, HelpCircle, TrendingUp } from 'lucide-react';
import { logoutUser } from '../lib/firebase';
import api from '../lib/api';
import { useAuthStore } from '../store/useStore';

const Layout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const hasLinkedCrypto = Boolean(user?.has_exchange_keys);
  const hasLinkedStock = Boolean(user?.has_alpaca_keys);
  const showAdvancedTabs = isPremium && hasLinkedCrypto && hasLinkedStock;
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout');
      await logoutUser();
      setProfileOpen(false);
      navigate('/login');
    } catch (e) {
      console.error('Logout failed', e);
    }
  };

  return (
    <div className="min-h-screen bg-[#0f131f] text-[#6b6375] dark:text-[#9ca3af] font-sans overflow-x-hidden selection:bg-cyan-500/30 selection:text-cyan-200">
      <ParticlesBackground />
      
      <div className="relative z-10 flex flex-col min-h-screen">
        
        {/* Navbar */}
        <nav className="border-b border-white/5 bg-[#131620]/80 backdrop-blur-md sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-8">
              <div className="text-white font-bold tracking-widest text-lg flex items-center gap-2">
                <img src="/favicon.svg" alt="Metaverse Sherpa" className="w-8 h-8" />
                Metaverse Sherpa
              </div>
              
              {/* Navigation links moved to bottom navbar */}
            </div>
            
            <div className="flex items-center gap-4">
              {isAuthenticated ? (
                <div className="relative" ref={profileRef}>
                  <div className="flex items-center gap-4 cursor-pointer">
                    <Link to="/help" className="text-gray-400 hover:text-white transition-colors">
                      <HelpCircle size={20} />
                    </Link>
                    <div onClick={() => setProfileOpen(!profileOpen)} className="flex items-center justify-center relative">
                      {(user as any)?.avatar_url ? (
                        <img src={(user as any).avatar_url} alt="Profile" className="w-8 h-8 rounded-full border border-white/20 object-cover" />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-green-500/20 text-green-400 flex items-center justify-center text-xs font-bold uppercase overflow-hidden border border-white/20">
                          {user?.full_name ? user.full_name.charAt(0) : user?.email?.charAt(0) || 'U'}
                        </div>
                      )}
                      {isPremium && (
                        <div className="absolute -bottom-1 -right-1 bg-yellow-500 rounded-full w-3.5 h-3.5 flex items-center justify-center text-[8px] border-[1.5px] border-[#1f2028] shadow-sm">
                          💎
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* Dropdown Menu */}
                  {profileOpen && (
                    <div className="absolute right-0 mt-2 w-48 bg-[#1f2028] border border-white/10 rounded-xl shadow-2xl py-1 z-50 animate-in fade-in zoom-in-95 duration-200">
                      <Link to="/referrals" onClick={() => setProfileOpen(false)} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors">
                        <Users size={16} className="text-emerald-400" /> Refer & Earn
                      </Link>
                      <div className="h-px bg-white/10 my-1"></div>
                      <button onClick={handleLogout} className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-left">
                        <Power size={16} className="text-rose-400" /> Logout
                      </button>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className={`flex-1 w-full max-w-7xl mx-auto flex flex-col ${isAuthenticated ? 'p-4 pb-24 md:p-8' : ''}`}>
          <Outlet />
        </main>

        {/* Unified Bottom Navbar */}
        {isAuthenticated && (
          <div className="fixed bottom-0 left-0 right-0 md:bottom-6 md:left-1/2 md:-translate-x-1/2 md:right-auto bg-[#131620]/95 md:bg-[#1f2028]/95 backdrop-blur-xl border-t md:border border-white/10 z-50 px-2 py-2 flex items-center justify-start md:justify-center gap-1 md:gap-2 pb-safe md:rounded-2xl shadow-2xl overflow-x-auto no-scrollbar max-w-full">
            <Link to="/dashboard" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/dashboard' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
              <LayoutDashboard size={20} className="md:w-4 md:h-4" />
              <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Dashboard</span>
            </Link>
            {showAdvancedTabs && (
              <Link to="/trades" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/trades' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <TrendingUp size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Trades</span>
              </Link>
            )}
            {showAdvancedTabs && (
              <Link to="/signals" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/signals' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <Activity size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Signals</span>
              </Link>
            )}
            {showAdvancedTabs && (
              <Link to="/stats" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/stats' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <BarChart2 size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Stats</span>
              </Link>
            )}
            {!isPremium && (
              <Link to="/premium" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/premium' ? 'text-yellow-500 md:bg-yellow-500/20' : 'text-gray-500 hover:text-yellow-500 md:text-gray-400 md:hover:bg-white/5'}`}>
                <Crown size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Premium</span>
              </Link>
            )}
            <Link to="/settings" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/settings' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
              <Settings size={20} className="md:w-4 md:h-4" />
              <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Settings</span>
            </Link>
          </div>
        )}

      </div>
    </div>
  );
};

export default Layout;
