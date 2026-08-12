export type Lang = "sv" | "en";

export interface Stop {
  id: number;
  slug: string;
  title: Record<Lang, string>;
  text: Record<Lang, string[]>;
  lat: number;
  lng: number;
  confidence: "confirmed" | "estimated";
  mapHint: string;
}
