import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/cx";

type Phase = "pending" | "revealing" | "done";

/**
 * Fades its children in with a 12px rise the first time it scrolls into view, each child 60ms after
 * the one before. With reduced motion, or no IntersectionObserver, everything is simply shown.
 */
export function Reveal({ className, children }: { className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<Phase>("pending");

  useEffect(() => {
    const node = ref.current;
    if (node === null) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    if (reduced || typeof IntersectionObserver === "undefined") {
      setPhase("done");
      return;
    }
    [...node.children].forEach((child, index) => (child as HTMLElement).style.setProperty("--i", String(index)));
    let timer: ReturnType<typeof setTimeout> | undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        setPhase("revealing");
        // Once the last child has finished, hand hover effects back to the cards themselves.
        timer = setTimeout(() => setPhase("done"), 360 + node.children.length * 60 + 80);
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  return (
    <div ref={ref} className={cx("reveal", className)} data-reveal={phase}>
      {children}
    </div>
  );
}
