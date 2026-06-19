from __future__ import annotations

import json
import math
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"

SCOREBOARD_PATH = REPORTS / "model_shadow_scoreboard.csv"
SCOREBOARD_SUMMARY_PATH = REPORTS / "model_shadow_scoreboard_summary.json"
SCOREBOARD_REPORT_PATH = REPORTS / "model_shadow_scoreboard_report.md"

FAILURE_BY_SECTOR_PATH = REPORTS / "model_failure_diagnostics_by_sector.csv"
FAILURE_BY_REGIME_PATH = REPORTS / "model_failure_diagnostics_by_regime.csv"
FAILURE_BY_WINDOW_PATH = REPORTS / "model_failure_diagnostics_by_window.csv"
FAILURE_TOP_EXAMPLES_PATH = REPORTS / "model_failure_diagnostics_top_examples.csv"
FAILURE_REPORT_PATH = REPORTS / "model_failure_diagnostics_report.md"

PREDICTION_DECISION_TABLE_PATH = REPORTS / "prediction_decision_separation_table.csv"
PREDICTION_DECISION_REPORT_PATH = REPORTS / "prediction_decision_separation_report.md"

PORTFOLIO_PLAN_PATH = DOCS / "github-portfolio-issue-plan.md"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_float(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if hasattr(value, "item"):
        value = value.item()
    return float(value)


def safe_mean(series: pd.Series):
    values = pd.to_numeric(series, errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def safe_corr(x: pd.Series, y: pd.Series, method: str = "spearman"):
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(frame) < 2 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return None
    return safe_float(frame["x"].corr(frame["y"], method=method))


def dcg(relevances: list[float], k: int) -> float:
    return float(sum(rel / math.log2(idx + 2) for idx, rel in enumerate(relevances[:k])))


def ndcg_at_k(predicted_relevances: list[float], ideal_relevances: list[float], k: int):
    if not predicted_relevances or not ideal_relevances:
        return None
    ideal = dcg(sorted(ideal_relevances, reverse=True), k)
    if ideal == 0:
        return None
    return float(dcg(predicted_relevances, k) / ideal)


def last_window(frame: pd.DataFrame, window: int | None) -> pd.DataFrame:
    if frame.empty or window is None:
        return frame.copy()
    dates = sorted(pd.to_datetime(frame["date"], errors="coerce").dropna().unique())
    keep = set(pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates[-window:])
    return frame[frame["date"].astype(str).isin(keep)].copy()


def aggregate_daily_validation(frame: pd.DataFrame, source: str, switch_candidate=False, verdict="") -> pd.DataFrame:
    if frame.empty or "model" not in frame.columns:
        return pd.DataFrame()
    rows = []
    for model, model_df in frame.groupby("model"):
        model_df = model_df.copy()
        for label, window in [("all", None), ("last_60", 60), ("last_20", 20), ("last_10", 10), ("last_5", 5)]:
            part = last_window(model_df, window)
            if part.empty:
                continue
            rows.append(
                {
                    "source": source,
                    "model": model,
                    "scope": "all_market",
                    "window": label,
                    "target_days": int(part["date"].nunique()),
                    "rows": int(len(part)),
                    "top3_overlap_rate": safe_mean(part.get("top3_overlap_rate", pd.Series(dtype="float64"))),
                    "rank_ic_spearman": safe_mean(part.get("rank_ic_spearman", pd.Series(dtype="float64"))),
                    "ndcg_at_3": safe_mean(part.get("ndcg_at_3", pd.Series(dtype="float64"))),
                    "top3_bottom3_spread": safe_mean(
                        part.get("top3_bottom3_excess_spread", pd.Series(dtype="float64"))
                    ),
                    "avg_daily_excess_return": safe_mean(
                        part.get("top3_avg_excess_return", pd.Series(dtype="float64"))
                    ),
                    "downside_rate": None,
                    "switch_candidate": bool(switch_candidate),
                    "recommended_use": "메인 유지" if model == "main_v5" else "shadow 비교",
                    "verdict": verdict,
                }
            )
    return pd.DataFrame(rows)


def daily_rank_metrics(panel: pd.DataFrame, score_col: str, model: str, source: str) -> pd.DataFrame:
    if panel.empty or score_col not in panel.columns:
        return pd.DataFrame()
    rows = []
    for date, day in panel.groupby("date"):
        day = day.copy()
        day["actual_return"] = pd.to_numeric(day.get("next_sector_return"), errors="coerce")
        if "next_sector_excess_return" in day.columns:
            day["actual_excess_return"] = pd.to_numeric(day["next_sector_excess_return"], errors="coerce")
        else:
            day["actual_excess_return"] = day["actual_return"] - day["actual_return"].mean()
        day["score"] = pd.to_numeric(day[score_col], errors="coerce")
        day = day.dropna(subset=["actual_return", "score", "sector"])
        if day.empty:
            continue
        sector_count = int(day["sector"].nunique())
        day["actual_return_rank"] = day["actual_return"].rank(ascending=False, method="first")
        day["rank_relevance"] = sector_count - day["actual_return_rank"] + 1
        score_ranked = day.sort_values(["score", "sector"], ascending=[False, True])
        actual_top3 = set(day.sort_values(["actual_return", "sector"], ascending=[False, True]).head(3)["sector"])
        pred_top3 = score_ranked.head(3)
        bottom3 = score_ranked.tail(3)
        rows.append(
            {
                "date": str(date),
                "model": model,
                "source": source,
                "pred_top3_sectors": " | ".join(pred_top3["sector"].astype(str).tolist()),
                "actual_top3_sectors": " | ".join(actual_top3),
                "top3_overlap_rate": float(pred_top3["sector"].isin(actual_top3).mean()),
                "top3_avg_return": safe_mean(pred_top3["actual_return"]),
                "top3_avg_excess_return": safe_mean(pred_top3["actual_excess_return"]),
                "bottom3_avg_excess_return": safe_mean(bottom3["actual_excess_return"]),
                "top3_bottom3_excess_spread": safe_mean(pred_top3["actual_excess_return"])
                - safe_mean(bottom3["actual_excess_return"]),
                "rank_ic_spearman": safe_corr(day["score"], day["actual_return"], "spearman"),
                "ndcg_at_3": ndcg_at_k(
                    pd.to_numeric(score_ranked["rank_relevance"], errors="coerce").dropna().tolist(),
                    pd.to_numeric(day["rank_relevance"], errors="coerce").dropna().tolist(),
                    3,
                ),
                "top1_sector": str(score_ranked.iloc[0]["sector"]) if not score_ranked.empty else None,
                "top1_excess_return": safe_float(score_ranked.iloc[0]["actual_excess_return"])
                if not score_ranked.empty
                else None,
            }
        )
    return pd.DataFrame(rows)


def add_lgbm_scoreboard_rows() -> pd.DataFrame:
    frame = read_csv(REPORTS / "shadow_lgbm_ranker_validation.csv")
    if frame.empty:
        return pd.DataFrame()
    daily = pd.concat(
        [
            daily_rank_metrics(frame, "main_rank_score", "main_v5", "shadow_lgbm_ranker"),
            daily_rank_metrics(frame, "shadow_lgbm_rank_score", "shadow_lgbm_ranker", "shadow_lgbm_ranker"),
        ],
        ignore_index=True,
    )
    summary = read_json(REPORTS / "shadow_lgbm_ranker_summary.json")
    return aggregate_daily_validation(
        daily,
        "shadow_lgbm_ranker",
        switch_candidate=summary.get("switch_candidate", False),
        verdict=summary.get("verdict", ""),
    )


def add_panic_scoreboard_rows() -> pd.DataFrame:
    summary = read_json(REPORTS / "panic_rebound_watch_shadow_summary.json")
    rows = []
    for item in summary.get("strategy_performance", []):
        rows.append(
            {
                "source": "panic_rebound_watch_shadow",
                "model": item.get("strategy"),
                "scope": "panic_only",
                "window": "panic_days",
                "target_days": item.get("evaluated_days"),
                "rows": item.get("evaluated_rows"),
                "top3_overlap_rate": item.get("actual_top3_rate"),
                "rank_ic_spearman": None,
                "ndcg_at_3": None,
                "top3_bottom3_spread": None,
                "avg_daily_excess_return": item.get("avg_daily_excess_return"),
                "downside_rate": item.get("downside_return_lt_minus_1pct"),
                "switch_candidate": bool(summary.get("safe_to_promote_final_action", False)),
                "recommended_use": "shadow 관찰",
                "verdict": summary.get("verdict", ""),
            }
        )
    return pd.DataFrame(rows)


def build_scoreboard() -> pd.DataFrame:
    pieces = []
    component_summary = read_json(REPORTS / "shadow_component_weight_score_summary.json")
    label_summary = read_json(REPORTS / "shadow_rank_label_v2_summary.json")
    pieces.append(
        aggregate_daily_validation(
            read_csv(REPORTS / "shadow_component_weight_score_validation.csv"),
            "shadow_component_weight_score",
            switch_candidate=component_summary.get("switch_candidate", False),
            verdict=component_summary.get("verdict", ""),
        )
    )
    pieces.append(
        aggregate_daily_validation(
            read_csv(REPORTS / "shadow_rank_label_v2_validation.csv"),
            "shadow_rank_label_v2",
            switch_candidate=label_summary.get("switch_candidate", False),
            verdict=label_summary.get("verdict", ""),
        )
    )
    pieces.append(add_lgbm_scoreboard_rows())
    pieces.append(add_panic_scoreboard_rows())

    v6 = read_json(REPORTS / "shadow_rank_model_v6_summary.json")
    if v6:
        pieces.append(
            pd.DataFrame(
                [
                    {
                        "source": "shadow_rank_model_v6",
                        "model": v6.get("model_version", "shadow_rank_model_v6"),
                        "scope": "live_pending",
                        "window": "pending",
                        "target_days": v6.get("evaluated_days", 0),
                        "rows": 0,
                        "top3_overlap_rate": None,
                        "rank_ic_spearman": None,
                        "ndcg_at_3": None,
                        "top3_bottom3_spread": None,
                        "avg_daily_excess_return": None,
                        "downside_rate": None,
                        "switch_candidate": bool(v6.get("switch_candidate", False)),
                        "recommended_use": "실전 결과 대기",
                        "verdict": v6.get("verdict", ""),
                    }
                ]
            )
        )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        scoreboard = pd.concat([p for p in pieces if not p.empty], ignore_index=True, sort=False)
    if scoreboard.empty:
        return scoreboard
    order = ["all", "last_60", "last_20", "last_10", "last_5", "panic_days", "pending"]
    scoreboard["window_order"] = scoreboard["window"].map({name: idx for idx, name in enumerate(order)}).fillna(99)
    scoreboard = scoreboard.sort_values(["source", "window_order", "model"]).drop(columns=["window_order"])
    scoreboard.to_csv(SCOREBOARD_PATH, index=False, encoding="utf-8-sig")
    return scoreboard


def build_failure_diagnostics() -> dict:
    panel = read_csv(REPORTS / "sector_rank_model_v5_backtest_predictions.csv")
    if panel.empty:
        return {"status": "missing_backtest"}

    score_col = "final_rank_score_v5" if "final_rank_score_v5" in panel.columns else "final_rank_score_v4"
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    panel["score"] = pd.to_numeric(panel[score_col], errors="coerce")
    panel["actual_return"] = pd.to_numeric(panel.get("next_sector_return"), errors="coerce")
    if "next_sector_excess_return" in panel.columns:
        panel["actual_excess_return"] = pd.to_numeric(panel["next_sector_excess_return"], errors="coerce")
    else:
        panel["actual_excess_return"] = panel["actual_return"] - panel.groupby("date")["actual_return"].transform("mean")
    panel = panel.dropna(subset=["date", "sector", "score", "actual_return"]).copy()
    panel["predicted_rank"] = panel.groupby("date")["score"].rank(ascending=False, method="first")
    panel["actual_rank"] = panel.groupby("date")["actual_return"].rank(ascending=False, method="first")
    panel["predicted_top3"] = panel["predicted_rank"] <= 3
    panel["actual_top3"] = panel["actual_rank"] <= 3
    panel["false_positive_top3"] = panel["predicted_top3"] & ~panel["actual_top3"]
    panel["missed_actual_top3"] = ~panel["predicted_top3"] & panel["actual_top3"]
    panel["top3_hit"] = panel["predicted_top3"] & panel["actual_top3"]
    panel["overrank_gap"] = panel["actual_rank"] - panel["predicted_rank"]

    by_sector = (
        panel.groupby("sector")
        .agg(
            rows=("sector", "size"),
            predicted_top3_count=("predicted_top3", "sum"),
            actual_top3_count=("actual_top3", "sum"),
            top3_hit_count=("top3_hit", "sum"),
            false_positive_top3_count=("false_positive_top3", "sum"),
            missed_actual_top3_count=("missed_actual_top3", "sum"),
            avg_actual_return_when_pred_top3=("actual_return", lambda s: safe_mean(s[panel.loc[s.index, "predicted_top3"]])),
            avg_actual_excess_when_pred_top3=(
                "actual_excess_return",
                lambda s: safe_mean(s[panel.loc[s.index, "predicted_top3"]]),
            ),
            avg_overrank_gap=("overrank_gap", "mean"),
        )
        .reset_index()
    )
    by_sector["false_positive_rate_when_pred_top3"] = by_sector["false_positive_top3_count"] / by_sector[
        "predicted_top3_count"
    ].replace(0, pd.NA)
    by_sector["miss_rate_when_actual_top3"] = by_sector["missed_actual_top3_count"] / by_sector["actual_top3_count"].replace(
        0, pd.NA
    )
    by_sector = by_sector.sort_values(
        ["false_positive_top3_count", "missed_actual_top3_count", "avg_overrank_gap"],
        ascending=[False, False, False],
    )
    by_sector.to_csv(FAILURE_BY_SECTOR_PATH, index=False, encoding="utf-8-sig")

    regime_col = "market_regime_v4" if "market_regime_v4" in panel.columns else None
    if regime_col:
        by_regime = (
            panel.groupby(regime_col)
            .agg(
                rows=("sector", "size"),
                days=("date", "nunique"),
                predicted_top3_count=("predicted_top3", "sum"),
                top3_hit_count=("top3_hit", "sum"),
                false_positive_top3_count=("false_positive_top3", "sum"),
                avg_actual_return_when_pred_top3=("actual_return", lambda s: safe_mean(s[panel.loc[s.index, "predicted_top3"]])),
                avg_actual_excess_when_pred_top3=(
                    "actual_excess_return",
                    lambda s: safe_mean(s[panel.loc[s.index, "predicted_top3"]]),
                ),
            )
            .reset_index()
            .rename(columns={regime_col: "market_regime"})
        )
        by_regime["top3_hit_rate_when_pred_top3"] = by_regime["top3_hit_count"] / by_regime[
            "predicted_top3_count"
        ].replace(0, pd.NA)
    else:
        by_regime = pd.DataFrame()
    by_regime.to_csv(FAILURE_BY_REGIME_PATH, index=False, encoding="utf-8-sig")

    daily_panel = panel.copy()
    daily_panel["next_sector_return"] = daily_panel["actual_return"]
    daily_panel["next_sector_excess_return"] = daily_panel["actual_excess_return"]
    daily = daily_rank_metrics(daily_panel, "score", "main_v5", "v5_failure")
    window_rows = []
    for label, window in [("all", None), ("last_60", 60), ("last_20", 20), ("last_10", 10), ("last_5", 5)]:
        part = last_window(daily, window)
        if part.empty:
            continue
        window_rows.append(
            {
                "window": label,
                "target_days": int(part["date"].nunique()),
                "top3_overlap_rate": safe_mean(part["top3_overlap_rate"]),
                "rank_ic_spearman": safe_mean(part["rank_ic_spearman"]),
                "ndcg_at_3": safe_mean(part["ndcg_at_3"]),
                "top3_bottom3_spread": safe_mean(part["top3_bottom3_excess_spread"]),
                "zero_overlap_days": int((pd.to_numeric(part["top3_overlap_rate"], errors="coerce") == 0).sum()),
                "negative_rank_ic_days": int((pd.to_numeric(part["rank_ic_spearman"], errors="coerce") < 0).sum()),
                "negative_spread_days": int((pd.to_numeric(part["top3_bottom3_excess_spread"], errors="coerce") < 0).sum()),
            }
        )
    by_window = pd.DataFrame(window_rows)
    by_window.to_csv(FAILURE_BY_WINDOW_PATH, index=False, encoding="utf-8-sig")

    examples = panel[panel["predicted_top3"]].copy()
    examples = examples.sort_values(["date", "actual_excess_return"], ascending=[False, True]).head(30)
    examples[
        [
            "date",
            "next_date",
            "sector",
            "predicted_rank",
            "actual_rank",
            "score",
            "actual_return",
            "actual_excess_return",
            "market_regime_v4" if "market_regime_v4" in examples.columns else "sector",
            "v5_action" if "v5_action" in examples.columns else "sector",
            "v5_no_trade_reason" if "v5_no_trade_reason" in examples.columns else "sector",
        ]
    ].to_csv(FAILURE_TOP_EXAMPLES_PATH, index=False, encoding="utf-8-sig")

    return {
        "status": "ok",
        "rows": int(len(panel)),
        "days": int(panel["date"].nunique()),
        "score_col": score_col,
        "worst_false_positive_sector": str(by_sector.iloc[0]["sector"]) if not by_sector.empty else None,
        "recent_last5_top3_overlap": safe_float(
            by_window.loc[by_window["window"] == "last_5", "top3_overlap_rate"].iloc[0]
        )
        if not by_window[by_window["window"] == "last_5"].empty
        else None,
    }


def truncate_text(value, limit=58) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_prediction_decision_table() -> pd.DataFrame:
    pred = read_csv(REPORTS / "tomorrow_sector_prediction.csv")
    if pred.empty:
        return pred
    panic = read_csv(REPORTS / "panic_rebound_watch_shadow_latest_candidates.csv")
    component = read_csv(REPORTS / "shadow_component_weight_score_latest_predictions.csv")
    label_v2 = read_csv(REPORTS / "shadow_rank_label_v2_latest_predictions.csv")

    out = pred.copy()
    if not panic.empty:
        out = out.merge(
            panic[
                [
                    "sector",
                    "panic_rebound_action_label",
                    "panic_rebound_candidate_rank",
                    "panic_rebound_watch_score",
                ]
            ],
            on="sector",
            how="left",
        )
    if not component.empty:
        out = out.merge(
            component[["sector", "shadow_component_rank", "shadow_component_weight_score"]],
            on="sector",
            how="left",
        )
    if not label_v2.empty:
        out = out.merge(
            label_v2[["sector", "shadow_rank_label_v2_rank", "shadow_rank_label_v2_score"]],
            on="sector",
            how="left",
        )

    cols = [
        "sector",
        "prediction_layer_rank",
        "prediction_layer_label",
        "prediction_layer_score",
        "prediction_expected_return_pct",
        "return_interval_lower_pct",
        "return_interval_upper_pct",
        "return_interval_confidence_label",
        "panic_rebound_action_label",
        "panic_rebound_candidate_rank",
        "shadow_component_rank",
        "shadow_rank_label_v2_rank",
        "action_layer_rank",
        "action_layer_label",
        "action_layer_risk_state",
        "final_action",
        "prediction_action_alignment",
        "final_decision_explanation",
        "entry_condition_note",
        "ranking_quality_gate_reason",
        "market_regime_v4",
        "market_regime_risk_v4",
    ]
    existing = [c for c in cols if c in out.columns]
    table = out[existing].copy()
    for c in [
        "final_decision_explanation",
        "entry_condition_note",
        "ranking_quality_gate_reason",
        "action_layer_risk_state",
    ]:
        if c in table.columns:
            table[c] = table[c].map(lambda v: truncate_text(v, 90))
    table = table.sort_values("prediction_layer_rank" if "prediction_layer_rank" in table.columns else "sector")
    table.to_csv(PREDICTION_DECISION_TABLE_PATH, index=False, encoding="utf-8-sig")
    return table


def write_scoreboard_report(scoreboard: pd.DataFrame) -> dict:
    if scoreboard.empty:
        summary = {"status": "empty", "generated_at": datetime.now().isoformat(timespec="seconds")}
        SCOREBOARD_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    all_market = scoreboard[(scoreboard["scope"] == "all_market") & (scoreboard["window"].isin(["last_20", "last_5"]))]
    switch_candidates = scoreboard[scoreboard["switch_candidate"] == True]  # noqa: E712
    summary = {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rows": int(len(scoreboard)),
        "sources": sorted(scoreboard["source"].dropna().unique().tolist()),
        "switch_candidate_count": int(len(switch_candidates)),
        "safe_to_replace_main_now": bool(len(switch_candidates) > 0),
        "recommendation": "메인 교체 금지, shadow 비교판으로 누적 관찰",
        "latest_windows_checked": int(len(all_market)),
        "outputs": {
            "scoreboard": str(SCOREBOARD_PATH.relative_to(ROOT)),
            "report": str(SCOREBOARD_REPORT_PATH.relative_to(ROOT)),
        },
    }
    SCOREBOARD_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    display_cols = [
        "source",
        "model",
        "scope",
        "window",
        "target_days",
        "top3_overlap_rate",
        "rank_ic_spearman",
        "ndcg_at_3",
        "top3_bottom3_spread",
        "avg_daily_excess_return",
        "downside_rate",
        "recommended_use",
    ]
    lines = [
        "# 메인-Shadow 모델 통합 비교판",
        "",
        f"- 생성 시각: {summary['generated_at']}",
        "- 목적: 메인 V5와 여러 shadow 모델의 성능을 한 표에서 비교하고, 교체 후보 여부를 매일 누적 판단한다.",
        f"- 현재 결론: {summary['recommendation']}",
        "",
        "## 전체 비교",
        "",
        scoreboard[display_cols].to_markdown(index=False, floatfmt=".4f"),
        "",
        "## 해석",
        "",
        "- `main_v5`보다 최근 구간에서 반복적으로 우수한 shadow가 나올 때만 교체 후보로 본다.",
        "- 패닉장 반등 후보는 전체 시장 모델과 직접 비교하지 않고 `panic_only` 범위에서만 본다.",
        "- `pending` 상태의 shadow는 실제 결과가 누적될 때까지 교체 판단에 사용하지 않는다.",
        "",
    ]
    SCOREBOARD_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return summary


def write_failure_report(summary: dict) -> None:
    by_sector = read_csv(FAILURE_BY_SECTOR_PATH)
    by_regime = read_csv(FAILURE_BY_REGIME_PATH)
    by_window = read_csv(FAILURE_BY_WINDOW_PATH)
    lines = [
        "# 메인 V5 실패 유형 진단",
        "",
        f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"- 사용 점수: `{summary.get('score_col')}`",
        f"- 검증 행: {summary.get('rows')}개, 거래일: {summary.get('days')}일",
        f"- 최근 5거래일 Top3 겹침률: {summary.get('recent_last5_top3_overlap')}",
        "",
        "## 최근 구간별 실패",
        "",
    ]
    if not by_window.empty:
        lines.append(by_window.to_markdown(index=False, floatfmt=".4f"))
    lines += ["", "## 섹터별 오판 상위", ""]
    if not by_sector.empty:
        show = by_sector.head(12)
        lines.append(show.to_markdown(index=False, floatfmt=".4f"))
    lines += ["", "## 시장 국면별 실패", ""]
    if not by_regime.empty:
        lines.append(by_regime.to_markdown(index=False, floatfmt=".4f"))
    lines += [
        "",
        "## 해석",
        "",
        "- Top3로 자주 뽑히지만 실제 Top3가 아닌 섹터는 과신 후보로 본다.",
        "- 실제 Top3였지만 예측 Top3에서 빠진 섹터는 누락 후보로 본다.",
        "- 이 리포트는 메인 점수를 바꾸지 않고 다음 개선 대상을 고르는 진단용이다.",
        "",
    ]
    FAILURE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_prediction_decision_report(table: pd.DataFrame) -> None:
    lines = [
        "# 예측 후보와 최종 행동 분리표",
        "",
        f"- 생성 시각: {datetime.now().isoformat(timespec='seconds')}",
        "- 목적: 상승 예측 후보와 실제 행동 판단을 분리해서, `상승 후보`가 곧바로 `진입 후보`로 오해되지 않게 한다.",
        "",
    ]
    if not table.empty:
        display = table.copy()
        keep = [
            "prediction_layer_rank",
            "sector",
            "prediction_layer_label",
            "prediction_expected_return_pct",
            "return_interval_lower_pct",
            "return_interval_upper_pct",
            "panic_rebound_action_label",
            "action_layer_label",
            "final_action",
            "prediction_action_alignment",
        ]
        display = display[[c for c in keep if c in display.columns]]
        lines += ["## 핵심 표", "", display.to_markdown(index=False, floatfmt=".4f"), ""]
    lines += [
        "## 해석 원칙",
        "",
        "- `prediction_layer_*`는 다음 거래일 상승 가능성 및 예상 수익률 판단이다.",
        "- `panic_rebound_action_label`은 패닉장 방어 추적 후보이며, 행동 승격 신호가 아니다.",
        "- `final_action`은 리스크 게이트와 랭킹 품질 게이트를 반영한 최종 행동이다.",
        "- 예측이 좋아도 `final_action`이 `회피 우선`이면 신규 진입은 보류한다.",
        "",
    ]
    PREDICTION_DECISION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_portfolio_issue_plan() -> None:
    text = """# GitHub 포트폴리오형 문제 해결 기록 운영안

이 문서는 강의에서 요구하는 포트폴리오형 GitHub 기록을 위해, 모델 개선 과정을 `문제 - 기간 - 원인 - 해결 - 검증 - 남은 과제` 구조로 정리하는 기준이다.

## 기록 단위

문제 하나를 하나의 Issue 또는 문서 섹션으로 기록한다. 단순 실행 로그가 아니라, 어떤 문제가 있었고 어떤 판단으로 해결했는지를 보여주는 것이 목적이다.

## 권장 Issue 형식

| 항목 | 작성 내용 |
|---|---|
| 문제 | 어떤 예측/수집/문서화 문제가 있었는지 |
| 기간 | 발견일, 수정일, 검증일 |
| 영향 | 모델 성능, 자동화, GitHub 표시, 해석 위험 중 어디에 영향을 줬는지 |
| 원인 | 데이터 부족, 라벨 문제, 리스크 게이트, 인코딩, 자동화 중복 등 |
| 해결 | 코드/리포트/문서에서 무엇을 바꿨는지 |
| 검증 | 실행한 스크립트, 생성된 파일, 핵심 수치 |
| 결과 | 메인 반영, shadow 관찰, 보류 중 어느 결론인지 |
| 다음 과제 | 아직 남은 리스크와 다음 확인 조건 |

## 추천 라벨

- `data`: 데이터 수집, 결측, 중복, API 문제
- `model`: 모델 구조, 변수, 라벨, 학습 문제
- `evaluation`: 검증 지표, 백테스트, 성능 비교
- `risk`: 리스크 게이트, 회피 조건, 패닉장 대응
- `docs`: README, 일기, 포트폴리오 문서
- `automation`: 자동화 실행, 알림, 스케줄 문제

## 현재 프로젝트에 적용할 핵심 기록

| 기간 | 문제 | 결과 |
|---|---|---|
| 2026-06-19 | LightGBM 랭킹 모델이 메인보다 낮은 성능을 보임 | 메인 교체 금지, shadow 비교만 유지 |
| 2026-06-19 | 구성요소 가중 shadow 점수가 최근 구간에서 불안정함 | 메인 교체 금지, 1주일 비교 유지 |
| 2026-06-19 | 수익률 반영 라벨 v2가 순위 성능을 낮춤 | 라벨 교체 금지, 별도 shadow로만 보관 |
| 2026-06-19 | 패닉장 반등 후보를 모두 놓칠 가능성 | 방어 추적 shadow 생성, 행동 승격 금지 |
| 2026-06-19 | 예측 후보와 최종 행동이 헷갈릴 위험 | 예측/관찰/행동 분리표 생성 |

## 운영 원칙

GitHub README에는 핵심 성과와 최신 판단만 요약하고, 자세한 해결 과정은 `docs/problem-solving-log.md`와 각 Issue에 남긴다. 메인 모델을 바꾸지 않은 실험도 실패가 아니라 검증 기록으로 남긴다.
"""
    PORTFOLIO_PLAN_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    scoreboard = build_scoreboard()
    scoreboard_summary = write_scoreboard_report(scoreboard)
    failure_summary = build_failure_diagnostics()
    write_failure_report(failure_summary)
    decision_table = build_prediction_decision_table()
    write_prediction_decision_report(decision_table)
    write_portfolio_issue_plan()

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scoreboard": scoreboard_summary,
        "failure_diagnostics": failure_summary,
        "prediction_decision_rows": int(len(decision_table)),
        "outputs": {
            "scoreboard": str(SCOREBOARD_PATH.relative_to(ROOT)),
            "scoreboard_report": str(SCOREBOARD_REPORT_PATH.relative_to(ROOT)),
            "failure_report": str(FAILURE_REPORT_PATH.relative_to(ROOT)),
            "prediction_decision_table": str(PREDICTION_DECISION_TABLE_PATH.relative_to(ROOT)),
            "prediction_decision_report": str(PREDICTION_DECISION_REPORT_PATH.relative_to(ROOT)),
            "portfolio_issue_plan": str(PORTFOLIO_PLAN_PATH.relative_to(ROOT)),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
