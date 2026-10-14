import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Reveal } from "./Reveal";

type Callback = (entries: Array<{ isIntersecting: boolean }>) => void;
let trigger: Callback = () => undefined;

function mockObserver() {
  class FakeObserver {
    constructor(callback: Callback) {
      trigger = callback;
    }
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("IntersectionObserver", FakeObserver);
}

function mockMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query.includes("reduce"), addEventListener() {}, removeEventListener() {} }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Reveal", () => {
  it("waits until it is on screen, numbers its children for the stagger, then settles", () => {
    vi.useFakeTimers();
    mockMotion(false);
    mockObserver();
    render(
      <Reveal className="grid">
        <p>one</p>
        <p>two</p>
      </Reveal>,
    );
    const box = screen.getByText("one").parentElement as HTMLElement;
    expect(box).toHaveAttribute("data-reveal", "pending");
    expect(screen.getByText("two").style.getPropertyValue("--i")).toBe("1");
    act(() => trigger([{ isIntersecting: true }]));
    expect(box).toHaveAttribute("data-reveal", "revealing");
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(box).toHaveAttribute("data-reveal", "done");
  });

  it("shows everything at once when reduced motion is asked for", () => {
    mockMotion(true);
    mockObserver();
    render(
      <Reveal>
        <p>content</p>
      </Reveal>,
    );
    expect(screen.getByText("content").parentElement).toHaveAttribute("data-reveal", "done");
  });
});
