import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { GexStrike, OiStrike } from "../api/client";

interface GexResponse {
  strikes: GexStrike[];
  gamma_flip: number | null;
}

export function useGex() {
  return useQuery<GexResponse>({
    queryKey: ["options", "gex"],
    queryFn: () => fetchApi<GexResponse>("/options/gex"),
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
