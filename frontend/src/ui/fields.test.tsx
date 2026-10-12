import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ChipSelect, StringList, fromMinor, toMinor } from "./fields";

describe("money", () => {
  it("turns what a member types into minor units", () => {
    expect(toMinor("1,500")).toBe(150000);
    expect(toMinor("12.5")).toBe(1250);
    expect(toMinor(" 3 000 ")).toBe(300000);
  });

  it("returns null for nothing or for text that is not a number", () => {
    expect(toMinor("")).toBeNull();
    expect(toMinor("abc")).toBeNull();
  });

  it("shows minor units as whole currency units", () => {
    expect(fromMinor(150000)).toBe("1500");
    expect(fromMinor(1250)).toBe("12.5");
    expect(fromMinor(undefined)).toBe("");
  });
});

function Chips({ initial = [] as string[] }) {
  const [value, setValue] = useState(initial);
  return <ChipSelect legend="Where will you sell?" options={[{ value: "africa", label: "Africa" }, { value: "europe", label: "Europe" }]} value={value} onChange={setValue} />;
}

describe("ChipSelect", () => {
  it("groups the options under a legend and reports which are pressed", async () => {
    render(<Chips initial={["africa"]} />);
    expect(screen.getByRole("group", { name: "Where will you sell?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Africa" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Europe" })).toHaveAttribute("aria-pressed", "false");
  });

  it("toggles an option on and off", async () => {
    const user = userEvent.setup();
    render(<Chips />);
    await user.click(screen.getByRole("button", { name: "Europe" }));
    expect(screen.getByRole("button", { name: "Europe" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Europe" }));
    expect(screen.getByRole("button", { name: "Europe" })).toHaveAttribute("aria-pressed", "false");
  });
});

function Lines({ max = 3 }) {
  const [value, setValue] = useState<string[]>([]);
  return <StringList label="Key features" value={value} onChange={setValue} max={max} />;
}

describe("StringList", () => {
  it("adds a line with the button and with Enter, then clears the field", async () => {
    const user = userEvent.setup();
    render(<Lines />);
    const field = screen.getByLabelText("Add to key features");
    await user.type(field, "Offline mode");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await user.type(field, "Sync{Enter}");
    expect(screen.getByText("Offline mode")).toBeInTheDocument();
    expect(screen.getByText("Sync")).toBeInTheDocument();
    expect(field).toHaveValue("");
  });

  it("ignores empty text and keeps the button disabled", async () => {
    render(<Lines />);
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  });

  it("removes a line by name", async () => {
    const user = userEvent.setup();
    render(<Lines />);
    await user.type(screen.getByLabelText("Add to key features"), "Offline mode{Enter}");
    await user.click(screen.getByRole("button", { name: "Remove Offline mode" }));
    expect(screen.queryByText("Offline mode")).not.toBeInTheDocument();
  });

  it("stops offering to add once the limit is reached", async () => {
    const user = userEvent.setup();
    render(<Lines max={1} />);
    await user.type(screen.getByLabelText("Add to key features"), "One{Enter}");
    expect(screen.queryByLabelText("Add to key features")).not.toBeInTheDocument();
    expect(screen.getByText("You can add up to 1.")).toBeInTheDocument();
  });
});
