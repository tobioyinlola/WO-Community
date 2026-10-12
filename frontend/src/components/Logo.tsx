import { useState } from "react";
import { cx } from "../lib/cx";

export const LOGO_SOURCES = {
  fullOnLight: "/assets/wo-logo-on-light.png",
  fullOnDark: "/assets/wo-logo-on-dark.png",
  markOnLight: "/assets/wo-mark-on-light.png",
  markOnDark: "/assets/wo-mark-on-dark.png",
};

interface LogoProps {
  /** The ground it sits on. `auto` follows the theme: dark artwork for the dark theme. */
  on?: "light" | "dark" | "auto";
  /** `mark` is the WO mark alone, for places narrower than 120px. */
  kind?: "full" | "mark";
  className?: string;
  height?: number;
}

/**
 * The brand logo as supplied; it is never redrawn or recoloured. While a file is missing the
 * name is set in the brand typeface so no screen ever shows a broken image.
 */
export function Logo({ on = "auto", kind = "full", className, height = 40 }: LogoProps) {
  const [broken, setBroken] = useState<Record<string, boolean>>({});
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
        style={{ height, width: "auto", display: "block" }}
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
