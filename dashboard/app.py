"""Streamlit Dashboard — interactive visualization for Crypto Signal Bot.

See docs/sub-specs/SS-23.md §13
"""

import logging
import os
import sys
from typing import Any

import plotly.graph_objects as go
import streamlit as st
import yaml

# Add project root to path so custom modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.evaluation.tracker import (
    compute_component_accuracy,
    compute_regime_accuracy,
    compute_win_rate,
)
from custom.utils.db import query

logger = logging.getLogger(__name__)

# ── Data loaders ────────────────────────────────────────────


def load_config() -> dict:
    """Load settings.yaml from project root.

    See docs/sub-specs/SS-23.md §13
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning("settings.yaml not found, using defaults")
        return {}


def load_signals(db_path: str, days: int = 30) -> list[dict[str, Any]]:
    """Load signal history from DB.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.
        days: Lookback window in days.

    Returns:
        List of signal dicts ordered by timestamp ascending.
    """
    return query(
        db_path,
        f"""SELECT timestamp, final_score, bias, strength, confidence,
                   regime, event_risk, consensus,
                   spot_flow, leverage_pos, options_struct, mean_reversion,
                   btc_price_at_signal, correct
            FROM signals
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC""",
    )


def load_latest_signal(db_path: str) -> dict[str, Any] | None:
    """Load the most recent signal.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.

    Returns:
        Latest signal dict or None if no signals.
    """
    rows = query(
        db_path,
        """SELECT final_score, bias, strength, confidence, regime, event_risk,
                  spot_flow, leverage_pos, options_struct, mean_reversion
           FROM signals ORDER BY timestamp DESC LIMIT 1""",
    )
    return rows[0] if rows else None


def load_gex_data(db_path: str) -> list[dict[str, Any]]:
    """Load latest GEX data by strike.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.

    Returns:
        List of GEX dicts ordered by strike ascending.
    """
    rows = query(
        db_path,
        """SELECT date, strike, call_gex, put_gex, net_gex, gamma_flip_price
           FROM gex_data
           WHERE date = (SELECT MAX(date) FROM gex_data)
           ORDER BY strike ASC""",
    )
    return rows


def load_options_oi(db_path: str) -> list[dict[str, Any]]:
    """Load latest options OI data.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.

    Returns:
        List of options OI dicts.
    """
    return query(
        db_path,
        """SELECT date, expiry, strike, call_oi, put_oi, call_iv, put_iv
           FROM options_oi
           WHERE date = (SELECT MAX(date) FROM options_oi)
           ORDER BY strike ASC""",
    )


def load_spot_prices(db_path: str, days: int = 30) -> list[dict[str, Any]]:
    """Load spot price history for candlestick chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.
        days: Lookback window in days.

    Returns:
        List of OHLCV dicts ordered by timestamp ascending.
    """
    return query(
        db_path,
        f"""SELECT timestamp, open, high, low, close, volume
            FROM spot_price
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC""",
    )


def load_confluence_zones(db_path: str) -> list[dict[str, Any]]:
    """Load latest confluence zone levels.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.

    Returns:
        List of level outcome dicts.
    """
    return query(
        db_path,
        """SELECT date, level_price, level_type, strength, components
           FROM level_outcomes
           WHERE date = (SELECT MAX(date) FROM level_outcomes)
           ORDER BY level_price ASC""",
    )


def load_futures_data(db_path: str, days: int = 30) -> list[dict[str, Any]]:
    """Load futures snapshot history.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.
        days: Lookback window in days.

    Returns:
        List of futures snapshot dicts ordered by timestamp ascending.
    """
    return query(
        db_path,
        f"""SELECT timestamp, funding_binance, funding_bybit, funding_okx,
                   funding_weighted_avg,
                   oi_total_usd, basis_pct,
                   top_trader_ls_ratio, global_ls_ratio
            FROM futures_snapshot
            WHERE timestamp >= datetime('now', '-{days} days')
            ORDER BY timestamp ASC""",
    )


def load_performance(db_path: str, days: int = 30) -> dict[str, Any]:
    """Load all performance metrics for the Performance tab.

    See docs/sub-specs/SS-23.md §13

    Args:
        db_path: Path to SQLite database.
        days: Rolling window in days.

    Returns:
        Dict with win_rate, component_accuracy, regime_accuracy.
    """
    return {
        "win_rate": compute_win_rate(db_path, days=days),
        "component_accuracy": compute_component_accuracy(db_path, days=days),
        "regime_accuracy": compute_regime_accuracy(db_path, days=days),
    }


# ── Chart builders ──────────────────────────────────────────


def build_score_gauge(score: float, bias: str) -> go.Figure:
    """Build a gauge chart for the final composite score.

    See docs/sub-specs/SS-23.md §13

    Args:
        score: Final composite score in [-1, 1].
        bias: Signal bias (LONG, SHORT, NEUTRAL).

    Returns:
        Plotly Figure with gauge indicator.
    """
    color = "#26a69a" if bias == "LONG" else "#ef5350" if bias == "SHORT" else "#78909c"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": f"Final Score ({bias})"},
        gauge={
            "axis": {"range": [-1, 1]},
            "bar": {"color": color},
            "steps": [
                {"range": [-1, -0.35], "color": "#ffcdd2"},
                {"range": [-0.35, 0.35], "color": "#e0e0e0"},
                {"range": [0.35, 1], "color": "#c8e6c9"},
            ],
        },
    ))
    fig.update_layout(height=250, margin={"t": 50, "b": 10, "l": 30, "r": 30})
    return fig


def build_signal_bars(signal: dict[str, Any]) -> go.Figure:
    """Build bar chart for individual signal components.

    See docs/sub-specs/SS-23.md §13

    Args:
        signal: Latest signal dict with component scores.

    Returns:
        Plotly Figure with horizontal bar chart.
    """
    names = ["Spot Flow", "Leverage", "Options", "Mean Rev"]
    keys = ["spot_flow", "leverage_pos", "options_struct", "mean_reversion"]
    values = [signal.get(k, 0) or 0 for k in keys]
    colors = ["#26a69a" if v > 0 else "#ef5350" for v in values]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker_color=colors, text=[f"{v:.2f}" for v in values], textposition="auto",
    ))
    fig.update_layout(
        title="Signal Components",
        xaxis={"range": [-1, 1], "title": "Score"},
        height=250, margin={"t": 40, "b": 30, "l": 80, "r": 20},
    )
    return fig


def build_signal_history(signals: list[dict[str, Any]]) -> go.Figure:
    """Build 30-day signal history line chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        signals: List of signal dicts with timestamp and final_score.

    Returns:
        Plotly Figure with line chart.
    """
    timestamps = [s["timestamp"] for s in signals]
    scores = [s["final_score"] for s in signals]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=scores, mode="lines+markers",
        name="Final Score", line={"color": "#1e88e5"},
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Signal History (30 days)",
        yaxis={"range": [-1, 1], "title": "Score"},
        xaxis={"title": "Time"},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_gex_chart(gex_data: list[dict[str, Any]]) -> go.Figure:
    """Build GEX by strike bar chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        gex_data: List of GEX dicts with strike and net_gex.

    Returns:
        Plotly Figure with bar chart.
    """
    strikes = [g["strike"] for g in gex_data]
    net_gex = [g["net_gex"] for g in gex_data]
    colors = ["#26a69a" if v > 0 else "#ef5350" for v in net_gex]

    fig = go.Figure(go.Bar(x=strikes, y=net_gex, marker_color=colors))

    # Overlay gamma flip line if available
    gamma_flip = next((g["gamma_flip_price"] for g in gex_data if g.get("gamma_flip_price")), None)
    if gamma_flip:
        fig.add_vline(x=gamma_flip, line_dash="dash", line_color="orange",
                       annotation_text=f"Gamma Flip: ${gamma_flip:,.0f}")

    fig.update_layout(
        title="GEX by Strike",
        xaxis={"title": "Strike Price"},
        yaxis={"title": "Net GEX"},
        height=400, margin={"t": 40, "b": 30},
    )
    return fig


def build_oi_heatmap(oi_data: list[dict[str, Any]]) -> go.Figure:
    """Build options OI heatmap by strike.

    See docs/sub-specs/SS-23.md §13

    Args:
        oi_data: List of options OI dicts.

    Returns:
        Plotly Figure with grouped bar chart of call/put OI.
    """
    strikes = [str(int(o["strike"])) for o in oi_data]
    call_oi = [o.get("call_oi", 0) or 0 for o in oi_data]
    put_oi = [o.get("put_oi", 0) or 0 for o in oi_data]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=strikes, y=call_oi, name="Call OI", marker_color="#26a69a"))
    fig.add_trace(go.Bar(x=strikes, y=put_oi, name="Put OI", marker_color="#ef5350"))
    fig.update_layout(
        title="Options Open Interest by Strike",
        barmode="group",
        xaxis={"title": "Strike", "tickangle": -45},
        yaxis={"title": "Open Interest"},
        height=400, margin={"t": 40, "b": 60},
    )
    return fig


def build_candlestick(prices: list[dict[str, Any]],
                      zones: list[dict[str, Any]]) -> go.Figure:
    """Build candlestick chart with confluence zones overlaid.

    See docs/sub-specs/SS-23.md §13

    Args:
        prices: List of OHLCV dicts.
        zones: List of confluence zone dicts.

    Returns:
        Plotly Figure with candlestick and horizontal zone bands.
    """
    fig = go.Figure(go.Candlestick(
        x=[p["timestamp"] for p in prices],
        open=[p["open"] for p in prices],
        high=[p["high"] for p in prices],
        low=[p["low"] for p in prices],
        close=[p["close"] for p in prices],
        name="BTC/USDT",
    ))

    for zone in zones:
        price = zone["level_price"]
        width_pct = 0.5  # ±0.5% zone width
        upper = price * (1 + width_pct / 100)
        lower = price * (1 - width_pct / 100)
        color = "rgba(38, 166, 154, 0.15)" if zone["level_type"] == "support" else "rgba(239, 83, 80, 0.15)"
        fig.add_hrect(y0=lower, y1=upper, fillcolor=color, line_width=0,
                      annotation_text=f"${price:,.0f} ({zone['strength']})")

    fig.update_layout(
        title="BTC/USDT with Confluence Zones",
        xaxis_rangeslider_visible=False,
        height=500, margin={"t": 40, "b": 30},
    )
    return fig


def build_funding_chart(futures: list[dict[str, Any]]) -> go.Figure:
    """Build multi-exchange funding rate chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        futures: List of futures snapshot dicts.

    Returns:
        Plotly Figure with funding rate lines per exchange.
    """
    timestamps = [f["timestamp"] for f in futures]

    fig = go.Figure()
    for name, key, color in [
        ("Binance", "funding_binance", "#f0b90b"),
        ("Bybit", "funding_bybit", "#f7a600"),
        ("OKX", "funding_okx", "#1e88e5"),
    ]:
        values = [f.get(key) for f in futures]
        fig.add_trace(go.Scatter(x=timestamps, y=values, name=name, line={"color": color}))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Funding Rates by Exchange",
        yaxis={"title": "Funding Rate (%)"},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_oi_chart(futures: list[dict[str, Any]]) -> go.Figure:
    """Build total OI chart over time.

    See docs/sub-specs/SS-23.md §13

    Args:
        futures: List of futures snapshot dicts.

    Returns:
        Plotly Figure with OI line chart.
    """
    fig = go.Figure(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("oi_total_usd", 0) for f in futures],
        mode="lines", name="Total OI",
        line={"color": "#7e57c2"},
    ))
    fig.update_layout(
        title="Total Open Interest (USD)",
        yaxis={"title": "OI (USD)"},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_basis_chart(futures: list[dict[str, Any]]) -> go.Figure:
    """Build basis (futures premium) chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        futures: List of futures snapshot dicts.

    Returns:
        Plotly Figure with basis line chart.
    """
    fig = go.Figure(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("basis_pct", 0) for f in futures],
        mode="lines", name="Basis %",
        line={"color": "#ff7043"},
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Futures Basis (%)",
        yaxis={"title": "Basis (%)"},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_ls_ratio_chart(futures: list[dict[str, Any]]) -> go.Figure:
    """Build L/S ratio chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        futures: List of futures snapshot dicts.

    Returns:
        Plotly Figure with L/S ratio line chart.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("top_trader_ls_ratio", 0) for f in futures],
        mode="lines", name="Top Trader L/S",
        line={"color": "#26a69a"},
    ))
    fig.add_trace(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("global_ls_ratio", 0) for f in futures],
        mode="lines", name="Global L/S",
        line={"color": "#78909c"},
    ))
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Long/Short Ratio",
        yaxis={"title": "L/S Ratio"},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_win_rate_chart(signals: list[dict[str, Any]]) -> go.Figure:
    """Build rolling win rate over time chart.

    See docs/sub-specs/SS-23.md §13

    Computes a cumulative win rate at each evaluated signal.

    Args:
        signals: List of signal dicts with correct field.

    Returns:
        Plotly Figure with win rate line chart.
    """
    evaluated = [s for s in signals if s.get("correct") is not None]
    if not evaluated:
        fig = go.Figure()
        fig.update_layout(title="Win Rate Over Time", height=350,
                          annotations=[{"text": "No evaluated signals yet",
                                        "showarrow": False, "font": {"size": 16}}])
        return fig

    timestamps = []
    rates = []
    wins = 0
    for i, s in enumerate(evaluated):
        wins += s["correct"]
        timestamps.append(s["timestamp"])
        rates.append(wins / (i + 1) * 100)

    fig = go.Figure(go.Scatter(
        x=timestamps, y=rates, mode="lines",
        name="Win Rate %", line={"color": "#26a69a"},
    ))
    fig.add_hline(y=50, line_dash="dash", line_color="red", opacity=0.5,
                  annotation_text="50%")
    fig.update_layout(
        title="Cumulative Win Rate Over Time",
        yaxis={"title": "Win Rate (%)", "range": [0, 100]},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_regime_accuracy_chart(regime_data: dict[str, dict[str, Any]]) -> go.Figure:
    """Build regime accuracy bar chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        regime_data: Dict mapping regime name to {win_rate, total, insufficient_data}.

    Returns:
        Plotly Figure with bar chart.
    """
    if not regime_data:
        fig = go.Figure()
        fig.update_layout(title="Accuracy by Regime", height=350,
                          annotations=[{"text": "No regime data yet",
                                        "showarrow": False, "font": {"size": 16}}])
        return fig

    regimes = list(regime_data.keys())
    rates = [regime_data[r]["win_rate"] for r in regimes]
    totals = [regime_data[r]["total"] for r in regimes]
    text = [f"{r:.0f}% (n={n})" for r, n in zip(rates, totals)]

    fig = go.Figure(go.Bar(
        x=regimes, y=rates, text=text, textposition="auto",
        marker_color=["#26a69a" if r >= 50 else "#ef5350" for r in rates],
    ))
    fig.add_hline(y=50, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Win Rate by Market Regime",
        yaxis={"title": "Win Rate (%)", "range": [0, 100]},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


def build_component_accuracy_chart(comp_data: dict[str, float]) -> go.Figure:
    """Build component accuracy (correlation) bar chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        comp_data: Dict mapping signal name to correlation coefficient.

    Returns:
        Plotly Figure with bar chart.
    """
    names = {"spot_flow": "Spot Flow", "leverage_pos": "Leverage",
             "options_struct": "Options", "mean_reversion": "Mean Rev"}
    labels = [names.get(k, k) for k in comp_data]
    values = list(comp_data.values())
    colors = ["#26a69a" if v > 0 else "#ef5350" for v in values]

    fig = go.Figure(go.Bar(
        x=labels, y=values, marker_color=colors,
        text=[f"{v:.3f}" for v in values], textposition="auto",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        title="Component Accuracy (Correlation with 24h Outcome)",
        yaxis={"title": "Correlation", "range": [-1, 1]},
        height=350, margin={"t": 40, "b": 30},
    )
    return fig


# ── Main app ────────────────────────────────────────────────


def main() -> None:
    """Main Streamlit application entry point.

    See docs/sub-specs/SS-23.md §13
    """
    st.set_page_config(page_title="Crypto Signal Bot", layout="wide")
    st.title("Crypto Signal Bot Dashboard")

    config = load_config()
    dash_cfg = config.get("dashboard", {})
    db_path = config.get("general", {}).get("database_path", "data/signals.db")
    lookback = dash_cfg.get("lookback_days", 30)

    tab_signals, tab_options, tab_levels, tab_futures, tab_perf = st.tabs(
        ["Signals", "Options/GEX", "Price Levels", "Futures", "Performance"]
    )

    # ── Signals Tab ──
    with tab_signals:
        latest = load_latest_signal(db_path)
        if latest:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(build_score_gauge(latest["final_score"], latest["bias"]),
                                use_container_width=True)
            with col2:
                st.plotly_chart(build_signal_bars(latest), use_container_width=True)

            st.markdown(f"**Regime:** {latest['regime']} | **Strength:** {latest['strength']} | "
                        f"**Confidence:** {latest['confidence']} | **Event Risk:** {latest['event_risk']:.2f}")

            signals = load_signals(db_path, days=lookback)
            if signals:
                st.plotly_chart(build_signal_history(signals), use_container_width=True)
            else:
                st.info("No signal history available.")
        else:
            st.info("No signals generated yet. Run the bot to start collecting data.")

    # ── Options/GEX Tab ──
    with tab_options:
        gex = load_gex_data(db_path)
        if gex:
            st.plotly_chart(build_gex_chart(gex), use_container_width=True)
        else:
            st.info("No GEX data available.")

        oi = load_options_oi(db_path)
        if oi:
            st.plotly_chart(build_oi_heatmap(oi), use_container_width=True)
        else:
            st.info("No options OI data available.")

    # ── Price Levels Tab ──
    with tab_levels:
        prices = load_spot_prices(db_path, days=lookback)
        zones = load_confluence_zones(db_path)
        if prices:
            st.plotly_chart(build_candlestick(prices, zones), use_container_width=True)
        else:
            st.info("No price data available.")

        if zones:
            st.subheader("Confluence Zones")
            st.dataframe([{
                "Price": f"${z['level_price']:,.0f}",
                "Type": z["level_type"],
                "Strength": z["strength"],
                "Components": z.get("components", ""),
            } for z in zones])
        else:
            st.info("No confluence zones detected.")

    # ── Futures Tab ──
    with tab_futures:
        futures = load_futures_data(db_path, days=lookback)
        if futures:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(build_funding_chart(futures), use_container_width=True)
            with col2:
                st.plotly_chart(build_oi_chart(futures), use_container_width=True)

            col3, col4 = st.columns(2)
            with col3:
                st.plotly_chart(build_basis_chart(futures), use_container_width=True)
            with col4:
                st.plotly_chart(build_ls_ratio_chart(futures), use_container_width=True)
        else:
            st.info("No futures data available.")

    # ── Performance Tab ──
    with tab_perf:
        perf_days = dash_cfg.get("performance_window_days", 30)
        perf = load_performance(db_path, days=perf_days)

        wr = perf["win_rate"]
        col1, col2, col3 = st.columns(3)
        col1.metric("Win Rate", f"{wr['win_rate']:.1f}%")
        col2.metric("Wins / Losses", f"{wr['wins']} / {wr['losses']}")
        col3.metric("Total Signals", wr["total"])

        if wr["insufficient_data"]:
            st.warning(f"Insufficient data for reliable statistics ({wr['total']}/30 minimum signals)")

        signals = load_signals(db_path, days=perf_days)
        st.plotly_chart(build_win_rate_chart(signals), use_container_width=True)

        col5, col6 = st.columns(2)
        with col5:
            st.plotly_chart(build_regime_accuracy_chart(perf["regime_accuracy"]),
                            use_container_width=True)
        with col6:
            st.plotly_chart(build_component_accuracy_chart(perf["component_accuracy"]),
                            use_container_width=True)


if __name__ == "__main__":
    main()
