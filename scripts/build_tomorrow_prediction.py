from __future__ import annotations

import json
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

import pandas as pd

from market_calendar import calendar_control_variables, next_krx_trading_day


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
HISTORY_PATH = REPORTS / "tomorrow_sector_prediction_history.csv"
ACCURACY_LOG_PATH = REPORTS / "prediction_accuracy_log.csv"
INTRADAY_SIGNAL_PATH = REPORTS / "intraday_rebound_signals.csv"
RETURN_BACKTEST_PATH = REPORTS / "sector_model_v2_backtest_predictions.csv"
RANKING_QUALITY_SUMMARY_PATH = REPORTS / "ranking_quality_summary.json"
FOMO_BLEND_RECOMMENDATION_PATH = REPORTS / "fomo_blend_weight_recommendation.json"
RETURN_INTERVAL_COVERAGE_PATH = REPORTS / "expected_return_interval_coverage.csv"
RETURN_INTERVAL_CALIBRATION_SUMMARY_PATH = REPORTS / "return_interval_calibration_summary.json"

ACTION_CORE = "\ud575\uc2ec \uad00\ucc30"
ACTION_AUX = "\ubcf4\uc870 \uad00\ucc30"
ACTION_WATCH = "\uad00\ub9dd"
ACTION_DEFENSIVE = "\ubc29\uc5b4 \uad00\ucc30"
ACTION_AVOID = "\ud68c\ud53c \uc6b0\uc120"
ACTION_NO_TRADE = "\uc2e0\uaddc \uc9c4\uc785 \uae08\uc9c0"
DECISION_POLICY_VERSION = "decision_layer_v9_ranking_quality_soft_gate"
ACTION_PRIORITY = {
    ACTION_NO_TRADE: 0,
    ACTION_AVOID: 0,
    ACTION_WATCH: 1,
    ACTION_DEFENSIVE: 2,
    ACTION_AUX: 3,
    ACTION_CORE: 4,
}
PANIC_REBOUND_REGIMES = {"capitulation", "risk_off_selloff"}

def rank01(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).rank(pct=True)


def numeric_series(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def clip01(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)


def rank_or_default(df: pd.DataFrame, col: str, default: float = 0.5) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    values = pd.to_numeric(df[col], errors="coerce")
    if values.dropna().nunique() <= 1:
        return pd.Series(default, index=df.index, dtype="float64")
    return rank01(values)


def choose_panic_rebound_score_column(df: pd.DataFrame) -> str:
    for column in ["prediction_layer_score", "rank_model_score", "tomorrow_total_score", "final_rank_score_v5"]:
        if column in df.columns and pd.to_numeric(df[column], errors="coerce").notna().any():
            return column
    return "tomorrow_total_score"


def fomo_freshness_weight(df: pd.DataFrame) -> pd.Series:
    if "fomo_final_weight" in df.columns:
        values = pd.to_numeric(df["fomo_final_weight"], errors="coerce")
        fallback = numeric_series(df, "fomo_freshness_weight", 1.0)
        if values.notna().any():
            return values.fillna(fallback).clip(lower=0.0, upper=1.0)
    return numeric_series(df, "fomo_freshness_weight", 1.0).clip(lower=0.0, upper=1.0)


def freshness_adjusted_rank(df: pd.DataFrame, col: str, default: float = 0.5) -> pd.Series:
    rank = rank_or_default(df, col, default)
    weight = fomo_freshness_weight(df)
    return clip01(0.5 + (rank - 0.5) * weight)


def fomo_overlay_score(df: pd.DataFrame) -> pd.Series:
    effect_rank = freshness_adjusted_rank(df, "expected_effect_score")
    weekend_rank = freshness_adjusted_rank(df, "weekend_attention_score")
    return clip01(0.75 * effect_rank + 0.25 * weekend_rank)


def load_fomo_blend_weight() -> tuple[float, str, str, str]:
    if not FOMO_BLEND_RECOMMENDATION_PATH.exists():
        return 0.0, "missing_recommendation", "", ""
    try:
        data = json.loads(FOMO_BLEND_RECOMMENDATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0.0, "invalid_recommendation", "", ""
    weight = data.get("recommended_fomo_overlay_weight", data.get("selected_fomo_overlay_weight", 0.0))
    try:
        weight = float(weight)
    except Exception:
        weight = 0.0
    weight = max(0.0, min(0.40, weight))
    return (
        weight,
        "fomo_blend_weight_recommendation",
        str(data.get("validation_window", "")),
        str(data.get("generated_at", "")),
    )


def apply_fomo_blend_overlay(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    weight, source, validation_window, generated_at = load_fomo_blend_weight()
    base_score = clip01(numeric_series(out, "tomorrow_total_score", 0.0))
    overlay = fomo_overlay_score(out)
    out["tomorrow_total_score_pre_fomo_blend"] = base_score
    out["fomo_overlay_score"] = overlay
    out["fomo_blend_weight"] = weight
    out["fomo_blend_source"] = source
    out["fomo_blend_validation_window"] = validation_window
    out["fomo_blend_generated_at"] = generated_at
    if weight > 0:
        out["tomorrow_total_score"] = clip01((1.0 - weight) * base_score + weight * overlay)
    return out


def primary_return_column(df: pd.DataFrame) -> str:
    if "primary_next_return_pred" in df.columns:
        values = pd.to_numeric(df["primary_next_return_pred"], errors="coerce")
        if values.notna().any() and not values.fillna(0.0).eq(0.0).all():
            return "primary_next_return_pred"
    return "ensemble_v2_next_return_pred"


def primary_rank_model_score(df: pd.DataFrame) -> pd.Series:
    v3 = numeric_series(df, "final_rank_score_v3")
    v4 = numeric_series(df, "final_rank_score_v4")
    v5 = numeric_series(df, "final_rank_score_v5")
    ret_rank = rank_or_default(df, primary_return_column(df))
    quality_rank = rank_or_default(df, "calibrated_quality_adjusted_up_proba")
    effect_rank = freshness_adjusted_rank(df, "expected_effect_score")
    live_rank = rank_or_default(df, "live_fomo_score")

    if "final_rank_score_v5" in df.columns and v5.max() > 0:
        score = 0.30 * v5 + 0.10 * v4 + 0.05 * v3 + 0.28 * ret_rank + 0.22 * quality_rank + 0.05 * effect_rank
    elif "final_rank_score_v4" in df.columns and v4.max() > 0:
        score = 0.28 * v4 + 0.08 * v3 + 0.32 * ret_rank + 0.24 * quality_rank + 0.05 * effect_rank + 0.03 * live_rank
    elif "final_rank_score_v3" in df.columns and v3.max() > 0:
        score = 0.22 * v3 + 0.35 * ret_rank + 0.25 * quality_rank + 0.10 * effect_rank + 0.08 * live_rank
    else:
        score = 0.42 * ret_rank + 0.33 * quality_rank + 0.15 * effect_rank + 0.10 * live_rank
    return clip01(score)


def load_return_interval_calibration() -> dict:
    disabled = {
        "enabled": False,
        "reason": "coverage_log_missing_or_insufficient",
        "rows": 0,
        "target_days": 0,
        "coverage_rate": None,
        "below_lower_rate": None,
        "above_upper_rate": None,
        "lower_padding_pct": 0.0,
        "upper_padding_pct": 0.0,
        "window": "none",
    }
    if not RETURN_INTERVAL_COVERAGE_PATH.exists():
        return disabled
    try:
        frame = pd.read_csv(RETURN_INTERVAL_COVERAGE_PATH, encoding="utf-8-sig")
    except Exception:
        disabled["reason"] = "coverage_log_read_failed"
        return disabled

    required = {
        "prediction_target_date",
        "interval_lower_pct",
        "interval_upper_pct",
        "actual_sector_return",
        "interval_coverage_hit",
        "interval_below_lower_flag",
        "interval_above_upper_flag",
    }
    if not required.issubset(frame.columns):
        disabled["reason"] = "coverage_log_missing_required_columns"
        return disabled

    frame = frame.copy()
    frame["prediction_target_date"] = pd.to_datetime(frame["prediction_target_date"], errors="coerce")
    for column in [
        "interval_lower_pct",
        "interval_upper_pct",
        "actual_sector_return",
        "interval_coverage_hit",
        "interval_below_lower_flag",
        "interval_above_upper_flag",
        "interval_center_abs_error_pct",
    ]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(
        subset=["prediction_target_date", "interval_lower_pct", "interval_upper_pct", "actual_sector_return"]
    )
    if frame.empty:
        disabled["reason"] = "coverage_log_has_no_valid_rows"
        return disabled

    last_dates = sorted(frame["prediction_target_date"].dropna().unique())[-5:]
    recent = frame[frame["prediction_target_date"].isin(last_dates)].copy()
    if recent["prediction_target_date"].nunique() < 3 or len(recent) < 36:
        disabled.update(
            {
                "reason": "coverage_log_needs_at_least_3_days_and_36_rows",
                "rows": int(len(recent)),
                "target_days": int(recent["prediction_target_date"].nunique()),
            }
        )
        return disabled

    recent["lower_miss_pct"] = (recent["interval_lower_pct"] - recent["actual_sector_return"]).clip(lower=0.0)
    recent["upper_miss_pct"] = (recent["actual_sector_return"] - recent["interval_upper_pct"]).clip(lower=0.0)
    if "interval_center_abs_error_pct" not in recent.columns:
        recent["interval_center_abs_error_pct"] = (
            recent["actual_sector_return"] - (recent["interval_lower_pct"] + recent["interval_upper_pct"]) / 2.0
        ).abs()

    coverage_rate = float(recent["interval_coverage_hit"].mean())
    below_rate = float(recent["interval_below_lower_flag"].mean())
    above_rate = float(recent["interval_above_upper_flag"].mean())
    lower_positive = recent.loc[recent["lower_miss_pct"] > 0, "lower_miss_pct"]
    upper_positive = recent.loc[recent["upper_miss_pct"] > 0, "upper_miss_pct"]
    abs_error = recent["interval_center_abs_error_pct"].dropna()

    lower_padding = 0.0
    if coverage_rate < 0.75 or below_rate > 0.18:
        miss_padding = float(lower_positive.quantile(0.80)) if not lower_positive.empty else 0.0
        error_padding = float(abs_error.quantile(0.70) * 0.25) if not abs_error.empty else 0.0
        lower_padding = max(miss_padding, error_padding, 0.25)
    if below_rate > 0.30 and not abs_error.empty:
        lower_padding = max(lower_padding, float(abs_error.quantile(0.80) * 0.35))

    upper_padding = 0.0
    if above_rate > 0.15:
        miss_padding = float(upper_positive.quantile(0.80)) if not upper_positive.empty else 0.0
        upper_padding = max(miss_padding, 0.20)

    lower_padding = float(min(max(lower_padding, 0.0), 2.50))
    upper_padding = float(min(max(upper_padding, 0.0), 1.50))
    enabled = lower_padding > 0 or upper_padding > 0
    return {
        "enabled": enabled,
        "reason": "recent_interval_miscalibration" if enabled else "coverage_within_tolerance",
        "rows": int(len(recent)),
        "target_days": int(recent["prediction_target_date"].nunique()),
        "date_min": recent["prediction_target_date"].min().strftime("%Y-%m-%d"),
        "date_max": recent["prediction_target_date"].max().strftime("%Y-%m-%d"),
        "coverage_rate": coverage_rate,
        "below_lower_rate": below_rate,
        "above_upper_rate": above_rate,
        "lower_padding_pct": lower_padding,
        "upper_padding_pct": upper_padding,
        "avg_interval_width_pct": float((recent["interval_upper_pct"] - recent["interval_lower_pct"]).mean()),
        "avg_abs_error_pct": float(abs_error.mean()) if not abs_error.empty else None,
        "window": "last_5_evaluated_days",
    }


def apply_return_interval_calibration(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    calibration = load_return_interval_calibration()
    out["return_interval_calibration_enabled"] = bool(calibration.get("enabled"))
    out["return_interval_calibration_reason"] = str(calibration.get("reason", ""))
    out["return_interval_calibration_window"] = str(calibration.get("window", "none"))
    out["return_interval_calibration_coverage_rate"] = calibration.get("coverage_rate")
    out["return_interval_calibration_below_lower_rate"] = calibration.get("below_lower_rate")
    out["return_interval_calibration_base_lower_padding_pct"] = float(calibration.get("lower_padding_pct") or 0.0)
    out["return_interval_calibration_base_upper_padding_pct"] = float(calibration.get("upper_padding_pct") or 0.0)
    if not calibration.get("enabled"):
        RETURN_INTERVAL_CALIBRATION_SUMMARY_PATH.write_text(
            json.dumps(calibration, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return out

    lower_before = numeric_series(out, "expected_return_low_pct", -2.5)
    upper_before = numeric_series(out, "expected_return_high_pct", 2.5)
    error_before = numeric_series(out, "expected_return_error_p80_pct", 2.5)
    out["expected_return_low_pct_raw"] = lower_before
    out["expected_return_high_pct_raw"] = upper_before
    out["expected_return_error_p80_pct_raw"] = error_before

    market_risk = numeric_series(out, "market_regime_risk_v4", 0.50)
    target_gap = numeric_series(out, "target_gap_days", 1.0)
    intraday_bridge = numeric_series(out, "intraday_bridge_score", 0.50)
    risk_multiplier = (
        1.0
        + 0.15 * market_risk.ge(0.75).astype(float)
        + 0.10 * target_gap.ge(3).astype(float)
        + 0.08 * intraday_bridge.lt(0.30).astype(float)
    ).clip(lower=1.0, upper=1.40)

    lower_padding = (float(calibration.get("lower_padding_pct") or 0.0) * risk_multiplier).clip(
        lower=0.0, upper=2.75
    )
    upper_padding = (float(calibration.get("upper_padding_pct") or 0.0) * (0.90 + 0.10 * risk_multiplier)).clip(
        lower=0.0, upper=1.75
    )
    out["return_interval_lower_calibration_padding_pct"] = lower_padding
    out["return_interval_upper_calibration_padding_pct"] = upper_padding
    out["expected_return_low_pct"] = lower_before - lower_padding
    out["expected_return_high_pct"] = upper_before + upper_padding
    out["expected_return_error_p80_pct"] = error_before + (lower_padding + upper_padding) * 0.35

    summary = dict(calibration)
    summary.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "live_prediction_interval_calibration",
            "average_applied_lower_padding_pct": float(lower_padding.mean()),
            "average_applied_upper_padding_pct": float(upper_padding.mean()),
            "max_applied_lower_padding_pct": float(lower_padding.max()),
            "note": "최근 실제 구간 이탈을 이용해 expected_return_low/high를 보수적으로 보정한다.",
        }
    )
    RETURN_INTERVAL_CALIBRATION_SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def add_return_primary_total_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    return_col = primary_return_column(out)
    ret_rank = rank_or_default(out, return_col)
    quality_rank = rank_or_default(out, "calibrated_quality_adjusted_up_proba")
    meaningful = numeric_series(out, "calibrated_meaningful_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    excess = numeric_series(out, "calibrated_excess_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    tradeable = numeric_series(out, "calibrated_tradeable_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    confidence = clip01(numeric_series(out, "expected_return_confidence_score"))
    auxiliary_rank_score = primary_rank_model_score(out)
    effect_rank = freshness_adjusted_rank(out, "expected_effect_score")
    live_rank = rank_or_default(out, "live_fomo_score")
    weekend_rank = freshness_adjusted_rank(out, "weekend_attention_score")
    out["tomorrow_total_score"] = clip01(
        0.28 * ret_rank
        + 0.22 * quality_rank
        + 0.12 * meaningful
        + 0.10 * excess
        + 0.08 * tradeable
        + 0.08 * auxiliary_rank_score
        + 0.05 * confidence
        + 0.04 * effect_rank
        + 0.02 * live_rank
        + 0.01 * weekend_rank
    )
    return out


def next_business_day(date_value: pd.Timestamp) -> pd.Timestamp:
    return next_krx_trading_day(date_value)


def prediction_dates() -> tuple[str, str]:
    latest_path = REPORTS / "sector_model_v2_latest_predictions.csv"
    if latest_path.exists():
        latest = pd.read_csv(latest_path, encoding="utf-8-sig")
        base = pd.to_datetime(latest["date"], errors="coerce").max()
        if not pd.isna(base):
            target = next_business_day(base)
            return base.strftime("%Y-%m-%d"), target.strftime("%Y-%m-%d")
    today = pd.Timestamp.today().normalize()
    return today.strftime("%Y-%m-%d"), next_business_day(today).strftime("%Y-%m-%d")


def append_history(out: pd.DataFrame, base_date: str, target_date: str, controls: dict) -> None:
    hist = out.copy()
    hist.insert(0, "prediction_id", f"{base_date}_to_{target_date}")
    hist.insert(1, "prediction_created_at", datetime.now().isoformat(timespec="seconds"))
    hist.insert(2, "prediction_base_date", base_date)
    hist.insert(3, "prediction_target_date", target_date)
    for col, value in [
        ("market_day_state", controls["market_day_state"]),
        ("collection_mode", controls["collection_mode"]),
        ("prediction_target_state", controls["prediction_target_state"]),
        ("target_gap_days", controls["target_gap_days"]),
    ]:
        if col not in hist.columns:
            hist[col] = value
    if HISTORY_PATH.exists():
        old = pd.read_csv(HISTORY_PATH, encoding="utf-8-sig")
        hist = pd.concat([old, hist], ignore_index=True, sort=False)
        hist = hist.drop_duplicates(["prediction_id", "sector"], keep="last")
    hist.to_csv(HISTORY_PATH, index=False, encoding="utf-8-sig")


def merge_v3(df: pd.DataFrame) -> pd.DataFrame:
    path = REPORTS / "sector_rank_model_v3_latest_predictions.csv"
    if not path.exists():
        return df
    v3 = pd.read_csv(path, encoding="utf-8-sig")
    cols = [
        c
        for c in [
            "sector",
            "final_rank_score_v3",
            "v3_action",
            "top3_proba_v3",
            "bottom3_proba_v3",
            "pred_next_excess_return_v3",
            "risk_penalty_v3",
        ]
        if c in v3.columns
    ]
    return df.merge(v3[cols], on="sector", how="left")


def merge_v4(df: pd.DataFrame) -> pd.DataFrame:
    path = REPORTS / "sector_rank_model_v4_latest_predictions.csv"
    if not path.exists():
        return df
    v4 = pd.read_csv(path, encoding="utf-8-sig")
    cols = [
        c
        for c in [
            "sector",
            "final_rank_score_v4",
            "v4_action",
            "market_regime_v4",
            "market_regime_risk_v4",
            "market_gate_v4",
            "xgb_rank_score_v4",
            "xgb_component_v4",
            "pre_risk_score_v4",
            "sector_risk_penalty_v4",
            "relative_strength_component_v4",
            "breadth_component_v4",
            "controlled_reversal_component_v4",
        ]
        if c in v4.columns
    ]
    return df.merge(v4[cols], on="sector", how="left")


def merge_v5(df: pd.DataFrame) -> pd.DataFrame:
    path = REPORTS / "sector_rank_model_v5_latest_predictions.csv"
    if not path.exists():
        return df
    v5 = pd.read_csv(path, encoding="utf-8-sig")
    cols = [
        c
        for c in [
            "sector",
            "final_rank_score_v5",
            "v5_action",
            "v5_no_trade_reason",
            "v5_no_trade_flag",
            "v5_largecap_only_flag",
            "v5_weak_breadth_flag",
            "v5_attention_overheat_flag",
            "v5_fx_stress_flag",
            "qlib_quality_component_v5",
            "paper_signal_component_v5",
            "paper_attention_score",
            "paper_attention_acceleration",
            "paper_fomo_overheat_score",
            "paper_attention_reversal_pressure",
            "paper_attention_rebound_pressure",
            "paper_fx_expected_impact_1d",
            "paper_fx_stress_score",
            "paper_graph_neighbor_mom_3d",
            "paper_graph_relative_strength",
            "sector_risk_penalty_v5",
            "krx_trade_value_weighted_return",
            "krx_top2_trade_value_weighted_return",
            "krx_top2_trade_value_share",
            "krx_largecap_return_gap",
        ]
        if c in v5.columns
    ]
    return df.merge(v5[cols], on="sector", how="left")


def merge_weekend_effects(df: pd.DataFrame) -> pd.DataFrame:
    path = REPORTS / "weekend_signal_effects.csv"
    if not path.exists():
        for col in [
            "expected_effect_score",
            "expected_effect_score_raw",
            "weekend_attention_score",
            "weekend_attention_score_raw",
            "news_3d",
            "news_momentum",
            "news_decay_score",
            "news_attention_acceleration",
            "attention_reversal_risk",
            "fomo_evidence_weight",
            "fomo_risk_pressure",
            "fomo_risk_discount",
            "fomo_final_weight",
        ]:
            df[col] = 0.0
        df["fomo_freshness_status"] = "missing"
        df["fomo_freshness_weight"] = 0.0
        df["fomo_freshness_reason"] = "weekend_signal_file_missing"
        df["fomo_weight_reason"] = "weekend_signal_file_missing"
        df["fomo_target_date"] = ""
        return df
    weekend = pd.read_csv(path, encoding="utf-8-sig")
    if "fomo_freshness_weight" not in weekend.columns:
        weekend["fomo_freshness_status"] = "legacy_unknown"
        weekend["fomo_freshness_weight"] = 0.35
        weekend["fomo_freshness_reason"] = "legacy_file_without_freshness_metadata"
    _, target_date = prediction_dates()
    if "fomo_target_date" in weekend.columns:
        target_mismatch = weekend["fomo_target_date"].fillna("").astype(str).ne(str(target_date))
        if target_mismatch.any():
            weekend.loc[target_mismatch, "fomo_freshness_status"] = "stale"
            weekend.loc[target_mismatch, "fomo_freshness_weight"] = (
                pd.to_numeric(weekend.loc[target_mismatch, "fomo_freshness_weight"], errors="coerce")
                .fillna(0.15)
                .clip(upper=0.15)
            )
            if "fomo_final_weight" in weekend.columns:
                weekend.loc[target_mismatch, "fomo_final_weight"] = (
                    pd.to_numeric(weekend.loc[target_mismatch, "fomo_final_weight"], errors="coerce")
                    .fillna(0.15)
                    .clip(upper=0.15)
                )
            weekend.loc[target_mismatch, "fomo_freshness_reason"] = "target_date_mismatch"
    cols = [
        c
        for c in [
            "sector",
            "expected_effect_score",
            "expected_effect_score_raw",
            "weekend_attention_score",
            "weekend_attention_score_raw",
            "news_3d",
            "news_momentum",
            "news_decay_score",
            "news_sentiment_decay",
            "news_attention_acceleration",
            "attention_reversal_risk",
            "search_source",
            "fomo_generated_at",
            "fomo_base_date",
            "fomo_target_date",
            "fomo_source_latest_at",
            "fomo_source_age_hours",
            "fomo_freshness_status",
            "fomo_freshness_weight",
            "fomo_freshness_reason",
            "fomo_evidence_weight",
            "fomo_risk_pressure",
            "fomo_risk_discount",
            "fomo_final_weight",
            "fomo_weight_reason",
        ]
        if c in weekend.columns
    ]
    return df.merge(
        weekend[cols],
        on="sector",
        how="left",
    )


def merge_intraday_bridge(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "intraday_rebound_score": 0.5,
        "intraday_continuation_score": 0.5,
        "intraday_reversal_risk": 0.0,
        "intraday_bridge_score": 0.5,
        "intraday_bridge_adjustment": 0.0,
        "intraday_signal_sector_return": pd.NA,
        "intraday_signal_advancers_ratio": pd.NA,
        "intraday_signal_trade_value_rank": pd.NA,
        "intraday_signal_label": "미수집",
    }
    out = df.copy()
    if not INTRADAY_SIGNAL_PATH.exists():
        for col, value in defaults.items():
            out[col] = value
        return out
    try:
        signals = pd.read_csv(INTRADAY_SIGNAL_PATH, encoding="utf-8-sig")
    except Exception:
        for col, value in defaults.items():
            out[col] = value
        return out
    if signals.empty or "sector" not in signals.columns:
        for col, value in defaults.items():
            out[col] = value
        return out

    if "collected_at" in signals.columns:
        signals["collected_at"] = pd.to_datetime(signals["collected_at"], errors="coerce")
        signals = signals.sort_values("collected_at").groupby("sector", as_index=False).tail(1)
    rename_map = {
        "rebound_score": "intraday_rebound_score",
        "sector_intraday_return": "intraday_signal_sector_return",
        "sector_advancers_ratio": "intraday_signal_advancers_ratio",
        "trade_value_rank": "intraday_signal_trade_value_rank",
    }
    keep = [
        "sector",
        "collected_at",
        "rebound_phase",
        "estimated_rebound_window",
        "intraday_signal_label",
        "intraday_continuation_score",
        "intraday_reversal_risk",
        "intraday_bridge_score",
        "intraday_bridge_adjustment",
        "rebound_score",
        "sector_intraday_return",
        "sector_advancers_ratio",
        "trade_value_rank",
    ]
    bridge = signals[[c for c in keep if c in signals.columns]].rename(columns=rename_map)
    out = out.drop(columns=[c for c in bridge.columns if c in out.columns and c != "sector"], errors="ignore")
    out = out.merge(bridge, on="sector", how="left")
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
        out[col] = out[col].fillna(value)
    return out


def numeric_fill(df: pd.DataFrame, cols: list[str], default: float = 0.0) -> None:
    for col in cols:
        if col not in df.columns:
            df[col] = default
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)


def apply_recent_reliability_calibration(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    defaults = {
        "recent_sector_n": 0,
        "recent_sector_hit_rate": pd.NA,
        "recent_sector_avg_return": pd.NA,
        "score_calibration_adj": 0.0,
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    if not ACCURACY_LOG_PATH.exists():
        return out
    try:
        hist = pd.read_csv(ACCURACY_LOG_PATH, encoding="utf-8-sig")
    except Exception:
        return out
    needed = {"prediction_target_date", "sector", "actual_sector_return"}
    if hist.empty or not needed.issubset(hist.columns):
        return out

    hist = hist.copy()
    hist["prediction_target_date"] = pd.to_datetime(hist["prediction_target_date"], errors="coerce")
    hist["actual_sector_return"] = pd.to_numeric(hist["actual_sector_return"], errors="coerce")
    hist = hist.dropna(subset=["prediction_target_date", "sector", "actual_sector_return"])
    if hist.empty:
        return out
    max_date = hist["prediction_target_date"].max()
    hist = hist[hist["prediction_target_date"] >= max_date - pd.Timedelta(days=60)]
    if len(hist) < 48:
        return out

    global_hit = float((hist["actual_sector_return"] > 0).mean())
    global_avg = float(hist["actual_sector_return"].mean())
    grouped = (
        hist.groupby("sector")["actual_sector_return"]
        .agg(
            recent_sector_n="count",
            recent_sector_hit_rate=lambda s: float((s > 0).mean()),
            recent_sector_avg_return="mean",
        )
        .reset_index()
    )
    grouped["recent_sector_shrink"] = grouped["recent_sector_n"] / (grouped["recent_sector_n"] + 8.0)
    hit_edge = (grouped["recent_sector_hit_rate"] - global_hit) * 2.0
    return_edge = ((grouped["recent_sector_avg_return"] - global_avg) / 2.5).clip(lower=-1.0, upper=1.0)
    grouped["score_calibration_adj"] = (0.05 * hit_edge + 0.03 * return_edge) * grouped["recent_sector_shrink"]
    grouped["score_calibration_adj"] = grouped["score_calibration_adj"].clip(lower=-0.06, upper=0.06)
    out = out.drop(columns=[c for c in grouped.columns if c in out.columns and c != "sector"], errors="ignore").merge(
        grouped, on="sector", how="left"
    )
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value
    out["score_calibration_adj"] = pd.to_numeric(out["score_calibration_adj"], errors="coerce").fillna(0.0)
    out["tomorrow_total_score"] = (
        pd.to_numeric(out["tomorrow_total_score"], errors="coerce").fillna(0.0) + out["score_calibration_adj"]
    ).clip(lower=0.0, upper=1.0)
    return out


def percentile_rank_against_reference(values: pd.Series, reference: pd.Series) -> pd.Series:
    ref = sorted(pd.to_numeric(reference, errors="coerce").dropna().tolist())
    if not ref:
        return pd.Series(0.5, index=values.index, dtype="float64")
    n = float(len(ref))
    current = pd.to_numeric(values, errors="coerce")
    return current.apply(lambda value: bisect_right(ref, value) / n if pd.notna(value) else 0.5).astype("float64")


def qcut_bin_count(series: pd.Series, max_bins: int = 5) -> int:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if valid.nunique() < 2:
        return 0
    return int(min(max_bins, valid.nunique()))


def apply_backtest_confidence_calibration(df: pd.DataFrame, target_date: str | None = None) -> pd.DataFrame:
    out = df.copy()
    defaults = {
        "rule_confidence_label": out.get("decision_confidence_label", pd.Series("low", index=out.index)).astype(str),
        "confidence_reliability_score": pd.NA,
        "confidence_empirical_hit_rate": pd.NA,
        "confidence_empirical_avg_return": pd.NA,
        "confidence_empirical_downside_rate": pd.NA,
        "confidence_reliability_n": 0.0,
        "confidence_reference_rows": 0,
        "confidence_reference_end_date": "",
        "confidence_label_source": "rule_only",
    }
    for col, value in defaults.items():
        if col not in out.columns:
            out[col] = value

    if not RETURN_BACKTEST_PATH.exists():
        return out
    try:
        hist = pd.read_csv(RETURN_BACKTEST_PATH, encoding="utf-8-sig")
    except Exception:
        return out

    needed = {
        "next_date",
        "next_sector_return",
        "primary_return_pred",
        "calibrated_quality_adjusted_up_proba",
        "expected_return_signal_to_noise",
        "expected_return_error_p80_pct",
    }
    if hist.empty or not needed.issubset(hist.columns):
        return out

    hist = hist.copy()
    hist["next_date"] = pd.to_datetime(hist["next_date"], errors="coerce")
    if target_date:
        target_ts = pd.to_datetime(target_date, errors="coerce")
        if not pd.isna(target_ts):
            hist = hist[hist["next_date"] < target_ts]

    numeric_cols = [
        "next_sector_return",
        "primary_return_pred",
        "calibrated_quality_adjusted_up_proba",
        "expected_return_signal_to_noise",
        "expected_return_error_p80_pct",
    ]
    for col in numeric_cols:
        hist[col] = pd.to_numeric(hist[col], errors="coerce")
    hist = hist.dropna(subset=["next_date", *numeric_cols])
    if len(hist) < 240:
        return out

    hist["actual_up"] = (hist["next_sector_return"] > 0).astype(float)
    hist["actual_downside"] = (hist["next_sector_return"] < -1.0).astype(float)
    global_hit = float(hist["actual_up"].mean())
    global_avg = float(hist["next_sector_return"].mean())
    global_downside = float(hist["actual_downside"].mean())

    hit_sum = pd.Series(global_hit * 0.45, index=out.index, dtype="float64")
    avg_sum = pd.Series(global_avg * 0.45, index=out.index, dtype="float64")
    downside_sum = pd.Series(global_downside * 0.45, index=out.index, dtype="float64")
    weight_sum = pd.Series(0.45, index=out.index, dtype="float64")
    n_sum = pd.Series(0.0, index=out.index, dtype="float64")
    dim_weight_sum = 0.0

    dimensions = [
        ("primary_return_pred", primary_return_column(out), 0.35),
        ("calibrated_quality_adjusted_up_proba", "calibrated_quality_adjusted_up_proba", 0.25),
        ("expected_return_signal_to_noise", "expected_return_signal_to_noise", 0.22),
        ("expected_return_error_p80_pct", "expected_return_error_p80_pct", 0.18),
    ]
    for hist_col, current_col, dim_weight in dimensions:
        if current_col not in out.columns:
            continue
        bins = qcut_bin_count(hist[hist_col])
        if bins < 2:
            continue
        bin_col = f"{hist_col}_confidence_bin"
        hist[bin_col] = pd.qcut(hist[hist_col], q=bins, labels=False, duplicates="drop")
        bins = int(pd.to_numeric(hist[bin_col], errors="coerce").max()) + 1
        if bins < 2:
            continue
        current_pct = percentile_rank_against_reference(numeric_series(out, current_col), hist[hist_col])
        current_bin = (current_pct * bins).clip(lower=0.0, upper=bins - 1e-9).astype(int)
        grouped = (
            hist.groupby(bin_col)["next_sector_return"]
            .agg(
                confidence_bin_n="count",
                confidence_bin_avg_return="mean",
                confidence_bin_hit_rate=lambda s: float((s > 0).mean()),
                confidence_bin_downside_rate=lambda s: float((s < -1.0).mean()),
            )
            .reset_index()
        )
        mapped = current_bin.to_frame("confidence_bin").merge(
            grouped, left_on="confidence_bin", right_on=bin_col, how="left"
        )
        n = pd.to_numeric(mapped["confidence_bin_n"], errors="coerce").fillna(0.0)
        shrink = (n / (n + 60.0)).clip(lower=0.0, upper=0.90)
        hit = shrink * pd.to_numeric(mapped["confidence_bin_hit_rate"], errors="coerce").fillna(global_hit) + (
            1.0 - shrink
        ) * global_hit
        avg_return = shrink * pd.to_numeric(mapped["confidence_bin_avg_return"], errors="coerce").fillna(global_avg) + (
            1.0 - shrink
        ) * global_avg
        downside = shrink * pd.to_numeric(
            mapped["confidence_bin_downside_rate"], errors="coerce"
        ).fillna(global_downside) + (1.0 - shrink) * global_downside
        effective_weight = dim_weight * shrink

        hit_sum = hit_sum + effective_weight * hit.to_numpy()
        avg_sum = avg_sum + effective_weight * avg_return.to_numpy()
        downside_sum = downside_sum + effective_weight * downside.to_numpy()
        weight_sum = weight_sum + effective_weight.to_numpy()
        n_sum = n_sum + dim_weight * n.to_numpy()
        dim_weight_sum += dim_weight

    empirical_hit = (hit_sum / weight_sum).clip(lower=0.0, upper=1.0)
    empirical_avg = avg_sum / weight_sum
    empirical_downside = (downside_sum / weight_sum).clip(lower=0.0, upper=1.0)
    reliability_n = n_sum / max(dim_weight_sum, 1e-9)

    hit_component = ((empirical_hit - 0.45) / 0.25).clip(lower=0.0, upper=1.0)
    return_component = ((empirical_avg + 0.25) / 1.25).clip(lower=0.0, upper=1.0)
    downside_component = ((0.55 - empirical_downside) / 0.35).clip(lower=0.0, upper=1.0)
    n_component = (reliability_n / 160.0).clip(lower=0.0, upper=1.0)
    model_confidence = clip01(numeric_series(out, "prediction_confidence_score", 0.0))
    out["confidence_reliability_score"] = clip01(
        0.30 * hit_component
        + 0.25 * return_component
        + 0.20 * downside_component
        + 0.15 * model_confidence
        + 0.10 * n_component
    )
    out["confidence_empirical_hit_rate"] = empirical_hit
    out["confidence_empirical_avg_return"] = empirical_avg
    out["confidence_empirical_downside_rate"] = empirical_downside
    out["confidence_reliability_n"] = reliability_n.round(1)
    out["confidence_reference_rows"] = int(len(hist))
    out["confidence_reference_end_date"] = hist["next_date"].max().strftime("%Y-%m-%d")
    out["confidence_label_source"] = "backtest_empirical_v1"

    label = pd.Series("low", index=out.index, dtype="object")
    medium = (
        (out["confidence_reliability_score"] >= 0.50)
        & (out["confidence_empirical_hit_rate"] >= global_hit - 0.02)
        & (out["confidence_empirical_avg_return"] > -0.10)
        & (numeric_series(out, "decision_score") >= 0.45)
        & (numeric_series(out, "risk_control_score") >= 0.35)
    )
    high = (
        (out["confidence_reliability_score"] >= 0.68)
        & (out["confidence_empirical_hit_rate"] >= global_hit + 0.06)
        & (out["confidence_empirical_avg_return"] >= 0.35)
        & (out["confidence_empirical_downside_rate"] <= global_downside - 0.06)
        & (numeric_series(out, "decision_score") >= 0.60)
        & (numeric_series(out, "risk_control_score") >= 0.55)
    )
    label[medium] = "medium"
    label[high] = "high"
    out["decision_confidence_label"] = label
    return out


def add_return_risk_reward_layer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    return_col = primary_return_column(out)
    point = numeric_series(out, return_col)
    low = numeric_series(out, "expected_return_low_pct", -2.5)
    high = numeric_series(out, "expected_return_high_pct", 2.5)
    error = numeric_series(out, "expected_return_error_p80_pct", 2.5).replace(0, pd.NA).fillna(2.5)

    interval_width = (high - low).abs()
    downside_room = (-low).clip(lower=0.0)
    upside_room = high.clip(lower=0.0)
    signal_to_noise = (point / error).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    upside_downside_ratio = (upside_room / (downside_room + 0.5)).replace(
        [float("inf"), float("-inf")], 0.0
    ).fillna(0.0)

    empirical_avg = numeric_series(out, "confidence_empirical_avg_return", 0.0)
    empirical_downside = numeric_series(out, "confidence_empirical_downside_rate", 0.30).clip(lower=0.0, upper=1.0)
    risk_control = clip01(numeric_series(out, "risk_control_score", 0.5))
    model_confidence = clip01(numeric_series(out, "prediction_confidence_score", 0.0))
    return_confidence = clip01(numeric_series(out, "expected_return_confidence_score", 0.0))
    reversal = clip01(numeric_series(out, "intraday_reversal_risk", 0.0))

    relative_return_score = rank_or_default(out, return_col)
    signal_score = ((signal_to_noise + 0.04) / 0.24).clip(lower=0.0, upper=1.0)
    empirical_return_score = ((empirical_avg + 0.10) / 0.70).clip(lower=0.0, upper=1.0)
    downside_score = ((0.42 - empirical_downside) / 0.22).clip(lower=0.0, upper=1.0)
    interval_score = (1.0 - ((interval_width - 3.5) / 4.0)).clip(lower=0.0, upper=1.0)
    upside_downside_score = (upside_downside_ratio / 1.4).clip(lower=0.0, upper=1.0)

    out["expected_return_interval_width_pct"] = interval_width
    out["expected_return_downside_room_pct"] = downside_room
    out["expected_return_upside_room_pct"] = upside_room
    out["expected_return_risk_reward_ratio"] = signal_to_noise
    out["expected_return_upside_downside_ratio"] = upside_downside_ratio
    out["expected_return_risk_adjusted_score"] = clip01(
        0.24 * relative_return_score
        + 0.22 * signal_score
        + 0.20 * empirical_return_score
        + 0.14 * downside_score
        + 0.10 * risk_control
        + 0.06 * model_confidence
        + 0.04 * return_confidence
    )
    out["expected_return_risk_adjusted_score"] = clip01(
        out["expected_return_risk_adjusted_score"] * (0.92 + 0.08 * interval_score) * (1.0 - 0.10 * reversal)
    )

    grade = pd.Series("중립/오차 큼", index=out.index, dtype="object")
    grade[(point <= 0) | (high <= 0)] = "하락 위험"
    grade[(point > 0) & (signal_to_noise < 0.025)] = "약한 상승/오차 큼"
    grade[
        (point > 0)
        & (signal_to_noise >= 0.025)
        & (out["expected_return_risk_adjusted_score"] >= 0.45)
    ] = "제한적 상승"
    grade[
        (point >= 0.10)
        & (signal_to_noise >= 0.03)
        & (empirical_avg > 0.15)
        & (empirical_downside < 0.30)
        & (out["expected_return_risk_adjusted_score"] >= 0.52)
    ] = "상승 우위"
    grade[
        (point >= 0.25)
        & (signal_to_noise >= 0.10)
        & (empirical_avg >= 0.35)
        & (empirical_downside <= 0.24)
        & (risk_control >= 0.55)
        & (out["expected_return_risk_adjusted_score"] >= 0.68)
    ] = "강한 상승 후보"
    grade[(reversal >= 0.55) & grade.isin(["상승 우위", "강한 상승 후보"])] = "상승 우위/반전 위험"
    out["expected_return_grade"] = grade

    reason = pd.Series("수익률 예측 대비 오차폭이 커서 보수 해석", index=out.index, dtype="object")
    reason[grade.eq("약한 상승/오차 큼")] = "예상 수익은 양수지만 오차폭 대비 신호가 약함"
    reason[grade.eq("제한적 상승")] = "양수 예측이나 기대수익 대비 위험 보상은 제한적"
    reason[grade.eq("상승 우위")] = "예상 수익, 경험 평균수익, 하락위험이 모두 양호"
    reason[grade.eq("강한 상승 후보")] = "예상 수익과 위험대비 보상이 동시에 강함"
    reason[grade.eq("상승 우위/반전 위험")] = "수익률 조건은 좋지만 장중 반전 위험이 높음"
    reason[grade.eq("하락 위험")] = "예상 수익 또는 상단 구간이 약해 하락 위험 우세"
    out["expected_return_grade_reason"] = reason

    adjustment = ((out["expected_return_risk_adjusted_score"] - 0.50) * 0.08).clip(lower=-0.04, upper=0.04)
    adjustment = adjustment.where(~grade.eq("하락 위험"), adjustment.clip(upper=0.0))
    adjustment = adjustment.where(~grade.eq("약한 상승/오차 큼"), adjustment.clip(upper=0.01))
    out["return_risk_score_adjustment"] = adjustment
    out["tomorrow_total_score"] = (numeric_series(out, "tomorrow_total_score") + adjustment).clip(
        lower=0.0, upper=1.0
    )
    return out


def add_expected_return_interval_layer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    center = numeric_series(out, "expected_return_mid_pct", 0.0)
    if center.eq(0).all():
        center = numeric_series(out, primary_return_column(out), 0.0)
    lower = numeric_series(out, "expected_return_low_pct", -2.5)
    upper = numeric_series(out, "expected_return_high_pct", 2.5)
    q10 = numeric_series(out, "expected_return_model_q10_pct", lower)
    q50 = numeric_series(out, "expected_return_model_q50_pct", center)
    q90 = numeric_series(out, "expected_return_model_q90_pct", upper)

    center = center.where(center.ne(0), q50)
    lower = pd.concat([lower, q10], axis=1).min(axis=1)
    upper = pd.concat([upper, q90], axis=1).max(axis=1)
    swapped = lower > upper
    safe_lower = lower.where(~swapped, upper)
    safe_upper = upper.where(~swapped, lower)
    width = (safe_upper - safe_lower).abs()
    downside = (-safe_lower).clip(lower=0.0)
    upside = safe_upper.clip(lower=0.0)
    confidence = clip01(numeric_series(out, "expected_return_confidence_score", 0.0))
    width_score = (1.0 - ((width - 3.5) / 5.0)).clip(lower=0.0, upper=1.0)
    lower_score = ((safe_lower + 2.5) / 4.5).clip(lower=0.0, upper=1.0)
    center_rank = rank_or_default(pd.DataFrame({"center": center}), "center")

    strength = clip01(0.38 * center_rank + 0.28 * lower_score + 0.20 * width_score + 0.14 * confidence)
    out["return_interval_center_pct"] = center
    out["return_interval_lower_pct"] = safe_lower
    out["return_interval_upper_pct"] = safe_upper
    out["return_interval_width_pct"] = width
    out["return_interval_downside_pct"] = downside
    out["return_interval_upside_pct"] = upside
    out["return_interval_confidence_score"] = confidence
    out["return_interval_strength_score"] = strength
    out["return_interval_strength_rank"] = strength.rank(ascending=False, method="first").astype(int)

    label = pd.Series("중립/혼합", index=out.index, dtype="object")
    label[(center > 0) & (safe_lower <= 0) & (safe_upper > 0)] = "상승 중심/하단 음수"
    label[(center > 0) & (safe_lower > 0)] = "구간 전체 양수"
    label[(safe_upper <= 0) | ((center <= 0) & (safe_lower < 0))] = "하방 우세"
    label[(width >= 6.5) & (safe_lower <= 0) & (safe_upper > 0)] = "상승 가능/오차 큼"
    out["return_interval_label"] = label

    confidence_label = pd.Series("낮음", index=out.index, dtype="object")
    confidence_label[(width <= 5.5) & (confidence >= 0.12)] = "보통"
    confidence_label[(width <= 4.5) & (confidence >= 0.20) & (safe_lower > -1.5)] = "상대적 안정"
    confidence_label[(width >= 7.0) | (confidence < 0.10)] = "낮음"
    out["return_interval_confidence_label"] = confidence_label

    interpretations = []
    action_notes = []
    for idx in out.index:
        interpretations.append(
            "중심 {center:+.2f}%, 구간 {lower:+.2f}%~{upper:+.2f}%, 폭 {width:.2f}%p".format(
                center=float(center.at[idx]),
                lower=float(safe_lower.at[idx]),
                upper=float(safe_upper.at[idx]),
                width=float(width.at[idx]),
            )
        )
        if safe_upper.at[idx] <= 0:
            note = "상단도 약해 보수 또는 회피 해석"
        elif safe_lower.at[idx] > 0:
            note = "하단도 양수라 상승 신호 신뢰가 상대적으로 높음"
        elif width.at[idx] >= 6.5:
            note = "중심은 양수지만 구간이 넓어 단일 수익률보다 리스크 확인 우선"
        elif center.at[idx] > 0:
            note = "양수 중심이나 하단은 음수라 장중 확인 후 접근"
        else:
            note = "상승 근거가 약해 관망 우선"
        action_notes.append(note)
    out["return_interval_interpretation"] = interpretations
    out["return_interval_action_note"] = action_notes
    return out


def apply_intraday_bridge_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    bridge = clip01(numeric_series(out, "intraday_bridge_score", 0.5))
    continuation = clip01(numeric_series(out, "intraday_continuation_score", 0.5))
    reversal = clip01(numeric_series(out, "intraday_reversal_risk", 0.0))
    raw_adjustment = numeric_series(out, "intraday_bridge_adjustment", 0.0).clip(lower=-0.06, upper=0.06)

    model_alignment = clip01(
        0.40 * rank_or_default(out, primary_return_column(out))
        + 0.35 * rank_or_default(out, "calibrated_quality_adjusted_up_proba")
        + 0.15 * rank_or_default(out, "expected_return_score")
        + 0.10 * rank_or_default(out, "final_rank_score_v5")
    )
    positive_gate = (0.35 + 0.65 * model_alignment).clip(lower=0.35, upper=1.0)
    negative_gate = (1.10 - 0.30 * model_alignment).clip(lower=0.75, upper=1.10)
    gated_adjustment = raw_adjustment.where(raw_adjustment < 0, raw_adjustment * positive_gate)
    gated_adjustment = gated_adjustment.where(gated_adjustment >= 0, gated_adjustment * negative_gate)
    reversal_penalty = (reversal - 0.55).clip(lower=0.0, upper=0.45) * 0.06

    out["intraday_bridge_model_alignment"] = model_alignment
    out["intraday_bridge_score_adjustment"] = (gated_adjustment - reversal_penalty).clip(lower=-0.07, upper=0.05)
    out["tomorrow_total_score"] = (
        numeric_series(out, "tomorrow_total_score", 0.0) + out["intraday_bridge_score_adjustment"]
    ).clip(lower=0.0, upper=1.0)
    out["intraday_bridge_comment"] = "중립"
    out.loc[(bridge >= 0.62) & (reversal < 0.45), "intraday_bridge_comment"] = "장중 지속 신호 보강"
    out.loc[(continuation >= 0.60) & (reversal >= 0.55), "intraday_bridge_comment"] = "반등은 있으나 반전위험 동반"
    out.loc[bridge < 0.42, "intraday_bridge_comment"] = "장중 반등 약함"
    return out


def apply_score_safety_caps(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    no_trade_mask = pd.to_numeric(out.get("v5_no_trade_flag", 0), errors="coerce").fillna(0) >= 1
    out.loc[no_trade_mask, "tomorrow_total_score"] = out.loc[no_trade_mask, "tomorrow_total_score"].clip(upper=0.37)

    largecap_only = pd.to_numeric(out.get("v5_largecap_only_flag", 0), errors="coerce").fillna(0) >= 1
    out.loc[largecap_only, "tomorrow_total_score"] = out.loc[largecap_only, "tomorrow_total_score"].clip(upper=0.45)

    attention_overheat = pd.to_numeric(out.get("v5_attention_overheat_flag", 0), errors="coerce").fillna(0) >= 1
    out.loc[attention_overheat, "tomorrow_total_score"] = out.loc[attention_overheat, "tomorrow_total_score"].clip(upper=0.58)

    fx_stress = pd.to_numeric(out.get("v5_fx_stress_flag", 0), errors="coerce").fillna(0) >= 1
    out.loc[fx_stress, "tomorrow_total_score"] = out.loc[fx_stress, "tomorrow_total_score"].clip(upper=0.62)

    sector_penalty_v4 = pd.to_numeric(out.get("sector_risk_penalty_v4", 0), errors="coerce").fillna(0)
    out.loc[sector_penalty_v4 >= 0.26, "tomorrow_total_score"] = out.loc[
        sector_penalty_v4 >= 0.26, "tomorrow_total_score"
    ].clip(upper=0.37)

    market_risk_v4 = pd.to_numeric(out.get("market_regime_risk_v4", 0.5), errors="coerce").fillna(0.5)
    out.loc[market_risk_v4 >= 0.75, "tomorrow_total_score"] = out.loc[
        market_risk_v4 >= 0.75, "tomorrow_total_score"
    ].clip(upper=0.58)
    return out


def assign_actions(df: pd.DataFrame) -> pd.Series:
    action = pd.Series(ACTION_WATCH, index=df.index, dtype="object")
    score = pd.to_numeric(df["tomorrow_total_score"], errors="coerce").fillna(0)
    market_risk = pd.to_numeric(df.get("market_regime_risk_v4", 0.5), errors="coerce").fillna(0.5)
    sector_penalty = pd.to_numeric(df.get("sector_risk_penalty_v4", 0.0), errors="coerce").fillna(0.0)
    v4_action = df.get("v4_action", pd.Series("", index=df.index)).astype(str)
    v5_action = df.get("v5_action", pd.Series("", index=df.index)).astype(str)

    action[score < 0.38] = ACTION_AVOID
    action[(score >= 0.62) & (market_risk < 0.65) & (sector_penalty < 0.18)] = ACTION_AUX
    action[(score >= 0.78) & (market_risk < 0.45) & (sector_penalty < 0.12)] = ACTION_CORE

    action[v4_action.eq(ACTION_AVOID)] = ACTION_AVOID
    action[v5_action.eq(ACTION_NO_TRADE)] = ACTION_AVOID
    action[v5_action.eq(ACTION_AVOID)] = ACTION_AVOID
    action[sector_penalty >= 0.26] = ACTION_AVOID
    action[(market_risk >= 0.75) & (score < 0.42) & (v4_action.ne(ACTION_WATCH))] = ACTION_AVOID
    return action


def conservative_action(left: str, right: str) -> str:
    left_priority = ACTION_PRIORITY.get(str(left), ACTION_PRIORITY[ACTION_WATCH])
    right_priority = ACTION_PRIORITY.get(str(right), ACTION_PRIORITY[ACTION_WATCH])
    return str(left) if left_priority <= right_priority else str(right)


def _as_optional_float(value) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_below(value, threshold: float) -> bool:
    numeric = _as_optional_float(value)
    return numeric is not None and numeric < threshold


def load_ranking_quality_gate() -> dict:
    gate = {
        "enabled": False,
        "level": "normal",
        "reason": "랭킹 품질 리포트 없음",
        "warning_count": 0,
        "warnings": [],
        "latest_date": "",
        "all_rank_ic_spearman": None,
        "all_top3_overlap": None,
        "last5_rank_ic_spearman": None,
        "last5_top3_spread": None,
        "last10_rank_ic_spearman": None,
        "last10_top3_spread": None,
    }
    if not RANKING_QUALITY_SUMMARY_PATH.exists():
        return gate
    try:
        summary = json.loads(RANKING_QUALITY_SUMMARY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        gate["reason"] = "랭킹 품질 리포트 읽기 실패"
        return gate

    if summary.get("status") != "ok":
        gate["reason"] = "랭킹 품질 리포트 상태 비정상"
        return gate

    windows = summary.get("windows") or {}
    last5 = windows.get("last_5d") or {}
    last10 = windows.get("last_10d") or {}
    warning_count = int(summary.get("warning_count") or 0)
    warnings = [str(item) for item in summary.get("warnings") or []]
    all_rank_ic = _as_optional_float(summary.get("rank_ic_spearman_avg"))
    all_top3_overlap = _as_optional_float(summary.get("top3_actual_top3_overlap_rate"))
    last5_rank_ic = _as_optional_float(last5.get("rank_ic_spearman_avg"))
    last5_spread = _as_optional_float(last5.get("top3_minus_bottom3_spread_avg"))
    last10_rank_ic = _as_optional_float(last10.get("rank_ic_spearman_avg"))
    last10_spread = _as_optional_float(last10.get("top3_minus_bottom3_spread_avg"))

    reasons = []
    if warning_count > 0:
        reasons.append("랭킹 품질 경고 존재")
    if _metric_below(all_top3_overlap, 0.30):
        reasons.append("전체 Top3 겹침률 30% 미만")
    if _metric_below(last10_rank_ic, 0.0):
        reasons.append("최근 10거래일 RankIC 음수")
    if _metric_below(last10_spread, 0.0):
        reasons.append("최근 10거래일 Top3-Bottom3 spread 음수")

    severe = (
        (_metric_below(last5_rank_ic, 0.0) and _metric_below(last5_spread, 0.0))
        or (_metric_below(last10_rank_ic, -0.05) and _metric_below(last10_spread, -0.25))
        or _metric_below(all_rank_ic, -0.02)
    )
    if severe:
        level = "severe"
    elif reasons:
        level = "caution"
    else:
        level = "normal"

    gate.update(
        {
            "enabled": True,
            "level": level,
            "reason": "; ".join(reasons) if reasons else "랭킹 품질 게이트 정상",
            "warning_count": warning_count,
            "warnings": warnings,
            "latest_date": str(summary.get("latest_date", "")),
            "all_rank_ic_spearman": all_rank_ic,
            "all_top3_overlap": all_top3_overlap,
            "last5_rank_ic_spearman": last5_rank_ic,
            "last5_top3_spread": last5_spread,
            "last10_rank_ic_spearman": last10_rank_ic,
            "last10_top3_spread": last10_spread,
        }
    )
    return gate


def downgrade_action_for_ranking_quality(action: str, level: str) -> str:
    action = str(action)
    if level == "severe":
        return {
            ACTION_CORE: ACTION_WATCH,
            ACTION_AUX: ACTION_WATCH,
            ACTION_DEFENSIVE: ACTION_WATCH,
        }.get(action, action)
    if level == "caution":
        return {
            ACTION_CORE: ACTION_AUX,
            ACTION_AUX: ACTION_WATCH,
        }.get(action, action)
    return action


def apply_ranking_quality_gate(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    gate = load_ranking_quality_gate()
    out["ranking_quality_gate_level"] = gate["level"]
    out["ranking_quality_gate_reason"] = gate["reason"]
    out["ranking_quality_gate_downgrade"] = 0
    out["ranking_quality_gate_warning_count"] = gate["warning_count"]
    out["ranking_quality_gate_latest_date"] = gate["latest_date"]
    out["ranking_quality_all_rank_ic_spearman"] = gate["all_rank_ic_spearman"]
    out["ranking_quality_all_top3_overlap"] = gate["all_top3_overlap"]
    out["ranking_quality_last5_rank_ic_spearman"] = gate["last5_rank_ic_spearman"]
    out["ranking_quality_last5_top3_spread"] = gate["last5_top3_spread"]
    out["ranking_quality_last10_rank_ic_spearman"] = gate["last10_rank_ic_spearman"]
    out["ranking_quality_last10_top3_spread"] = gate["last10_top3_spread"]

    if gate["level"] == "normal" or "final_action" not in out.columns:
        if "tomorrow_action" in out.columns and "final_action" in out.columns:
            out["tomorrow_action"] = out["final_action"]
        return out

    original = out["final_action"].astype(str)
    gated = original.apply(lambda action: downgrade_action_for_ranking_quality(action, gate["level"]))
    changed = original.ne(gated)
    out.loc[changed, "final_action"] = gated[changed]
    out.loc[changed, "ranking_quality_gate_downgrade"] = 1
    if "action_conflict_flag" in out.columns:
        out.loc[changed, "action_conflict_flag"] = 1
    if "final_action_reason" in out.columns:
        out.loc[changed, "final_action_reason"] = "최근 랭킹 품질 약화로 행동 강도 보수화: " + gate["reason"]
    out["tomorrow_action"] = out["final_action"]
    return out


def add_avoid_pressure_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    final_action = out.get("final_action", pd.Series(ACTION_WATCH, index=out.index)).astype(str)
    no_trade = numeric_series(out, "v5_no_trade_flag").ge(1.0)
    market_risk = numeric_series(out, "market_regime_risk_v4", 0.5).clip(lower=0.0, upper=1.0)
    sector_risk_v4 = (numeric_series(out, "sector_risk_penalty_v4") / 0.35).clip(lower=0.0, upper=1.0)
    sector_risk_v5 = (numeric_series(out, "sector_risk_penalty_v5") / 0.35).clip(lower=0.0, upper=1.0)
    bridge = numeric_series(out, "intraday_bridge_score", 0.5).clip(lower=0.0, upper=1.0)
    reversal = numeric_series(out, "intraday_reversal_risk").clip(lower=0.0, upper=1.0)
    confidence = out.get("decision_confidence_label", pd.Series("", index=out.index)).astype(str)
    gate_level = out.get("ranking_quality_gate_level", pd.Series("normal", index=out.index)).astype(str)

    trigger_frame = pd.DataFrame(
        {
            "no_trade": no_trade.astype(int),
            "market_panic": market_risk.ge(0.75).astype(int),
            "sector_risk_v4": numeric_series(out, "sector_risk_penalty_v4").ge(0.26).astype(int),
            "sector_risk_v5": numeric_series(out, "sector_risk_penalty_v5").ge(0.30).astype(int),
            "confidence_low": confidence.eq("low").astype(int),
            "intraday_bridge_weak": bridge.lt(0.42).astype(int),
            "intraday_reversal_high": reversal.ge(0.55).astype(int),
            "ranking_quality_caution": gate_level.isin(["caution", "severe"]).astype(int),
        },
        index=out.index,
    )
    out["avoid_gate_count"] = trigger_frame.sum(axis=1)
    out["avoid_pressure_score"] = clip01(
        0.24 * market_risk
        + 0.18 * no_trade.astype(float)
        + 0.16 * sector_risk_v4
        + 0.14 * sector_risk_v5
        + 0.12 * (1.0 - bridge)
        + 0.08 * reversal
        + 0.08 * confidence.eq("low").astype(float)
    )

    defensive_score = clip01(
        0.24 * numeric_series(out, "excess_strength_score")
        + 0.22 * numeric_series(out, "expected_return_risk_adjusted_score")
        + 0.20 * numeric_series(out, "rank_model_score")
        + 0.14 * numeric_series(out, "absolute_up_score")
        + 0.10 * bridge
        + 0.10 * (1.0 - reversal)
    )
    out["defensive_watch_candidate_score"] = defensive_score

    profile = out.get("decision_profile", pd.Series("", index=out.index)).astype(str)
    grade = out.get("expected_return_grade", pd.Series("", index=out.index)).astype(str)
    positive_count = numeric_series(out, "positive_signal_count")
    risk_count = numeric_series(out, "risk_block_count")
    defensive_candidate = (
        final_action.eq(ACTION_AVOID)
        & no_trade
        & profile.isin(["defensive_relative", "mixed"])
        & grade.isin(["상승 우위", "제한적 상승"])
        & defensive_score.ge(0.50)
        & numeric_series(out, "excess_strength_score").ge(0.50)
        & positive_count.ge(2)
        & risk_count.le(6)
    )
    out["defensive_watch_candidate_flag"] = defensive_candidate.astype(int)
    out["defensive_watch_candidate_rank"] = 0
    if defensive_candidate.any():
        ranks = out.loc[defensive_candidate, "defensive_watch_candidate_score"].rank(
            ascending=False, method="first"
        )
        out.loc[defensive_candidate, "defensive_watch_candidate_rank"] = ranks.astype(int)

    out["avoid_pressure_note"] = "회피 진단 대상 아님"
    out.loc[final_action.eq(ACTION_AVOID), "avoid_pressure_note"] = "회피 유지: 주요 리스크 게이트 우세"
    out.loc[defensive_candidate, "avoid_pressure_note"] = (
        "회피 유지: 시장 패닉 게이트가 우선이나 상대강도 기준 방어 후보로 추적"
    )
    out["panic_watch_action"] = "일반 판단"
    out.loc[final_action.eq(ACTION_AVOID), "panic_watch_action"] = "회피 유지"
    out.loc[
        final_action.eq(ACTION_AVOID) & out["avoid_pressure_score"].ge(0.80),
        "panic_watch_action",
    ] = "강한 회피"
    out.loc[defensive_candidate, "panic_watch_action"] = "방어 추적"
    return out


def add_final_actions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "score_action" not in out.columns:
        out["score_action"] = assign_actions(out)
    if "decision_action" not in out.columns:
        out["decision_action"] = out["score_action"]

    out["final_action"] = [
        conservative_action(score_action, decision_action)
        for score_action, decision_action in zip(out["score_action"], out["decision_action"])
    ]

    no_trade = numeric_series(out, "v5_no_trade_flag").ge(1.0)
    hard_avoid = (
        no_trade
        | out.get("v5_action", pd.Series("", index=out.index)).astype(str).eq(ACTION_NO_TRADE)
        | out.get("v5_action", pd.Series("", index=out.index)).astype(str).eq(ACTION_AVOID)
        | (
            out.get("v4_action", pd.Series("", index=out.index)).astype(str).eq(ACTION_AVOID)
            & (numeric_series(out, "decision_score") < 0.55)
        )
        | (numeric_series(out, "sector_risk_penalty_v4") >= 0.75)
    )
    out.loc[hard_avoid, "final_action"] = ACTION_AVOID

    out["action_conflict_flag"] = (
        out["score_action"].astype(str).ne(out["decision_action"].astype(str))
        | out["final_action"].astype(str).ne(out["score_action"].astype(str))
        | out["final_action"].astype(str).ne(out["decision_action"].astype(str))
    ).astype(int)

    out["final_action_reason"] = "점수와 리스크 판단이 같은 방향"
    out.loc[
        out["score_action"].astype(str).ne(out["decision_action"].astype(str)),
        "final_action_reason",
    ] = "점수 기반 판단과 리스크 판단이 달라 더 보수적인 최종 행동을 선택"
    out.loc[
        numeric_series(out, "prediction_confidence_score") < 0.30,
        "final_action_reason",
    ] = "예측 신뢰도가 낮아 최종 행동을 보수화"
    out.loc[
        out["decision_profile"].astype(str).eq("weak"),
        "final_action_reason",
    ] = "상승 확률과 초과수익 신호가 모두 약함"
    out.loc[
        (numeric_series(out, "intraday_bridge_score") < 0.42) & out["final_action"].astype(str).isin([ACTION_AVOID, ACTION_WATCH]),
        "final_action_reason",
    ] = "장중 반등 브릿지 신호가 약함"
    out.loc[
        numeric_series(out, "intraday_reversal_risk") >= 0.55,
        "final_action_reason",
    ] = "장중 반등은 있으나 마감 반전 위험이 큼"
    out.loc[hard_avoid, "final_action_reason"] = "상위 리스크 모델의 회피 조건 발생"
    out.loc[
        out["final_action"].astype(str).eq(ACTION_DEFENSIVE)
        & out["final_action_reason"].eq("점수와 리스크 판단이 같은 방향"),
        "final_action_reason",
    ] = "상대 강도는 있으나 절대 상승 신뢰가 부족해 방어 관찰"

    # Backward-compatible user-facing column: older evaluators read tomorrow_action.
    out["tomorrow_action"] = out["final_action"]
    return out


def add_signal_conflict_explanations(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    final_action = out.get("final_action", pd.Series(ACTION_WATCH, index=out.index)).astype(str)
    v4_action = out.get("v4_action", pd.Series("", index=out.index)).astype(str)
    v5_action = out.get("v5_action", pd.Series("", index=out.index)).astype(str)
    grade = out.get("expected_return_grade", pd.Series("", index=out.index)).astype(str)
    confidence = out.get("decision_confidence_label", pd.Series("", index=out.index)).astype(str)

    score = numeric_series(out, "tomorrow_total_score")
    risk_adjusted_return = numeric_series(out, "expected_return_risk_adjusted_score")
    bridge = numeric_series(out, "intraday_bridge_score", 0.5)
    reversal = numeric_series(out, "intraday_reversal_risk")
    empirical_avg = numeric_series(out, "confidence_empirical_avg_return")
    empirical_downside = numeric_series(out, "confidence_empirical_downside_rate", 0.35)
    interval_width = numeric_series(out, "expected_return_interval_width_pct", 5.0)
    risk_control = numeric_series(out, "risk_control_score", 0.5)
    sector_penalty_v4 = numeric_series(out, "sector_risk_penalty_v4")
    sector_penalty_v5 = numeric_series(out, "sector_risk_penalty_v5")

    positive_flags = pd.DataFrame(
        {
            "return_grade": grade.isin(["강한 상승 후보", "상승 우위", "상승 우위/반전 위험", "제한적 상승"]),
            "risk_adjusted_return": risk_adjusted_return >= 0.52,
            "total_score": score >= 0.58,
            "intraday_bridge": (bridge >= 0.50) & (reversal < 0.45),
            "backtest_return": (empirical_avg > 0.10) & (empirical_downside < 0.35),
        },
        index=out.index,
    )
    risk_flags = pd.DataFrame(
        {
            "final_avoid": final_action.eq(ACTION_AVOID),
            "low_confidence": confidence.eq("low"),
            "risk_model_avoid": v4_action.eq(ACTION_AVOID) | v5_action.isin([ACTION_AVOID, ACTION_NO_TRADE]),
            "weak_intraday_bridge": bridge < 0.42,
            "high_reversal_risk": reversal >= 0.45,
            "wide_return_interval": interval_width >= 6.0,
            "weak_risk_control": risk_control < 0.45,
            "sector_penalty": (sector_penalty_v4 >= 0.18) | (sector_penalty_v5 >= 0.14),
        },
        index=out.index,
    )

    positive_count = positive_flags.astype(int).sum(axis=1)
    risk_count = risk_flags.astype(int).sum(axis=1)
    out["positive_signal_count"] = positive_count
    out["risk_block_count"] = risk_count
    out["signal_conflict_score"] = (
        (positive_count.clip(upper=len(positive_flags.columns)) / len(positive_flags.columns))
        * (risk_count.clip(upper=len(risk_flags.columns)) / len(risk_flags.columns))
    ).round(4)

    conflict_type = pd.Series("중립 관찰", index=out.index, dtype="object")
    conflict_type[(final_action.isin([ACTION_CORE, ACTION_AUX])) & (positive_count >= 2) & (risk_count <= 1)] = "진입 후보"
    conflict_type[(final_action.eq(ACTION_AVOID)) & (positive_count >= 2)] = "상승신호-리스크충돌"
    conflict_type[
        final_action.isin([ACTION_WATCH, ACTION_DEFENSIVE]) & (positive_count >= 2)
    ] = "상승신호-보수관찰"
    conflict_type[(final_action.eq(ACTION_AVOID)) & (positive_count <= 1) & (risk_count >= 2)] = "약신호-회피일치"
    conflict_type[(final_action.eq(ACTION_AVOID)) & (positive_count >= 2) & (risk_count >= 4)] = "상승신호-강한리스크충돌"
    out["signal_conflict_type"] = conflict_type

    def risk_reasons(row: pd.Series) -> list[str]:
        reasons: list[str] = []
        if str(row.get("decision_confidence_label", "")) == "low":
            reasons.append("백테스트 신뢰도 low")
        if str(row.get("v4_action", "")) == ACTION_AVOID or str(row.get("v5_action", "")) in [ACTION_AVOID, ACTION_NO_TRADE]:
            reasons.append("V4/V5 리스크 게이트")
        if pd.to_numeric(row.get("intraday_bridge_score", 0.5), errors="coerce") < 0.42:
            reasons.append("장중 브릿지 약세")
        if pd.to_numeric(row.get("intraday_reversal_risk", 0.0), errors="coerce") >= 0.45:
            reasons.append("마감 반전 위험")
        if pd.to_numeric(row.get("expected_return_interval_width_pct", 5.0), errors="coerce") >= 6.0:
            reasons.append("예상 수익 오차 확대")
        if pd.to_numeric(row.get("risk_control_score", 0.5), errors="coerce") < 0.45:
            reasons.append("리스크 통제 점수 약세")
        if not reasons:
            reasons.append(str(row.get("final_action_reason", "보수 게이트")))
        return reasons

    def build_explanation(row: pd.Series) -> str:
        ctype = str(row.get("signal_conflict_type", "중립 관찰"))
        final = str(row.get("final_action", ACTION_WATCH))
        grade_text = str(row.get("expected_return_grade", ""))
        positives = int(row.get("positive_signal_count", 0))
        risks = int(row.get("risk_block_count", 0))
        reasons = ", ".join(risk_reasons(row)[:3])

        if ctype in ["상승신호-리스크충돌", "상승신호-강한리스크충돌"]:
            return f"{grade_text} 신호와 {positives}개 상승 근거는 있으나 {reasons} 때문에 최종 판단은 {final}이다."
        if ctype == "상승신호-보수관찰":
            return f"{grade_text} 신호는 우호적이지만 확인된 상승 근거 {positives}개 대비 리스크 차단 {risks}개가 남아 {final}으로 낮춰 본다."
        if ctype == "진입 후보":
            return f"수익률, 점수, 리스크 게이트가 같은 방향이라 {final} 후보로 볼 수 있다."
        if ctype == "약신호-회피일치":
            return f"상승 근거가 부족하고 {reasons}도 겹쳐 {final} 판단과 신호가 일치한다."
        return f"상승 근거 {positives}개, 리스크 차단 {risks}개로 현재는 {final} 판단을 유지한다."

    def build_entry_note(row: pd.Series) -> str:
        notes: list[str] = []
        if str(row.get("decision_confidence_label", "")) == "low":
            notes.append("신뢰도 medium 이상 회복")
        if pd.to_numeric(row.get("intraday_bridge_score", 0.5), errors="coerce") < 0.50:
            notes.append("장중 브릿지 0.50 이상")
        if pd.to_numeric(row.get("intraday_reversal_risk", 0.0), errors="coerce") >= 0.35:
            notes.append("반전 위험 0.35 미만")
        if str(row.get("v4_action", "")) == ACTION_AVOID or str(row.get("v5_action", "")) in [ACTION_AVOID, ACTION_NO_TRADE]:
            notes.append("V4/V5 회피 게이트 해제")
        if pd.to_numeric(row.get("expected_return_interval_width_pct", 5.0), errors="coerce") >= 6.0:
            notes.append("예상 수익 오차 축소")
        if not notes:
            return "현재 조건 유지 시 다음 장 초반 거래대금과 상승 확산 확인"
        return " / ".join(notes[:3]) + " 확인 전까지 보수 대응"

    out["final_decision_explanation"] = out.apply(build_explanation, axis=1)
    out["entry_condition_note"] = out.apply(build_entry_note, axis=1)
    return out


def add_decision_layer_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    return_col = primary_return_column(out)
    ret_rank = rank_or_default(out, return_col)
    quality_rank = rank_or_default(out, "calibrated_quality_adjusted_up_proba")
    effect_rank = freshness_adjusted_rank(out, "expected_effect_score")
    live_rank = rank_or_default(out, "live_fomo_score")
    intraday_bridge = clip01(numeric_series(out, "intraday_bridge_score", 0.5))
    intraday_reversal = clip01(numeric_series(out, "intraday_reversal_risk", 0.0))
    intraday_rank = rank_or_default(out, "intraday_bridge_score")
    v3 = numeric_series(out, "final_rank_score_v3")
    v4 = numeric_series(out, "final_rank_score_v4")
    v5 = numeric_series(out, "final_rank_score_v5")

    mid_return = numeric_series(out, "expected_return_mid_pct")
    return_error = numeric_series(out, "expected_return_error_p80_pct", 2.5).replace(0, pd.NA).fillna(2.5)
    return_signal_score = (0.5 + 0.5 * (mid_return / return_error).clip(lower=-1.0, upper=1.0)).clip(0.0, 1.0)
    return_confidence = clip01(numeric_series(out, "expected_return_confidence_score"))
    out["expected_return_score"] = clip01(0.35 * ret_rank + 0.45 * return_signal_score + 0.20 * return_confidence)

    quality = numeric_series(out, "calibrated_quality_adjusted_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    combined = numeric_series(out, "calibrated_absolute_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    meaningful = numeric_series(out, "calibrated_meaningful_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    tradeable = numeric_series(out, "calibrated_tradeable_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    excess_prob = numeric_series(out, "calibrated_excess_up_proba", 0.5).clip(lower=0.0, upper=1.0)
    out["absolute_up_score"] = clip01(
        0.40 * quality
        + 0.20 * combined
        + 0.15 * meaningful
        + 0.10 * tradeable
        + 0.15 * out["expected_return_score"]
    )

    excess_v3_rank = rank_or_default(out, "pred_next_excess_return_v3")
    market_gap_rank = rank_or_default(out, "sector_vs_market_return_gap")
    relative_v4 = clip01(numeric_series(out, "relative_strength_component_v4", 0.5))
    paper_relative_rank = rank_or_default(out, "paper_graph_relative_strength")
    out["excess_strength_score"] = clip01(
        0.35 * excess_prob
        + 0.25 * excess_v3_rank
        + 0.15 * market_gap_rank
        + 0.15 * relative_v4
        + 0.10 * paper_relative_rank
    )

    out["rank_model_score"] = primary_rank_model_score(out)
    out["model_signal_score"] = clip01(
        0.16 * out["rank_model_score"]
        + 0.34 * out["absolute_up_score"]
        + 0.18 * out["excess_strength_score"]
        + 0.24 * out["expected_return_score"]
        + 0.08 * intraday_rank
    )

    prob_edge = ((out["absolute_up_score"] - 0.5) / 0.35).clip(lower=0.0, upper=1.0)
    range_label = out.get("expected_return_range_label", pd.Series("", index=out.index)).astype(str)
    range_component = pd.Series(0.25, index=out.index, dtype="float64")
    range_component[range_label.eq("positive_range")] = 1.0
    range_component[range_label.eq("mixed_range") & (mid_return > 0)] = 0.45
    range_component[range_label.eq("mixed_range") & (mid_return <= 0)] = 0.25
    range_component[range_label.eq("negative_range")] = 0.05

    agreement_parts = []
    for col in [
        "final_rank_score_v5",
        "final_rank_score_v4",
        "final_rank_score_v3",
        return_col,
        "calibrated_quality_adjusted_up_proba",
    ]:
        if col in out.columns:
            values = numeric_series(out, col)
            if values.nunique(dropna=True) > 1:
                agreement_parts.append(rank01(values))
    if len(agreement_parts) >= 2:
        agreement_frame = pd.concat(agreement_parts, axis=1)
        model_agreement = (1.0 - agreement_frame.std(axis=1).fillna(0.0) / 0.35).clip(lower=0.0, upper=1.0)
    else:
        model_agreement = pd.Series(0.5, index=out.index, dtype="float64")

    recent_hit = numeric_series(out, "recent_sector_hit_rate", 0.5)
    recent_reliability = ((recent_hit - 0.35) / 0.30).clip(lower=0.0, upper=1.0)
    out["prediction_confidence_score"] = clip01(
        0.28 * prob_edge
        + 0.23 * return_confidence
        + 0.19 * model_agreement
        + 0.14 * range_component
        + 0.08 * recent_reliability
        + 0.08 * intraday_bridge
    )

    market_risk = numeric_series(out, "market_regime_risk_v4", 0.5).clip(lower=0.0, upper=1.0)
    sector_penalty_v4 = (numeric_series(out, "sector_risk_penalty_v4") / 0.35).clip(lower=0.0, upper=1.0)
    sector_penalty_v5 = (numeric_series(out, "sector_risk_penalty_v5") / 0.35).clip(lower=0.0, upper=1.0)
    no_trade = numeric_series(out, "v5_no_trade_flag").ge(1.0)
    largecap_only = numeric_series(out, "v5_largecap_only_flag").ge(1.0)
    attention_overheat = numeric_series(out, "v5_attention_overheat_flag").ge(1.0)
    fx_stress = numeric_series(out, "v5_fx_stress_flag").ge(1.0)

    risk_score = (
        0.45 * (1.0 - market_risk)
        + 0.20 * (1.0 - sector_penalty_v4)
        + 0.20 * (1.0 - sector_penalty_v5)
        + 0.15 * (1.0 - no_trade.astype(float))
    )
    risk_multiplier = 1.0 - 0.20 * fx_stress.astype(float) - 0.15 * attention_overheat.astype(float) - 0.10 * largecap_only.astype(float)
    risk_score = risk_score * risk_multiplier
    risk_score = risk_score * (1.0 - 0.12 * intraday_reversal)
    risk_score[no_trade] = risk_score[no_trade].clip(upper=0.30)
    out["risk_control_score"] = clip01(risk_score)

    raw_decision_score = 0.70 * out["model_signal_score"] + 0.30 * out["prediction_confidence_score"]
    risk_gate = 0.35 + 0.65 * out["risk_control_score"]
    out["decision_score"] = clip01(raw_decision_score * risk_gate)
    out["decision_score_gap_vs_total"] = out["decision_score"] - clip01(numeric_series(out, "tomorrow_total_score"))

    profile = pd.Series("mixed", index=out.index, dtype="object")
    absolute_strong = out["absolute_up_score"] >= 0.62
    absolute_weak = out["absolute_up_score"] < 0.52
    excess_strong = out["excess_strength_score"] >= 0.62
    excess_weak = out["excess_strength_score"] < 0.50
    profile[absolute_strong & excess_strong] = "core_absolute_excess"
    profile[absolute_strong & excess_weak] = "market_beta"
    profile[absolute_weak & excess_strong] = "defensive_relative"
    profile[absolute_weak & excess_weak] = "weak"
    out["decision_profile"] = profile

    label = pd.Series("low", index=out.index, dtype="object")
    medium = (
        (out["decision_score"] >= 0.50)
        & (out["prediction_confidence_score"] >= 0.35)
        & (out["risk_control_score"] >= 0.45)
    )
    high = (
        (out["decision_score"] >= 0.70)
        & (out["prediction_confidence_score"] >= 0.55)
        & (out["risk_control_score"] >= 0.65)
    )
    label[medium] = "medium"
    label[high] = "high"
    out["decision_confidence_label"] = label

    decision_action = pd.Series(ACTION_WATCH, index=out.index, dtype="object")
    decision_action[
        (out["decision_score"] < 0.38)
        | (out["decision_profile"].eq("weak") & (out["prediction_confidence_score"] < 0.50))
    ] = ACTION_AVOID
    decision_action[
        out["decision_profile"].eq("defensive_relative")
        & (out["risk_control_score"] >= 0.45)
        & (out["decision_score"] >= 0.45)
    ] = ACTION_DEFENSIVE
    decision_action[
        (out["decision_score"] >= 0.55)
        & (out["risk_control_score"] >= 0.45)
        & (
            ((out["absolute_up_score"] >= 0.58) & (out["excess_strength_score"] >= 0.50))
            | ((out["absolute_up_score"] >= 0.50) & (out["excess_strength_score"] >= 0.62))
        )
    ] = ACTION_AUX
    decision_action[
        (out["decision_score"] >= 0.68)
        & (out["prediction_confidence_score"] >= 0.42)
        & (out["risk_control_score"] >= 0.55)
        & out["decision_profile"].eq("core_absolute_excess")
    ] = ACTION_CORE
    v4_action = out.get("v4_action", pd.Series("", index=out.index)).astype(str)
    v5_action = out.get("v5_action", pd.Series("", index=out.index)).astype(str)
    decision_action[v4_action.eq(ACTION_AVOID) & (out["decision_score"] < 0.55)] = ACTION_AVOID
    decision_action[v5_action.eq(ACTION_AVOID)] = ACTION_AVOID
    decision_action[no_trade] = ACTION_AVOID
    decision_action[sector_penalty_v4 >= 0.75] = ACTION_AVOID
    out["decision_action"] = decision_action
    out["decision_policy_version"] = DECISION_POLICY_VERSION
    return out


def add_prediction_action_layers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    signal_score = clip01(numeric_series(out, "model_signal_score", 0.0))
    decision_score = clip01(numeric_series(out, "decision_score", 0.0))
    risk_control = clip01(numeric_series(out, "risk_control_score", 0.0))
    expected_return = numeric_series(out, primary_return_column(out), 0.0)
    confidence = clip01(numeric_series(out, "prediction_confidence_score", 0.0))
    final_action = out.get("final_action", pd.Series(ACTION_WATCH, index=out.index)).astype(str)
    v5_action = out.get("v5_action", pd.Series("", index=out.index)).astype(str)
    v5_reason = out.get("v5_no_trade_reason", pd.Series("", index=out.index)).astype(str)
    gate_level = out.get("ranking_quality_gate_level", pd.Series("", index=out.index)).astype(str)
    gate_reason = out.get("ranking_quality_gate_reason", pd.Series("", index=out.index)).astype(str)
    final_reason = out.get("final_action_reason", pd.Series("", index=out.index)).astype(str)

    out["prediction_layer_score"] = signal_score
    out["prediction_layer_rank"] = signal_score.rank(ascending=False, method="first").astype(int)
    out["prediction_layer_top3_flag"] = out["prediction_layer_rank"].le(3).astype(int)
    out["prediction_expected_return_pct"] = expected_return
    out["prediction_expected_return_rank"] = expected_return.rank(ascending=False, method="first").astype(int)

    prediction_label = pd.Series("중립/약함", index=out.index, dtype="object")
    prediction_label[(signal_score >= 0.62) & (expected_return > 0)] = "상승 후보"
    prediction_label[(signal_score >= 0.52) & (prediction_label.eq("중립/약함"))] = "상승 관찰"
    prediction_label[(signal_score < 0.42) | (expected_return < 0)] = "약세/불확실"
    out["prediction_layer_label"] = prediction_label

    out["action_layer_score"] = decision_score
    out["action_layer_rank"] = decision_score.rank(ascending=False, method="first").astype(int)
    out["action_layer_label"] = final_action
    out["prediction_action_score_gap"] = signal_score - decision_score

    risk_state = pd.Series("정상", index=out.index, dtype="object")
    risk_state[risk_control < 0.45] = "리스크 주의"
    risk_state[final_action.eq(ACTION_AVOID) | v5_action.eq(ACTION_NO_TRADE)] = "리스크 차단"
    risk_state[gate_level.isin(["caution", "severe"])] = risk_state[gate_level.isin(["caution", "severe"])].where(
        risk_state[gate_level.isin(["caution", "severe"])].eq("리스크 차단"),
        "품질 주의",
    )
    out["action_layer_risk_state"] = risk_state

    alignment = pd.Series("예측-행동 일치", index=out.index, dtype="object")
    positive_prediction = prediction_label.isin(["상승 후보", "상승 관찰"])
    blocked_action = final_action.isin([ACTION_AVOID, ACTION_WATCH])
    alignment[positive_prediction & blocked_action] = "상승예측-행동보류"
    alignment[~positive_prediction & final_action.eq(ACTION_AVOID)] = "약신호-회피일치"
    alignment[positive_prediction & final_action.isin([ACTION_CORE, ACTION_AUX, ACTION_DEFENSIVE])] = "상승예측-행동연결"
    out["prediction_action_alignment"] = alignment

    reasons = []
    for idx in out.index:
        parts = []
        grade = str(out.at[idx, "expected_return_grade"]) if "expected_return_grade" in out.columns else ""
        if grade:
            parts.append(f"예상수익={grade}")
        parts.append(f"신호점수={signal_score.at[idx]:.3f}")
        parts.append(f"신뢰도={confidence.at[idx]:.3f}")
        reasons.append("; ".join(parts))
    out["prediction_layer_reason"] = reasons

    action_reasons = []
    for idx in out.index:
        parts = []
        if final_reason.at[idx]:
            parts.append(final_reason.at[idx])
        if v5_reason.at[idx]:
            parts.append(f"V5={v5_reason.at[idx]}")
        if gate_reason.at[idx]:
            parts.append(f"랭킹품질={gate_reason.at[idx]}")
        action_reasons.append("; ".join(dict.fromkeys(parts)))
    out["action_layer_reason"] = action_reasons
    return out


def add_operational_action_layer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    final_action = out.get("final_action", pd.Series(ACTION_WATCH, index=out.index)).astype(str)
    panic_action = out.get("panic_watch_action", pd.Series("", index=out.index)).astype(str)

    operational = pd.Series("관망", index=out.index, dtype="object")
    operational[final_action.eq(ACTION_CORE)] = "핵심 후보"
    operational[final_action.eq(ACTION_AUX)] = "보조 후보"
    operational[final_action.eq(ACTION_DEFENSIVE)] = "방어 관찰"
    operational[final_action.eq(ACTION_WATCH)] = "관망"
    operational[final_action.eq(ACTION_AVOID)] = "회피 유지"
    operational[panic_action.eq("방어 추적")] = "방어 추적"
    operational[panic_action.eq("강한 회피")] = "강한 회피"
    out["operational_action"] = operational

    out["operational_action_rank"] = 0
    defensive = operational.eq("방어 추적")
    out.loc[defensive, "operational_action_rank"] = numeric_series(
        out, "defensive_watch_candidate_rank", 0
    )[defensive].astype(int)

    reason = pd.Series("최종 행동 기준 유지", index=out.index, dtype="object")
    reason[operational.eq("방어 추적")] = (
        "최종 행동은 회피지만, 패닉장 안에서 상대강도와 예상수익 근거가 남아 장중 회복 확인 대상으로 분리"
    )
    reason[operational.eq("회피 유지")] = "시장 패닉 게이트, 낮은 신뢰도, 약한 장중 브릿지 때문에 신규 진입 보류"
    reason[operational.eq("강한 회피")] = "시장 패닉에 섹터별 위험 페널티 또는 회피 압력이 겹쳐 우선 제외"
    reason[operational.isin(["핵심 후보", "보조 후보", "방어 관찰"])] = (
        "예측 신호와 행동 게이트가 연결되어 후보로 유지"
    )
    out["operational_action_reason"] = reason

    condition = pd.Series("현재 조건 유지", index=out.index, dtype="object")
    condition[operational.eq("방어 추적")] = (
        "시장 브레드스 회복, 장중 브릿지 0.50 이상, V5 신규진입금지 해제 확인"
    )
    condition[operational.eq("회피 유지")] = "시장 패닉 게이트 해제 전까지 관찰 후순위"
    condition[operational.eq("강한 회피")] = "패닉 완화와 섹터 위험 페널티 축소 전까지 제외"
    out["operational_confirm_condition"] = condition
    return out


def add_panic_rebound_watch_layer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    score_column = choose_panic_rebound_score_column(out)
    if score_column not in out.columns:
        out[score_column] = 0.0

    score = numeric_series(out, score_column)
    out["panic_rebound_score_rank"] = score.rank(ascending=False, method="first").astype(int)
    out["panic_rebound_score_pct"] = rank01(score)
    out["panic_rebound_relative_pct"] = rank_or_default(out, "relative_strength_component_v4")
    out["panic_rebound_qlib_pct"] = rank_or_default(out, "qlib_quality_component_v5")
    out["panic_rebound_paper_pct"] = rank_or_default(out, "paper_signal_component_v5")
    out["panic_rebound_largecap_gap_pct"] = rank_or_default(out, "krx_largecap_return_gap")
    out["panic_rebound_trade_value_pct"] = rank_or_default(out, "krx_trade_value_weighted_return")
    out["panic_rebound_overheat_pct"] = rank_or_default(out, "paper_fomo_overheat_score")
    out["panic_rebound_fx_stress_pct"] = rank_or_default(out, "paper_fx_stress_score")

    market_risk = numeric_series(out, "market_regime_risk_v4", 0.0)
    regime = out.get("market_regime_v4", pd.Series("", index=out.index)).fillna("").astype(str)
    out["panic_rebound_market_gate"] = (
        regime.isin(PANIC_REBOUND_REGIMES) | market_risk.ge(0.70)
    ).astype(int)

    out["panic_rebound_watch_score"] = clip01(
        0.30 * out["panic_rebound_score_pct"]
        + 0.25 * out["panic_rebound_relative_pct"]
        + 0.17 * out["panic_rebound_qlib_pct"]
        + 0.10 * out["panic_rebound_paper_pct"]
        + 0.10 * out["panic_rebound_largecap_gap_pct"]
        + 0.08 * out["panic_rebound_trade_value_pct"]
        - 0.06 * out["panic_rebound_overheat_pct"]
        - 0.04 * out["panic_rebound_fx_stress_pct"]
    )

    out["panic_rebound_relaxed_candidate"] = (
        out["panic_rebound_market_gate"].eq(1)
        & out["panic_rebound_score_rank"].le(5)
        & out["panic_rebound_watch_score"].ge(0.55)
        & out["panic_rebound_relative_pct"].ge(0.45)
        & out["panic_rebound_qlib_pct"].ge(0.35)
        & out["panic_rebound_overheat_pct"].le(0.90)
        & out["panic_rebound_fx_stress_pct"].le(0.95)
    ).astype(int)
    out["panic_rebound_strict_candidate"] = (
        out["panic_rebound_market_gate"].eq(1)
        & out["panic_rebound_score_rank"].le(5)
        & out["panic_rebound_watch_score"].ge(0.62)
        & out["panic_rebound_relative_pct"].ge(0.58)
        & (
            out["panic_rebound_largecap_gap_pct"].ge(0.45)
            | out["panic_rebound_trade_value_pct"].ge(0.45)
            | out["panic_rebound_qlib_pct"].ge(0.60)
        )
        & out["panic_rebound_overheat_pct"].le(0.85)
        & out["panic_rebound_fx_stress_pct"].le(0.90)
    ).astype(int)

    out["panic_rebound_candidate_rank"] = 0
    candidate = out["panic_rebound_relaxed_candidate"].eq(1)
    if candidate.any():
        out.loc[candidate, "panic_rebound_candidate_rank"] = (
            out.loc[candidate, "panic_rebound_watch_score"]
            .rank(ascending=False, method="first")
            .astype(int)
        )

    out["panic_rebound_action_label"] = "일반 판단"
    out.loc[out["panic_rebound_market_gate"].eq(1), "panic_rebound_action_label"] = "회피 유지"
    out.loc[out["panic_rebound_relaxed_candidate"].eq(1), "panic_rebound_action_label"] = "방어 관찰"
    out.loc[out["panic_rebound_strict_candidate"].eq(1), "panic_rebound_action_label"] = "방어 추적"

    reason = pd.Series("패닉 반등 후보 조건 아님", index=out.index, dtype="object")
    reason[out["panic_rebound_market_gate"].eq(1)] = "패닉/급락장으로 반등 후보 별도 점검 대상"
    reason[out["panic_rebound_relaxed_candidate"].eq(1)] = (
        "패닉장 안에서 예측 점수, 상대강도, 품질 점수가 살아 있어 방어 관찰 후보"
    )
    reason[out["panic_rebound_strict_candidate"].eq(1)] = (
        "패닉장 안에서 예측 점수와 상대강도, 대형주/거래대금 근거가 동시에 살아 있어 우선 추적 후보"
    )
    out["panic_rebound_reason"] = reason

    condition = pd.Series("시장 패닉 게이트 발생 시 재평가", index=out.index, dtype="object")
    condition[out["panic_rebound_relaxed_candidate"].eq(1)] = (
        "다음 장에서 시장 브레드스 회복, 거래대금 유지, 장중 브릿지 개선 여부 확인"
    )
    condition[out["panic_rebound_strict_candidate"].eq(1)] = (
        "방어 추적: 장 초반 수급 유지와 과열 재발 여부를 우선 확인"
    )
    out["panic_rebound_confirm_condition"] = condition
    return out


def write_prediction_action_layer_report(out: pd.DataFrame, base_date: str, target_date: str) -> None:
    path = REPORTS / "prediction_action_layer_report.md"
    lines = [
        "# 예측 레이어와 행동 레이어 분리 리포트",
        "",
        f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"- 예측 기준일: {base_date}",
        f"- 예측 대상일: {target_date}",
        "- 목적: 섹터 상승 예측과 리스크 기반 최종 행동을 분리해서 해석",
        "",
        "## 요약",
        "",
    ]
    if "prediction_action_alignment" in out.columns:
        alignment_counts = out["prediction_action_alignment"].value_counts(dropna=False).to_dict()
        lines.append(f"- 예측/행동 정렬 상태: {alignment_counts}")
    if "action_layer_risk_state" in out.columns:
        risk_counts = out["action_layer_risk_state"].value_counts(dropna=False).to_dict()
        lines.append(f"- 행동 리스크 상태: {risk_counts}")
    if "operational_action" in out.columns:
        operational_counts = out["operational_action"].value_counts(dropna=False).to_dict()
        lines.append(f"- 운영 라벨 상태: {operational_counts}")
    if "panic_rebound_action_label" in out.columns:
        rebound_counts = out["panic_rebound_action_label"].value_counts(dropna=False).to_dict()
        lines.append(f"- 패닉 반등 관찰 라벨: {rebound_counts}")
    lines.extend(
        [
            "",
            "## 예측 Top5와 최종 행동",
            "",
            "| 예측순위 | 섹터 | 예측 라벨 | 예측 점수 | 예상수익률 | 리스크 상태 | 최종 행동 | 운영 라벨 | 패닉반등 | 해석 |",
            "|---:|---|---|---:|---:|---|---|---|---|---|",
        ]
    )
    for _, row in out.sort_values("prediction_layer_rank").head(5).iterrows():
        rebound_label = str(row.get("panic_rebound_action_label", ""))
        if "panic_rebound_watch_score" in row.index:
            rebound_label = f"{rebound_label}({float(row.get('panic_rebound_watch_score', 0.0)):.3f})"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(int(row["prediction_layer_rank"])),
                    str(row["sector"]),
                    str(row["prediction_layer_label"]),
                    f"{float(row['prediction_layer_score']):.3f}",
                    f"{float(row['prediction_expected_return_pct']):.3f}",
                    str(row["action_layer_risk_state"]),
                    str(row["action_layer_label"]),
                    str(row.get("operational_action", "")),
                    rebound_label,
                    str(row["prediction_action_alignment"]),
                ]
            )
            + " |"
        )
    if "operational_action" in out.columns:
        watch = out[out["operational_action"].astype(str).eq("방어 추적")].copy()
        if not watch.empty:
            lines.extend(
                [
                    "",
                    "## 방어 추적 후보",
                    "",
                    "| 추적순위 | 섹터 | 예측순위 | 예상수익률 | 예상구간 | 확인 조건 |",
                    "|---:|---|---:|---:|---|---|",
                ]
            )
            for _, row in watch.sort_values("operational_action_rank").iterrows():
                interval = (
                    f"{float(row.get('expected_return_low_pct', 0.0)):.2f}%"
                    f" ~ {float(row.get('expected_return_high_pct', 0.0)):.2f}%"
                )
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(int(row.get("operational_action_rank", 0))),
                            str(row["sector"]),
                            str(int(row["prediction_layer_rank"])),
                            f"{float(row['prediction_expected_return_pct']):.3f}%",
                            interval,
                            str(row.get("operational_confirm_condition", "")),
                        ]
                    )
                    + " |"
                )
    if "panic_rebound_action_label" in out.columns:
        rebound = out[numeric_series(out, "panic_rebound_relaxed_candidate").astype(int).eq(1)].copy()
        if not rebound.empty:
            lines.extend(
                [
                    "",
                    "## 패닉 반등 관찰 후보",
                    "",
                    "| 반등순위 | 섹터 | 반등라벨 | 반등점수 | 예측순위 | 최종 행동 | 확인 조건 |",
                    "|---:|---|---|---:|---:|---|---|",
                ]
            )
            for _, row in rebound.sort_values("panic_rebound_candidate_rank").iterrows():
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(int(row.get("panic_rebound_candidate_rank", 0))),
                            str(row["sector"]),
                            str(row.get("panic_rebound_action_label", "")),
                            f"{float(row.get('panic_rebound_watch_score', 0.0)):.3f}",
                            str(int(row.get("prediction_layer_rank", 0))),
                            str(row.get("final_action", "")),
                            str(row.get("panic_rebound_confirm_condition", "")),
                        ]
                    )
                    + " |"
                )
    lines.extend(
        [
            "",
            "## 운영 해석",
            "",
            "- `prediction_layer_*`는 모델이 상대적으로 강하다고 본 섹터 후보를 의미한다.",
            "- `action_layer_*`는 시장 국면, 랭킹 품질, no-trade 게이트를 반영한 최종 행동 판단이다.",
            "- `operational_action`은 최종 행동과 별도로 패닉장 안에서 장중 확인할 후보를 분리한 운영 라벨이다.",
            "- `panic_rebound_*`는 급락장 이후 반등 주도 가능성을 표시하는 관찰 레이어이며, 최종 행동을 자동 완화하지 않는다.",
            "- `상승예측-행동보류`는 모델 신호는 있으나 리스크 조건 때문에 신규 진입을 막은 상태다.",
            "- 이 리포트는 투자 추천이 아니라 모델 해석과 검증을 위한 산출물이다.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_expected_return_interval_report(out: pd.DataFrame, base_date: str, target_date: str) -> None:
    path = REPORTS / "expected_return_interval_report.md"
    lines = [
        "# 예상수익률 구간 해석 리포트",
        "",
        f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"- 예측 기준일: {base_date}",
        f"- 예측 대상일: {target_date}",
        "- 목적: 예상수익률을 단일 숫자가 아니라 중심값, 하단, 상단, 구간 폭, 신뢰도로 해석한다.",
        "",
        "## 요약",
        "",
    ]
    if "return_interval_label" in out.columns:
        lines.append(f"- 구간 라벨 분포: {out['return_interval_label'].value_counts(dropna=False).to_dict()}")
    if "return_interval_confidence_label" in out.columns:
        lines.append(
            f"- 구간 신뢰도 분포: {out['return_interval_confidence_label'].value_counts(dropna=False).to_dict()}"
        )
    if "return_interval_calibration_enabled" in out.columns:
        enabled_counts = out["return_interval_calibration_enabled"].value_counts(dropna=False).to_dict()
        avg_lower_padding = float(numeric_series(out, "return_interval_lower_calibration_padding_pct").mean())
        avg_upper_padding = float(numeric_series(out, "return_interval_upper_calibration_padding_pct").mean())
        coverage_rate = pd.to_numeric(
            out.get("return_interval_calibration_coverage_rate", pd.Series(dtype="float64")),
            errors="coerce",
        ).dropna()
        below_rate = pd.to_numeric(
            out.get("return_interval_calibration_below_lower_rate", pd.Series(dtype="float64")),
            errors="coerce",
        ).dropna()
        lines.extend(
            [
                "",
                "## 구간 보정",
                "",
                f"- 보정 적용 분포: {enabled_counts}",
                f"- 평균 하단 보정폭: {avg_lower_padding:.3f}%p",
                f"- 평균 상단 보정폭: {avg_upper_padding:.3f}%p",
                f"- 최근 구간 적중률: {float(coverage_rate.iloc[0]):.3f}" if not coverage_rate.empty else "- 최근 구간 적중률: 없음",
                f"- 최근 하단 이탈률: {float(below_rate.iloc[0]):.3f}" if not below_rate.empty else "- 최근 하단 이탈률: 없음",
            ]
        )
    widest = (
        out.sort_values("return_interval_width_pct", ascending=False).head(3)["sector"].astype(str).tolist()
        if "return_interval_width_pct" in out.columns
        else []
    )
    lines.append(f"- 오차 구간이 가장 넓은 섹터: {widest}")
    lines.extend(
        [
            "",
            "## 구간 신호 Top5",
            "",
            "| 구간순위 | 섹터 | 중심값 | 하단 | 상단 | 폭 | 구간 라벨 | 신뢰도 | 해석 |",
            "|---:|---|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for _, row in out.sort_values("return_interval_strength_rank").head(5).iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(int(row["return_interval_strength_rank"])),
                    str(row["sector"]),
                    f"{float(row['return_interval_center_pct']):.3f}",
                    f"{float(row['return_interval_lower_pct']):.3f}",
                    f"{float(row['return_interval_upper_pct']):.3f}",
                    f"{float(row['return_interval_width_pct']):.3f}",
                    str(row["return_interval_label"]),
                    str(row["return_interval_confidence_label"]),
                    str(row["return_interval_action_note"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 운영 해석",
            "",
            "- `return_interval_center_pct`는 모델이 본 예상수익률의 중심값이다.",
            "- `return_interval_lower_pct`와 `return_interval_upper_pct`는 보수적 하단/상단 구간이다.",
            "- 하단이 음수이면 중심값이 양수여도 실제 손실 가능성을 함께 봐야 한다.",
            "- 구간 폭이 넓으면 예측 방향보다 불확실성이 큰 상태로 해석한다.",
            "- 이 리포트는 예측 해석과 사후 검증을 위한 산출물이며 투자 추천이 아니다.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    base_date, target_date = prediction_dates()
    controls = calendar_control_variables(base_date, target_date)
    advisor = pd.read_csv(REPORTS / "daily_portfolio_advisor.csv", encoding="utf-8-sig")
    df = merge_v3(advisor)
    df = merge_v4(df)
    df = merge_v5(df)
    df = merge_weekend_effects(df)
    df = merge_intraday_bridge(df)

    numeric_fill(
        df,
        [
            "primary_next_return_pred",
            "ensemble_v2_next_return_pred",
            "expected_return_model_q10_pct",
            "expected_return_model_q50_pct",
            "expected_return_model_q90_pct",
            "expected_return_mid_pct",
            "expected_return_low_pct",
            "expected_return_high_pct",
            "expected_return_error_p80_pct",
            "expected_return_signal_to_noise",
            "expected_return_confidence_score",
            "combined_up_proba",
            "quality_adjusted_up_proba",
            "calibrated_absolute_up_proba",
            "calibrated_quality_adjusted_up_proba",
            "calibrated_meaningful_up_proba",
            "calibrated_excess_up_proba",
            "calibrated_tradeable_up_proba",
            "meaningful_up_proba",
            "excess_up_proba",
            "tradeable_up_proba",
            "market_direction_score",
            "market_sector_return_mean",
            "market_sector_positive_ratio",
            "market_sector_negative_ratio",
            "market_breadth_mean",
            "market_return_ma3",
            "market_direction_score_ma3",
            "sector_vs_market_return_gap",
            "sector_market_alignment",
            "live_fomo_score",
            "expected_effect_score",
            "weekend_attention_score",
            "fomo_freshness_weight",
            "final_rank_score_v3",
            "bottom3_proba_v3",
            "final_rank_score_v4",
            "final_rank_score_v5",
            "market_regime_risk_v4",
            "sector_risk_penalty_v4",
            "relative_strength_component_v4",
            "sector_risk_penalty_v5",
            "v5_no_trade_flag",
            "v5_largecap_only_flag",
            "v5_attention_overheat_flag",
            "v5_fx_stress_flag",
            "paper_signal_component_v5",
            "paper_attention_score",
            "paper_fomo_overheat_score",
            "paper_attention_reversal_pressure",
            "paper_attention_rebound_pressure",
            "paper_fx_stress_score",
            "paper_graph_neighbor_mom_3d",
            "paper_graph_relative_strength",
            "intraday_rebound_score",
            "intraday_continuation_score",
            "intraday_reversal_risk",
            "intraday_bridge_score",
            "intraday_bridge_adjustment",
            "intraday_signal_sector_return",
            "intraday_signal_advancers_ratio",
            "intraday_signal_trade_value_rank",
        ],
        default=0.0,
    )
    if df["quality_adjusted_up_proba"].eq(0).all() and df["combined_up_proba"].ne(0).any():
        df["quality_adjusted_up_proba"] = df["combined_up_proba"]
    calibration_fallbacks = {
        "calibrated_absolute_up_proba": "combined_up_proba",
        "calibrated_quality_adjusted_up_proba": "quality_adjusted_up_proba",
        "calibrated_meaningful_up_proba": "meaningful_up_proba",
        "calibrated_excess_up_proba": "excess_up_proba",
        "calibrated_tradeable_up_proba": "tradeable_up_proba",
    }
    for calibrated_col, raw_col in calibration_fallbacks.items():
        if df[calibrated_col].eq(0).all() and df[raw_col].ne(0).any():
            df[calibrated_col] = df[raw_col]
    df = add_return_primary_total_score(df)
    df = apply_fomo_blend_overlay(df)
    df = apply_intraday_bridge_adjustment(df)

    df = apply_recent_reliability_calibration(df)
    df = apply_score_safety_caps(df)
    df = add_decision_layer_scores(df)
    df = apply_backtest_confidence_calibration(df, target_date=target_date)
    df = apply_return_interval_calibration(df)
    df = add_return_risk_reward_layer(df)
    df = add_expected_return_interval_layer(df)
    df["score_action"] = assign_actions(df)
    df = add_final_actions(df)
    df = apply_ranking_quality_gate(df)
    df = add_signal_conflict_explanations(df)
    df = add_avoid_pressure_diagnostics(df)
    df = add_prediction_action_layers(df)
    df = add_operational_action_layer(df)
    df = add_panic_rebound_watch_layer(df)

    cols = [
        "sector",
        "prediction_layer_rank",
        "prediction_layer_label",
        "prediction_layer_score",
        "prediction_layer_top3_flag",
        "prediction_expected_return_pct",
        "prediction_expected_return_rank",
        "return_interval_strength_rank",
        "return_interval_label",
        "return_interval_center_pct",
        "return_interval_lower_pct",
        "return_interval_upper_pct",
        "return_interval_width_pct",
        "return_interval_confidence_label",
        "return_interval_strength_score",
        "return_interval_interpretation",
        "return_interval_action_note",
        "prediction_layer_reason",
        "action_layer_rank",
        "action_layer_label",
        "action_layer_score",
        "action_layer_risk_state",
        "action_layer_reason",
        "prediction_action_score_gap",
        "prediction_action_alignment",
        "tomorrow_total_score",
        "final_action",
        "tomorrow_action",
        "score_action",
        "decision_action",
        "action_conflict_flag",
        "final_action_reason",
        "ranking_quality_gate_level",
        "ranking_quality_gate_reason",
        "ranking_quality_gate_downgrade",
        "ranking_quality_gate_warning_count",
        "ranking_quality_gate_latest_date",
        "ranking_quality_all_rank_ic_spearman",
        "ranking_quality_all_top3_overlap",
        "ranking_quality_last5_rank_ic_spearman",
        "ranking_quality_last5_top3_spread",
        "ranking_quality_last10_rank_ic_spearman",
        "ranking_quality_last10_top3_spread",
        "avoid_gate_count",
        "avoid_pressure_score",
        "avoid_pressure_note",
        "panic_watch_action",
        "operational_action",
        "operational_action_rank",
        "operational_action_reason",
        "operational_confirm_condition",
        "panic_rebound_action_label",
        "panic_rebound_candidate_rank",
        "panic_rebound_watch_score",
        "panic_rebound_market_gate",
        "panic_rebound_score_rank",
        "panic_rebound_score_pct",
        "panic_rebound_relative_pct",
        "panic_rebound_qlib_pct",
        "panic_rebound_paper_pct",
        "panic_rebound_largecap_gap_pct",
        "panic_rebound_trade_value_pct",
        "panic_rebound_overheat_pct",
        "panic_rebound_fx_stress_pct",
        "panic_rebound_relaxed_candidate",
        "panic_rebound_strict_candidate",
        "panic_rebound_reason",
        "panic_rebound_confirm_condition",
        "defensive_watch_candidate_flag",
        "defensive_watch_candidate_score",
        "defensive_watch_candidate_rank",
        "signal_conflict_type",
        "signal_conflict_score",
        "positive_signal_count",
        "risk_block_count",
        "final_decision_explanation",
        "entry_condition_note",
        "decision_profile",
        "rank_model_score",
        "model_signal_score",
        "absolute_up_score",
        "excess_strength_score",
        "expected_return_score",
        "expected_return_risk_adjusted_score",
        "return_risk_score_adjustment",
        "prediction_confidence_score",
        "risk_control_score",
        "decision_score",
        "decision_score_gap_vs_total",
        "decision_confidence_label",
        "rule_confidence_label",
        "confidence_reliability_score",
        "confidence_empirical_hit_rate",
        "confidence_empirical_avg_return",
        "confidence_empirical_downside_rate",
        "confidence_reliability_n",
        "confidence_reference_rows",
        "confidence_reference_end_date",
        "confidence_label_source",
        "decision_policy_version",
        "primary_next_return_pred",
        "ensemble_v2_next_return_pred",
        "expected_return_model_q10_pct",
        "expected_return_model_q50_pct",
        "expected_return_model_q90_pct",
        "expected_return_mid_pct",
        "expected_return_low_pct",
        "expected_return_high_pct",
        "expected_return_error_p80_pct",
        "expected_return_low_pct_raw",
        "expected_return_high_pct_raw",
        "expected_return_error_p80_pct_raw",
        "return_interval_calibration_enabled",
        "return_interval_calibration_reason",
        "return_interval_calibration_window",
        "return_interval_calibration_coverage_rate",
        "return_interval_calibration_below_lower_rate",
        "return_interval_calibration_base_lower_padding_pct",
        "return_interval_calibration_base_upper_padding_pct",
        "return_interval_lower_calibration_padding_pct",
        "return_interval_upper_calibration_padding_pct",
        "expected_return_interval_width_pct",
        "expected_return_downside_room_pct",
        "expected_return_upside_room_pct",
        "expected_return_risk_reward_ratio",
        "expected_return_upside_downside_ratio",
        "expected_return_signal_to_noise",
        "expected_return_confidence_score",
        "expected_return_confidence",
        "expected_return_range_label",
        "expected_return_grade",
        "expected_return_grade_reason",
        "combined_up_proba",
        "quality_adjusted_up_proba",
        "calibrated_absolute_up_proba",
        "calibrated_quality_adjusted_up_proba",
        "meaningful_up_proba",
        "calibrated_meaningful_up_proba",
        "excess_up_proba",
        "calibrated_excess_up_proba",
        "tradeable_up_proba",
        "calibrated_tradeable_up_proba",
        "market_direction_score",
        "market_sector_return_mean",
        "market_sector_positive_ratio",
        "market_sector_negative_ratio",
        "market_breadth_mean",
        "market_return_ma3",
        "market_direction_score_ma3",
        "sector_vs_market_return_gap",
        "sector_market_alignment",
        "expected_effect_score",
        "expected_effect_score_raw",
        "weekend_attention_score",
        "weekend_attention_score_raw",
        "fomo_freshness_status",
        "fomo_freshness_weight",
        "fomo_freshness_reason",
        "fomo_evidence_weight",
        "fomo_risk_pressure",
        "fomo_risk_discount",
        "fomo_final_weight",
        "fomo_weight_reason",
        "fomo_overlay_score",
        "fomo_blend_weight",
        "fomo_blend_validation_window",
        "fomo_blend_generated_at",
        "tomorrow_total_score_pre_fomo_blend",
        "fomo_source_latest_at",
        "fomo_target_date",
        "live_fomo_score",
        "advisor_grade",
        "calibration_adjusted_grade",
        "news_3d",
        "news_momentum",
        "news_decay_score",
        "news_attention_acceleration",
        "attention_reversal_risk",
        "sector_intraday_return",
        "sector_trade_value",
        "sector_trade_value_weighted_return",
        "sector_top2_trade_value_weighted_return",
        "sector_top2_trade_value_share",
        "final_rank_score_v5",
        "v5_action",
        "v5_no_trade_reason",
        "v5_no_trade_flag",
        "v5_largecap_only_flag",
        "v5_weak_breadth_flag",
        "v5_attention_overheat_flag",
        "v5_fx_stress_flag",
        "qlib_quality_component_v5",
        "paper_signal_component_v5",
        "paper_attention_score",
        "paper_fomo_overheat_score",
        "paper_attention_reversal_pressure",
        "paper_attention_rebound_pressure",
        "paper_fx_stress_score",
        "paper_graph_neighbor_mom_3d",
        "sector_risk_penalty_v5",
        "krx_trade_value_weighted_return",
        "krx_top2_trade_value_weighted_return",
        "krx_top2_trade_value_share",
        "krx_largecap_return_gap",
        "final_rank_score_v4",
        "v4_action",
        "market_regime_v4",
        "market_regime_risk_v4",
        "market_gate_v4",
        "sector_risk_penalty_v4",
        "relative_strength_component_v4",
        "xgb_component_v4",
        "final_rank_score_v3",
        "v3_action",
        "top3_proba_v3",
        "bottom3_proba_v3",
        "pred_next_excess_return_v3",
        "risk_penalty_v3",
        "paper_graph_relative_strength",
        "recent_sector_n",
        "recent_sector_hit_rate",
        "recent_sector_avg_return",
        "score_calibration_adj",
        "intraday_rebound_score",
        "intraday_continuation_score",
        "intraday_reversal_risk",
        "intraday_bridge_score",
        "intraday_bridge_adjustment",
        "intraday_bridge_model_alignment",
        "intraday_bridge_score_adjustment",
        "intraday_bridge_comment",
        "intraday_signal_label",
        "intraday_signal_sector_return",
        "intraday_signal_advancers_ratio",
        "intraday_signal_trade_value_rank",
        "rebound_phase",
        "estimated_rebound_window",
        "collected_at",
    ]
    out = df[[c for c in cols if c in df.columns]].sort_values("tomorrow_total_score", ascending=False)
    out.insert(0, "market_day_state", controls["market_day_state"])
    out.insert(1, "collection_mode", controls["collection_mode"])
    out.insert(2, "prediction_target_state", controls["prediction_target_state"])
    out.insert(3, "target_gap_days", controls["target_gap_days"])
    append_history(out, base_date, target_date, controls)
    out.to_csv(REPORTS / "tomorrow_sector_prediction.csv", index=False, encoding="utf-8-sig")
    write_prediction_action_layer_report(out, base_date, target_date)
    write_expected_return_interval_report(out, base_date, target_date)
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "prediction_base_date": base_date,
        "prediction_target_date": target_date,
        "market_day_state": controls["market_day_state"],
        "collection_mode": controls["collection_mode"],
        "prediction_target_state": controls["prediction_target_state"],
        "target_gap_days": controls["target_gap_days"],
        "rows": int(len(out)),
        "top_sectors": out.head(5)["sector"].tolist(),
        "prediction_layer_top_sectors": out.sort_values("prediction_layer_rank").head(5)["sector"].tolist()
        if "prediction_layer_rank" in out.columns
        else [],
        "top_decision_sectors": out.sort_values("decision_score", ascending=False).head(5)["sector"].tolist()
        if "decision_score" in out.columns
        else [],
        "action_layer_top_sectors": out.sort_values("action_layer_rank").head(5)["sector"].tolist()
        if "action_layer_rank" in out.columns
        else [],
        "prediction_action_alignment_counts": out["prediction_action_alignment"].value_counts(dropna=False).to_dict()
        if "prediction_action_alignment" in out.columns
        else {},
        "action_layer_risk_state_counts": out["action_layer_risk_state"].value_counts(dropna=False).to_dict()
        if "action_layer_risk_state" in out.columns
        else {},
        "prediction_action_layer_report": "reports/prediction_action_layer_report.md",
        "decision_policy_version": DECISION_POLICY_VERSION,
        "fomo_blend_weight": float(pd.to_numeric(out.get("fomo_blend_weight", 0.0), errors="coerce").fillna(0.0).max())
        if "fomo_blend_weight" in out.columns
        else 0.0,
        "fomo_blend_validation_window": str(out["fomo_blend_validation_window"].dropna().iloc[0])
        if "fomo_blend_validation_window" in out.columns and out["fomo_blend_validation_window"].dropna().size
        else "",
        "ranking_quality_gate_level": str(out["ranking_quality_gate_level"].dropna().iloc[0])
        if "ranking_quality_gate_level" in out.columns and out["ranking_quality_gate_level"].dropna().size
        else "",
        "ranking_quality_gate_reason": str(out["ranking_quality_gate_reason"].dropna().iloc[0])
        if "ranking_quality_gate_reason" in out.columns and out["ranking_quality_gate_reason"].dropna().size
        else "",
        "ranking_quality_gate_downgrade_count": int(
            pd.to_numeric(out.get("ranking_quality_gate_downgrade", 0), errors="coerce").fillna(0).sum()
        ),
        "ranking_quality_gate_warning_count": int(
            pd.to_numeric(out.get("ranking_quality_gate_warning_count", 0), errors="coerce").fillna(0).max()
        )
        if "ranking_quality_gate_warning_count" in out.columns
        else 0,
        "ranking_quality_gate_metrics": {
            "latest_date": str(out["ranking_quality_gate_latest_date"].dropna().iloc[0])
            if "ranking_quality_gate_latest_date" in out.columns and out["ranking_quality_gate_latest_date"].dropna().size
            else "",
            "all_rank_ic_spearman": float(
                pd.to_numeric(out.get("ranking_quality_all_rank_ic_spearman", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_all_rank_ic_spearman" in out.columns
            and pd.to_numeric(out["ranking_quality_all_rank_ic_spearman"], errors="coerce").dropna().size
            else None,
            "all_top3_overlap": float(
                pd.to_numeric(out.get("ranking_quality_all_top3_overlap", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_all_top3_overlap" in out.columns
            and pd.to_numeric(out["ranking_quality_all_top3_overlap"], errors="coerce").dropna().size
            else None,
            "last5_rank_ic_spearman": float(
                pd.to_numeric(out.get("ranking_quality_last5_rank_ic_spearman", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_last5_rank_ic_spearman" in out.columns
            and pd.to_numeric(out["ranking_quality_last5_rank_ic_spearman"], errors="coerce").dropna().size
            else None,
            "last5_top3_spread": float(
                pd.to_numeric(out.get("ranking_quality_last5_top3_spread", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_last5_top3_spread" in out.columns
            and pd.to_numeric(out["ranking_quality_last5_top3_spread"], errors="coerce").dropna().size
            else None,
            "last10_rank_ic_spearman": float(
                pd.to_numeric(out.get("ranking_quality_last10_rank_ic_spearman", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_last10_rank_ic_spearman" in out.columns
            and pd.to_numeric(out["ranking_quality_last10_rank_ic_spearman"], errors="coerce").dropna().size
            else None,
            "last10_top3_spread": float(
                pd.to_numeric(out.get("ranking_quality_last10_top3_spread", 0), errors="coerce").dropna().iloc[0]
            )
            if "ranking_quality_last10_top3_spread" in out.columns
            and pd.to_numeric(out["ranking_quality_last10_top3_spread"], errors="coerce").dropna().size
            else None,
        },
        "final_action_counts": out["final_action"].value_counts(dropna=False).to_dict()
        if "final_action" in out.columns
        else {},
        "score_action_counts": out["score_action"].value_counts(dropna=False).to_dict()
        if "score_action" in out.columns
        else {},
        "decision_action_counts": out["decision_action"].value_counts(dropna=False).to_dict()
        if "decision_action" in out.columns
        else {},
        "action_conflict_count": int(pd.to_numeric(out.get("action_conflict_flag", 0), errors="coerce").fillna(0).sum()),
        "signal_conflict_type_counts": out["signal_conflict_type"].value_counts(dropna=False).to_dict()
        if "signal_conflict_type" in out.columns
        else {},
        "avoid_pressure_top_sectors": out.sort_values("avoid_pressure_score", ascending=False)
        .head(5)["sector"]
        .tolist()
        if "avoid_pressure_score" in out.columns
        else [],
        "defensive_watch_candidate_count": int(
            pd.to_numeric(out.get("defensive_watch_candidate_flag", 0), errors="coerce").fillna(0).sum()
        ),
        "defensive_watch_candidate_sectors": out.loc[
            pd.to_numeric(out.get("defensive_watch_candidate_flag", 0), errors="coerce").fillna(0).astype(int).eq(1)
        ]
        .sort_values("defensive_watch_candidate_rank")
        .head(5)["sector"]
        .tolist()
        if "defensive_watch_candidate_flag" in out.columns
        else [],
        "panic_watch_action_counts": out["panic_watch_action"].value_counts(dropna=False).to_dict()
        if "panic_watch_action" in out.columns
        else {},
        "operational_action_counts": out["operational_action"].value_counts(dropna=False).to_dict()
        if "operational_action" in out.columns
        else {},
        "operational_watch_sectors": out.loc[
            out.get("operational_action", pd.Series("", index=out.index)).astype(str).eq("방어 추적")
        ]
        .sort_values("operational_action_rank")
        .head(5)["sector"]
        .tolist()
        if "operational_action" in out.columns
        else [],
        "panic_rebound_action_counts": out["panic_rebound_action_label"].value_counts(dropna=False).to_dict()
        if "panic_rebound_action_label" in out.columns
        else {},
        "panic_rebound_candidate_count": int(numeric_series(out, "panic_rebound_relaxed_candidate").astype(int).sum())
        if "panic_rebound_relaxed_candidate" in out.columns
        else 0,
        "panic_rebound_strict_candidate_count": int(
            numeric_series(out, "panic_rebound_strict_candidate").astype(int).sum()
        )
        if "panic_rebound_strict_candidate" in out.columns
        else 0,
        "panic_rebound_candidate_sectors": out.loc[
            numeric_series(out, "panic_rebound_relaxed_candidate").astype(int).eq(1)
        ]
        .sort_values("panic_rebound_candidate_rank")
        .head(5)["sector"]
        .tolist()
        if "panic_rebound_relaxed_candidate" in out.columns
        else [],
        "panic_rebound_strict_candidate_sectors": out.loc[
            numeric_series(out, "panic_rebound_strict_candidate").astype(int).eq(1)
        ]
        .sort_values("panic_rebound_candidate_rank")
        .head(5)["sector"]
        .tolist()
        if "panic_rebound_strict_candidate" in out.columns
        else [],
        "high_signal_conflict_sectors": out.sort_values("signal_conflict_score", ascending=False)
        .head(5)["sector"]
        .tolist()
        if "signal_conflict_score" in out.columns
        else [],
        "decision_profile_counts": out["decision_profile"].value_counts(dropna=False).to_dict()
        if "decision_profile" in out.columns
        else {},
        "decision_confidence_counts": out["decision_confidence_label"].value_counts(dropna=False).to_dict()
        if "decision_confidence_label" in out.columns
        else {},
        "expected_return_grade_counts": out["expected_return_grade"].value_counts(dropna=False).to_dict()
        if "expected_return_grade" in out.columns
        else {},
        "return_interval_label_counts": out["return_interval_label"].value_counts(dropna=False).to_dict()
        if "return_interval_label" in out.columns
        else {},
        "return_interval_confidence_counts": out["return_interval_confidence_label"].value_counts(dropna=False).to_dict()
        if "return_interval_confidence_label" in out.columns
        else {},
        "return_interval_top_sectors": out.sort_values("return_interval_strength_rank").head(5)["sector"].tolist()
        if "return_interval_strength_rank" in out.columns
        else [],
        "return_interval_widest_sectors": out.sort_values("return_interval_width_pct", ascending=False)
        .head(5)["sector"]
        .tolist()
        if "return_interval_width_pct" in out.columns
        else [],
        "return_interval_calibration_enabled_counts": out["return_interval_calibration_enabled"]
        .value_counts(dropna=False)
        .to_dict()
        if "return_interval_calibration_enabled" in out.columns
        else {},
        "return_interval_avg_lower_calibration_padding": float(
            numeric_series(out, "return_interval_lower_calibration_padding_pct").mean()
        ),
        "return_interval_avg_upper_calibration_padding": float(
            numeric_series(out, "return_interval_upper_calibration_padding_pct").mean()
        ),
        "return_interval_calibration_summary": str(RETURN_INTERVAL_CALIBRATION_SUMMARY_PATH.relative_to(ROOT)),
        "expected_return_interval_report": str((REPORTS / "expected_return_interval_report.md").relative_to(ROOT)),
        "top_return_risk_adjusted_sectors": out.sort_values("expected_return_risk_adjusted_score", ascending=False)
        .head(5)["sector"]
        .tolist()
        if "expected_return_risk_adjusted_score" in out.columns
        else [],
        "avg_return_risk_score_adjustment": float(
            pd.to_numeric(out.get("return_risk_score_adjustment", 0), errors="coerce").fillna(0.0).mean()
        ),
        "rule_confidence_counts": out["rule_confidence_label"].value_counts(dropna=False).to_dict()
        if "rule_confidence_label" in out.columns
        else {},
        "confidence_label_source_counts": out["confidence_label_source"].value_counts(dropna=False).to_dict()
        if "confidence_label_source" in out.columns
        else {},
        "confidence_reference_rows": int(pd.to_numeric(out.get("confidence_reference_rows", 0), errors="coerce").max())
        if "confidence_reference_rows" in out.columns
        else 0,
        "confidence_reference_end_date": str(out["confidence_reference_end_date"].dropna().iloc[0])
        if "confidence_reference_end_date" in out.columns and out["confidence_reference_end_date"].dropna().size
        else "",
        "intraday_bridge_top_sectors": out.sort_values("intraday_bridge_score", ascending=False).head(5)["sector"].tolist()
        if "intraday_bridge_score" in out.columns
        else [],
        "intraday_reversal_risk_top_sectors": out.sort_values("intraday_reversal_risk", ascending=False).head(5)[
            "sector"
        ].tolist()
        if "intraday_reversal_risk" in out.columns
        else [],
        "v4_enabled": bool("final_rank_score_v4" in out.columns and out["final_rank_score_v4"].notna().any()),
        "v5_enabled": bool("final_rank_score_v5" in out.columns and out["final_rank_score_v5"].notna().any()),
        "v5_no_trade_count": int(out["v5_action"].astype(str).eq(ACTION_NO_TRADE).sum())
        if "v5_action" in out.columns
        else 0,
    }
    (REPORTS / "tomorrow_sector_prediction_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
