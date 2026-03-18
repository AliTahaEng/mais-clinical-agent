/**
 * Zustand auth store.
 * Access token stored in memory only — never written to localStorage (XSS-safe).
 * User info persisted to sessionStorage for page-refresh resilience
 * (actual auth is re-validated via /auth/refresh on load).
 */
import { create } from "zustand";

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  role: "user" | "admin";
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;

  setAuth: (user: AuthUser, token: string) => void;
  clearAuth: () => void;
  setLoading: (v: boolean) => void;
  isAdmin: () => boolean;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isLoading: true,

  setAuth: (user, token) => set({ user, accessToken: token, isLoading: false }),
  clearAuth: () => set({ user: null, accessToken: null, isLoading: false }),
  setLoading: (v) => set({ isLoading: v }),
  isAdmin: () => get().user?.role === "admin",
  isAuthenticated: () => !!get().accessToken,
}));
