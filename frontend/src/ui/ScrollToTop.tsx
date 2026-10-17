import { useLayoutEffect } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/**
 * Starts every newly opened page at the top, as a full page load would. A link to a spot on the
 * page (#section) goes there instead; going back or forward is left to the browser; and changing
 * only a filter or tab in the address (?tab=) keeps the reader where they are.
 */
export function ScrollToTop() {
  const { pathname, hash } = useLocation();
  const navigation = useNavigationType();

  useLayoutEffect(() => {
    if (navigation === "POP") return;
    if (hash) {
      const target = document.getElementById(decodeURIComponent(hash.slice(1)));
      if (target) {
        target.scrollIntoView();
        return;
      }
    }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname, hash, navigation]);

  return null;
}
