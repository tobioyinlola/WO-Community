import { useInfiniteQuery, type QueryKey } from "@tanstack/react-query";

interface Page<T> {
  results: T[];
  next_cursor: string | null;
}

/** A list the API pages with a cursor: the flattened items plus what "Load more" needs. */
export function useCursorList<T, P extends Page<T> = Page<T>>(
  key: QueryKey,
  fetchPage: (cursor: string) => Promise<P>,
) {
  const query = useInfiniteQuery({
    queryKey: key,
    initialPageParam: "",
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.results) ?? [];
  return {
    query,
    items,
    isEmpty: query.isSuccess && items.length === 0,
    hasNext: Boolean(query.hasNextPage),
    loadMore: () => void query.fetchNextPage(),
    loadingMore: query.isFetchingNextPage,
  };
}

/** Removes empty values so they are not sent as filters. */
export function compact<T extends Record<string, unknown>>(values: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(values).filter(([, v]) => v !== "" && v !== undefined && v !== null),
  ) as Partial<T>;
}
