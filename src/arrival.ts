import type { Stop } from "./types";
import { distanceMetres } from "./hooks/useGeolocation";

// Some stops are close together (6 and 7 are ~43 m apart), and phone GPS wanders by
// 10–30 m, so a single radius makes the "you're near" banner flicker between stops.
// Instead a stop has to be clearly reached to become active, and stays active until
// the walker has clearly left it or is clearly nearer another stop.
const ENTER_M = 30;
const EXIT_M = 55;
const SWITCH_MARGIN_M = 12;
// Fixes worse than this are too vague to change which stop is active.
const MAX_USEFUL_ACCURACY_M = 50;

export function nextActiveStop(
  stops: Stop[],
  prevId: number | null,
  pos: { lat: number; lng: number } | null,
  accuracy: number | null
): number | null {
  if (!pos) return null;
  if (accuracy != null && accuracy > MAX_USEFUL_ACCURACY_M) return prevId;

  const dists = stops.map((s) => ({ id: s.id, d: distanceMetres(pos.lat, pos.lng, s.lat, s.lng) }));
  const nearest = dists.reduce((a, b) => (b.d < a.d ? b : a));
  const prev = dists.find((x) => x.id === prevId);

  if (prev && prev.d <= EXIT_M) {
    if (nearest.id !== prev.id && nearest.d <= ENTER_M && nearest.d + SWITCH_MARGIN_M < prev.d) {
      return nearest.id;
    }
    return prev.id;
  }
  return nearest.d <= ENTER_M ? nearest.id : null;
}

// Straight-line route length; real walking distance is a bit longer.
export function routeLengthMetres(stops: Stop[]): number {
  let total = 0;
  for (let i = 1; i < stops.length; i++) {
    total += distanceMetres(stops[i - 1].lat, stops[i - 1].lng, stops[i].lat, stops[i].lng);
  }
  return total;
}
