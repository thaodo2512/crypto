import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { OHLCV, Technicals } from "../api/client";

export function useLatestPrice(symbol?: string) {
  return useQuery<OHLCV>({
    queryKey: ["price", "latest", symbol],
    queryFn: () => fetchApi<OHLCV>("/price/latest", symbol),
    refetchInterval: 30_000,
  });
}

export function usePriceOHLCV(days = 7, symbol?: string) {
  return useQuery<OHLCV[]>({
    queryKey: ["price", "ohlcv", days, symbol],
    queryFn: () => fetchApi<OHLCV[]>(`/price/ohlcv?days=${days}`, symbol),
    refetchInterval: 30_000,
  });
}

export function useTechnicals(symbol?: string) {
  return useQuery<Technicals>({
    queryKey: ["technicals", symbol],
    queryFn: () => fetchApi<Technicals>("/technicals", symbol),
    refetchInterval: 30_000,
  });
}

export function useKlines(interval: string, limit = 200, symbol?: string) {
  return useQuery<OHLCV[]>({
    queryKey: ["klines", interval, limit, symbol],
    queryFn: () => fetchApi<OHLCV[]>(`/price/klines?interval=${interval}&limit=${limit}`, symbol),
    refetchInterval: interval === "1m" ? 10_000 : 30_000,
  });
}
