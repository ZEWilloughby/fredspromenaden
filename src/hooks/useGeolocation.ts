import { useEffect, useState } from "react";

export interface GeoState {
  lat: number | null;
  lng: number | null;
  accuracy: number | null;
  error: string | null;
  permission: "prompt" | "granted" | "denied" | "unsupported";
}

export function useGeolocation(enabled: boolean): GeoState {
  const [state, setState] = useState<GeoState>({
    lat: null,
    lng: null,
    accuracy: null,
    error: null,
    permission: "prompt",
  });

  useEffect(() => {
    if (!enabled) return;
    if (!("geolocation" in navigator)) {
      setState((s) => ({ ...s, permission: "unsupported", error: "Geolocation not supported" }));
      return;
    }

    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setState({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          error: null,
          permission: "granted",
        });
      },
      (err) => {
        setState((s) => ({
          ...s,
          error: err.message,
          permission: err.code === err.PERMISSION_DENIED ? "denied" : s.permission,
        }));
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [enabled]);

  return state;
}

// Haversine distance in metres.
export function distanceMetres(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
