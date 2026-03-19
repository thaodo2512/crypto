import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { FuturesSnapshot } from "../api/client";

export function useFuturesHistory(days = 7, symbol?: string) {
  return useQuery<FuturesSnapshot[]>({
    queryKey: ["futures", "history", days, symbol],
    queryFn: () => fetchApi<FuturesSnapshot[]>(`/futures/history?days=${days}`, symbol),
    refetchInterval: 30_000,
  });
}
