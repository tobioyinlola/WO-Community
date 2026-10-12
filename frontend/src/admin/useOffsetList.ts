import { useInfiniteQuery } from "@tanstack/react-query";

interface Page<T> {
  results: T[];
  next?: string | null;
}

/** The console's lists take `limit` and `offset` and say whether there is a next page. */
export function useOffsetList<T>(key: readonly unknown[], load: (offset: number, limit: number) => Promise<Page<T>>, limit = 25) {
  const query = useInfiniteQuery({
    queryKey: [...key, limit],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => load(pageParam, limit),
    getNextPageParam: (last, all) => (last.next ? all.length * limit : undefined),
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
