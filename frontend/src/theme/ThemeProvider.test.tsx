import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeProvider, useTheme } from "./ThemeProvider";

function Probe() {
  const { theme } = useTheme();
  return <p data-testid="state">{theme}</p>;
}

// The product is light only for now: neither the device setting nor an old saved choice changes it.
describe("ThemeProvider", () => {
  it("stays light when the device prefers dark", () => {
    window.__systemDark = true;
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("ignores and clears a dark choice saved earlier", () => {
    window.localStorage.setItem("wo-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("light");
    expect(window.localStorage.getItem("wo-theme")).toBeNull();
  });
});
