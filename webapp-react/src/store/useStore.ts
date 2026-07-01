import { create } from 'zustand'

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  login: (userData: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  login: (userData) => set({ user: userData, isAuthenticated: true }),
  logout: () => set({ user: null, isAuthenticated: false }),
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
