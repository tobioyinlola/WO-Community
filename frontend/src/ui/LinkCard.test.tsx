import { render, screen } from "@testing-library/react";
import { LinkCard } from "./LinkCard";
import { RichText } from "./blocks";

describe("links in posts", () => {
  it("a card names the site and the page, and opens in a new tab", () => {
    render(
      <LinkCard
        preview={{ url: "https://example.com/story", title: "A good read", description: "Why it matters", site_name: "Example", image: null }}
      />,
    );
    const link = screen.getByRole("link", { name: /A good read/ });
    expect(link).toHaveAttribute("href", "https://example.com/story");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("Example")).toBeInTheDocument();
    expect(screen.getByText("Why it matters")).toBeInTheDocument();
  });

  it("a link whose page could not be read still says where it goes", () => {
    render(<LinkCard preview={{ url: "https://news.example.org/a", title: "news.example.org", description: "", site_name: "news.example.org", image: null }} />);
    expect(screen.getAllByText("news.example.org").length).toBeGreaterThan(0);
  });

  it("shows the picture when the page has one", () => {
    const { container } = render(
      <LinkCard preview={{ url: "https://e.com/x", title: "T", description: "", site_name: "E", image: { thumb: "https://img/t.webp", large: "https://img/l.webp" } }} />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", "https://img/t.webp");
  });

  it("links in rich text open in a new tab, and unsafe ones are dropped", () => {
    render(<RichText html={'<p>See <a href="https://example.com/a">this</a> and <a href="javascript:alert(1)">that</a></p>'} />);
    const good = screen.getByRole("link", { name: "this" });
    expect(good).toHaveAttribute("target", "_blank");
    expect(good).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.queryByRole("link", { name: "that" })).not.toBeInTheDocument();
  });
});
