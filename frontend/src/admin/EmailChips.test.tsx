import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { EmailChips } from "./EmailChips";
import { addChips, isValidShape, MAX_EMAILS, sendable, splitList, type Chip } from "./emailTags";

function Harness({ start = [] }: { start?: Chip[] }) {
  const [chips, setChips] = useState<Chip[]>(start);
  return (
    <>
      <EmailChips chips={chips} onChange={setChips} />
      <p data-testid="sendable">{sendable(chips).join("|")}</p>
    </>
  );
}

describe("parsing", () => {
  it("splits on commas, semicolons, spaces and new lines", () => {
    expect(splitList("a@x.co, b@x.co;c@x.co\nd@x.co  <e@x.co>")).toEqual(["a@x.co", "b@x.co", "c@x.co", "d@x.co", "e@x.co"]);
  });
  it("checks the shape of an address", () => {
    expect(isValidShape("ada@example.com")).toBe(true);
    for (const bad of ["ada", "ada@", "@example.com", "ada@example", "a b@example.com"]) expect(isValidShape(bad)).toBe(false);
  });
  it("merges repeats without regard to capitals and stops at the limit", () => {
    const first = addChips([], ["A@x.co", "a@x.co", "bad"]);
    expect(first.chips.map((c) => c.email)).toEqual(["A@x.co", "bad"]);
    expect(first.merged).toBe(1);
    expect(first.chips[1]?.flag).toBe("invalid");
    const many = addChips([], Array.from({ length: MAX_EMAILS + 3 }, (_, i) => `u${i}@x.co`));
    expect(many.chips).toHaveLength(MAX_EMAILS);
    expect(many.overflow).toBe(3);
  });
});

describe("EmailChips", () => {
  it("closes a chip on Enter, comma, space and semicolon", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByLabelText("Email addresses");
    await user.type(box, "a@x.co{Enter}b@x.co,c@x.co d@x.co;");
    expect(screen.getByTestId("sendable")).toHaveTextContent("a@x.co|b@x.co|c@x.co|d@x.co");
  });

  it("turns a pasted list into one chip each, shows a bad one as an error and merges a repeat", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByLabelText("Email addresses"));
    await user.paste("a@x.co, nope\nb@x.co A@x.co");
    expect(screen.getByText("Not a valid email address")).toBeInTheDocument();
    expect(screen.getByTestId("sendable")).toHaveTextContent("a@x.co|b@x.co");
    expect(screen.getByRole("status")).toHaveTextContent("1 repeated address was merged");
  });

  it("closes the chip when the field loses focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByLabelText("Email addresses"), "a@x.co");
    await user.tab();
    expect(screen.getByRole("button", { name: "Remove a@x.co" })).toBeInTheDocument();
  });

  it("removes a chip with its X and the last one with Backspace", async () => {
    const user = userEvent.setup();
    render(<Harness start={[{ email: "a@x.co" }, { email: "b@x.co" }, { email: "c@x.co" }]} />);
    await user.click(screen.getByRole("button", { name: "Remove a@x.co" }));
    expect(screen.getByTestId("sendable")).toHaveTextContent("b@x.co|c@x.co");
    await user.click(screen.getByLabelText("Email addresses"));
    await user.keyboard("{Backspace}");
    expect(screen.getByTestId("sendable")).toHaveTextContent("b@x.co");
  });

  it("does not send members or pending invites, and says why", () => {
    render(<Harness start={[{ email: "a@x.co" }, { email: "m@x.co", flag: "member" }, { email: "p@x.co", flag: "pending" }]} />);
    expect(screen.getByText("Already a member")).toBeInTheDocument();
    expect(screen.getByText("Invite pending")).toBeInTheDocument();
    expect(screen.getByTestId("sendable")).toHaveTextContent("a@x.co");
  });
});
