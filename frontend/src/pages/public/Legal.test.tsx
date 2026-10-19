import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Legal } from "./Legal";
import { parse } from "./legal/LegalText";

function open(doc: string) {
  render(
    <MemoryRouter initialEntries={[`/legal/${doc}`]}>
      <Routes>
        <Route path="/legal/:doc" element={<Legal />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Legal pages", () => {
  it.each([
    ["terms", "Terms and Conditions", "1.22 Governing law and disputes"],
    ["privacy", "Privacy Policy", "2.10 Your rights"],
    ["conduct", "Code of Conduct", "3.9 Appeals"],
  ])("shows the full %s with its dates and sections", (doc, title, section) => {
    open(doc);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText("Effective date:")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: section })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: section })).toHaveAttribute("href", expect.stringMatching(/^#s-/));
    // Nothing left to fill in.
    expect(document.body.textContent).not.toMatch(/\[[^\]]*\]/);
  });

  it("draws the privacy table as a table", () => {
    open("privacy");
    expect(screen.getByRole("columnheader", { name: "Why (legal basis)" })).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBeGreaterThan(5);
  });

  it("says when a page does not exist", () => {
    open("nope");
    expect(screen.getByText("We could not find that page")).toBeInTheDocument();
  });

  it("parses lists, tables and paragraphs", () => {
    const blocks = parse("## A\n\nText one\nstill one\n\n1. first\n2. second\n\n- dot\n\n| h1 | h2 |\n|---|---|\n| a | b |\n");
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "numbers", "bullets", "table"]);
    expect(blocks[1]).toEqual({ kind: "paragraph", text: "Text one still one" });
    expect(blocks[4]).toEqual({ kind: "table", head: ["h1", "h2"], rows: [["a", "b"]] });
  });
});
