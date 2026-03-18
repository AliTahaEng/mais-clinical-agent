/**
 * Zustand store for admin authentication token.
 */
import { create } from "zustand";

interface AdminState {
  token: string;
  setToken: (token: string) => void;
  clearToken: () => void;
}

export const useAdminStore = create<AdminState>((set) => ({
  token: "",
  setToken: (token) => set({ token }),
  clearToken: () => set({ token: "" }),
}));
