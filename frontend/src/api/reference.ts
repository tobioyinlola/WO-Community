import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./client";

export interface Option {
  value: string;
  label: string;
}

/** The lists change rarely, so they are fetched once and kept for the whole visit. */
const FOREVER = { staleTime: Infinity, gcTime: Infinity } as const;

export function useCountries() {
  return useQuery({
    queryKey: ["reference", "countries"],
    queryFn: async (): Promise<Option[]> =>
      (await unwrap(api.GET("/api/v1/reference/countries"))).map((c) => ({
        value: c.code,
        label: c.name,
      })),
    ...FOREVER,
  });
}

export function useSectors() {
  return useQuery({
    queryKey: ["reference", "sectors"],
    queryFn: async (): Promise<Option[]> =>
      (await unwrap(api.GET("/api/v1/reference/sectors"))).map((s) => ({
        value: s.slug,
        label: s.name,
      })),
    ...FOREVER,
  });
}

export function useStages() {
  return useQuery({
    queryKey: ["reference", "stages"],
    queryFn: async (): Promise<Option[]> =>
      (await unwrap(api.GET("/api/v1/reference/stages"))).map((s) => ({
        value: s.slug,
        label: s.name,
      })),
    ...FOREVER,
  });
}

export function useSkills() {
  return useQuery({
    queryKey: ["reference", "skills"],
    queryFn: async (): Promise<Option[]> =>
      (await unwrap(api.GET("/api/v1/reference/skills"))).map((s) => ({
        value: s.slug,
        label: s.name,
      })),
    ...FOREVER,
  });
}

/** A select needs a blank first choice so nothing is picked for the member. */
export function withPlaceholder(options: Option[] | undefined, label = "Choose one"): Option[] {
  return [{ value: "", label }, ...(options ?? [])];
}
