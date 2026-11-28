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

const AUTH_CACHE_KEY = 'ms_auth_ui_cache';

export type CachedAuthUser = Pick<
  User,
  | 'email'
  | 'full_name'
  | 'avatar_url'
  | 'is_premium'
  | 'premium_expiry'
  | 'is_admin'
  | 'has_alpaca_keys'
  | 'ai_strategy_builder_enabled'
  | 'payments_count'
>;

function readCachedAuthUser(): CachedAuthUser | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(AUTH_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed.email === 'string' ? parsed : null;
  } catch {
    return null;
  }
}

function writeCachedAuthUser(user: User | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (!user) {
      localStorage.removeItem(AUTH_CACHE_KEY);
      return;
    }
    const snapshot: CachedAuthUser = {
      email: user.email,
      full_name: user.full_name,
      avatar_url: user.avatar_url,
      is_premium: user.is_premium,
      premium_expiry: user.premium_expiry,
      is_admin: user.is_admin,
      has_alpaca_keys: user.has_alpaca_keys,
      ai_strategy_builder_enabled: user.ai_strategy_builder_enabled,
      payments_count: user.payments_count,
    };
    localStorage.setItem(AUTH_CACHE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore storage quota/private-mode errors
  }
}

export const hasCachedAuthSession = (): boolean => Boolean(readCachedAuthUser());

interface AuthState {
  user: User | null;
  cachedUser: CachedAuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isSyncing: boolean;
  isLoggingOut: boolean;
  authError: string | null;
  setUser: (user: User | null) => void;
  setSyncing: (isSyncing: boolean) => void;
  setLoggingOut: (isLoggingOut: boolean) => void;
  setAuthError: (authError: string | null) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  cachedUser: readCachedAuthUser(),
  isAuthenticated: false,
  isLoading: true,
  isSyncing: false,
  isLoggingOut: false,
  authError: null,
  setUser: (user) => {
    writeCachedAuthUser(user);
    set({ user, cachedUser: null, isAuthenticated: !!user, isLoading: false, isSyncing: false });
  },
  setSyncing: (isSyncing) => set({ isSyncing }),
  setLoggingOut: (isLoggingOut) => set({ isLoggingOut }),
  setAuthError: (authError) => set({ authError }),
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
