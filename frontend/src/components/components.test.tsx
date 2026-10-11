import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  Alert,
  Avatar,
  Badge,
  Button,
  CardLink,
  Checkbox,
  Input,
  MemberCard,
  Modal,
  Select,
  StatTile,
  Switch,
  Tabs,
  TopNav,
  initials,
  tintFor,
} from ".";

describe("Button", () => {
  it("renders the variant and size classes and defaults to type button", () => {
    render(
      <Button variant="accent" size="lg">
        Join
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Join" });
    expect(button).toHaveClass("wo-btn", "wo-btn--accent", "wo-btn--lg");
    expect(button).toHaveAttribute("type", "button");
  });

  it("marks a loading button busy and keeps its label", () => {
    render(<Button loading>Saving</Button>);
    const button = screen.getByRole("button", { name: "Saving" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveClass("wo-btn--loading");
  });

  it("does not fire when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Go
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("Input", () => {
  it("ties the label, hint and error to the control", () => {
    render(<Input label="Work email" hint="We never share it." error="Enter a full email address." />);
    const field = screen.getByLabelText("Work email");
    expect(field).toHaveAttribute("aria-invalid", "true");
    const described = field.getAttribute("aria-describedby") ?? "";
    expect(described.split(" ")).toHaveLength(2);
    expect(document.getElementById(described.split(" ")[0] ?? "")).toHaveTextContent(
      "Enter a full email address.",
    );
  });

  it("is not marked invalid without an error", () => {
    render(<Input label="Full name" />);
    expect(screen.getByLabelText("Full name")).not.toHaveAttribute("aria-invalid");
  });

  it("lists the options of a select", () => {
    render(
      <Select
        label="Stage"
        options={[
          { value: "seed", label: "Seed" },
          { value: "a", label: "Series A" },
        ]}
      />,
    );
    expect(screen.getByRole("combobox", { name: "Stage" })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });
});

describe("Checkbox and Switch", () => {
  it("toggles by clicking the label", async () => {
    render(<Checkbox label="Email me about demo days" />);
    const box = screen.getByRole("checkbox", { name: "Email me about demo days" });
    await userEvent.click(screen.getByText("Email me about demo days"));
    expect(box).toBeChecked();
  });

  it("exposes a switch role", () => {
    render(<Switch label="Weekly digest" defaultChecked />);
    expect(screen.getByRole("switch", { name: "Weekly digest" })).toBeChecked();
  });
});

describe("Badge", () => {
  it("uses the fixed role variants and an optional dot", () => {
    render(
      <Badge variant="mentor" dot>
        Mentor
      </Badge>,
    );
    const badge = screen.getByText("Mentor");
    expect(badge).toHaveClass("wo-badge", "wo-badge--mentor");
    expect(badge.querySelector(".wo-dot")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Avatar", () => {
  it("takes two letters from the name and names itself", () => {
    expect(initials("Amaka Obi")).toBe("AO");
    expect(initials("  Tunde  ")).toBe("T");
    render(<Avatar name="Amaka Obi" shape="arch" size="lg" tint="peach" />);
    const avatar = screen.getByRole("img", { name: "Amaka Obi" });
    expect(avatar).toHaveClass("wo-avatar--arch", "wo-avatar--lg", "wo-avatar--peach");
    expect(avatar).toHaveTextContent("AO");
  });

  it("gives the same member the same tint every time", () => {
    expect(tintFor("member-42")).toBe(tintFor("member-42"));
    const tints = new Set(["a", "b", "c", "d", "e", "f", "g", "h"].map(tintFor));
    expect(tints.size).toBeGreaterThan(1);
  });
});

describe("Card", () => {
  it("a link card is one anchor with its text", () => {
    render(<CardLink href="/events/demo">Demo Day</CardLink>);
    const link = screen.getByRole("link", { name: "Demo Day" });
    expect(link).toHaveClass("wo-card");
    expect(link).toHaveAttribute("href", "/events/demo");
  });
});

describe("MemberCard", () => {
  it("leaves out fields the viewer cannot see", () => {
    render(<MemberCard id="1" name="Amaka Obi" roles={["founder"]} />);
    expect(screen.getByRole("heading", { name: "Amaka Obi" })).toBeInTheDocument();
    expect(screen.getByText("Founder")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".wo-member__meta")).toHaveLength(0);
  });

  it("shows at most three roles and calls back with the id", async () => {
    const onConnect = vi.fn();
    render(
      <MemberCard
        id="m-9"
        name="Tunde Kolade"
        title="Partner"
        company="Delta Capital"
        roles={["founder", "operator", "investor", "mentor"]}
        onConnect={onConnect}
      />,
    );
    expect(document.querySelectorAll(".wo-badge")).toHaveLength(3);
    expect(screen.getByText("Partner, Delta Capital")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(onConnect).toHaveBeenCalledWith("m-9");
  });
});

describe("Tabs", () => {
  const items = [
    { id: "about", label: "About", panel: <p>About panel</p> },
    { id: "activity", label: "Activity", panel: <p>Activity panel</p> },
    { id: "mentoring", label: "Mentorship", panel: <p>Mentoring panel</p> },
  ];

  it("shows one panel and selects with the arrow keys, wrapping at the ends", async () => {
    render(<Tabs label="Profile" items={items} />);
    const first = screen.getByRole("tab", { name: "About" });
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("About panel")).toBeVisible();
    expect(screen.queryByText("Activity panel")).not.toBeVisible();

    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Activity" })).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Mentorship" })).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "About" })).toHaveAttribute("aria-selected", "true");
  });

  it("only the selected tab is in the tab order", () => {
    render(<Tabs label="Profile" items={items} defaultValue="activity" />);
    expect(screen.getByRole("tab", { name: "Activity" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "About" })).toHaveAttribute("tabindex", "-1");
  });
});

describe("Alert", () => {
  it("announces errors as alerts and the rest as status, with a glyph and a title", () => {
    const { rerender } = render(<Alert tone="danger" title="Not approved" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Not approved");
    rerender(
      <Alert tone="success" title="You're approved">
        Welcome.
      </Alert>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("You're approved");
    expect(document.querySelector(".wo-alert__icon")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Modal", () => {
  function Harness({ onClose }: { onClose: () => void }) {
    return (
      <>
        <button type="button">Opener</button>
        <Modal
          open
          onClose={onClose}
          title="Book this session?"
          actions={
            <>
              <Button variant="ghost">Cancel</Button>
              <Button>Confirm booking</Button>
            </>
          }
        >
          Thursday, 15:00 WAT.
        </Modal>
      </>
    );
  }

  it("is a labelled modal dialog and closes on Escape", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Book this session?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("holds focus inside while tabbing", async () => {
    render(<Harness onClose={() => undefined} />);
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Confirm booking" });
    expect(cancel).toHaveFocus();
    await userEvent.tab();
    expect(confirm).toHaveFocus();
    await userEvent.tab();
    expect(cancel).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(confirm).toHaveFocus();
  });

  it("returns focus to what opened it", async () => {
    function Page() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open
          </button>
          <Modal open={open} onClose={() => setOpen(false)} title="Sure?">
            Body
          </Modal>
        </>
      );
    }
    render(<Page />);
    const opener = screen.getByRole("button", { name: "Open" });
    await userEvent.click(opener);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});

describe("TopNav", () => {
  const logo = {
    fullOnLight: "/a.png",
    fullOnDark: "/b.png",
    markOnLight: "/c.png",
    markOnDark: "/d.png",
  };

  it("marks the current page and offers a menu toggle", async () => {
    render(
      <TopNav
        logo={logo}
        links={[
          { label: "Directory", href: "/directory", current: true },
          { label: "Jobs", href: "/jobs" },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Directory" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Jobs" })).not.toHaveAttribute("aria-current");
    const menu = screen.getByRole("button", { name: "Open menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(menu);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
  });

  it("shows no more than five links", () => {
    const links = Array.from({ length: 7 }, (_, i) => ({ label: `Link ${i}`, href: `/l${i}` }));
    render(<TopNav logo={logo} links={links} />);
    expect(screen.getAllByRole("link").filter((a) => a.className.includes("wo-nav__link"))).toHaveLength(5);
  });
});

describe("StatTile", () => {
  it("shows the label, value and a worded change", () => {
    render(<StatTile variant="brand" label="Members" value="4,200+" delta="+12% this month" />);
    expect(screen.getByText("Members")).toBeInTheDocument();
    expect(screen.getByText("4,200+")).toBeInTheDocument();
    expect(screen.getByText("+12% this month")).toBeInTheDocument();
  });
});
