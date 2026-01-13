/**
 * Settings utilities.
 * 
 * Provides a unified interface for settings operations that works
 * in both Electron and web environments (with fallback).
 * 
 * basically, wrappers for the functions in @electron.ts
 */

import type { UserSettings } from "./models";
import * as electronAPI from "./electron";

/**
 * Get user settings.
 * Uses Electron IPC if available, otherwise falls back to HTTP API.
 */
export async function getSettings(): Promise<UserSettings> {
  if (electronAPI.isElectron()) {
    return electronAPI.getSettings();
  }
  
  // Fallback to HTTP API for web environment
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const response = await fetch(`${API_BASE_URL}/settings`);
  if (!response.ok) {
    throw new Error(`Failed to get settings: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Update user settings.
 * Uses Electron IPC if available, otherwise falls back to HTTP API.
 */
export async function updateSettings(settings: UserSettings): Promise<UserSettings> {
  if (electronAPI.isElectron()) {
    return electronAPI.updateSettings(settings);
  }
  
  // Fallback to HTTP API for web environment
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const response = await fetch(`${API_BASE_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to update settings: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Find Chrome installation paths.
 * Only available in Electron environment.
 */
export async function findChromePath(): Promise<string[]> {
  if (!electronAPI.isElectron()) {
    throw new Error("findChromePath is only available in Electron environment");
  }
  
  return electronAPI.findChromePath();
}

/**
 * Open file picker to select Chrome executable.
 */
export async function chooseChromePath(): Promise<string | null> {
  if (!electronAPI.isElectron()) {
    throw new Error("chooseChromePath is only available in Electron environment");
  }

  return electronAPI.chooseChromePath();
}
