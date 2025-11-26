import { create } from 'zustand';
import { persist } from 'zustand/middleware';


export interface User {
    id: string
    email: string | null
    name: string | null
    avatar: string | null
}

interface AuthStore {
    user: User | null;

    setUser: (user: User | null) => void;

}


export const useAuthStore = create<AuthStore>()(
    persist(
        (set, get) => ({
            user: null,
            setUser: (user) => set({ user })
        }),
        {
            name: "auth",
            partialize: (state) => ({
                user: state.user
            })
        }
    )
)