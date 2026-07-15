import React, { useState, useRef, useEffect } from 'react';
import ParticlesBackground from './ParticlesBackground';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
const SettingsIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const LayoutDashboardIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="3" y="3" width="7" height="9" rx="1" />
    <rect x="14" y="3" width="7" height="5" rx="1" />
    <rect x="14" y="12" width="7" height="9" rx="1" />
    <rect x="3" y="16" width="7" height="5" rx="1" />
  </svg>
);

const ActivityIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const CrownIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="m2 4 3 12h14l3-12-6 7-4-7-4 7-6-7z" />
    <path d="M5 20h14" />
  </svg>
);

const UsersIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const PowerIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
    <line x1="12" y1="2" x2="12" y2="12" />
  </svg>
);

const HelpCircleIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <circle cx="12" cy="12" r="10" />
    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const TrendingUpIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
    <polyline points="17 6 23 6 23 12" />
  </svg>
);

const ShieldAlertIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const BookOpenIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);

const BriefcaseIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
  </svg>
);

const LightbulbIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1.3.5 2.6 1.5 3.5.8.8 1.3 1.5 1.5 2.5" />
    <path d="M9 18h6" />
    <path d="M10 22h4" />
  </svg>
);
import api from '../lib/api';
import { useAuthStore } from '../store/useStore';

const Layout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000);
  const hasLinkedCrypto = Boolean(user?.has_exchange_keys);
  const hasLinkedStock = Boolean(user?.has_alpaca_keys);
  const showAdvancedTabs = isPremium && (hasLinkedCrypto || hasLinkedStock);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  
  const [isBannerDismissed, setIsBannerDismissed] = useState(
    () => sessionStorage.getItem('premiumBannerDismissed') === 'true'
  );

  const handleDismissBanner = () => {
    setIsBannerDismissed(true);
    sessionStorage.setItem('premiumBannerDismissed', 'true');
  };

  const premiumExpiry = user?.premium_expiry || 0;
  const now = Date.now() / 1000;
  const daysUntilExpiry = Math.ceil((premiumExpiry - now) / 86400);
  const showExpirationBanner = isAuthenticated && isPremium && !isBannerDismissed && daysUntilExpiry >= 0 && daysUntilExpiry <= 7;

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
      const { logoutUser } = await import('../lib/firebase');
      await logoutUser();
      setProfileOpen(false);
      navigate('/login');
    } catch (e) {
      console.error('Logout failed', e);
    }
  };

  return (
    <div className="min-h-screen bg-[#0f131f] text-gray-300 dark:text-gray-300 font-sans overflow-x-hidden selection:bg-cyan-500/30 selection:text-cyan-200">
      <ParticlesBackground />
      
      <div className="relative z-10 flex flex-col min-h-screen">
        
        {/* Navbar */}
        <nav className="border-b border-white/5 bg-[#131620]/80 backdrop-blur-md sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-8">
              <Link to={isAuthenticated ? "/dashboard" : "/"} className="text-white font-bold tracking-widest text-lg flex items-center gap-2 hover:opacity-80 transition-opacity">
                <img src="/favicon.svg" alt="Metaverse Sherpa" className="w-8 h-8" />
                Metaverse Sherpa
              </Link>
              
              {/* Navigation links moved to bottom navbar */}
            </div>
            
            <div className="flex items-center gap-4">
              {isAuthenticated ? (
                <div className="relative" ref={profileRef}>
                  <div className="flex items-center gap-4 cursor-pointer">
                    <Link to="/help" className="text-gray-400 hover:text-white transition-colors">
                      <HelpCircleIcon size={20} />
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
                      <Link to={isPremium ? "/portfolio" : "/premium"} onClick={() => setProfileOpen(false)} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors">
                        <BriefcaseIcon size={16} className="text-cyan-400" /> My Portfolio
                      </Link>
                      {isPremium && (
                        <Link to="/recommendations" onClick={() => setProfileOpen(false)} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors">
                        <LightbulbIcon size={16} className="text-cyan-400" /> Recommendations
                        </Link>
                      )}
                      <Link to="/referrals" onClick={() => setProfileOpen(false)} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors">
                        <UsersIcon size={16} className="text-emerald-400" /> Refer & Earn
                      </Link>
                      {user?.is_admin && (
                        <Link to="/admin" onClick={() => setProfileOpen(false)} className="flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors">
                          <ShieldAlertIcon size={16} className="text-purple-400" /> Admin
                        </Link>
                      )}
                      <div className="h-px bg-white/10 my-1"></div>
                      <button onClick={handleLogout} className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-colors text-left">
                        <PowerIcon size={16} className="text-rose-400" /> Logout
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                location.pathname !== '/login' && (
                  <Link to="/login" className="bg-[#3cd7ff] hover:bg-white text-black px-4 py-1.5 rounded-lg font-bold text-xs shadow-[0_0_15px_rgba(60,215,255,0.3)] transition-all uppercase tracking-wider">
                    Login
                  </Link>
                  
                )
              )}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className={`flex-1 w-full max-w-7xl mx-auto flex flex-col ${isAuthenticated ? 'p-4 pb-32 md:p-8 md:pb-32' : 'pb-12'}`}>
          <Outlet />
          
          {/* Financial Disclaimer Footer */}
          <footer className="mt-auto pt-24 pb-8 px-4 text-center">
            <div className="max-w-4xl mx-auto text-[10px] sm:text-xs text-gray-400 leading-relaxed space-y-4">
              <p>
                <strong>Disclaimer:</strong> Trading stocks, options, cryptocurrencies, and other financial instruments involves a high degree of risk and may not be suitable for all investors. Past performance of any trading system or methodology is not necessarily indicative of future results.
              </p>
              <p>
                Metaversesherpa provides algorithmic trading tools and portfolio analytics for informational and educational purposes only. We are not registered financial advisors. By using this platform, you acknowledge that you are solely responsible for your own investment decisions and any resulting financial losses.
              </p>
              <p>
                © {new Date().getFullYear()} Metaversesherpa AI. All rights reserved.
              </p>
            </div>
          </footer>
        </main>

        {showExpirationBanner && (
          <div className="fixed bottom-0 left-0 right-0 md:bottom-24 md:left-1/2 md:-translate-x-1/2 md:right-auto z-40 px-4 pb-[80px] md:pb-0 pointer-events-none w-full max-w-lg">
            <div className="bg-gradient-to-r from-yellow-500 to-yellow-400 rounded-xl p-3 shadow-[0_0_20px_rgba(234,179,8,0.4)] flex items-center justify-between gap-4 pointer-events-auto text-black">
              <div className="flex items-center gap-3">
                <CrownIcon size={20} className="text-black shrink-0" />
                <div className="text-xs sm:text-sm font-medium">
                  Your Premium subscription expires in {daysUntilExpiry} day{daysUntilExpiry !== 1 ? 's' : ''}. 
                  <Link to="/premium" className="ml-1 underline font-bold hover:text-white transition-colors">
                    Renew now
                  </Link>
                </div>
              </div>
              <button onClick={handleDismissBanner} className="text-black hover:text-white transition-colors shrink-0 p-1">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          </div>
        )}

        {/* Unified Bottom Navbar */}
        {isAuthenticated && (
          <div className="fixed bottom-0 left-0 right-0 md:bottom-6 md:left-1/2 md:-translate-x-1/2 md:right-auto bg-[#131620]/95 md:bg-[#1f2028]/95 backdrop-blur-xl border-t md:border border-white/10 z-50 px-2 py-2 flex items-center justify-center gap-1 md:gap-2 pb-safe md:rounded-2xl shadow-2xl overflow-x-auto no-scrollbar max-w-full">
            <Link to="/dashboard" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/dashboard' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
              <LayoutDashboardIcon size={20} className="md:w-4 md:h-4" />
              <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Dashboard</span>
            </Link>
            {isPremium && (
              <Link to="/portfolio" className={`hidden md:flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/portfolio' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <BriefcaseIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Portfolio</span>
              </Link>
            )}
            {showAdvancedTabs && (
              <Link to="/trades" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/trades' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <TrendingUpIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Trades</span>
              </Link>
            )}
            {showAdvancedTabs && (
              <Link to="/signals" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/signals' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <ActivityIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Signals</span>
              </Link>
            )}

            {!isPremium && (
              <Link to="/premium" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/premium' ? 'text-yellow-500 md:bg-yellow-500/20' : 'text-gray-500 hover:text-yellow-500 md:text-gray-400 md:hover:bg-white/5'}`}>
                <CrownIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Premium</span>
              </Link>
            )}
            {!showAdvancedTabs && (
              <Link to="/strategies" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/strategies' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <BookOpenIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Strategies</span>
              </Link>
            )}
            {isPremium && (
              <Link to="/recommendations" className={`${showAdvancedTabs ? 'hidden md:flex' : 'flex'} flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/recommendations' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
                <LightbulbIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Recommendations</span>
              </Link>
            )}
            {user?.is_admin && (
              <Link to="/admin" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/admin' ? 'text-purple-400 md:bg-purple-400/20' : 'text-gray-500 hover:text-purple-400 md:text-gray-400 md:hover:bg-white/5'}`}>
                <ShieldAlertIcon size={20} className="md:w-4 md:h-4" />
                <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Admin</span>
              </Link>
            )}
            <Link to="/settings" className={`flex flex-col md:flex-row items-center justify-center gap-1.5 md:gap-2 min-w-[64px] md:min-w-0 px-2 md:px-4 py-2 rounded-lg transition-colors ${location.pathname === '/settings' ? 'text-cyan-400 md:bg-white/10 md:text-white' : 'text-gray-500 hover:text-gray-300 md:text-gray-400 md:hover:text-white md:hover:bg-white/5'}`}>
              <SettingsIcon size={20} className="md:w-4 md:h-4" />
              <span className="text-[10px] md:text-sm font-medium whitespace-nowrap">Settings</span>
            </Link>
          </div>
        )}

      </div>
    </div>
  );
};

export default Layout;
