export default function AboutPage() {
  return (
    <div className="space-y-4 max-w-3xl">
      {/* Header */}
      <div className="card p-6">
        <h1 className="text-xl font-bold mb-2">BTC Signal Terminal</h1>
        <p className="text-sm text-text-secondary leading-relaxed">
          A decision support tool for BTC/USDT swing trading. It collects data from spot, futures,
          and options markets, computes 4 composite directional signals with adaptive regime-based
          weights, and delivers actionable trade plans via Telegram. This is NOT an auto-trading bot
          — all trades require human approval.
        </p>
      </div>

      {/* How It Works */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">How It Works</h2>
        <div className="space-y-3 text-xs text-text-secondary leading-relaxed">
          <div className="flex gap-3">
            <span className="text-purple font-data font-bold shrink-0 w-5 text-right">1</span>
            <div><span className="text-text-primary font-medium">Collect</span> — Every 2-15 minutes, data is fetched from Binance (spot + futures), Bybit, OKX, and Deribit (options).</div>
          </div>
          <div className="flex gap-3">
            <span className="text-purple font-data font-bold shrink-0 w-5 text-right">2</span>
            <div><span className="text-text-primary font-medium">Compute</span> — Every 4 hours, 4 composite signals are calculated from the collected data, each scoring [-1.0, +1.0].</div>
          </div>
          <div className="flex gap-3">
            <span className="text-purple font-data font-bold shrink-0 w-5 text-right">3</span>
            <div><span className="text-text-primary font-medium">Weigh</span> — Signals are combined using adaptive weights that shift based on the detected market regime (trending, ranging, transitional).</div>
          </div>
          <div className="flex gap-3">
            <span className="text-purple font-data font-bold shrink-0 w-5 text-right">4</span>
            <div><span className="text-text-primary font-medium">Plan</span> — If the signal passes entry gates (MODERATE+ strength, MEDIUM+ confidence), a trade plan is generated with entry, SL, TP1/TP2/TP3 levels.</div>
          </div>
          <div className="flex gap-3">
            <span className="text-purple font-data font-bold shrink-0 w-5 text-right">5</span>
            <div><span className="text-text-primary font-medium">Monitor</span> — Open trades are tracked every 2 minutes against SL/TP levels. Alerts are sent on hits, with R-multiple tracking.</div>
          </div>
        </div>
      </div>

      {/* 4 Composite Signals */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">4 Composite Signals</h2>
        <div className="space-y-5">
          {/* Signal 1 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-data font-bold text-bull bg-bull/10 px-2 py-0.5 rounded">S1</span>
              <span className="text-sm font-semibold">Spot Flow</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-2">
              Measures real buying/selling pressure on the spot market.
            </p>
            <div className="bg-bg-primary/50 rounded-lg p-3 text-[11px] font-data text-text-muted space-y-1">
              <div><span className="text-text-secondary">CVD Z-Score</span> (50%) — Cumulative volume delta vs 30-day history. Divergence amplifier ×1.5, 4h contradiction dampener ×0.7.</div>
              <div><span className="text-text-secondary">Whale Trades</span> (25%) — Buy/sell volume ratio of large trades. Ratio 0.5 = neutral, 1.0 = all buying.</div>
              <div><span className="text-text-secondary">Orderbook Imbalance</span> (25%) — Bid vs ask depth. Anti-spoof filter reduces signal when imbalance {">"} 0.6.</div>
              <div className="pt-1 text-text-muted">Final score × volume multiplier (0.6x to 1.3x based on volume ratio).</div>
            </div>
          </div>

          {/* Signal 2 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-data font-bold text-cyan bg-cyan/10 px-2 py-0.5 rounded">S2</span>
              <span className="text-sm font-semibold">Leverage Positioning</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-2">
              Reads futures market positioning for crowding and contrarian signals.
            </p>
            <div className="bg-bg-primary/50 rounded-lg p-3 text-[11px] font-data text-text-muted space-y-1">
              <div><span className="text-text-secondary">Funding Rate</span> (30%) — Contrarian: extreme positive funding → bearish, extreme negative → bullish. Neutral band ±0.01%.</div>
              <div><span className="text-text-secondary">OI-Price Regime</span> (30%) — NEW_LONGS (+0.8), NEW_SHORTS (-0.8), LONG_CLOSING (-0.3), SHORT_CLOSING (+0.3).</div>
              <div><span className="text-text-secondary">Smart vs Retail</span> (25%) — Top trader L/S vs global L/S divergence. Follow smart money on disagreement.</div>
              <div><span className="text-text-secondary">Taker Aggression</span> (15%) — Buy/sell ratio × 3.0, clipped to [-1, +1].</div>
              <div className="pt-1 text-text-muted">Internal consistency multiplier: 3+ agree → ×1.3, conflict → ×0.5.</div>
            </div>
          </div>

          {/* Signal 3 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-data font-bold text-purple bg-purple/10 px-2 py-0.5 rounded">S3</span>
              <span className="text-sm font-semibold">Options Structure</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-2">
              Extracts directional signals from the BTC options market on Deribit.
            </p>
            <div className="bg-bg-primary/50 rounded-lg p-3 text-[11px] font-data text-text-muted space-y-1">
              <div><span className="text-text-secondary">Gamma Flip Distance</span> (40%) — Linear: spot above gamma flip → bullish. ±8% from flip → ±1.0.</div>
              <div><span className="text-text-secondary">Net GEX Z-Score</span> (25%) — Net gamma exposure vs 30-day history. Capped at ±0.6.</div>
              <div><span className="text-text-secondary">IV Skew</span> (20%) — Contrarian: expensive puts → bullish. Linear ±8 → ±0.6.</div>
              <div><span className="text-text-secondary">Max Pain Gravity</span> (15%) — Price below max pain → bullish pull. Linear ±10% → ±0.5.</div>
            </div>
          </div>

          {/* Signal 4 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] font-data font-bold text-gold bg-gold/10 px-2 py-0.5 rounded">S4</span>
              <span className="text-sm font-semibold">Mean Reversion</span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed mb-2">
              Identifies overextended conditions that may revert to the mean.
            </p>
            <div className="bg-bg-primary/50 rounded-lg p-3 text-[11px] font-data text-text-muted space-y-1">
              <div><span className="text-text-secondary">RSI (14)</span> (30%) — Symmetric around 50. Interpolates: 50→70 gives 0→-0.5, 70→80 gives -0.5→-1.0. Mirrored for oversold.</div>
              <div><span className="text-text-secondary">VWAP Distance</span> (20%) — Linear: ±8% from VWAP → ∓0.8. Above VWAP → bearish reversion.</div>
              <div><span className="text-text-secondary">Futures Basis</span> (20%) — Linear: ±30% annualized → ∓0.8, dead zone ±5%. High contango → bearish.</div>
              <div><span className="text-text-secondary">Fear & Greed</span> (15%) — Contrarian, linear: 60-80 → 0 to -0.8, 20-40 → 0 to +0.8.</div>
              <div><span className="text-text-secondary">Bollinger Position</span> (15%) — Linear from center: at upper band → -0.8, at lower band → +0.8.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Regime Detection */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">Adaptive Regime Weights</h2>
        <p className="text-xs text-text-secondary leading-relaxed mb-3">
          The market regime is detected using ADX (trend strength) and Bollinger Band width percentile (volatility compression).
          Signal weights shift based on what works best in each regime:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-data">
            <thead>
              <tr className="text-text-muted uppercase tracking-wider border-b border-border-subtle">
                <th className="text-left py-2 px-2">Regime</th>
                <th className="text-right py-2 px-2 text-bull">Spot Flow</th>
                <th className="text-right py-2 px-2 text-cyan">Leverage</th>
                <th className="text-right py-2 px-2 text-purple">Options</th>
                <th className="text-right py-2 px-2 text-gold">Mean Rev</th>
              </tr>
            </thead>
            <tbody className="text-text-secondary">
              {[
                { name: "Strong Trend", s: 35, l: 30, o: 20, m: 15, desc: "ADX > 30, wide BBs" },
                { name: "Moderate Trend", s: 30, l: 25, o: 25, m: 20, desc: "ADX 25-30" },
                { name: "Wide Range", s: 20, l: 20, o: 30, m: 30, desc: "ADX < 25, wide BBs" },
                { name: "Tight Range", s: 15, l: 20, o: 30, m: 35, desc: "ADX < 20, narrow BBs" },
                { name: "Transitional", s: 25, l: 25, o: 25, m: 25, desc: "Default / unclear" },
              ].map((r) => (
                <tr key={r.name} className="border-b border-border-subtle/30">
                  <td className="py-2 px-2">
                    <div className="font-medium text-text-primary">{r.name}</div>
                    <div className="text-[9px] text-text-muted">{r.desc}</div>
                  </td>
                  <td className="text-right py-2 px-2">{r.s}%</td>
                  <td className="text-right py-2 px-2">{r.l}%</td>
                  <td className="text-right py-2 px-2">{r.o}%</td>
                  <td className="text-right py-2 px-2">{r.m}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trade Plan */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">Trade Plan & Risk</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-text-secondary leading-relaxed">
          <div>
            <h3 className="text-text-primary font-medium mb-2">Entry Gates</h3>
            <ul className="space-y-1.5 text-[11px]">
              <li className="flex gap-2"><span className="text-bull">1</span> Signal strength must be MODERATE or higher (|score| {"≥"} 0.20)</li>
              <li className="flex gap-2"><span className="text-bull">2</span> Confidence must be MEDIUM or higher (consensus + data quality)</li>
              <li className="flex gap-2"><span className="text-bull">3</span> At least 1 confluence zone must exist near current price</li>
            </ul>
          </div>
          <div>
            <h3 className="text-text-primary font-medium mb-2">Exit Levels</h3>
            <ul className="space-y-1.5 text-[11px]">
              <li className="flex gap-2"><span className="text-bear">SL</span> Nearest support/resistance ± 0.3% buffer (fallback ±2%)</li>
              <li className="flex gap-2"><span className="text-gold">TP1</span> Nearest confluence zone or 1.5R minimum — exit 50% position</li>
              <li className="flex gap-2"><span className="text-gold">TP2</span> Next confluence zone or 2.5R — exit 30% position</li>
              <li className="flex gap-2"><span className="text-gold">TP3</span> Trailing stop 2% from high — exit remaining 20%</li>
              <li className="flex gap-2"><span className="text-text-muted">48h</span> Time stop — re-evaluate if no level hit</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Event Risk */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">Event Risk</h2>
        <p className="text-xs text-text-secondary leading-relaxed mb-3">
          A separate risk score [0, 1.0] that dampens the signal when dangerous conditions are detected.
          Above 0.8 → STAY OUT (no trades).
        </p>
        <div className="bg-bg-primary/50 rounded-lg p-3 text-[11px] font-data text-text-muted space-y-1">
          <div><span className="text-text-secondary">Options Expiry</span> — Large BTC options expiring within 24-48h.</div>
          <div><span className="text-text-secondary">Liquidation Cascade</span> — Estimated liquidation volume from OI drops.</div>
          <div><span className="text-text-secondary">Gamma Flip Proximity</span> — Price within 1-3% of gamma flip boundary.</div>
          <div><span className="text-text-secondary">DVol</span> — Deribit implied vol above 60 (elevated) or 80 (extreme).</div>
          <div><span className="text-text-secondary">Macro Events</span> — T1 events (FOMC, CPI) suspend signals 2h before → 1h after.</div>
        </div>
        <p className="text-[10px] text-text-muted mt-2">
          Final risk = 0.6 × average(active components) + 0.4 × peak(components)
        </p>
      </div>

      {/* Hard Limits */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">Immutable Constraints</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { label: "Max Risk / Trade", value: "2%", color: "#ef4444" },
            { label: "Max Leverage", value: "3x", color: "#ef4444" },
            { label: "Min R:R", value: "1.5:1", color: "#f59e0b" },
            { label: "Stay Out Threshold", value: "0.8", color: "#ef4444" },
            { label: "Signal Suspension", value: "2h pre / 1h post T1", color: "#f59e0b" },
            { label: "AI Role", value: "Advisory only", color: "#6366f1" },
          ].map((c) => (
            <div key={c.label} className="bg-bg-primary/50 rounded-lg p-3 border border-border-subtle/30">
              <div className="text-[9px] uppercase tracking-wider text-text-muted mb-1">{c.label}</div>
              <div className="text-sm font-data font-bold" style={{ color: c.color }}>{c.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Data Sources */}
      <div className="card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary mb-4">Data Sources</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
          {[
            { name: "Binance", data: "Spot OHLCV, futures OI, funding, L/S, taker", interval: "2-15min" },
            { name: "Bybit", data: "Futures OI, funding rate", interval: "15min" },
            { name: "OKX", data: "Futures OI, funding rate", interval: "15min" },
            { name: "Deribit", data: "Options OI, IV, GEX, DVol, large trades", interval: "4h" },
            { name: "Alternative.me", data: "Fear & Greed Index", interval: "Daily" },
            { name: "FinancialJuice", data: "Breaking news headlines (RSS)", interval: "15min" },
            { name: "Forex Factory", data: "Macro economic calendar", interval: "12h" },
            { name: "Claude AI", data: "Headline classification, narrative analysis", interval: "On-demand" },
          ].map((s) => (
            <div key={s.name} className="bg-bg-primary/50 rounded-lg p-2.5 border border-border-subtle/30">
              <div className="text-text-primary font-medium mb-1">{s.name}</div>
              <div className="text-text-muted text-[10px] leading-relaxed">{s.data}</div>
              <div className="text-text-muted text-[9px] mt-1 font-data">{s.interval}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-[10px] text-text-muted py-4 font-data">
        Built with Freqtrade + FastAPI + React + Claude AI
      </div>
    </div>
  );
}
