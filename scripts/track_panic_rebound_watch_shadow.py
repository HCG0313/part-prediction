from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

BACKTEST_SOURCE_PATH = REPORTS / "sector_rank_model_v5_backtest_predictions.csv"
CURRENT_PREDICTION_PATH = REPORTS / "tomorrow_sector_prediction.csv"

BACKTEST_OUTPUT_PATH = REPORTS / "panic_rebound_watch_shadow_backtest.csv"
STRATEGY_OUTPUT_PATH = REPORTS / "panic_rebound_watch_shadow_strategy_performance.csv"
LATEST_OUTPUT_PATH = REPORTS / "panic_rebound_watch_shadow_latest_candidates.csv"
SUMMARY_OUTPUT_PATH = REPORTS / "panic_rebound_watch_shadow_summary.json"
REPORT_OUTPUT_PATH = REPORTS / "panic_rebound_watch_shadow_report.md"

MODEL_VERSION = "panic_rebound_watch_shadow_v1"
PANIC_REGIMES = {"capitulation", "risk_off_selloff"}
TOP_K = 3


def configure_utf8() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def clean_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def json_ready(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if hasattr(value, "item"):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def records_for_json(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: json_ready(value) for key, value in row.items()} for row in frame.to_dict("records")]


def format_number(value: Any, digits: int = 4) -> str:
    number = clean_number(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def format_percent(value: Any, digits: int = 1) -> str:
    number = clean_number(value)
    if number is None:
        return "-"
    return f"{number * 100:.{digits}f}%"


def numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(default)


def rank_pct_by_date(df: pd.DataFrame, column: str, default: float = 0.5, ascending: bool = True) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    values = pd.to_numeric(df[column], errors="coerce")
    ranked = values.groupby(df["date"]).rank(pct=True, method="average", ascending=ascending)
    return ranked.fillna(default).astype(float)


def load_backtest() -> pd.DataFrame:
    if not BACKTEST_SOURCE_PATH.exists():
        raise FileNotFoundError(f"Missing backtest source: {BACKTEST_SOURCE_PATH}")
    df = pd.read_csv(BACKTEST_SOURCE_PATH, encoding="utf-8-sig")
    required = {
        "date",
        "sector",
        "market_regime_v4",
        "market_regime_risk_v4",
        "final_rank_score_v5",
        "relative_strength_component_v4",
        "next_sector_return",
        "next_sector_excess_return",
        "future_excess_rank",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Backtest source is missing required columns: {missing}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date", "sector"]).copy()
    return df.sort_values(["date", "sector"]).reset_index(drop=True)


def choose_current_score_column(current: pd.DataFrame) -> str:
    for column in ["prediction_layer_score", "rank_model_score", "tomorrow_total_score", "final_rank_score_v5"]:
        if column in current.columns and pd.to_numeric(current[column], errors="coerce").notna().any():
            return column
    raise ValueError("Current prediction file has no usable score column.")


def add_shadow_features(df: pd.DataFrame, score_column: str = "final_rank_score_v5") -> pd.DataFrame:
    out = df.copy()
    if score_column not in out.columns:
        out[score_column] = 0.0

    out["panic_rebound_score_rank"] = out.groupby("date")[score_column].rank(ascending=False, method="first")
    out["panic_rebound_score_pct"] = rank_pct_by_date(out, score_column, ascending=True)
    out["panic_rebound_relative_pct"] = rank_pct_by_date(out, "relative_strength_component_v4", ascending=True)
    out["panic_rebound_qlib_pct"] = rank_pct_by_date(out, "qlib_quality_component_v5", ascending=True)
    out["panic_rebound_paper_pct"] = rank_pct_by_date(out, "paper_signal_component_v5", ascending=True)
    out["panic_rebound_largecap_gap_pct"] = rank_pct_by_date(out, "krx_largecap_return_gap", ascending=True)
    out["panic_rebound_trade_value_pct"] = rank_pct_by_date(out, "krx_trade_value_weighted_return", ascending=True)
    out["panic_rebound_overheat_pct"] = rank_pct_by_date(out, "paper_fomo_overheat_score", ascending=True)
    out["panic_rebound_fx_stress_pct"] = rank_pct_by_date(out, "paper_fx_stress_score", ascending=True)

    market_risk = numeric(out, "market_regime_risk_v4", 0.0)
    regime = out["market_regime_v4"].fillna("").astype(str)
    out["panic_rebound_market_gate"] = (regime.isin(PANIC_REGIMES) | market_risk.ge(0.70)).astype(int)

    out["panic_rebound_watch_score"] = (
        0.30 * out["panic_rebound_score_pct"]
        + 0.25 * out["panic_rebound_relative_pct"]
        + 0.17 * out["panic_rebound_qlib_pct"]
        + 0.10 * out["panic_rebound_paper_pct"]
        + 0.10 * out["panic_rebound_largecap_gap_pct"]
        + 0.08 * out["panic_rebound_trade_value_pct"]
        - 0.06 * out["panic_rebound_overheat_pct"]
        - 0.04 * out["panic_rebound_fx_stress_pct"]
    ).clip(0.0, 1.0)

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
    candidate_mask = out["panic_rebound_relaxed_candidate"].eq(1)
    if candidate_mask.any():
        out.loc[candidate_mask, "panic_rebound_candidate_rank"] = (
            out.loc[candidate_mask]
            .groupby("date")["panic_rebound_watch_score"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    out["panic_rebound_strict_top2"] = (
        out["panic_rebound_strict_candidate"].eq(1) & out["panic_rebound_candidate_rank"].between(1, 2)
    ).astype(int)
    out["panic_rebound_action_label"] = "일반 판단"
    out.loc[out["panic_rebound_market_gate"].eq(1), "panic_rebound_action_label"] = "회피 유지"
    out.loc[out["panic_rebound_relaxed_candidate"].eq(1), "panic_rebound_action_label"] = "방어 관찰"
    out.loc[out["panic_rebound_strict_candidate"].eq(1), "panic_rebound_action_label"] = "방어 추적"
    return out


def summarize_strategy(df: pd.DataFrame, flag_col: str) -> dict[str, Any]:
    selected = df[df[flag_col].eq(1)].copy()
    evaluated = selected.dropna(subset=["next_sector_return", "next_sector_excess_return"]).copy()
    if evaluated.empty:
        return {
            "strategy": flag_col,
            "selected_rows": int(len(selected)),
            "evaluated_rows": 0,
            "evaluated_days": 0,
            "avg_selected_per_day": None,
            "avg_daily_return": None,
            "avg_actual_return": None,
            "avg_actual_excess_return": None,
            "absolute_positive_rate": None,
            "relative_excess_positive_rate": None,
            "actual_top3_rate": None,
            "downside_return_lt_minus_1pct": None,
            "downside_excess_lt_minus_1pct": None,
        }

    ret = numeric(evaluated, "next_sector_return")
    excess = numeric(evaluated, "next_sector_excess_return")
    future_rank = numeric(evaluated, "future_excess_rank", 99.0)
    daily = evaluated.assign(_ret=ret, _excess=excess).groupby("date").agg(
        daily_return=("_ret", "mean"),
        daily_excess=("_excess", "mean"),
        selected_count=("sector", "count"),
    )
    return {
        "strategy": flag_col,
        "selected_rows": int(len(selected)),
        "evaluated_rows": int(len(evaluated)),
        "evaluated_days": int(evaluated["date"].nunique()),
        "avg_selected_per_day": clean_number(daily["selected_count"].mean()),
        "avg_daily_return": clean_number(daily["daily_return"].mean()),
        "avg_daily_excess_return": clean_number(daily["daily_excess"].mean()),
        "avg_actual_return": clean_number(ret.mean()),
        "avg_actual_excess_return": clean_number(excess.mean()),
        "absolute_positive_rate": clean_number((ret > 0).mean()),
        "relative_excess_positive_rate": clean_number((excess > 0).mean()),
        "actual_top3_rate": clean_number((future_rank <= TOP_K).mean()),
        "downside_return_lt_minus_1pct": clean_number((ret < -1.0).mean()),
        "downside_excess_lt_minus_1pct": clean_number((excess < -1.0).mean()),
    }


def build_strategy_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["panic_v5_top3"] = (out["panic_rebound_market_gate"].eq(1) & out["panic_rebound_score_rank"].le(3)).astype(int)
    out["panic_v5_top5"] = (out["panic_rebound_market_gate"].eq(1) & out["panic_rebound_score_rank"].le(5)).astype(int)
    return out


def current_candidates() -> pd.DataFrame:
    if not CURRENT_PREDICTION_PATH.exists():
        return pd.DataFrame()
    current = pd.read_csv(CURRENT_PREDICTION_PATH, encoding="utf-8-sig")
    if current.empty or "sector" not in current.columns:
        return pd.DataFrame()
    score_column = choose_current_score_column(current)
    current["date"] = pd.Timestamp.today().normalize()
    if "market_regime_v4" not in current.columns:
        current["market_regime_v4"] = ""
    if "market_regime_risk_v4" not in current.columns:
        current["market_regime_risk_v4"] = 0.0
    current = current.rename(columns={score_column: "_current_score"})
    scored = add_shadow_features(current, "_current_score")
    keep = [
        "sector",
        "panic_rebound_action_label",
        "panic_rebound_candidate_rank",
        "panic_rebound_watch_score",
        "panic_rebound_score_rank",
        "panic_rebound_relative_pct",
        "panic_rebound_largecap_gap_pct",
        "panic_rebound_overheat_pct",
        "panic_rebound_fx_stress_pct",
        "final_action",
        "prediction_layer_rank",
        "action_layer_label",
    ]
    keep = [col for col in keep if col in scored.columns]
    latest = scored[scored["panic_rebound_relaxed_candidate"].eq(1)][keep].sort_values(
        ["panic_rebound_candidate_rank", "panic_rebound_watch_score"],
        ascending=[True, False],
    )
    return latest


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return "_데이터 없음_"
    shown = frame[columns].copy()
    for col in shown.columns:
        if pd.api.types.is_float_dtype(shown[col]):
            shown[col] = shown[col].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    return shown.to_markdown(index=False)


def write_report(summary: dict[str, Any], strategy: pd.DataFrame, latest: pd.DataFrame) -> None:
    lines = [
        "# 패닉장 반등 후보 방어 추적 Shadow 검증",
        "",
        f"- 생성 시각: {summary['generated_at']}",
        f"- 모델 버전: `{MODEL_VERSION}`",
        f"- 검증 국면: `{', '.join(sorted(PANIC_REGIMES))}`",
        f"- 패닉/급락 검증일 수: {summary['panic_days']}일",
        "- 목적: 패닉장에서도 예측 후보를 전부 죽이지 않고 `방어 추적` 후보로 살릴 수 있는지 검증",
        "- 메인 `final_action`은 변경하지 않았다.",
        "",
        "## 진행 판단",
        "",
        f"- 최종 행동 완화 가능 여부: `{summary['safe_to_promote_final_action']}`",
        f"- 별도 모니터 라벨 사용 가능 여부: `{summary['safe_to_use_watch_label']}`",
        f"- 결론: {summary['verdict']}",
        "",
        "## 전략별 검증",
        "",
        markdown_table(
            strategy,
            [
                "strategy",
                "selected_rows",
                "evaluated_days",
                "avg_selected_per_day",
                "avg_daily_return",
                "avg_daily_excess_return",
                "actual_top3_rate",
                "downside_return_lt_minus_1pct",
                "downside_excess_lt_minus_1pct",
            ],
        ),
        "",
        "## 최신 방어 추적 후보",
        "",
    ]
    if latest.empty:
        lines.append("_현재 조건을 통과한 방어 추적 후보 없음_")
    else:
        lines.append(markdown_table(latest, list(latest.columns)))
    lines.extend(
        [
            "",
            "## 다음 기준",
            "",
            "- 이 shadow rule은 매수 신호가 아니라 `회피 우선` 아래의 관찰 라벨로만 사용한다.",
            "- strict 후보가 평균 초과수익, Top3 비율, 하방 위험을 동시에 만족할 때만 행동 완화를 다시 검토한다.",
            "- 장 마감 자동화에서는 리포트만 갱신하고, 현재 단계에서는 메인 행동층에 연결하지 않는다.",
            "",
        ]
    )
    REPORT_OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    configure_utf8()
    REPORTS.mkdir(parents=True, exist_ok=True)
    scored = build_strategy_flags(add_shadow_features(load_backtest()))
    panic = scored[scored["panic_rebound_market_gate"].eq(1)].copy()
    strategies = [
        "panic_v5_top3",
        "panic_v5_top5",
        "panic_rebound_relaxed_candidate",
        "panic_rebound_strict_candidate",
        "panic_rebound_strict_top2",
    ]
    strategy = pd.DataFrame([summarize_strategy(panic, flag) for flag in strategies])
    latest = current_candidates()
    strict_row = strategy[strategy["strategy"].eq("panic_rebound_strict_candidate")]
    strict = strict_row.iloc[0].to_dict() if not strict_row.empty else {}
    strict_days = int(strict.get("evaluated_days") or 0)
    strict_excess = clean_number(strict.get("avg_daily_excess_return"))
    strict_top3 = clean_number(strict.get("actual_top3_rate"))
    strict_downside = clean_number(strict.get("downside_excess_lt_minus_1pct"))

    safe_to_use_watch_label = bool(
        strict_days >= 15
        and strict_excess is not None
        and strict_top3 is not None
        and strict_downside is not None
        and strict_excess > 0
        and strict_top3 >= 0.25
        and strict_downside <= 0.45
    )
    summary = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "model_version": MODEL_VERSION,
        "source_file": str(BACKTEST_SOURCE_PATH.relative_to(ROOT)),
        "rows": int(len(scored)),
        "trading_days": int(scored["date"].nunique()),
        "panic_rows": int(len(panic)),
        "panic_days": int(panic["date"].nunique()),
        "panic_regime_day_counts": panic.groupby("market_regime_v4")["date"].nunique().to_dict(),
        "strategy_performance": records_for_json(strategy),
        "latest_candidates": records_for_json(latest),
        "safe_to_promote_final_action": False,
        "safe_to_use_watch_label": safe_to_use_watch_label,
        "verdict": (
            "방어 추적 라벨은 모니터링용으로 사용 가능하지만, 최종 행동 완화는 아직 금지"
            if safe_to_use_watch_label
            else "최종 행동 완화 금지, shadow 관찰만 진행"
        ),
        "outputs": {
            "backtest": str(BACKTEST_OUTPUT_PATH.relative_to(ROOT)),
            "strategy": str(STRATEGY_OUTPUT_PATH.relative_to(ROOT)),
            "latest": str(LATEST_OUTPUT_PATH.relative_to(ROOT)),
            "report": str(REPORT_OUTPUT_PATH.relative_to(ROOT)),
        },
    }
    scored.to_csv(BACKTEST_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    strategy.to_csv(STRATEGY_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    latest.to_csv(LATEST_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    SUMMARY_OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, strategy, latest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
