import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "../api/client";
import type { Signal, DailySnapshot, RiskBreakdown, MacroEvent } from "../api/client";

export function useLatestSignal(symbol?: string) {
  return useQuery<Signal>({
    queryKey: ["signal", "latest", symbol],
    queryFn: () => fetchApi<Signal>("/signal/latest", symbol),
    refetchInterval: 30_000,
  });
}

export function useSignalHistory(days = 30, symbol?: string) {
  return useQuery<Signal[]>({
    queryKey: ["signal", "history", days, symbol],
    queryFn: () => fetchApi<Signal[]>(`/signal/history?days=${days}`, symbol),
    refetchInterval: 30_000,
  });
}

export function useDailySnapshot(symbol?: string) {
  return useQuery<DailySnapshot>({
    queryKey: ["daily-snapshot", symbol],
    queryFn: () => fetchApi<DailySnapshot>("/daily-snapshot", symbol),
    refetchInterval: 30_000,
  });
}

export function useRiskBreakdown(symbol?: string) {
  return useQuery<RiskBreakdown>({
    queryKey: ["risk", "breakdown", symbol],
    queryFn: () => fetchApi<RiskBreakdown>("/risk/breakdown", symbol),
    refetchInterval: 30_000,
  });
}

export function useUpcomingEvents(days = 7, symbol?: string) {
  return useQuery<MacroEvent[]>({
    queryKey: ["events", "upcoming", days, symbol],
    queryFn: () => fetchApi<MacroEvent[]>(`/events/upcoming?days=${days}`, symbol),
    refetchInterval: 60_000,
  });
}
