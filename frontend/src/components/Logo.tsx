import { useState } from "react";
import { cx } from "../lib/cx";

export const LOGO_SOURCES = {
  fullOnLight: "/brand/wo-logo-on-light.png",
  fullOnDark: "/brand/wo-logo-on-dark.png",
  markOnLight: "/brand/wo-mark-on-light.png",
  markOnDark: "/brand/wo-mark-on-dark.png",
};

/** Width over height of the supplied full logo files (680 x 578). */
const FULL_RATIO = 680 / 578;
/** The design system: the full logo is never shown narrower than 120px; below that, the mark. */
export const FULL_LOGO_MIN_WIDTH = 120;
export const FULL_LOGO_MIN_HEIGHT = Math.ceil(FULL_LOGO_MIN_WIDTH / FULL_RATIO);

interface LogoProps {
  /** The ground it sits on. `auto` follows the theme: dark artwork for the dark theme. */
  on?: "light" | "dark" | "auto";
  /** `mark` is the WO mark alone. A full logo asked for under 120px wide is shown as the mark. */
  kind?: "full" | "mark";
  className?: string;
  height?: number;
}

/**
 * The brand logo as supplied; it is never redrawn or recoloured. While a file is missing the
 * name is set in the brand typeface so no screen ever shows a broken image.
 */
export function Logo({ on = "auto", kind: asked = "full", className, height = 40 }: LogoProps) {
  const [broken, setBroken] = useState<Record<string, boolean>>({});
  const kind = asked === "full" && height < FULL_LOGO_MIN_HEIGHT ? "mark" : asked;
  const sources = {
    light: kind === "full" ? LOGO_SOURCES.fullOnLight : LOGO_SOURCES.markOnLight,
    dark: kind === "full" ? LOGO_SOURCES.fullOnDark : LOGO_SOURCES.markOnDark,
  };

  const render = (ground: "light" | "dark", extra?: string) => {
    if (broken[ground]) {
      return (
        <span className={cx("wo-wordmark", extra, className)} style={{ fontSize: height * 0.5 }}>
          {kind === "full" ? "WO Community" : "WO"}
        </span>
      );
    }
    return (
      <img
        className={cx(extra, className)}
        src={sources[ground]}
        alt=""
        // With both versions on the page, the theme classes decide which one shows.
        style={{ height, width: "auto", ...(extra ? {} : { display: "block" }) }}
        onError={() => setBroken((current) => ({ ...current, [ground]: true }))}
      />
    );
  };

  if (on === "auto") {
    return (
      <>
        {render("light", "wo-logo-for-light")}
        {render("dark", "wo-logo-for-dark")}
      </>
    );
  }
  return render(on);
}
