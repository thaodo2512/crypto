import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { Performance, HealthInfo, SignalOutcome } from "../api/client";

export function usePerformance(days = 30, symbol?: string) {
  return useQuery<Performance>({
    queryKey: ["performance", days, symbol],
    queryFn: () => fetchApi<Performance>(`/performance?days=${days}`, symbol),
    refetchInterval: 30_000,
  });
}

export function useHealth() {
  return useQuery<HealthInfo>({
    queryKey: ["health"],
    queryFn: () => fetchApi<HealthInfo>("/health"),
    refetchInterval: 30_000,
  });
}

export function useSignalOutcomes(days = 30, symbol?: string) {
  return useQuery<SignalOutcome[]>({
    queryKey: ["signal-outcomes", days, symbol],
    queryFn: () => fetchApi<SignalOutcome[]>(`/signal/outcomes?days=${days}`, symbol),
    refetchInterval: 60_000,
  });
}
