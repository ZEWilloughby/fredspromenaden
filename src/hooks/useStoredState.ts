import { useEffect, useState } from "react";

// useState backed by localStorage. Storage can be unavailable (private mode, blocked
// site data), so every access is guarded and the app works without it.
export function useStoredState<T>(key: string, initial: () => T): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      if (raw != null) return JSON.parse(raw) as T;
    } catch {
      // fall through to the default
    }
    return initial();
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // not persisted; fine
    }
  }, [key, value]);

  return [value, setValue];
}
