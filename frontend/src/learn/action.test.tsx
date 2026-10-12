import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { CourseAction } from "./Landing";

type Course = Parameters<typeof CourseAction>[0]["course"];

const base: Course = {
  slug: "founders",
  access: "free",
  enrolment_active: true,
  access_request: "none",
  resume: null,
  progress: { enrolled: false, completed_at: null },
} as Course;

function show(course: Partial<Course>, extra: { target?: string; onEnrol?: () => void; onAsk?: () => void } = {}) {
  const props = { onEnrol: vi.fn(), onAsk: vi.fn(), ...extra };
  render(
    <MemoryRouter>
      <CourseAction course={{ ...base, ...course }} {...props} />
    </MemoryRouter>,
  );
  return props;
}

describe("the course page button", () => {
  it("lets anyone enrol on a free course", async () => {
    const { onEnrol } = show({});
    await userEvent.click(screen.getByRole("button", { name: "Enrol for free" }));
    expect(onEnrol).toHaveBeenCalledOnce();
  });

  it("asks for access on a paid course instead of enrolling", async () => {
    const { onAsk, onEnrol } = show({ access: "paid" });
    expect(screen.queryByRole("button", { name: "Enrol for free" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Request access" }));
    expect(onAsk).toHaveBeenCalledOnce();
    expect(onEnrol).not.toHaveBeenCalled();
  });

  it("shows a request that is waiting, and cannot be sent twice", () => {
    show({ access: "paid", access_request: "pending" });
    expect(screen.getByRole("button", { name: "Request sent" })).toBeDisabled();
  });

  it("says when enrolment is closed, on free and paid courses alike", () => {
    show({ enrolment_active: false });
    expect(screen.getByRole("button", { name: "Enrolment is closed" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Enrol for free" })).toBeNull();
  });

  it("starts, continues or reviews for someone who is enrolled", () => {
    const { unmount } = render(
      <MemoryRouter>
        <CourseAction course={{ ...base, progress: { enrolled: true, completed_at: null } }} target="l1" onEnrol={vi.fn()} onAsk={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Start learning" })).toHaveAttribute("href", "/app/learn/courses/founders/lecture/l1");
    unmount();

    const resume = { lesson_id: "l2" } as Course["resume"];
    const view = render(
      <MemoryRouter>
        <CourseAction course={{ ...base, resume, progress: { enrolled: true, completed_at: null } }} target="l2" onEnrol={vi.fn()} onAsk={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Continue learning" })).toBeInTheDocument();
    view.unmount();

    render(
      <MemoryRouter>
        <CourseAction course={{ ...base, resume, progress: { enrolled: true, completed_at: "2026-10-10T09:00:00Z" } }} target="l1" onEnrol={vi.fn()} onAsk={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Review the course" })).toBeInTheDocument();
  });

  it("keeps an enrolled person's button even when enrolment has closed", () => {
    show({ enrolment_active: false, progress: { enrolled: true, completed_at: null } }, { target: "l1" });
    expect(screen.getByRole("link", { name: "Start learning" })).toBeInTheDocument();
  });
});
