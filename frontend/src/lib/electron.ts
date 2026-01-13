/**
 * Electron IPC API interface.
 * 
 * These functions communicate with the Electron main process via IPC.
 * They are only available when running in an Electron environment.
 */

declare global {
  interface Window {
    electronAPI?: {
      findChromePath: () => Promise<string[]>;
      chooseChromePath: () => Promise<string | null>;
      getSettings: () => Promise<UserSettings>;
      updateSettings: (settings: UserSettings) => Promise<UserSettings>;
    };
  }
}

import type { UserSettings } from "./models";

/**
 * Check if running in Electron environment.
 */
export function isElectron(): boolean {
  return typeof window !== "undefined" && window.electronAPI !== undefined;
}

/**
 * Find Chrome installation paths on the system.
 * 
 * @returns Array of valid Chrome executable paths
 * @throws Error if not running in Electron or if IPC fails
 */
export async function findChromePath(): Promise<string[]> {
  if (!isElectron()) {
    throw new Error("findChromePath is only available in Electron environment");
  }
  
  return window.electronAPI!.findChromePath();
}

/**
 * Open file picker to choose Chrome executable.
 */
export async function chooseChromePath(): Promise<string | null> {
  if (!isElectron()) {
    throw new Error("chooseChromePath is only available in Electron environment");
  }

  return window.electronAPI!.chooseChromePath();
}

/**
 * Get user settings from the local filesystem.
 * 
 * @returns User settings object
 * @throws Error if not running in Electron or if IPC fails
 */
export async function getSettings(): Promise<UserSettings> {
  if (!isElectron()) {
    throw new Error("getSettings is only available in Electron environment");
  }
  
  return window.electronAPI!.getSettings();
}

/**
 * Update user settings and save to the local filesystem.
 * 
 * @param settings - Settings object to save
 * @returns Updated settings object
 * @throws Error if not running in Electron or if IPC fails
 */
export async function updateSettings(settings: UserSettings): Promise<UserSettings> {
  if (!isElectron()) {
    throw new Error("updateSettings is only available in Electron environment");
  }
  
  return window.electronAPI!.updateSettings(settings);
}
