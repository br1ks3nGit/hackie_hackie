import { useSyncExternalStore } from 'react';
import { API_BASE_URL } from './config';

const HEALTH_TIMEOUT_MS = 5000;

// Starts online: offline is only inferred from an API call that failed to reach the server.
let online = true;
const listeners = new Set<() => void>();

export function setOnline(next: boolean): void {
  if (online === next) return;
  online = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, () => online);
}

// Light reachability check for the offline banner's retry. Any HTTP response means online.
export async function checkConnection(): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    await fetch(`${API_BASE_URL}/health`, { signal: controller.signal });
    setOnline(true);
    return true;
  } catch {
    setOnline(false);
    return false;
  } finally {
    clearTimeout(timer);
  }
}
