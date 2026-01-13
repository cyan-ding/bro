import { getSettings, updateSettings } from "@/lib/settings";
import { UserSettings } from "@/lib/models";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ConfigStore {
  settings: UserSettings | null;
  loadSettings: () => Promise<void>;
  updateSettings: (updates: UserSettings) => Promise<void>;
}

export const useConfigStore = create<ConfigStore>()(
  persist(
    (set, get) => ({
      settings: null,
      loadSettings: async () => {
        try {
          const settings = await getSettings();
          set({ settings });
        } catch (error) {
          console.error("Failed to load settings", error)
        }
      },
      updateSettings: async (updates) => {
        const current = get().settings;
        if (!current) return;

        try {
          const updated = await updateSettings(updates);
          set({ settings: updated });
        } catch (error) {
          console.error("Failed to update settings", error);
        }
      }
    }),
    {
      name: "bro-config",
      partialize: (state) => ({ settings: state.settings })
    }
  )
);
