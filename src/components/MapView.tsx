import { MapContainer, TileLayer, Marker, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import { useEffect } from "react";
import type { Stop } from "../types";

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

// Leaflet sometimes measures the container before the flex layout settles,
// so the initial bounds fit is computed against a stale (usually 300x150) size.
function FixSize({ bounds }: { bounds: L.LatLngBounds }) {
  const map = useMap();
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      map.invalidateSize();
      map.fitBounds(bounds, { padding: [32, 32] });
    });
    return () => cancelAnimationFrame(id);
  }, [map, bounds]);
  return null;
}

interface Props {
  stops: Stop[];
  activeStopId: number | null;
  onSelectStop: (id: number) => void;
  userPos: { lat: number; lng: number } | null;
}

export default function MapView({ stops, activeStopId, onSelectStop, userPos }: Props) {
  const routeLine = stops.map((s) => [s.lat, s.lng] as [number, number]);
  const bounds = L.latLngBounds(routeLine);

  return (
    <MapContainer
      bounds={bounds}
      boundsOptions={{ padding: [32, 32] }}
      className="map-container"
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FixSize bounds={bounds} />
      <Polyline positions={routeLine} pathOptions={{ color: "#2f6f4f", weight: 3, dashArray: "6 6" }} />
      {stops.map((stop) => (
        <Marker
          key={stop.id}
          position={[stop.lat, stop.lng]}
          icon={numberedIcon(stop.id, stop.id === activeStopId, stop.confidence)}
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
