import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

/**
 * A row of cards that scrolls sideways and snaps to a card, with the next card partly showing.
 * Touch and trackpad scroll natively; the round buttons and the arrow keys move one card.
 */
export function Carousel({ label, children }: { label: string; children: ReactNode }) {
  const track = useRef<HTMLUListElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  const measure = useCallback(() => {
    const el = track.current;
    if (el === null) return;
    setEdge({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const move = (direction: 1 | -1) => {
    const el = track.current;
    if (el === null) return;
    const card = el.querySelector("li");
    const step = card ? card.getBoundingClientRect().width + 16 : el.clientWidth * 0.8;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    el.scrollBy({ left: direction * step, behavior: reduced ? "auto" : "smooth" });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    }
  };

  return (
    <div className="site-carousel" role="region" aria-roledescription="carousel" aria-label={label}>
      {/* A scrolling area has to be reachable by keyboard, or its off screen cards could not be read. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex, jsx-a11y/no-noninteractive-element-interactions */}
      <ul ref={track} className="site-carousel__track" onScroll={measure} onKeyDown={onKeyDown} tabIndex={0} aria-label={`${label}, use the left and right arrow keys to move`}>
        {children}
      </ul>
      <div className="site-carousel__controls">
        <button type="button" className="site-roundbtn" aria-label="Previous" disabled={edge.start} onClick={() => move(-1)}>
          <ChevronLeft size={20} strokeWidth={2} aria-hidden="true" />
        </button>
        <button type="button" className="site-roundbtn" aria-label="Next" disabled={edge.end} onClick={() => move(1)}>
          <ChevronRight size={20} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
