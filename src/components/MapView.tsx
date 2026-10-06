import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import { useEffect, useMemo } from "react";
import type { Stop, Lang } from "../types";

function numberedIcon(n: number, active: boolean, confidence: Stop["confidence"]): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div class="stop-pin ${active ? "stop-pin--active" : ""} ${
      confidence === "estimated" ? "stop-pin--estimated" : ""
    }">${n}</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

// Leaflet sometimes measures the container before the flex layout settles, so the
// initial bounds fit is computed against a stale (usually 300x150) size. It also can't
// measure while hidden, so re-measure whenever the map comes back into view, without
// refitting, so the walker's own zoom and pan are kept.
function FixSize({ bounds, visible }: { bounds: L.LatLngBounds; visible: boolean }) {
  const map = useMap();
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      map.invalidateSize();
      map.fitBounds(bounds, { padding: [32, 32] });
    });
    return () => cancelAnimationFrame(id);
  }, [map, bounds]);
  useEffect(() => {
    if (!visible) return;
    const id = requestAnimationFrame(() => map.invalidateSize());
    return () => cancelAnimationFrame(id);
  }, [map, visible]);
  return null;
}

interface Props {
  stops: Stop[];
  lang: Lang;
  visible: boolean;
  activeStopId: number | null;
  onSelectStop: (id: number) => void;
  userPos: { lat: number; lng: number } | null;
}

export default function MapView({ stops, lang, visible, activeStopId, onSelectStop, userPos }: Props) {
  const routeLine = useMemo(() => stops.map((s) => [s.lat, s.lng] as [number, number]), [stops]);
  const bounds = useMemo(() => L.latLngBounds(routeLine), [routeLine]);
  const icons = useMemo(
    () => new Map(stops.map((s) => [s.id, numberedIcon(s.id, s.id === activeStopId, s.confidence)])),
    [stops, activeStopId]
  );

  return (
    <MapContainer
      bounds={bounds}
      boundsOptions={{ padding: [32, 32] }}
      className="map-container"
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FixSize bounds={bounds} visible={visible} />
      <Polyline positions={routeLine} pathOptions={{ color: "#2f6f4f", weight: 3, dashArray: "6 6" }} />
      {stops.map((stop) => (
        <Marker
          key={`${stop.id}-${lang}`}
          position={[stop.lat, stop.lng]}
          icon={icons.get(stop.id)!}
          title={`${stop.id}. ${stop.title[lang]}`}
          alt={`${stop.id}. ${stop.title[lang]}`}
          eventHandlers={{ click: () => onSelectStop(stop.id) }}
        />
      ))}
      {userPos && (
        <CircleMarker
          center={[userPos.lat, userPos.lng]}
          radius={8}
          pathOptions={{ color: "#1a73e8", fillColor: "#4285f4", fillOpacity: 0.9 }}
        />
      )}
    </MapContainer>
  );
}
