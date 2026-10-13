import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeAll, describe, expect, it } from "vitest";
import { Drawer } from "./Drawer";

beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => undefined;
});

function Harness({ dirty = false }: { dirty?: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Drawer open={open} onOpenChange={setOpen} title="Contact support" eyebrow="New request" footer={<button type="button">Send request</button>} dirty={dirty && text !== ""}>
        <label>
          Subject
          <input value={text} onChange={(e) => setText(e.target.value)} />
        </label>
      </Drawer>
    </>
  );
}

describe("Drawer", () => {
  it("opens as a named dialog with its footer, and gives focus back on close", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);
    expect(screen.getByRole("dialog", { name: "Contact support" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send request" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("keeps Tab inside while open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    for (let i = 0; i < 8; i += 1) await user.tab();
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("closes at once when nothing was typed", async () => {
    const user = userEvent.setup();
    render(<Harness dirty />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks before throwing away typed text, and keeps editing on request", async () => {
    const user = userEvent.setup();
    render(<Harness dirty />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.type(screen.getByLabelText("Subject"), "Cannot sign in");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog", { name: "Discard your changes?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep editing" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByLabelText("Subject")).toHaveValue("Cannot sign in");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("discards when told to", async () => {
    const user = userEvent.setup();
    render(<Harness dirty />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.type(screen.getByLabelText("Subject"), "x");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
