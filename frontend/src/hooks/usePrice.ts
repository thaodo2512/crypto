import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { OHLCV, Technicals } from "../api/client";

export function useLatestPrice() {
  return useQuery<OHLCV>({
    queryKey: ["price", "latest"],
    queryFn: () => fetchApi<OHLCV>("/price/latest"),
    refetchInterval: 30_000,
  });
}

export function usePriceOHLCV(days = 7) {
  return useQuery<OHLCV[]>({
    queryKey: ["price", "ohlcv", days],
    queryFn: () => fetchApi<OHLCV[]>(`/price/ohlcv?days=${days}`),
    refetchInterval: 30_000,
  });
}

export function useTechnicals() {
  return useQuery<Technicals>({
    queryKey: ["technicals"],
    queryFn: () => fetchApi<Technicals>("/technicals"),
    refetchInterval: 30_000,
  });
}
