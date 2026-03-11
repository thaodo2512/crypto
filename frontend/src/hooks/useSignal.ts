import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { Signal, DailySnapshot, RiskBreakdown, MacroEvent } from "../api/client";

export function useLatestSignal() {
  return useQuery<Signal>({
    queryKey: ["signal", "latest"],
    queryFn: () => fetchApi<Signal>("/signal/latest"),
    refetchInterval: 30_000,
  });
}

export function useSignalHistory(days = 30) {
  return useQuery<Signal[]>({
    queryKey: ["signal", "history", days],
    queryFn: () => fetchApi<Signal[]>(`/signal/history?days=${days}`),
    refetchInterval: 30_000,
  });
}

export function useDailySnapshot() {
  return useQuery<DailySnapshot>({
    queryKey: ["daily-snapshot"],
    queryFn: () => fetchApi<DailySnapshot>("/daily-snapshot"),
    refetchInterval: 30_000,
  });
}

export function useRiskBreakdown() {
  return useQuery<RiskBreakdown>({
    queryKey: ["risk", "breakdown"],
    queryFn: () => fetchApi<RiskBreakdown>("/risk/breakdown"),
    refetchInterval: 30_000,
  });
}

export function useUpcomingEvents(days = 7) {
  return useQuery<MacroEvent[]>({
    queryKey: ["events", "upcoming", days],
    queryFn: () => fetchApi<MacroEvent[]>(`/events/upcoming?days=${days}`),
    refetchInterval: 60_000,
  });
}
