import { useQuery } from "@tanstack/react-query";
import { SearchX } from "lucide-react";
import { Fragment } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { messageOf } from "../api/errors";
import { Alert } from "../components";
import { EmptyState, PageHeader, SkeletonRows } from "../ui/blocks";
import { fetchResults, toGroups } from "./GlobalSearch";
import { highlightParts, iconOf, tagOf, type Scope } from "./searchModel";

function Marked({ text, term }: { text: string; term: string }) {
  return (
    <>
      {highlightParts(text, term).map((part, i) => (part.match ? <mark key={i}>{part.text}</mark> : <Fragment key={i}>{part.text}</Fragment>))}
    </>
  );
}

/** Everything that matches, with a filter for each kind of thing. Opened from "See all results". */
export function SearchPage({ scope }: { scope: Scope }) {
  const [params, setParams] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const type = params.get("type") ?? "";

  // Fetch every group once and filter in the page, so the chips can show how many each holds.
  const results = useQuery({
    queryKey: ["search", "page", scope, q],
    enabled: q.length >= 2,
    queryFn: () => fetchResults(scope, q, 20),
  });
  const groups = toGroups(scope, results.data);
  const shown = type ? groups.filter((g) => g.id === type) : groups;
  const total = groups.reduce((n, g) => n + g.hits.length, 0);

  const choose = (next: string) => {
    const copy = new URLSearchParams(params);
    if (next) copy.set("type", next);
    else copy.delete("type");
    setParams(copy, { replace: true });
  };

  return (
    <>
      <PageHeader
        eyebrow="Search"
        title={q ? `Results for “${q}”` : "Search"}
        lead={q.length < 2 ? "Type at least two letters in the search box above." : results.isSuccess ? `${total} ${total === 1 ? "result" : "results"}` : undefined}
      />

      {groups.length > 0 ? (
        <div className="wo-search__filters" role="group" aria-label="Filter by type">
          <button type="button" className="wo-chip" aria-pressed={type === ""} onClick={() => choose("")}>
            All <span>{total}</span>
          </button>
          {groups.map((g) => (
            <button key={g.id} type="button" className="wo-chip" aria-pressed={type === g.id} onClick={() => choose(g.id)}>
              {g.label} <span>{g.hits.length}</span>
            </button>
          ))}
        </div>
      ) : null}

      {results.isPending && q.length >= 2 ? <SkeletonRows /> : null}
      {results.isError ? (
        <Alert tone="danger" title="We could not search">
          {messageOf(results.error)}
        </Alert>
      ) : null}
      {results.isSuccess && groups.length === 0 ? (
        <EmptyState title={`No results for “${q}”`} icon={<SearchX size={22} strokeWidth={1.5} />}>
          Check the spelling, or use fewer words.
        </EmptyState>
      ) : null}

      {shown.map((g) => (
        <section key={g.id} className="wo-search__section" aria-labelledby={`sr-${g.id}`}>
          <h2 id={`sr-${g.id}`} className="wo-search__sectionhead">
            {g.label}
          </h2>
          <ul className="wo-search__results">
            {g.hits.map((hit) => {
              const Icon = iconOf(hit.type);
              return (
                <li key={hit.key}>
                  <Link to={hit.to} className="wo-search__row wo-search__row--page">
                    <Icon size={18} strokeWidth={1.5} aria-hidden="true" />
                    <span className="wo-search__main">
                      <span className="wo-search__title">
                        <Marked text={hit.title} term={q} />
                      </span>
                      {hit.subtitle ? (
                        <span className="wo-search__sub">
                          <Marked text={hit.subtitle} term={q} />
                        </span>
                      ) : null}
                    </span>
                    <span className="wo-search__tag">{tagOf(hit.type)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </>
  );
}
