import { useCallback, useEffect, useState } from "react";

// Routes live in the hash (#/stopp/4) so links work on any static host or subpath,
// and so the phone's back button returns to the map instead of leaving the app.
const STOP_HASH = /^#\/(?:stopp|stop)\/(\d+)\/?$/;

function parse(hash: string): number | null {
  const m = STOP_HASH.exec(hash);
  return m ? Number(m[1]) : null;
}

export function stopHref(id: number): string {
  return `#/stopp/${id}`;
}

export function useRoute() {
  const [stopId, setStopId] = useState<number | null>(() => parse(window.location.hash));

  useEffect(() => {
    const sync = () => setStopId(parse(window.location.hash));
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, []);

  // Opening a stop from the map adds a history entry; stepping between stops replaces it,
  // so a single "back" always lands on the map.
  const openStop = useCallback((id: number, { replace = false } = {}) => {
    const state = replace ? window.history.state : { fromMap: true };
    const method = replace ? "replaceState" : "pushState";
    window.history[method](state, "", stopHref(id));
    setStopId(id);
  }, []);

  const backToMap = useCallback(() => {
    if (window.history.state?.fromMap) {
      window.history.back();
    } else {
      // Arrived via a direct link: there is no map entry behind us to go back to.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      setStopId(null);
    }
  }, []);

  return { stopId, openStop, backToMap };
}
