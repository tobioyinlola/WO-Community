import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { Badge, CardText, CardTitle, CardTo } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { EmptyState, Loaded, PageHeader, RichText, SkeletonCards, useDocumentTitle } from "../../ui/blocks";

export function NewsList() {
  const query = useQuery({
    queryKey: ["public", "news"],
    queryFn: () => unwrap(api.GET("/api/v1/public/news", { params: { query: { limit: 30 } } })),
  });
  return (
    <div className="wo-container" style={{ padding: "var(--space-12) var(--page-margin) var(--space-24)" }}>
      <PageHeader eyebrow="News" title="From the community" lead="Awards, funding, partnerships and announcements." />
      <Loaded
        query={query}
        skeleton={<SkeletonCards />}
        isEmpty={(d) => d.results.length === 0}
        empty={<EmptyState title="Nothing published yet">Check back soon.</EmptyState>}
      >
        {(data) => (
          <div className="app-grid">
            {data.results.map((item) => (
              <CardTo key={item.slug} to={`/news/${item.slug}`}>
                <Badge variant="operator">{humanise(item.type)}</Badge>
                <CardTitle style={{ marginTop: "var(--space-3)" }}>{item.title}</CardTitle>
                <CardText>{item.excerpt}</CardText>
                <p className="caption app-faint" style={{ margin: "var(--space-3) 0 0" }}>
                  {formatDate(item.published_at)}
                </p>
              </CardTo>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}

export function NewsItem() {
  const { slug = "" } = useParams();
  const query = useQuery({
    queryKey: ["public", "news", slug],
    queryFn: () => unwrap(api.GET("/api/v1/public/news/{slug}", { params: { path: { slug } } })),
  });
  useDocumentTitle(query.data?.title ?? "News");
  return (
    <div className="wo-container wo-container--narrow" style={{ padding: "var(--space-12) var(--page-margin) var(--space-24)" }}>
      <p style={{ margin: "0 0 var(--space-6)" }}>
        <Link className="app-link" to="/news">
          All news
        </Link>
      </p>
      <Loaded query={query}>
        {(item) => (
          <article>
            <Badge variant="operator">{humanise(item.type)}</Badge>
            <h1 className="h1" style={{ margin: "var(--space-4) 0" }}>
              {item.title}
            </h1>
            <p className="body-sm app-faint">{formatDate(item.published_at)}</p>
            <RichText html={item.body} />
          </article>
        )}
      </Loaded>
    </div>
  );
}
