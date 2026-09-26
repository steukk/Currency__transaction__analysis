from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_RATES_PATH = ROOT / "data" / "raw" / "daily_forex_rates.csv"
OUTPUT_PATH = ROOT / "data" / "synthetic_deals.csv"
PROCESSED_DIR = ROOT / "data" / "processed"

LIQUID_CURRENCIES = [
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "CHF",
    "CAD",
    "AUD",
    "NZD",
    "CNY",
    "HKD",
    "SGD",
    "NOK",
    "SEK",
    "DKK",
    "PLN",
    "CZK",
    "TRY",
    "MXN",
    "ZAR",
]

SEGMENTS = ["large_corporate", "mid_corporate", "financial_institution", "sme"]
CHANNELS = ["email", "phone", "e_fx_portal", "messenger"]
EXCEPTIONS = [
    "none",
    "limit_delay",
    "incomplete_ssi",
    "manual_reentry_error",
    "late_confirmation",
    "settlement_fail",
    "duplicate_request",
]
REJECTION_REASONS = ["none", "insufficient_limit", "expired_quote", "compliance_block", "client_declined"]


def load_market_rates(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Kaggle file not found: {path}. Run: "
            "kaggle datasets download -d asaniczka/forex-exchange-rate-since-2004-updated-daily -p data\\raw --unzip"
        )

    rates = pd.read_csv(path, parse_dates=["date"])
    rates = rates[
        rates["base_currency"].isin(["USD", "EUR"])
        & rates["currency"].isin(LIQUID_CURRENCIES)
        & (rates["currency"] != rates["base_currency"])
        & rates["exchange_rate"].notna()
        & (rates["exchange_rate"] > 0)
    ].copy()
    rates["currency_pair"] = rates["base_currency"] + "/" + rates["currency"]
    rates = rates.sort_values("date", ascending=False).reset_index(drop=True)

    if rates.empty:
        raise ValueError("No usable FX rates found after filtering the Kaggle dataset.")
    return rates


def add_minutes(series: pd.Series, minutes: np.ndarray) -> pd.Series:
    return series + pd.to_timedelta(minutes, unit="m")


def weighted_choice(rng: np.random.Generator, values: list[str], weights: list[float], rows: int) -> np.ndarray:
    return rng.choice(values, size=rows, p=np.array(weights) / np.sum(weights))


def build_deals(rates: pd.DataFrame, rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sampled = rates.sample(n=rows, replace=True, random_state=seed).reset_index(drop=True)

    request_dates = sampled["date"].dt.normalize()
    business_minute = rng.integers(8 * 60, 18 * 60, size=rows)
    request_time = request_dates + pd.to_timedelta(business_minute, unit="m")

    segment = weighted_choice(rng, SEGMENTS, [0.34, 0.38, 0.12, 0.16], rows)
    channel = weighted_choice(rng, CHANNELS, [0.33, 0.25, 0.28, 0.14], rows)
    buy_sell = weighted_choice(rng, ["buy", "sell"], [0.52, 0.48], rows)

    manual_flag = rng.random(rows) < np.select(
        [channel == "e_fx_portal", channel == "email", channel == "phone"],
        [0.18, 0.58, 0.72],
        default=0.64,
    )

    exception_type = weighted_choice(
        rng,
        EXCEPTIONS,
        [0.665, 0.095, 0.075, 0.055, 0.05, 0.035, 0.025],
        rows,
    )

    rework_count = rng.poisson(0.15, rows)
    rework_count += np.where(np.isin(exception_type, ["incomplete_ssi", "manual_reentry_error"]), 1, 0)
    rework_count += np.where(exception_type == "duplicate_request", rng.integers(1, 3, rows), 0)

    notional = np.exp(rng.normal(13.5, 1.15, rows)).round(-3)
    notional *= np.select(
        [segment == "large_corporate", segment == "financial_institution", segment == "sme"],
        [3.0, 4.2, 0.35],
        default=1.0,
    )
    notional = np.clip(notional, 10_000, 250_000_000).round(2)

    quote_delay = rng.gamma(2.0, 3.0, rows) + np.where(manual_flag, rng.gamma(1.8, 4.0, rows), 0)
    accept_delay = rng.gamma(2.4, 6.0, rows) + np.where(exception_type == "late_confirmation", rng.gamma(5, 18, rows), 0)
    limit_delay = rng.gamma(2.0, 5.0, rows) + np.where(exception_type == "limit_delay", rng.gamma(6, 14, rows), 0)
    capture_delay = rng.gamma(1.8, 4.0, rows) + np.where(manual_flag, rng.gamma(2.2, 6.5, rows), 0)
    confirmation_delay = rng.gamma(2.1, 8.0, rows) + np.where(exception_type == "late_confirmation", rng.gamma(4, 20, rows), 0)
    settlement_delay = rng.gamma(2.4, 15.0, rows) + np.where(exception_type == "settlement_fail", rng.gamma(8, 25, rows), 0)
    rework_delay = rework_count * rng.gamma(2.0, 18.0, rows)

    quote_time = add_minutes(request_time, quote_delay)
    client_accept_time = add_minutes(quote_time, accept_delay)
    limit_check_time = add_minutes(client_accept_time, limit_delay)
    trade_capture_time = add_minutes(limit_check_time, capture_delay + rework_delay)
    confirmation_time = add_minutes(trade_capture_time, confirmation_delay)
    settlement_time = add_minutes(confirmation_time, settlement_delay)

    rejected = rng.random(rows) < np.select(
        [
            exception_type == "limit_delay",
            exception_type == "duplicate_request",
            exception_type == "none",
        ],
        [0.12, 0.08, 0.018],
        default=0.045,
    )
    failed = (exception_type == "settlement_fail") & (rng.random(rows) < 0.36)
    cancelled = (exception_type == "late_confirmation") & (rng.random(rows) < 0.08)

    status = np.where(rejected, "rejected", np.where(failed, "settlement_failed", np.where(cancelled, "cancelled", "settled")))
    rejection_reason = np.where(
        rejected,
        weighted_choice(rng, REJECTION_REASONS[1:], [0.54, 0.18, 0.12, 0.16], rows),
        "none",
    )

    total_minutes = (settlement_time - request_time).dt.total_seconds() / 60
    sla_minutes = np.select(
        [segment == "large_corporate", segment == "financial_institution", segment == "sme"],
        [180, 150, 360],
        default=240,
    )
    sla_breach = total_minutes > sla_minutes
    manual_steps = np.where(manual_flag, rng.integers(3, 8, rows), rng.integers(0, 3, rows)) + rework_count

    deals = pd.DataFrame(
        {
            "deal_id": [f"FXS-{i:07d}" for i in range(1, rows + 1)],
            "client_id": [f"C{v:05d}" for v in rng.integers(1, 950, rows)],
            "client_segment": segment,
            "product_type": "FX Spot",
            "currency_pair": sampled["currency_pair"],
            "buy_sell": buy_sell,
            "notional": notional,
            "exchange_rate": sampled["exchange_rate"].round(6),
            "market_rate_date": sampled["date"].dt.date.astype(str),
            "request_channel": channel,
            "request_time": request_time,
            "quote_time": quote_time,
            "client_accept_time": client_accept_time,
            "limit_check_time": limit_check_time,
            "trade_capture_time": trade_capture_time,
            "confirmation_time": confirmation_time,
            "settlement_time": settlement_time,
            "deal_status": status,
            "manual_processing_flag": manual_flag,
            "manual_steps_count": manual_steps,
            "rework_count": rework_count,
            "exception_type": exception_type,
            "rejection_reason": rejection_reason,
            "sla_minutes": sla_minutes,
            "sla_breach": sla_breach,
        }
    )

    time_cols = [c for c in deals.columns if c.endswith("_time")]
    for col in time_cols:
        deals[col] = deals[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    return deals


def write_data_dictionary() -> None:
    dictionary = pd.DataFrame(
        [
            ("deal_id", "Synthetic unique identifier of the OTC FX Spot deal"),
            ("client_id", "Synthetic corporate client identifier"),
            ("client_segment", "Client segment used for SLA and notional distribution"),
            ("product_type", "FX product type, restricted to FX Spot in v1"),
            ("currency_pair", "Currency pair derived from Kaggle market rates"),
            ("buy_sell", "Client direction from the bank perspective"),
            ("notional", "Deal amount in base currency"),
            ("exchange_rate", "Market exchange rate from Kaggle dataset"),
            ("market_rate_date", "Date of the market rate observation"),
            ("request_channel", "Client request channel"),
            ("*_time", "Synthetic process timestamp"),
            ("deal_status", "Final synthetic processing status"),
            ("manual_processing_flag", "Whether the deal required manual processing"),
            ("manual_steps_count", "Synthetic count of manual actions"),
            ("rework_count", "Synthetic number of returns to correction"),
            ("exception_type", "Synthetic operational exception category"),
            ("rejection_reason", "Reason for rejected deals"),
            ("sla_minutes", "Target SLA threshold in minutes"),
            ("sla_breach", "Whether total processing time exceeded SLA"),
        ],
        columns=["field", "description"],
    )
    dictionary.to_csv(PROCESSED_DIR / "data_dictionary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    rates = load_market_rates(RAW_RATES_PATH)
    deals = build_deals(rates, args.rows, args.seed)

    rates.sample(n=min(50_000, len(rates)), random_state=args.seed).to_csv(
        PROCESSED_DIR / "market_rates_sample.csv", index=False
    )
    deals.to_csv(OUTPUT_PATH, index=False)
    write_data_dictionary()

    print(f"Wrote {len(deals):,} deals to {OUTPUT_PATH}")
    print(f"Kaggle market observations available: {len(rates):,}")
    print(f"SLA breach rate: {deals['sla_breach'].mean():.1%}")
    print(f"Manual processing rate: {deals['manual_processing_flag'].mean():.1%}")


if __name__ == "__main__":
    main()

