import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/** Which tools are switched on, and whether AI writing is available. */
export function useToolkitConfig() {
  return useQuery({
    queryKey: ["toolkit", "config"],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/config")),
    staleTime: 5 * 60_000,
  });
}

/** AI is assumed available until the answer arrives, so nothing flickers away on a fast load. */
export function useAiEnabled(): boolean {
  return useToolkitConfig().data?.ai_enabled ?? true;
}

/** Whether a tool is on. Until the answer arrives every tool is shown. */
export function useFeature(name: string): boolean {
  return useToolkitConfig().data?.features[name] ?? true;
}
