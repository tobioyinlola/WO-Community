import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ThemeProvider, useTheme } from "./ThemeProvider";

function Probe() {
  const { choice, theme, setChoice } = useTheme();
  return (
    <div>
      <p data-testid="state">{`${choice}:${theme}`}</p>
      <button type="button" onClick={() => setChoice("dark")}>
        Dark
      </button>
      <button type="button" onClick={() => setChoice("system")}>
        System
      </button>
    </div>
  );
}

describe("ThemeProvider", () => {
  it("follows the operating system until the member chooses", async () => {
    window.__systemDark = true;
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("system:dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });

  it("remembers an explicit choice and lets go of it for system", async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    await userEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(window.localStorage.getItem("wo-theme")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "System" }));
    expect(window.localStorage.getItem("wo-theme")).toBeNull();
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("starts from a saved choice", () => {
    window.localStorage.setItem("wo-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("dark:dark");
  });
});
