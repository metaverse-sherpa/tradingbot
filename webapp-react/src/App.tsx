import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';

import Dashboard from './components/Dashboard';
import Settings from './components/Settings';
import StatsPage from './components/StatsPage';
import SignalsPage from './components/SignalsPage';
import TradesPage from './components/TradesPage';
import StrategiesPage from './components/StrategiesPage';
import BacktestsPage from './components/BacktestsPage';
import PremiumPage from './components/PremiumPage';
import ReferralsPage from './components/ReferralsPage';
import AdminPage from './components/AdminPage';
import LogsPage from './components/LogsPage';
import HelpPage from './components/HelpPage';
import LandingPage from './components/LandingPage';
import LoginPage from './components/LoginPage';
import { useEffect } from 'react';
import { auth } from './lib/firebase';
import { onIdTokenChanged } from 'firebase/auth';
import api from './lib/api';
import { useAuthStore } from './store/useStore';

const App: React.FC = () => {
  const { setUser, isAuthenticated, isLoading } = useAuthStore();
  
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
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<LandingPage />} />
          <Route path="login" element={!isAuthenticated ? <LoginPage /> : <Dashboard />} />
          {isAuthenticated && (
            <>
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="settings" element={<Settings />} />
              <Route path="stats" element={<StatsPage />} />
              <Route path="signals" element={<SignalsPage />} />
              <Route path="trades" element={<TradesPage />} />
              <Route path="strategies" element={<StrategiesPage />} />
              <Route path="backtests" element={<BacktestsPage />} />
              <Route path="premium" element={<PremiumPage />} />
              <Route path="referrals" element={<ReferralsPage />} />
              <Route path="admin" element={<AdminPage />} />
              <Route path="logs" element={<LogsPage />} />
              <Route path="help" element={<HelpPage />} />
            </>
          )}
          <Route path="*" element={<Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
