import { useEffect, useMemo, useState } from "react";
import stopsData from "./data/stops.json";
import type { Stop, Lang } from "./types";
import MapView from "./components/MapView";
import StopDetail from "./components/StopDetail";
import { useGeolocation, distanceMetres } from "./hooks/useGeolocation";
import "leaflet/dist/leaflet.css";
import "./App.css";

const stops = stopsData as Stop[];
const ARRIVAL_RADIUS_M = 40;

const copy = {
  sv: {
    title: "Fredspromenaden",
    subtitle: "En vandring genom Ålands fredsarbete",
    gpsOn: "GPS på",
    gpsOff: "GPS av",
    arrived: "Du är nära",
    open: "Öppna",
    dismiss: "Stäng",
    listTitle: "Alla stopp",
  },
  en: {
    title: "The Peace Walk",
    subtitle: "A walk through Åland's peace work",
    gpsOn: "GPS on",
    gpsOff: "GPS off",
    arrived: "You're near",
    open: "Open",
    dismiss: "Dismiss",
    listTitle: "All stops",
  },
};

export default function App() {
  const [lang, setLang] = useState<Lang>("sv");
  const [view, setView] = useState<"map" | "detail">("map");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gpsEnabled, setGpsEnabled] = useState(false);
  const [dismissedArrival, setDismissedArrival] = useState<number | null>(null);

  const geo = useGeolocation(gpsEnabled);
  const userPos = geo.lat != null && geo.lng != null ? { lat: geo.lat, lng: geo.lng } : null;

  const nearest = useMemo(() => {
    if (!userPos) return null;
    let best: { stop: Stop; dist: number } | null = null;
    for (const stop of stops) {
      const d = distanceMetres(userPos.lat, userPos.lng, stop.lat, stop.lng);
      if (!best || d < best.dist) best = { stop, dist: d };
    }
    return best;
  }, [userPos]);

  const selectedStop = stops.find((s) => s.id === selectedId) ?? null;
  const selectedDistance =
    userPos && selectedStop
      ? distanceMetres(userPos.lat, userPos.lng, selectedStop.lat, selectedStop.lng)
      : null;

  const showArrivalBanner =
    gpsEnabled &&
    nearest &&
    nearest.dist <= ARRIVAL_RADIUS_M &&
    nearest.stop.id !== dismissedArrival &&
    !(view === "detail" && selectedId === nearest.stop.id);

  useEffect(() => {
    if (!nearest || nearest.dist > ARRIVAL_RADIUS_M) {
      setDismissedArrival(null);
    }
  }, [nearest?.stop.id, nearest?.dist]);

  const c = copy[lang];

  function openStop(id: number) {
    setSelectedId(id);
    setView("detail");
  }

  function backToMap() {
    setView("map");
  }

  const idx = selectedStop ? stops.findIndex((s) => s.id === selectedStop.id) : -1;

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1 className="app__title">{c.title}</h1>
          <p className="app__subtitle">{c.subtitle}</p>
        </div>
        <div className="app__controls">
          <button
            className={`btn btn--toggle ${gpsEnabled ? "btn--active" : ""}`}
            onClick={() => setGpsEnabled((v) => !v)}
          >
            {gpsEnabled ? c.gpsOn : c.gpsOff}
          </button>
          <button className="btn btn--toggle" onClick={() => setLang(lang === "sv" ? "en" : "sv")}>
            {lang === "sv" ? "EN" : "SV"}
          </button>
        </div>
      </header>

      {showArrivalBanner && nearest && (
        <div className="arrival-banner">
          <span>
            {c.arrived}: <strong>{nearest.stop.title[lang]}</strong>
          </span>
          <div className="arrival-banner__actions">
            <button className="btn btn--small" onClick={() => openStop(nearest.stop.id)}>
              {c.open}
            </button>
            <button
              className="btn btn--small btn--ghost"
              onClick={() => setDismissedArrival(nearest.stop.id)}
            >
              {c.dismiss}
            </button>
          </div>
        </div>
      )}

      {view === "map" && (
        <>
          <MapView
            stops={stops}
            activeStopId={nearest && nearest.dist <= ARRIVAL_RADIUS_M ? nearest.stop.id : null}
            onSelectStop={openStop}
            userPos={userPos}
          />
          <div className="stop-list">
            <h2 className="stop-list__title">{c.listTitle}</h2>
            <ul>
              {stops.map((s) => (
                <li key={s.id}>
                  <button className="stop-list__item" onClick={() => openStop(s.id)}>
                    <span className="stop-list__num">{s.id}</span>
                    <span>{s.title[lang]}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {view === "detail" && selectedStop && (
        <StopDetail
          stop={selectedStop}
          lang={lang}
          distanceMetres={selectedDistance}
          onBack={backToMap}
          onPrev={() => idx > 0 && openStop(stops[idx - 1].id)}
          onNext={() => idx < stops.length - 1 && openStop(stops[idx + 1].id)}
          hasPrev={idx > 0}
          hasNext={idx < stops.length - 1}
        />
      )}
    </div>
  );
}
