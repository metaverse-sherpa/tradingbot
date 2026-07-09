import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Layout from './components/Layout';

const Dashboard = React.lazy(() => import('./components/Dashboard'));
const Settings = React.lazy(() => import('./components/Settings'));
const SignalsPage = React.lazy(() => import('./components/SignalsPage'));
const TradesPage = React.lazy(() => import('./components/TradesPage'));
const StrategiesPage = React.lazy(() => import('./components/StrategiesPage'));
const ValkyrieElitePage = React.lazy(() => import('./components/ValkyrieElitePage'));
const SherpaVelocityPage = React.lazy(() => import('./components/SherpaVelocityPage'));
const BacktestsPage = React.lazy(() => import('./components/BacktestsPage'));
const PremiumPage = React.lazy(() => import('./components/PremiumPage'));
const ReferralsPage = React.lazy(() => import('./components/ReferralsPage'));
const AdminPage = React.lazy(() => import('./components/AdminPage'));
const LogsPage = React.lazy(() => import('./components/LogsPage'));
const HelpPage = React.lazy(() => import('./components/HelpPage'));
const LandingPage = React.lazy(() => import('./components/LandingPage'));
const LoginPage = React.lazy(() => import('./components/LoginPage'));
import { useEffect } from 'react';
import { auth } from './lib/firebase';
import { onIdTokenChanged } from 'firebase/auth';
import api from './lib/api';
import { useAuthStore } from './store/useStore';

// Type inference sometimes needs static import, but we'll dynamic import the component
const PortfolioPage = React.lazy(() => import('./components/PortfolioPage'));

const RequireAuthFallback = () => {
  const { isAuthenticated } = useAuthStore();
  const location = useLocation();
  
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }
  
  // Save the attempted URL for redirecting after login
  return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
};

const PageLoader = () => (
  <div className="flex-1 flex items-center justify-center min-h-[50vh]">
    <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
  </div>
);

const App: React.FC = () => {
  const { user, setUser, isAuthenticated, isLoading } = useAuthStore();
  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000) || !!user?.is_admin;
  
  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    const unsubscribe = onIdTokenChanged(auth, async (user) => {
      if (user) {
        const syncUser = async () => {
          try {
            // Sync with backend
            const res = await api.post('/auth/sync', {});
            const finalUser = { ...res.data.user, avatar_url: user.photoURL || res.data.user.avatar_url };
            setUser(finalUser);
          } catch (e) {
            console.error("Auth sync failed", e);
            setUser(null);
          }
        };
        syncUser();
        // Background polling for global user updates every 15 mins
        interval = setInterval(syncUser, 15 * 60 * 1000);
      } else {
        setUser(null);
        if (interval) clearInterval(interval);
      }
    });

    return () => {
      unsubscribe();
      if (interval) clearInterval(interval);
    };
  }, [setUser]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#0b0e14] text-white flex items-center justify-center font-sans">
        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <React.Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<LandingPage />} />
            <Route path="login" element={<LoginPage />} />
            <Route path="strategies" element={<StrategiesPage />} />
            <Route path="strategies/valkyrie-elite" element={<ValkyrieElitePage />} />
            <Route path="strategies/sherpa-velocity" element={<SherpaVelocityPage />} />
            {isAuthenticated && (
              <>
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="settings" element={<Settings />} />
                <Route path="stats" element={<Navigate to="/signals" replace />} />
                <Route path="signals" element={<SignalsPage />} />
                <Route path="trades" element={<TradesPage />} />
                <Route path="backtests" element={<BacktestsPage />} />
                <Route path="premium" element={<PremiumPage />} />
                <Route path="referrals" element={<ReferralsPage />} />
                <Route path="portfolio" element={isPremium ? <PortfolioPage /> : <Navigate to="/premium" replace />} />
                {user?.is_admin && (
                  <>
                    <Route path="admin" element={<AdminPage />} />
                    <Route path="logs" element={<LogsPage />} />
                  </>
                )}
                <Route path="help" element={<HelpPage />} />
              </>
            )}
            <Route path="*" element={<RequireAuthFallback />} />
          </Route>
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  );

};

export default App;
