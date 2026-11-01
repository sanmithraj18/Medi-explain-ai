import { create } from 'zustand';
import type { User, Subscription } from '@/types';

interface AuthState {
  user: User | null;
  subscription: Subscription | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setSubscription: (sub: Subscription | null) => void;
  setLoading: (loading: boolean) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  subscription: null,
  loading: true,
  setUser: (user) => set({ user }),
  setSubscription: (subscription) => set({ subscription }),
  setLoading: (loading) => set({ loading }),
  reset: () => set({ user: null, subscription: null, loading: false }),
}));
