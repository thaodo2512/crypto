import { useState, useCallback, useEffect } from "react";
import { useWebSocket } from "./api/websocket";
import { useQueryClient } from "@tanstack/react-query";
import { fetchApi, type Asset } from "./api/client";
import SignalPage from "./pages/SignalPage";
import PricePage from "./pages/PricePage";
import OptionsPage from "./pages/OptionsPage";
import FuturesPage from "./pages/FuturesPage";
import PerformancePage from "./pages/PerformancePage";
import AboutPage from "./pages/AboutPage";

type Tab = "signals" | "price" | "options" | "futures" | "performance" | "about";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "signals", label: "Signals", icon: "SIG" },
  { id: "price", label: "Price", icon: "PRC" },
  { id: "options", label: "Options", icon: "OPT" },
  { id: "futures", label: "Futures", icon: "FUT" },
  { id: "performance", label: "Perf", icon: "PRF" },
  { id: "about", label: "About", icon: "ABT" },
];

function TabContent({ tab, symbol }: { tab: Tab; symbol: string }) {
  switch (tab) {
    case "signals":
      return <SignalPage symbol={symbol} />;
    case "price":
      return <PricePage symbol={symbol} />;
    case "options":
      return <OptionsPage symbol={symbol} />;
    case "futures":
      return <FuturesPage symbol={symbol} />;
    case "performance":
      return <PerformancePage symbol={symbol} />;
    case "about":
      return <AboutPage />;
  }
}

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("signals");
  const [activeAsset, setActiveAsset] = useState("BTC");
  const [assets, setAssets] = useState<Asset[]>([{ symbol: "BTC", enabled: true, has_options: true }]);
  const queryClient = useQueryClient();

  useEffect(() => {
    fetchApi<Asset[]>("/assets").then(setAssets).catch(() => {});
  }, []);

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
      <nav className="hidden md:flex flex-col w-16 lg:w-48 border-r border-border-subtle shrink-0"
        style={{ background: "linear-gradient(180deg, rgba(12, 16, 24, 0.98), rgba(6, 10, 16, 1))" }}
      >
        {/* Logo area + asset selector */}
        <div className="p-3 lg:p-4 border-b border-border-subtle">
          <div className="text-center lg:text-left">
            <span className="text-xs font-bold text-text-primary tracking-[0.2em] hidden lg:inline font-data">
              {activeAsset} SIGNAL
            </span>
            <span className="text-xs font-bold text-text-primary lg:hidden font-data">
              {activeAsset}
            </span>
          </div>
          {/* Asset selector */}
          {assets.length > 1 && (
            <div className="flex gap-1 mt-2 justify-center lg:justify-start">
              {assets.map((a) => (
                <button
                  key={a.symbol}
                  onClick={() => {
                    setActiveAsset(a.symbol);
                    queryClient.invalidateQueries();
                  }}
                  className={`px-2 py-0.5 text-[9px] font-bold font-data tracking-wider rounded transition-colors cursor-pointer
                    ${activeAsset === a.symbol
                      ? "bg-neutral/20 text-text-primary border border-neutral/40"
                      : "text-text-muted hover:text-text-secondary border border-transparent"
                    }`}
                >
                  {a.symbol}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Nav items */}
        <div className="flex-1 py-2">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-3 lg:px-4 py-3 text-[10px] uppercase tracking-wider transition-colors cursor-pointer
                  ${
                    isActive
                      ? "text-text-primary bg-border-subtle/20 border-r-2 border-neutral"
                      : "text-text-muted hover:text-text-secondary hover:bg-border-subtle/10"
                  }`}
              >
                <span className="font-bold text-[10px] w-8 text-center shrink-0 font-data">
                  {tab.icon}
                </span>
                <span className="hidden lg:inline font-medium">{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Connection status */}
        <div className="p-3 border-t border-border-subtle">
          <div className="flex items-center gap-2 justify-center lg:justify-start">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                connected ? "bg-bull" : "bg-bear animate-pulse"
              }`}
            />
            <span className="text-[9px] text-text-muted hidden lg:inline font-data tracking-wider">
              {connected ? "LIVE" : "OFFLINE"}
            </span>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
        {/* Mobile header */}
        <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border-subtle sticky top-0 z-20"
          style={{ background: "linear-gradient(135deg, rgba(12, 16, 24, 0.98), rgba(12, 16, 24, 0.90))", backdropFilter: "blur(8px)" }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold tracking-[0.2em] font-data">{activeAsset} SIGNAL</span>
            {/* Mobile asset selector */}
            {assets.length > 1 && (
              <div className="flex gap-1">
                {assets.map((a) => (
                  <button
                    key={a.symbol}
                    onClick={() => {
                      setActiveAsset(a.symbol);
                      queryClient.invalidateQueries();
                    }}
                    className={`px-1.5 py-0.5 text-[8px] font-bold font-data rounded cursor-pointer
                      ${activeAsset === a.symbol
                        ? "bg-neutral/20 text-text-primary"
                        : "text-text-muted"
                      }`}
                  >
                    {a.symbol}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                connected ? "bg-bull" : "bg-bear animate-pulse"
              }`}
            />
            <span className="text-[9px] text-text-muted font-data">
              {connected ? "LIVE" : "OFF"}
            </span>
          </div>
        </div>

        <div className="p-3 sm:p-4 lg:p-6 max-w-[1400px] mx-auto">
          <TabContent tab={activeTab} symbol={activeAsset} />
        </div>
      </main>

      {/* Mobile bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t border-border-subtle flex z-20"
        style={{ background: "linear-gradient(135deg, rgba(12, 16, 24, 0.98), rgba(12, 16, 24, 0.90))", backdropFilter: "blur(8px)" }}
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 transition-colors cursor-pointer
                ${
                  isActive
                    ? "text-text-primary"
                    : "text-text-muted active:text-text-secondary"
                }`}
            >
              <span className="text-[10px] font-bold font-data">{tab.icon}</span>
              <span className="text-[8px] uppercase tracking-wider">
                {tab.label}
              </span>
              {isActive && (
                <span className="w-4 h-[2px] bg-neutral rounded-full mt-0.5" />
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
