import { create } from "zustand";

export interface User {
  id: string;
  email: string | null;
  name: string | null;
  avatar: string | null;
}

interface AuthStore {
  user: User | null;
  setUser: (user: User | null) => void;
  authToken: string | null;
  setAuthToken: (authToken: string | null) => void;
}

export const useAuthStore = create<AuthStore>()((set, get) => ({
  user: null,
  setUser: (user) => set({ user }),
  authToken: null,
  setAuthToken: (authToken) => set({ authToken }),
}));
