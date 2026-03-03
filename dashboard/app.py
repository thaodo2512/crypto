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

# ── Theme constants ────────────────────────────────────────

BG_PRIMARY = "#0a0e17"
BG_CARD = "#111827"
BG_SURFACE = "#1a2035"
BORDER = "#1e293b"
TEXT_PRIMARY = "#e2e8f0"
TEXT_MUTED = "#64748b"
BULL = "#00d4aa"
BULL_DIM = "rgba(0, 212, 170, 0.15)"
BEAR = "#ff4757"
BEAR_DIM = "rgba(255, 71, 87, 0.15)"
NEUTRAL = "#748ffc"
GOLD = "#f59e0b"
CYAN = "#22d3ee"
PURPLE = "#a78bfa"
ORANGE = "#fb923c"
GRID_COLOR = "rgba(100, 116, 139, 0.12)"

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono, SF Mono, Menlo, monospace", color=TEXT_PRIMARY, size=11),
    xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, showgrid=True),
    yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, showgrid=True),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
    margin=dict(t=40, b=30, l=50, r=20),
    hoverlabel=dict(bgcolor=BG_CARD, font_size=11, font_family="JetBrains Mono, monospace"),
)


# ── Inject custom CSS ──────────────────────────────────────

def inject_css() -> None:
    """Inject custom dark theme CSS into the Streamlit app.

    See docs/sub-specs/SS-23.md §13
    """
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&display=swap');

    :root {
        --bg-primary: #0a0e17;
        --bg-card: #111827;
        --bg-surface: #1a2035;
        --border: #1e293b;
        --text-primary: #e2e8f0;
        --text-muted: #64748b;
        --bull: #00d4aa;
        --bear: #ff4757;
        --gold: #f59e0b;
        --cyan: #22d3ee;
    }

    .stApp {
        background: linear-gradient(145deg, #0a0e17 0%, #0f1629 50%, #0a0e17 100%);
        font-family: 'Outfit', sans-serif;
    }

    /* Header */
    .dashboard-header {
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.8), rgba(26, 32, 53, 0.6));
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 28px 36px;
        margin-bottom: 24px;
        backdrop-filter: blur(20px);
        position: relative;
        overflow: hidden;
    }
    .dashboard-header::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, var(--bull), var(--cyan), var(--gold));
    }
    .dashboard-header h1 {
        font-family: 'Outfit', sans-serif;
        font-weight: 800;
        font-size: 1.8rem;
        color: #f1f5f9;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .dashboard-header .subtitle {
        font-family: 'JetBrains Mono', monospace;
        color: var(--text-muted);
        font-size: 0.78rem;
        margin-top: 6px;
        letter-spacing: 0.5px;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, var(--bg-card), var(--bg-surface));
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px 24px;
        text-align: center;
        position: relative;
        overflow: hidden;
        transition: border-color 0.2s;
    }
    .metric-card:hover { border-color: rgba(100, 116, 139, 0.4); }
    .metric-card .label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.65rem;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 8px;
    }
    .metric-card .value {
        font-family: 'Outfit', sans-serif;
        font-size: 1.7rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    .metric-card .sub {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        color: var(--text-muted);
        margin-top: 4px;
    }
    .metric-card.bull { border-left: 3px solid var(--bull); }
    .metric-card.bull .value { color: var(--bull); }
    .metric-card.bear { border-left: 3px solid var(--bear); }
    .metric-card.bear .value { color: var(--bear); }
    .metric-card.neutral { border-left: 3px solid var(--cyan); }
    .metric-card.neutral .value { color: var(--cyan); }
    .metric-card.gold { border-left: 3px solid var(--gold); }
    .metric-card.gold .value { color: var(--gold); }

    /* Signal badge */
    .signal-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1px;
    }
    .signal-badge.long { background: rgba(0, 212, 170, 0.15); color: var(--bull); border: 1px solid rgba(0, 212, 170, 0.3); }
    .signal-badge.short { background: rgba(255, 71, 87, 0.15); color: var(--bear); border: 1px solid rgba(255, 71, 87, 0.3); }
    .signal-badge.neutral-badge { background: rgba(116, 143, 252, 0.15); color: #748ffc; border: 1px solid rgba(116, 143, 252, 0.3); }

    /* Info strip */
    .info-strip {
        display: flex;
        gap: 24px;
        padding: 14px 20px;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        margin: 16px 0;
        flex-wrap: wrap;
    }
    .info-strip .item {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
    }
    .info-strip .item-label { color: var(--text-muted); }
    .info-strip .item-value { color: var(--text-primary); font-weight: 500; margin-left: 6px; }

    /* Section headers */
    .section-title {
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1.05rem;
        color: var(--text-primary);
        margin: 28px 0 16px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border);
        letter-spacing: -0.3px;
    }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 60px 30px;
        background: linear-gradient(135deg, var(--bg-card), rgba(26, 32, 53, 0.4));
        border: 1px dashed var(--border);
        border-radius: 16px;
        margin: 20px 0;
    }
    .empty-state .icon { font-size: 2.5rem; margin-bottom: 14px; opacity: 0.6; }
    .empty-state .title {
        font-family: 'Outfit', sans-serif;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 8px;
    }
    .empty-state .desc {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: var(--text-muted);
        line-height: 1.7;
    }

    /* Override Streamlit defaults */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: var(--bg-card);
        border-radius: 10px;
        padding: 4px;
        border: 1px solid var(--border);
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        letter-spacing: 0.5px;
        border-radius: 8px;
        padding: 8px 20px;
        color: var(--text-muted);
    }
    .stTabs [aria-selected="true"] {
        background: var(--bg-surface) !important;
        color: var(--text-primary) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] { background: transparent !important; }
    .stTabs [data-baseweb="tab-border"] { display: none; }

    /* Plotly chart containers */
    .stPlotlyChart { border-radius: 12px; overflow: hidden; }

    /* DataFrame styling */
    .stDataFrame { border-radius: 10px; overflow: hidden; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: var(--bg-card);
        border-right: 1px solid var(--border);
    }

    /* Hide default streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)


# ── HTML helpers ───────────────────────────────────────────

def render_header() -> None:
    """Render the dashboard header with gradient accent.

    See docs/sub-specs/SS-23.md §13
    """
    st.markdown("""
    <div class="dashboard-header">
        <h1>CRYPTO SIGNAL BOT</h1>
        <div class="subtitle">BTC/USDT COMPOSITE SIGNAL DASHBOARD</div>
    </div>
    """, unsafe_allow_html=True)


def render_metric(label: str, value: str, style: str = "", sub: str = "") -> str:
    """Return HTML for a styled metric card.

    See docs/sub-specs/SS-23.md §13

    Args:
        label: Metric label.
        value: Metric value.
        style: CSS class modifier (bull, bear, neutral, gold).
        sub: Optional subtitle text.

    Returns:
        HTML string for the metric card.
    """
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f"""
    <div class="metric-card {style}">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {sub_html}
    </div>
    """


def render_empty(icon: str, title: str, desc: str) -> None:
    """Render a styled empty state placeholder.

    See docs/sub-specs/SS-23.md §13

    Args:
        icon: Emoji or text icon.
        title: Empty state title.
        desc: Descriptive text.
    """
    st.markdown(f"""
    <div class="empty-state">
        <div class="icon">{icon}</div>
        <div class="title">{title}</div>
        <div class="desc">{desc}</div>
    </div>
    """, unsafe_allow_html=True)


def render_info_strip(items: list[tuple[str, str]]) -> None:
    """Render a horizontal info strip with label-value pairs.

    See docs/sub-specs/SS-23.md §13

    Args:
        items: List of (label, value) tuples.
    """
    inner = "".join(
        f'<span class="item"><span class="item-label">{lbl}:</span>'
        f'<span class="item-value">{val}</span></span>'
        for lbl, val in items
    )
    st.markdown(f'<div class="info-strip">{inner}</div>', unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Render a styled section title.

    See docs/sub-specs/SS-23.md §13

    Args:
        text: Section title text.
    """
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


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


def _apply_theme(fig: go.Figure, height: int = 350) -> go.Figure:
    """Apply the dark trading terminal theme to a Plotly figure.

    See docs/sub-specs/SS-23.md §13

    Args:
        fig: Plotly figure to style.
        height: Chart height in pixels.

    Returns:
        The styled figure.
    """
    fig.update_layout(**PLOTLY_LAYOUT, height=height)
    return fig


def build_score_gauge(score: float, bias: str) -> go.Figure:
    """Build a gauge chart for the final composite score.

    See docs/sub-specs/SS-23.md §13

    Args:
        score: Final composite score in [-1, 1].
        bias: Signal bias (LONG, SHORT, NEUTRAL).

    Returns:
        Plotly Figure with gauge indicator.
    """
    color = BULL if bias == "LONG" else BEAR if bias == "SHORT" else NEUTRAL
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        number={"font": {"size": 42, "family": "Outfit, sans-serif", "color": color},
                "valueformat": "+.3f"},
        gauge={
            "axis": {"range": [-1, 1], "tickcolor": TEXT_MUTED,
                     "tickfont": {"size": 9, "color": TEXT_MUTED}},
            "bar": {"color": color, "thickness": 0.7},
            "bgcolor": BG_SURFACE,
            "borderwidth": 0,
            "steps": [
                {"range": [-1, -0.6], "color": "rgba(255, 71, 87, 0.25)"},
                {"range": [-0.6, -0.35], "color": "rgba(255, 71, 87, 0.12)"},
                {"range": [-0.35, 0.35], "color": "rgba(100, 116, 139, 0.08)"},
                {"range": [0.35, 0.6], "color": "rgba(0, 212, 170, 0.12)"},
                {"range": [0.6, 1], "color": "rgba(0, 212, 170, 0.25)"},
            ],
            "threshold": {
                "line": {"color": GOLD, "width": 3},
                "thickness": 0.8,
                "value": score,
            },
        },
    ))
    return _apply_theme(fig, height=280)


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
    component_colors = [CYAN, PURPLE, GOLD, ORANGE]
    bar_colors = [component_colors[i] if abs(v) > 0.15 else TEXT_MUTED
                  for i, v in enumerate(values)]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        marker=dict(
            color=bar_colors,
            line=dict(width=0),
        ),
        text=[f"{v:+.2f}" for v in values],
        textposition="auto",
        textfont=dict(size=12, family="JetBrains Mono, monospace"),
    ))
    fig.update_layout(
        xaxis=dict(range=[-1, 1], dtick=0.25,
                   showgrid=True, gridcolor=GRID_COLOR),
        yaxis=dict(showgrid=False),
    )
    fig.add_vline(x=0, line_color=TEXT_MUTED, line_width=1, opacity=0.4)
    return _apply_theme(fig, height=280)


def build_signal_history(signals: list[dict[str, Any]]) -> go.Figure:
    """Build signal history chart with individual component traces overlaid.

    See docs/sub-specs/SS-23.md §13

    Args:
        signals: List of signal dicts with timestamp, final_score, and components.

    Returns:
        Plotly Figure with multi-trace line chart.
    """
    timestamps = [s["timestamp"] for s in signals]

    fig = go.Figure()

    # Component traces (subtle, behind main line)
    components = [
        ("Spot Flow", "spot_flow", CYAN, 1),
        ("Leverage", "leverage_pos", PURPLE, 1),
        ("Options", "options_struct", GOLD, 1),
        ("Mean Rev", "mean_reversion", ORANGE, 1),
    ]
    for name, key, color, width in components:
        values = [s.get(key, 0) or 0 for s in signals]
        fig.add_trace(go.Scatter(
            x=timestamps, y=values,
            mode="lines", name=name,
            line=dict(color=color, width=width, dash="dot"),
            opacity=0.5,
            hovertemplate=f"{name}: %{{y:+.3f}}<extra></extra>",
        ))

    # Final score — bold, on top
    scores = [s["final_score"] for s in signals]
    fig.add_trace(go.Scatter(
        x=timestamps, y=scores,
        mode="lines+markers", name="Final Score",
        line=dict(color="#f1f5f9", width=2.5),
        marker=dict(size=4, color="#f1f5f9"),
        hovertemplate="Final: %{y:+.3f}<extra></extra>",
    ))

    # Shade bull/bear zones
    fig.add_hrect(y0=0.35, y1=1, fillcolor=BULL_DIM, line_width=0)
    fig.add_hrect(y0=-1, y1=-0.35, fillcolor=BEAR_DIM, line_width=0)
    fig.add_hline(y=0, line_color=TEXT_MUTED, line_width=1, line_dash="dash", opacity=0.3)

    fig.update_layout(
        yaxis=dict(range=[-1.05, 1.05], dtick=0.25),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
            font=dict(size=9),
        ),
    )
    return _apply_theme(fig, height=400)


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
    colors = [BULL if v > 0 else BEAR for v in net_gex]

    fig = go.Figure(go.Bar(
        x=strikes, y=net_gex, marker_color=colors,
        marker_line_width=0,
        hovertemplate="Strike: $%{x:,.0f}<br>Net GEX: %{y:,.0f}<extra></extra>",
    ))

    gamma_flip = next((g["gamma_flip_price"] for g in gex_data if g.get("gamma_flip_price")), None)
    if gamma_flip:
        fig.add_vline(x=gamma_flip, line_dash="dash", line_color=GOLD, line_width=2,
                      annotation_text=f"Gamma Flip: ${gamma_flip:,.0f}",
                      annotation_font=dict(color=GOLD, size=10))

    fig.update_layout(
        xaxis=dict(title="Strike Price"),
        yaxis=dict(title="Net GEX"),
    )
    return _apply_theme(fig, height=420)


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
    fig.add_trace(go.Bar(x=strikes, y=call_oi, name="Call OI",
                         marker_color=BULL, marker_line_width=0))
    fig.add_trace(go.Bar(x=strikes, y=put_oi, name="Put OI",
                         marker_color=BEAR, marker_line_width=0))
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Strike", tickangle=-45),
        yaxis=dict(title="Open Interest"),
    )
    return _apply_theme(fig, height=420)


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
        increasing_line_color=BULL,
        decreasing_line_color=BEAR,
        increasing_fillcolor=BULL,
        decreasing_fillcolor=BEAR,
    ))

    for zone in zones:
        price = zone["level_price"]
        width_pct = 0.5
        upper = price * (1 + width_pct / 100)
        lower = price * (1 - width_pct / 100)
        color = BULL_DIM if zone["level_type"] == "support" else BEAR_DIM
        fig.add_hrect(y0=lower, y1=upper, fillcolor=color, line_width=0,
                      annotation_text=f"${price:,.0f} ({zone['strength']})",
                      annotation_font=dict(size=9, color=TEXT_MUTED))

    fig.update_layout(xaxis_rangeslider_visible=False)
    return _apply_theme(fig, height=520)


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
        ("Binance", "funding_binance", GOLD),
        ("Bybit", "funding_bybit", ORANGE),
        ("OKX", "funding_okx", CYAN),
    ]:
        # Raw values are decimals (e.g. 0.0001 = 0.01%), multiply by 100 for %
        values = [(f.get(key) or 0) * 100 for f in futures]
        fig.add_trace(go.Scatter(
            x=timestamps, y=values, name=name,
            line=dict(color=color, width=1.5),
            hovertemplate=f"{name}: %{{y:.4f}}%<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.3)
    fig.update_layout(yaxis=dict(title="Funding Rate (%)"))
    return _apply_theme(fig, height=350)


def build_oi_chart(futures: list[dict[str, Any]]) -> go.Figure:
    """Build total OI chart over time.

    See docs/sub-specs/SS-23.md §13

    Args:
        futures: List of futures snapshot dicts.

    Returns:
        Plotly Figure with OI area chart.
    """
    fig = go.Figure(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("oi_total_usd", 0) for f in futures],
        mode="lines", name="Total OI",
        line=dict(color=PURPLE, width=1.5),
        fill="tozeroy",
        fillcolor="rgba(167, 139, 250, 0.08)",
        hovertemplate="OI: $%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(yaxis=dict(title="OI (USD)"))
    return _apply_theme(fig, height=350)


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
        line=dict(color=ORANGE, width=1.5),
        fill="tozeroy",
        fillcolor="rgba(251, 146, 60, 0.08)",
        hovertemplate="Basis: %{y:.3f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.3)
    fig.update_layout(yaxis=dict(title="Basis (%)"))
    return _apply_theme(fig, height=350)


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
        line=dict(color=BULL, width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=[f["timestamp"] for f in futures],
        y=[f.get("global_ls_ratio", 0) for f in futures],
        mode="lines", name="Global L/S",
        line=dict(color=TEXT_MUTED, width=1.5),
    ))
    fig.add_hline(y=1.0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.3)
    fig.update_layout(yaxis=dict(title="L/S Ratio"))
    return _apply_theme(fig, height=350)


def build_win_rate_chart(signals: list[dict[str, Any]]) -> go.Figure:
    """Build rolling win rate over time chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        signals: List of signal dicts with correct field.

    Returns:
        Plotly Figure with win rate line chart.
    """
    evaluated = [s for s in signals if s.get("correct") is not None]
    if not evaluated:
        fig = go.Figure()
        fig.update_layout(
            annotations=[{
                "text": "Awaiting evaluated signals",
                "showarrow": False,
                "font": {"size": 14, "color": TEXT_MUTED,
                         "family": "JetBrains Mono, monospace"},
            }],
        )
        return _apply_theme(fig, height=350)

    timestamps = []
    rates = []
    wins = 0
    for i, s in enumerate(evaluated):
        wins += s["correct"]
        timestamps.append(s["timestamp"])
        rates.append(wins / (i + 1) * 100)

    fig = go.Figure(go.Scatter(
        x=timestamps, y=rates, mode="lines",
        name="Win Rate %", line=dict(color=BULL, width=2),
        fill="tozeroy", fillcolor="rgba(0, 212, 170, 0.06)",
        hovertemplate="Win Rate: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=50, line_dash="dash", line_color=BEAR, opacity=0.4,
                  annotation_text="50%",
                  annotation_font=dict(color=TEXT_MUTED, size=9))
    fig.update_layout(yaxis=dict(title="Win Rate (%)", range=[0, 100]))
    return _apply_theme(fig, height=350)


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
        fig.update_layout(
            annotations=[{
                "text": "Awaiting regime data",
                "showarrow": False,
                "font": {"size": 14, "color": TEXT_MUTED,
                         "family": "JetBrains Mono, monospace"},
            }],
        )
        return _apply_theme(fig, height=350)

    regimes = list(regime_data.keys())
    rates = [regime_data[r]["win_rate"] for r in regimes]
    totals = [regime_data[r]["total"] for r in regimes]
    colors = [BULL if r >= 50 else BEAR for r in rates]

    fig = go.Figure(go.Bar(
        x=regimes, y=rates,
        text=[f"{r:.0f}% (n={n})" for r, n in zip(rates, totals)],
        textposition="auto",
        textfont=dict(size=10, family="JetBrains Mono, monospace"),
        marker_color=colors, marker_line_width=0,
    ))
    fig.add_hline(y=50, line_dash="dash", line_color=TEXT_MUTED, opacity=0.3)
    fig.update_layout(yaxis=dict(title="Win Rate (%)", range=[0, 100]))
    return _apply_theme(fig, height=350)


def build_component_accuracy_chart(comp_data: dict[str, float]) -> go.Figure:
    """Build component accuracy (correlation) bar chart.

    See docs/sub-specs/SS-23.md §13

    Args:
        comp_data: Dict mapping signal name to correlation coefficient.

    Returns:
        Plotly Figure with bar chart.
    """
    label_map = {"spot_flow": "Spot Flow", "leverage_pos": "Leverage",
                 "options_struct": "Options", "mean_reversion": "Mean Rev"}
    color_map = {"spot_flow": CYAN, "leverage_pos": PURPLE,
                 "options_struct": GOLD, "mean_reversion": ORANGE}
    labels = [label_map.get(k, k) for k in comp_data]
    values = list(comp_data.values())
    colors = [color_map.get(k, TEXT_MUTED) for k in comp_data]

    fig = go.Figure(go.Bar(
        x=labels, y=values, marker_color=colors, marker_line_width=0,
        text=[f"{v:+.3f}" for v in values], textposition="auto",
        textfont=dict(size=11, family="JetBrains Mono, monospace"),
    ))
    fig.add_hline(y=0, line_dash="dash", line_color=TEXT_MUTED, opacity=0.3)
    fig.update_layout(yaxis=dict(title="Correlation", range=[-1, 1]))
    return _apply_theme(fig, height=350)


# ── Main app ────────────────────────────────────────────────


def main() -> None:
    """Main Streamlit application entry point.

    See docs/sub-specs/SS-23.md §13
    """
    st.set_page_config(
        page_title="Crypto Signal Bot",
        page_icon="</>",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_css()
    render_header()

    config = load_config()
    dash_cfg = config.get("dashboard", {})
    db_path = config.get("general", {}).get("database_path", "data/signals.db")
    lookback = dash_cfg.get("lookback_days", 30)

    tab_signals, tab_options, tab_levels, tab_futures, tab_perf = st.tabs([
        "SIGNALS", "OPTIONS / GEX", "PRICE LEVELS", "FUTURES", "PERFORMANCE",
    ])

    # ── Signals Tab ──
    with tab_signals:
        latest = load_latest_signal(db_path)
        if latest:
            bias = latest["bias"]
            score = latest["final_score"]
            badge_class = "long" if bias == "LONG" else "short" if bias == "SHORT" else "neutral-badge"
            score_style = "bull" if bias == "LONG" else "bear" if bias == "SHORT" else "neutral"

            # Top metrics row
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(render_metric(
                    "COMPOSITE SCORE", f"{score:+.3f}", score_style,
                ), unsafe_allow_html=True)
            with c2:
                st.markdown(render_metric(
                    "BIAS",
                    f'<span class="signal-badge {badge_class}">{bias}</span>',
                    "",
                ), unsafe_allow_html=True)
            with c3:
                st.markdown(render_metric(
                    "STRENGTH", latest["strength"], "gold",
                ), unsafe_allow_html=True)
            with c4:
                er = latest["event_risk"]
                er_style = "bear" if er > 0.7 else "gold" if er > 0.4 else "bull"
                st.markdown(render_metric(
                    "EVENT RISK", f"{er:.2f}", er_style,
                ), unsafe_allow_html=True)

            # Info strip
            render_info_strip([
                ("Regime", latest["regime"]),
                ("Confidence", latest["confidence"]),
                ("Spot Flow", f"{latest.get('spot_flow', 0) or 0:+.2f}"),
                ("Leverage", f"{latest.get('leverage_pos', 0) or 0:+.2f}"),
                ("Options", f"{latest.get('options_struct', 0) or 0:+.2f}"),
                ("Mean Rev", f"{latest.get('mean_reversion', 0) or 0:+.2f}"),
            ])

            # Gauge + component bars
            section_title("Signal Breakdown")
            col_g, col_b = st.columns(2)
            with col_g:
                st.plotly_chart(build_score_gauge(score, bias), use_container_width=True)
            with col_b:
                st.plotly_chart(build_signal_bars(latest), use_container_width=True)

            # Signal history with component traces
            signals = load_signals(db_path, days=lookback)
            if signals:
                section_title("Signal History")
                st.plotly_chart(build_signal_history(signals), use_container_width=True)
        else:
            render_empty(
                "</>",
                "Awaiting First Signal",
                "The bot is initializing and collecting market data.<br>"
                "Signals will appear here once the first analysis cycle completes.<br>"
                "This typically takes 15-60 minutes after startup."
            )

    # ── Options/GEX Tab ──
    with tab_options:
        gex = load_gex_data(db_path)
        if gex:
            section_title("Gamma Exposure by Strike")
            st.plotly_chart(build_gex_chart(gex), use_container_width=True)
        else:
            render_empty("<//>", "No GEX Data",
                         "Options data updates every 4 hours.<br>GEX analysis will appear after the first options collection cycle.")

        oi = load_options_oi(db_path)
        if oi:
            section_title("Open Interest Distribution")
            st.plotly_chart(build_oi_heatmap(oi), use_container_width=True)
        else:
            render_empty("</>", "No Options OI Data",
                         "Open interest data will populate alongside GEX data.")

    # ── Price Levels Tab ──
    with tab_levels:
        prices = load_spot_prices(db_path, days=lookback)
        zones = load_confluence_zones(db_path)
        if prices:
            section_title("BTC/USDT Price Action")
            st.plotly_chart(build_candlestick(prices, zones), use_container_width=True)
        else:
            render_empty("</>", "No Price Data",
                         "Price data collection starts immediately on boot.<br>Candles will appear within minutes.")

        if zones:
            section_title("Confluence Zones")
            st.dataframe([{
                "Price": f"${z['level_price']:,.0f}",
                "Type": z["level_type"],
                "Strength": z["strength"],
                "Components": z.get("components", ""),
            } for z in zones], use_container_width=True)

    # ── Futures Tab ──
    with tab_futures:
        futures = load_futures_data(db_path, days=lookback)
        if futures:
            col1, col2 = st.columns(2)
            with col1:
                section_title("Funding Rates")
                st.plotly_chart(build_funding_chart(futures), use_container_width=True)
            with col2:
                section_title("Open Interest")
                st.plotly_chart(build_oi_chart(futures), use_container_width=True)

            col3, col4 = st.columns(2)
            with col3:
                section_title("Futures Basis")
                st.plotly_chart(build_basis_chart(futures), use_container_width=True)
            with col4:
                section_title("Long/Short Ratio")
                st.plotly_chart(build_ls_ratio_chart(futures), use_container_width=True)
        else:
            render_empty("</>", "No Futures Data",
                         "Futures snapshots are collected every 15 minutes.<br>Data will appear after the first collection cycle.")

    # ── Performance Tab ──
    with tab_perf:
        perf_days = dash_cfg.get("performance_window_days", 30)
        perf = load_performance(db_path, days=perf_days)

        wr = perf["win_rate"]

        # Top metrics
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            wr_style = "bull" if wr["win_rate"] >= 50 else "bear"
            st.markdown(render_metric("WIN RATE", f"{wr['win_rate']:.1f}%", wr_style),
                        unsafe_allow_html=True)
        with c2:
            st.markdown(render_metric("WINS", str(wr["wins"]), "bull"),
                        unsafe_allow_html=True)
        with c3:
            st.markdown(render_metric("LOSSES", str(wr["losses"]), "bear"),
                        unsafe_allow_html=True)
        with c4:
            st.markdown(render_metric("TOTAL SIGNALS", str(wr["total"]), "neutral"),
                        unsafe_allow_html=True)

        if wr["insufficient_data"]:
            st.markdown(
                f'<div class="info-strip"><span class="item">'
                f'<span class="item-label">Insufficient data for reliable statistics</span>'
                f'<span class="item-value">({wr["total"]}/30 minimum signals)</span>'
                f'</span></div>',
                unsafe_allow_html=True,
            )

        signals = load_signals(db_path, days=perf_days)
        section_title("Win Rate Over Time")
        st.plotly_chart(build_win_rate_chart(signals), use_container_width=True)

        col5, col6 = st.columns(2)
        with col5:
            section_title("Accuracy by Regime")
            st.plotly_chart(build_regime_accuracy_chart(perf["regime_accuracy"]),
                            use_container_width=True)
        with col6:
            section_title("Component Accuracy")
            st.plotly_chart(build_component_accuracy_chart(perf["component_accuracy"]),
                            use_container_width=True)


if __name__ == "__main__":
    main()
