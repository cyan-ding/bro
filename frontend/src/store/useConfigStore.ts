import { create } from "zustand";

interface ConfigStore {
  chromePath: string | null
  setChromePath: (chromePath: string | null) => void
  localModels: string[] 
  setLocalModels: (localModels: string[]) => void;
  providerModels: string[]
  setProviderModels: (providerModels: string[]) => void;

}

export const useAuthStore = create<ConfigStore>()((set, get) => ({
    chromePath: null,
    setChromePath: (chromePath) => set({chromePath}),
    localModels: [] ,
    setLocalModels: (localModels) => set({localModels}),
    providerModels: [],
    setProviderModels: (providerModels) => set({providerModels}),
}));
