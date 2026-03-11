import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { GexStrike, OiStrike } from "../api/client";

export function useGex() {
  return useQuery<GexStrike[]>({
    queryKey: ["options", "gex"],
    queryFn: () => fetchApi<GexStrike[]>("/options/gex"),
    refetchInterval: 30_000,
  });
}

export function useOptionsOI() {
  return useQuery<OiStrike[]>({
    queryKey: ["options", "oi"],
    queryFn: () => fetchApi<OiStrike[]>("/options/oi"),
    refetchInterval: 30_000,
  });
}
