import { useEffect, useRef } from "react";
import type { Stop, Lang } from "../types";

interface Props {
  stop: Stop;
  position: number;
  total: number;
  lang: Lang;
  distanceMetres: number | null;
  onBack: () => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}

const copy = {
  sv: { back: "Karta", prev: "Föregående", next: "Nästa", near: "meter bort", directions: "Vägbeskrivning hit" },
  en: { back: "Map", prev: "Previous", next: "Next", near: "metres away", directions: "Directions here" },
};

export default function StopDetail({
  stop,
  position,
  total,
  lang,
  distanceMetres,
  onBack,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: Props) {
  const c = copy[lang];
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Move focus to the new stop so screen readers announce it instead of staying on the old button.
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${stop.lat},${stop.lng}&travelmode=walking`;

  return (
    <article className="stop-detail">
      <button className="btn btn--ghost stop-detail__back" onClick={onBack}>
        ← {c.back}
      </button>
      <div className="stop-detail__badge">
        {position} / {total}
      </div>
      <h2 ref={headingRef} tabIndex={-1} className="stop-detail__title">
        {stop.title[lang]}
      </h2>
      <p className="stop-detail__meta">
        {distanceMetres !== null && (
          <span className="stop-detail__distance">
            {Math.round(distanceMetres)} {c.near}
          </span>
        )}
        <a href={directionsUrl} target="_blank" rel="noopener">
          {c.directions} ↗
        </a>
      </p>
      {stop.text[lang].map((p, i) => (
        <p key={i}>{p}</p>
      ))}
      <nav className="stop-detail__nav">
        <button className="btn" onClick={onPrev} disabled={!hasPrev}>
          ← {c.prev}
        </button>
        <button className="btn" onClick={onNext} disabled={!hasNext}>
          {c.next} →
        </button>
      </nav>
    </article>
  );
}
