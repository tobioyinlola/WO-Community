import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TickerView, type TickerItem } from "./BannerTicker";

const items: TickerItem[] = [
  { id: "1", kind: "urgent", text: "Maintenance tonight", link: "/jobs" },
  { id: "2", kind: "news", text: "We raised a round", link: "https://example.com/story" },
];

function reducedMotion(on: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: on && query.includes("reduce"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function show(onDismiss?: () => void) {
  render(
    <MemoryRouter>
      <TickerView items={items} onDismiss={onDismiss} />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("TickerView", () => {
  it("is a normal list a screen reader can read, with the moving copy hidden from it", () => {
    reducedMotion(false);
    show();
    const region = screen.getByRole("region", { name: "Announcements and news" });
    const lists = region.querySelectorAll("ul");
    expect(lists).toHaveLength(2);
    expect(lists[1]).toHaveAttribute("aria-hidden", "true");
    expect(within(lists[0] as HTMLElement).getAllByRole("link")).toHaveLength(2);
    expect(screen.getAllByText(/Urgent:/).length).toBeGreaterThan(0);
  });

  it("opens an outside link in a new tab safely and an app link inside the app", () => {
    reducedMotion(false);
    show();
    const outside = screen.getAllByRole("link", { name: /We raised a round/ })[0];
    expect(outside).toHaveAttribute("target", "_blank");
    expect(outside).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getAllByRole("link", { name: /Maintenance tonight/ })[0]).toHaveAttribute("href", "/app/jobs");
  });

  it("has a pause and play control", async () => {
    reducedMotion(false);
    const user = userEvent.setup();
    show();
    const pause = screen.getByRole("button", { name: "Pause the moving announcements" });
    expect(pause).toHaveAttribute("aria-pressed", "false");
    await user.click(pause);
    expect(screen.getByRole("button", { name: "Play the moving announcements" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Announcements and news" })).toHaveAttribute("data-paused", "true");
  });

  it("with reduced motion shows one item at a time with previous and next", async () => {
    reducedMotion(true);
    const user = userEvent.setup();
    show();
    expect(screen.queryByRole("button", { name: /Pause/ })).not.toBeInTheDocument();
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Maintenance tonight/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /We raised a round/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous announcement" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next announcement" }));
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /We raised a round/ })).toBeInTheDocument();
  });

  it("can be closed", async () => {
    reducedMotion(false);
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    show(onDismiss);
    await user.click(screen.getByRole("button", { name: "Close announcements" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
