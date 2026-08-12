import type { Stop, Lang } from "../types";

interface Props {
  stop: Stop;
  lang: Lang;
  distanceMetres: number | null;
  onBack: () => void;
  onPrev: () => void;
  onNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
}

const copy = {
  sv: { back: "Karta", prev: "Föregående", next: "Nästa", near: "meter bort" },
  en: { back: "Map", prev: "Previous", next: "Next", near: "metres away" },
};

export default function StopDetail({
  stop,
  lang,
  distanceMetres,
  onBack,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: Props) {
  const c = copy[lang];
  return (
    <div className="stop-detail">
      <button className="btn btn--ghost stop-detail__back" onClick={onBack}>
        ← {c.back}
      </button>
      <div className="stop-detail__badge">{stop.id} / 11</div>
      <h1>{stop.title[lang]}</h1>
      {distanceMetres !== null && (
        <p className="stop-detail__distance">
          {Math.round(distanceMetres)} {c.near}
        </p>
      )}
      {stop.text[lang].map((p, i) => (
        <p key={i}>{p}</p>
      ))}
      <div className="stop-detail__nav">
        <button className="btn" onClick={onPrev} disabled={!hasPrev}>
          ← {c.prev}
        </button>
        <button className="btn" onClick={onNext} disabled={!hasNext}>
          {c.next} →
        </button>
      </div>
    </div>
  );
}
