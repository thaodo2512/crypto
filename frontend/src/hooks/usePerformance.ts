import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { Performance, HealthInfo, SignalOutcome } from "../api/client";

export function usePerformance(days = 30) {
  return useQuery<Performance>({
    queryKey: ["performance", days],
    queryFn: () => fetchApi<Performance>(`/performance?days=${days}`),
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

export function useSignalOutcomes(days = 30) {
  return useQuery<SignalOutcome[]>({
    queryKey: ["signal-outcomes", days],
    queryFn: () => fetchApi<SignalOutcome[]>(`/signal/outcomes?days=${days}`),
    refetchInterval: 60_000,
  });
}
