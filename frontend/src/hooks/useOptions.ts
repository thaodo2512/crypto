import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { GexStrike, OiStrike } from "../api/client";

interface GexResponse {
  strikes: GexStrike[];
  gamma_flip: number | null;
}

export function useGex(symbol?: string) {
  return useQuery<GexResponse>({
    queryKey: ["options", "gex", symbol],
    queryFn: () => fetchApi<GexResponse>("/options/gex", symbol),
    refetchInterval: 30_000,
  });
}

export function useOptionsOI(symbol?: string) {
  return useQuery<OiStrike[]>({
    queryKey: ["options", "oi", symbol],
    queryFn: () => fetchApi<OiStrike[]>("/options/oi", symbol),
    refetchInterval: 30_000,
  });
}
