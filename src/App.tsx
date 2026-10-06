import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import stopsData from "./data/stops.json";
import type { Stop, Lang } from "./types";
import MapView from "./components/MapView";
import StopDetail from "./components/StopDetail";
import { useGeolocation, distanceMetres, type GeoError } from "./hooks/useGeolocation";
import { useRoute } from "./hooks/useRoute";
import { useStoredState } from "./hooks/useStoredState";
import { nextActiveStop, routeLengthMetres } from "./arrival";
import "leaflet/dist/leaflet.css";
import "./App.css";

const stops = stopsData as Stop[];

const SOURCE_URL = "https://peace.ax/mojligheter/fredspromenaden/";
// Straight lines between stops undercount the walk; streets add roughly a fifth.
const WALK_KM = (routeLengthMetres(stops) * 1.2) / 1000;
// Walking at ~4.5 km/h plus a few minutes of reading at each stop, rounded to 15 min.
const WALK_MIN = Math.round(((WALK_KM / 4.5) * 60 + stops.length * 3) / 15) * 15;

const copy = {
  sv: {
    locale: "sv-FI",
    title: "Fredspromenaden",
    subtitle: "En vandring genom Ålands fredsarbete",
    gpsOn: "GPS på",
    gpsOff: "GPS av",
    gpsSearching: "Söker…",
    switchLang: "Switch to English",
    arrived: "Du är nära",
    open: "Öppna",
    dismiss: "Stäng",
    listTitle: "Alla stopp",
    summary: (km: string, min: number) => `${stops.length} stopp · ca ${km} km · ca ${min} min`,
    read: "läst",
    resetRead: "Nollställ lästa",
    gpsDenied:
      "Webbläsaren har inte tillåtelse att använda din position. Ändra det i webbläsarens inställningar för att använda GPS. Du kan också bläddra bland stoppen utan GPS.",
    gpsUnsupported: "Den här enheten kan inte visa din position. Du kan fortfarande bläddra bland stoppen.",
    gpsUnavailable: "Kunde inte fastställa din position just nu. Försöker igen…",
    about: "Texterna kommer från Ålands fredsinstituts guide till Fredspromenaden.",
    aboutLink: "Läs mer på peace.ax",
  },
  en: {
    locale: "en-GB",
    title: "The Peace Walk",
    subtitle: "A walk through Åland's peace work",
    gpsOn: "GPS on",
    gpsOff: "GPS off",
    gpsSearching: "Locating…",
    switchLang: "Byt till svenska",
    arrived: "You're near",
    open: "Open",
    dismiss: "Dismiss",
    listTitle: "All stops",
    summary: (km: string, min: number) => `${stops.length} stops · about ${km} km · about ${min} min`,
    read: "read",
    resetRead: "Clear read stops",
    gpsDenied:
      "Your browser isn't allowed to use your location. Change this in your browser settings to use GPS. You can still browse the stops without it.",
    gpsUnsupported: "This device can't share your location. You can still browse the stops.",
    gpsUnavailable: "Can't find your position right now. Still trying…",
    about: "Texts from Ålands fredsinstitut's guide to the Peace Walk.",
    aboutLink: "More at peace.ax",
  },
};

function defaultLang(): Lang {
  const langs = navigator.languages ?? [navigator.language];
  return langs.some((l) => l.toLowerCase().startsWith("sv")) ? "sv" : "en";
}

export default function App() {
  const [storedLang, setLang] = useStoredState<Lang>("fp-lang", defaultLang);
  const lang: Lang = storedLang === "en" ? "en" : "sv";
  const [visited, setVisited] = useStoredState<number[]>("fp-visited", () => []);
  const [gpsEnabled, setGpsEnabled] = useState(false);
  const [gpsNotice, setGpsNotice] = useState<GeoError>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [dismissedId, setDismissedId] = useState<number | null>(null);
  const { stopId, openStop, backToMap } = useRoute();
  const listScrollY = useRef(0);

  const geo = useGeolocation(gpsEnabled);
  const userPos = useMemo(
    () => (geo.lat != null && geo.lng != null ? { lat: geo.lat, lng: geo.lng } : null),
    [geo.lat, geo.lng]
  );

  // Denied or unsupported location is final until the user tries again, so switch GPS off
  // and explain why, rather than leaving a toggle that says "on" and does nothing.
  useEffect(() => {
    if (geo.error === "denied" || geo.error === "unsupported") {
      setGpsNotice(geo.error);
      setGpsEnabled(false);
    }
  }, [geo.error]);

  useEffect(() => {
    const next = nextActiveStop(stops, activeId, userPos, geo.accuracy);
    if (next !== activeId) {
      setActiveId(next);
      setDismissedId(null);
    }
  }, [userPos, geo.accuracy, activeId]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const selectedStop = stops.find((s) => s.id === stopId) ?? null;
  const view = selectedStop ? "detail" : "map";

  useEffect(() => {
    if (selectedStop && !visited.includes(selectedStop.id)) {
      setVisited((v) => [...v, selectedStop.id]);
    }
  }, [selectedStop, visited, setVisited]);

  useEffect(() => {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  }, []);

  // A new stop always starts at the top; returning to the map puts the list back where it was.
  useLayoutEffect(() => {
    window.scrollTo(0, view === "detail" ? 0 : listScrollY.current);
  }, [view, stopId]);

  const selectedDistance =
    userPos && selectedStop
      ? distanceMetres(userPos.lat, userPos.lng, selectedStop.lat, selectedStop.lng)
      : null;

  const activeStop = stops.find((s) => s.id === activeId) ?? null;
  const showArrivalBanner = activeStop && activeStop.id !== dismissedId && activeStop.id !== stopId;

  const c = copy[lang];

  function openFromMap(id: number) {
    if (view === "map") listScrollY.current = window.scrollY;
    openStop(id, { replace: view === "detail" });
  }

  function toggleGps() {
    setGpsNotice(null);
    setGpsEnabled((v) => !v);
  }

  const idx = selectedStop ? stops.indexOf(selectedStop) : -1;
  const gpsLabel = !gpsEnabled ? c.gpsOff : userPos ? c.gpsOn : c.gpsSearching;
  const gpsMessage =
    gpsNotice === "denied"
      ? c.gpsDenied
      : gpsNotice === "unsupported"
        ? c.gpsUnsupported
        : gpsEnabled && geo.error === "unavailable"
          ? c.gpsUnavailable
          : null;

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
            onClick={toggleGps}
            aria-pressed={gpsEnabled}
          >
            {gpsLabel}
          </button>
          <button
            className="btn btn--toggle"
            onClick={() => setLang(lang === "sv" ? "en" : "sv")}
            aria-label={c.switchLang}
            lang={lang === "sv" ? "en" : "sv"}
          >
            {lang === "sv" ? "EN" : "SV"}
          </button>
        </div>
      </header>

      {gpsMessage && (
        <div className="notice" role="status">
          <span>{gpsMessage}</span>
          {gpsNotice && (
            <button className="btn btn--small btn--ghost" onClick={() => setGpsNotice(null)}>
              {c.dismiss}
            </button>
          )}
        </div>
      )}

      {showArrivalBanner && (
        <div className="arrival-banner" role="status">
          <span>
            {c.arrived}: <strong>{activeStop.title[lang]}</strong>
          </span>
          <div className="arrival-banner__actions">
            <button className="btn btn--small" onClick={() => openFromMap(activeStop.id)}>
              {c.open}
            </button>
            <button className="btn btn--small btn--ghost" onClick={() => setDismissedId(activeStop.id)}>
              {c.dismiss}
            </button>
          </div>
        </div>
      )}

      {/* The map view stays mounted while a stop is open, so zoom, pan and list position survive. */}
      <div className="map-view" hidden={view !== "map"}>
        <MapView
          stops={stops}
          lang={lang}
          visible={view === "map"}
          activeStopId={activeId}
          onSelectStop={openFromMap}
          userPos={userPos}
        />
        <div className="stop-list">
          <h2 className="stop-list__title">{c.listTitle}</h2>
          <p className="stop-list__summary">
            {c.summary(
              (Math.round(WALK_KM * 2) / 2).toLocaleString(c.locale, { maximumFractionDigits: 1 }),
              WALK_MIN
            )}
          </p>
          <ul>
            {stops.map((s) => {
              const isRead = visited.includes(s.id);
              return (
                <li key={s.id}>
                  <button
                    className={`stop-list__item ${isRead ? "stop-list__item--read" : ""}`}
                    onClick={() => openFromMap(s.id)}
                  >
                    <span className="stop-list__num">{s.id}</span>
                    <span className="stop-list__name">{s.title[lang]}</span>
                    {isRead && (
                      <span className="stop-list__read">
                        <span aria-hidden="true">✓</span>
                        <span className="visually-hidden">{c.read}</span>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          {visited.length > 0 && (
            <button className="btn btn--small btn--ghost stop-list__reset" onClick={() => setVisited([])}>
              {c.resetRead}
            </button>
          )}
          <footer className="about">
            <p>
              {c.about}{" "}
              <a href={SOURCE_URL} target="_blank" rel="noopener">
                {c.aboutLink}
              </a>
            </p>
          </footer>
        </div>
      </div>

      {selectedStop && (
        <StopDetail
          key={selectedStop.id}
          stop={selectedStop}
          position={idx + 1}
          total={stops.length}
          lang={lang}
          distanceMetres={selectedDistance}
          onBack={backToMap}
          onPrev={() => idx > 0 && openFromMap(stops[idx - 1].id)}
          onNext={() => idx < stops.length - 1 && openFromMap(stops[idx + 1].id)}
          hasPrev={idx > 0}
          hasNext={idx < stops.length - 1}
        />
      )}
    </div>
  );
}
