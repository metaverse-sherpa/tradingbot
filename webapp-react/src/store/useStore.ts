import { create } from 'zustand'

export interface User {
  id?: number;
  email: string;
  full_name?: string | null;
  uid?: string;
  premium_expiry?: number;
  is_premium?: boolean;
  is_admin?: boolean;
  is_active?: boolean;
  avatar_url?: string | null;
  telegram_chat_id?: number | null;
  has_exchange_keys?: boolean;
  has_alpaca_keys?: boolean;
  exchange_id?: string;
  alpaca_endpoint?: string;
  active_crypto_strategy?: string;
  active_stock_strategy?: string;
  risk_pct?: number;
  stock_risk_pct?: number;
  hide_dollars?: boolean;
  email_notifications?: boolean;
  email_frequency?: string;
  browser_notifications?: boolean;
  ai_strategy_builder_enabled?: boolean;
  payments_count?: number;
  invite_link?: string;
  referral_count?: number;
  referral_credits?: number;
  developer_api_key?: string | null;
  disabled_strategies?: string[];
  risk_profile?: string;
  investment_goal?: string;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  setUser: (user) => set({ user, isAuthenticated: !!user, isLoading: false }),
}))

interface PositionState {
  positions: any[];
  setPositions: (positions: any[]) => void;
}

export const usePositionStore = create<PositionState>((set) => ({
  positions: [],
  setPositions: (positions) => set({ positions }),
}))

interface HistoryState {
  trades: any[];
  setTrades: (trades: any[]) => void;
}

export const useHistoryStore = create<HistoryState>((set) => ({
  trades: [],
  setTrades: (trades) => set({ trades }),
}))

interface DashboardState {
  activeTab: 'crypto' | 'stock';
  setTab: (tab: 'crypto' | 'stock') => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  activeTab: (localStorage.getItem('preferredCategoryTab') as 'crypto' | 'stock') || 'crypto',
  setTab: (tab) => {
    localStorage.setItem('preferredCategoryTab', tab);
    set({ activeTab: tab });
  },
}))
