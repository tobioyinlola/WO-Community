import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Carousel } from "./Carousel";
import { CountUp } from "./CountUp";
import { Faq } from "./Faq";

function motion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const ITEMS = [
  { question: "First question?", answer: "First answer." },
  { question: "Second question?", answer: "Second answer." },
  { question: "Third question?", answer: "Third answer." },
];

describe("Faq", () => {
  it("opens the first question and keeps only one open at a time", async () => {
    const user = userEvent.setup();
    render(<Faq items={ITEMS} />);
    const [one, two, three] = ITEMS.map((i) => screen.getByRole("button", { name: i.question })) as [HTMLElement, HTMLElement, HTMLElement];
    expect(one).toHaveAttribute("aria-expanded", "true");
    expect(two).toHaveAttribute("aria-expanded", "false");
    await user.click(three);
    expect(one).toHaveAttribute("aria-expanded", "false");
    expect(three).toHaveAttribute("aria-expanded", "true");
    await user.click(three);
    expect(three).toHaveAttribute("aria-expanded", "false");
  });

  it("joins each button to its answer for assistive technology", () => {
    render(<Faq items={ITEMS} />);
    const button = screen.getByRole("button", { name: "Second question?" });
    const panel = document.getElementById(button.getAttribute("aria-controls") ?? "");
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute("role", "region");
    expect(panel).toHaveAttribute("aria-labelledby", button.id);
    expect(panel).toHaveTextContent("Second answer.");
  });

  it("works from the keyboard", async () => {
    const user = userEvent.setup();
    render(<Faq items={ITEMS} />);
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Second question?" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Second question?" })).toHaveAttribute("aria-expanded", "true");
  });
});

describe("Carousel", () => {
  function show() {
    const scrollBy = vi.fn();
    Element.prototype.scrollBy = scrollBy as unknown as typeof Element.prototype.scrollBy;
    // jsdom has no layout, so give the track something to scroll.
    vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(1000);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(300);
    render(
      <Carousel label="Things">
        <li>one</li>
        <li>two</li>
      </Carousel>,
    );
    return scrollBy;
  }

  it("is a labelled carousel with a track a keyboard can reach", () => {
    motion(false);
    show();
    expect(screen.getByRole("region", { name: "Things" })).toHaveAttribute("aria-roledescription", "carousel");
    expect(screen.getByRole("list", { name: /Things/ })).toHaveAttribute("tabindex", "0");
  });

  it("moves a card with the round buttons, smoothly unless motion is reduced", async () => {
    motion(false);
    const scrollBy = show();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(scrollBy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "smooth" }));
    expect(scrollBy.mock.calls[0]?.[0].left).toBeGreaterThan(0);
  });

  it("moves with the arrow keys and uses an instant jump when motion is reduced", async () => {
    motion(true);
    const scrollBy = show();
    const user = userEvent.setup();
    screen.getByRole("list", { name: /Things/ }).focus();
    await user.keyboard("{ArrowRight}");
    expect(scrollBy).toHaveBeenCalledWith(expect.objectContaining({ behavior: "auto" }));
    await user.keyboard("{ArrowLeft}");
    expect(scrollBy.mock.calls[1]?.[0].left).toBeLessThan(0);
  });

  it("will not go back from the start", () => {
    motion(false);
    show();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  });
});

describe("CountUp", () => {
  it("shows the real figure at once when motion is reduced", () => {
    motion(true);
    render(<CountUp value={1234} />);
    expect(screen.getAllByText("1,234").length).toBeGreaterThan(0);
  });

  it("always carries the final figure for screen readers, and counts up on screen", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance", "Date"] });
    motion(false);
    let trigger: (entries: Array<{ isIntersecting: boolean }>) => void = () => undefined;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: typeof trigger) {
          trigger = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(performance.now()), 16));
    vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
    const { container } = render(<CountUp value={40} durationMs={400} />);
    const hidden = container.querySelector(".wo-visually-hidden");
    expect(hidden).toHaveTextContent("40");
    const visible = container.querySelector("[aria-hidden='true']") as HTMLElement;
    expect(visible).toHaveTextContent("0");
    act(() => trigger([{ isIntersecting: true }]));
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(visible).toHaveTextContent("40");
  });
});
