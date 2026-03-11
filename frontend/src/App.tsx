import { useState, useCallback } from "react";
import { useWebSocket } from "./api/websocket";
import { useQueryClient } from "@tanstack/react-query";
import SignalPage from "./pages/SignalPage";
import PricePage from "./pages/PricePage";
import OptionsPage from "./pages/OptionsPage";
import FuturesPage from "./pages/FuturesPage";
import PerformancePage from "./pages/PerformancePage";

type Tab = "signals" | "price" | "options" | "futures" | "performance";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "signals", label: "Signals", icon: "SIG" },
  { id: "price", label: "Price", icon: "PRC" },
  { id: "options", label: "Options", icon: "OPT" },
  { id: "futures", label: "Futures", icon: "FUT" },
  { id: "performance", label: "Perf", icon: "PRF" },
];

function TabContent({ tab }: { tab: Tab }) {
  switch (tab) {
    case "signals":
      return <SignalPage />;
    case "price":
      return <PricePage />;
    case "options":
      return <OptionsPage />;
    case "futures":
      return <FuturesPage />;
    case "performance":
      return <PerformancePage />;
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("signals");
  const queryClient = useQueryClient();

  const handleWsMessage = useCallback(
    (msg: { type: string }) => {
      if (msg.type === "price") {
        queryClient.invalidateQueries({ queryKey: ["price"] });
      } else if (msg.type === "signal") {
        queryClient.invalidateQueries({ queryKey: ["signal"] });
        queryClient.invalidateQueries({ queryKey: ["daily-snapshot"] });
      }
    },
    [queryClient]
  );

  const { connected } = useWebSocket(handleWsMessage);

  return (
    <div className="flex flex-col md:flex-row h-screen w-screen overflow-hidden bg-bg-primary">
      {/* Desktop sidebar */}
      <nav className="hidden md:flex flex-col w-16 lg:w-48 bg-bg-card border-r border-border-subtle shrink-0">
        {/* Logo area */}
        <div className="p-3 lg:p-4 border-b border-border-subtle">
          <div className="text-center lg:text-left">
            <span className="text-sm font-bold text-text-primary tracking-wider hidden lg:inline">
              BTC SIGNAL
            </span>
            <span className="text-sm font-bold text-text-primary lg:hidden">
              BTC
            </span>
          </div>
        </div>

        {/* Nav items */}
        <div className="flex-1 py-2">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-3 lg:px-4 py-3 text-xs uppercase tracking-wider transition-colors cursor-pointer
                  ${
                    isActive
                      ? "text-neutral bg-neutral/10 border-r-2 border-neutral"
                      : "text-text-muted hover:text-text-secondary hover:bg-bg-card-hover"
                  }`}
              >
                <span className="font-bold text-[11px] w-8 text-center shrink-0">
                  {tab.icon}
                </span>
                <span className="hidden lg:inline">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Connection status */}
        <div className="p-3 border-t border-border-subtle">
          <div className="flex items-center gap-2 justify-center lg:justify-start">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-bull" : "bg-bear animate-pulse"
              }`}
            />
            <span className="text-[10px] text-text-muted hidden lg:inline">
              {connected ? "LIVE" : "OFFLINE"}
            </span>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
        {/* Mobile header */}
        <div className="md:hidden flex items-center justify-between px-4 py-3 bg-bg-card border-b border-border-subtle sticky top-0 z-20">
          <span className="text-sm font-bold tracking-wider">BTC SIGNAL</span>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                connected ? "bg-bull" : "bg-bear animate-pulse"
              }`}
            />
            <span className="text-[10px] text-text-muted">
              {connected ? "LIVE" : "OFF"}
            </span>
          </div>
        </div>

        <div className="p-3 sm:p-4 lg:p-6 max-w-[1400px] mx-auto">
          <TabContent tab={activeTab} />
        </div>
      </main>

      {/* Mobile bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-bg-card border-t border-border-subtle flex z-20">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-colors cursor-pointer
                ${
                  isActive
                    ? "text-neutral"
                    : "text-text-muted active:text-text-secondary"
                }`}
            >
              <span className="text-[11px] font-bold">{tab.icon}</span>
              <span className="text-[9px] uppercase tracking-wider">
                {tab.label}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
