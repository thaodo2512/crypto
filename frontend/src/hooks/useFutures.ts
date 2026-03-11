import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { FuturesSnapshot } from "../api/client";

export function useFuturesHistory(days = 7) {
  return useQuery<FuturesSnapshot[]>({
    queryKey: ["futures", "history", days],
    queryFn: () => fetchApi<FuturesSnapshot[]>(`/futures/history?days=${days}`),
    refetchInterval: 30_000,
  });
}
