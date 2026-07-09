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

const PageLoader = () => (
  <div className="flex-1 flex items-center justify-center min-h-[50vh]">
    <div className="w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
  </div>
);

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) return <PageLoader />;
  
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }

  return <>{children}</>;
};

const PremiumRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) return <PageLoader />;

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }

  const isPremium = Boolean(user?.is_premium) || ((user?.premium_expiry || 0) > Date.now() / 1000) || !!user?.is_admin;
  if (!isPremium) {
    return <Navigate to="/premium" replace />;
  }

  return <>{children}</>;
};

const AdminRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

  if (isLoading) return <PageLoader />;

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  }

  if (!user?.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

const App: React.FC = () => {
  const { setUser } = useAuthStore();
  
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
            <Route path="dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
            <Route path="stats" element={<Navigate to="/signals" replace />} />
            <Route path="signals" element={<ProtectedRoute><SignalsPage /></ProtectedRoute>} />
            <Route path="trades" element={<ProtectedRoute><TradesPage /></ProtectedRoute>} />
            <Route path="backtests" element={<ProtectedRoute><BacktestsPage /></ProtectedRoute>} />
            <Route path="premium" element={<ProtectedRoute><PremiumPage /></ProtectedRoute>} />
            <Route path="referrals" element={<ProtectedRoute><ReferralsPage /></ProtectedRoute>} />
            <Route path="portfolio" element={<PremiumRoute><PortfolioPage /></PremiumRoute>} />
            
            <Route path="admin" element={<AdminRoute><AdminPage /></AdminRoute>} />
            <Route path="logs" element={<AdminRoute><LogsPage /></AdminRoute>} />
            
            <Route path="help" element={<ProtectedRoute><HelpPage /></ProtectedRoute>} />
            
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  );

};

export default App;
