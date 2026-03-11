const BASE_URL = "/api";

export async function fetchApi<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ---------- Types ----------

export interface Signal {
  timestamp: string;
  final_score: number;
  bias: string;
  strength: string;
  regime: string;
  event_risk: number;
  spot_flow: number;
  leverage_pos: number;
  options_struct: number;
  mean_reversion: number;
  btc_price_at_signal: number;
  weights_json: string;
}

export interface OHLCV {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface GexStrike {
  strike: number;
  call_gex: number;
  put_gex: number;
  net_gex: number;
  gamma_flip_price: number;
}

export interface OiStrike {
  strike: number;
  call_oi: number;
  put_oi: number;
  call_iv: number | null;
  put_iv: number | null;
  expiry: string;
}

export interface FuturesSnapshot {
  timestamp: string;
  funding_binance: number;
  funding_bybit: number;
  funding_okx: number;
  funding_weighted_avg: number;
  oi_total_usd: number;
  basis_pct: number;
  top_trader_ls_ratio: number;
  taker_buy_sell_ratio: number;
}

export interface RiskBreakdown {
  final: number;
  components: {
    options_expiry: number;
    liquidation: number;
    gamma_flip: number;
    dvol: number;
    macro: number;
  };
}

export interface MacroEvent {
  date: string;
  time_utc: string;
  event: string;
  tier: number;
  forecast: number | null;
  actual: number | null;
  previous: number | null;
  source: string;
  hours_until: number | null;
}

export interface Performance {
  win_rate: {
    win_rate: number;
    wins: number;
    losses: number;
    total: number;
  };
  component_accuracy: {
    spot_flow: number;
    leverage_pos: number;
    options_struct: number;
    mean_reversion: number;
  };
  regime_accuracy: Record<string, number>;
}

export interface HealthInfo {
  status: string;
  uptime_seconds: number;
  last_signal: string;
  collectors: Record<string, { status: string; last_success: string }>;
}

export interface DailySnapshot {
  fear_greed: number;
  dvol: number;
  regime: string;
  btc_price: number;
}

export interface Technicals {
  rsi_14: number;
  ema_21: number;
  ema_55: number;
  ema_200: number;
  adx_14: number;
  bb_upper: number;
  bb_lower: number;
  vwap: number;
}
