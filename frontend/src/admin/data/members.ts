import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/** How many members match some filters, read as a page of one so only the total travels. */
export function useMemberCount(extra: Record<string, string | boolean>, base: Record<string, string> = {}) {
  return useQuery({
    queryKey: ["admin", "members", "count", base, extra],
    queryFn: () => unwrap(api.GET("/api/v1/admin/members", { params: { query: { limit: 1, ...base, ...extra } as never } })).then((p) => p.count),
    placeholderData: keepPreviousData,
  });
}
