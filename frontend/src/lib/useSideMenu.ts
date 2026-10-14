import { useEffect } from "react";

/** The widest screen where the site menu is a side drawer rather than a row of links. */
const DRAWER_QUERY = "(max-width: 767px)";

/**
 * Behaviour for a menu that slides in from the side: Escape closes it, the page behind it does not
 * scroll while it is open, and widening the window to desktop size closes it.
 */
export function useSideMenu(open: boolean, close: () => void) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const media = window.matchMedia(DRAWER_QUERY);
    const onChange = () => {
      if (!media.matches) close();
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    media.addEventListener("change", onChange);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
      media.removeEventListener("change", onChange);
    };
  }, [open, close]);
}
