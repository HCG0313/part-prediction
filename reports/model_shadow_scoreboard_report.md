# 메인-Shadow 모델 통합 비교판

- 생성 시각: 2026-06-20T00:01:17
- 목적: 메인 V5와 여러 shadow 모델의 성능을 한 표에서 비교하고, 교체 후보 여부를 매일 누적 판단한다.
- 현재 결론: 메인 교체 금지, shadow 비교판으로 누적 관찰

## 전체 비교

| source                        | model                             | scope        | window     |   target_days |   top3_overlap_rate |   rank_ic_spearman |   ndcg_at_3 |   top3_bottom3_spread |   avg_daily_excess_return |   downside_rate | recommended_use   |
|:------------------------------|:----------------------------------|:-------------|:-----------|--------------:|--------------------:|-------------------:|------------:|----------------------:|--------------------------:|----------------:|:------------------|
| panic_rebound_watch_shadow    | panic_rebound_relaxed_candidate   | panic_only   | panic_days |            46 |              0.3333 |           nan      |    nan      |              nan      |                   -0.0854 |          0.3577 | shadow 관찰       |
| panic_rebound_watch_shadow    | panic_rebound_strict_candidate    | panic_only   | panic_days |            43 |              0.3636 |           nan      |    nan      |              nan      |                   -0.0976 |          0.3737 | shadow 관찰       |
| panic_rebound_watch_shadow    | panic_rebound_strict_top2         | panic_only   | panic_days |            43 |              0.3472 |           nan      |    nan      |              nan      |                   -0.0012 |          0.3611 | shadow 관찰       |
| panic_rebound_watch_shadow    | panic_v5_top3                     | panic_only   | panic_days |            46 |              0.3188 |           nan      |    nan      |              nan      |                   -0.1053 |          0.3116 | shadow 관찰       |
| panic_rebound_watch_shadow    | panic_v5_top5                     | panic_only   | panic_days |            46 |              0.3130 |           nan      |    nan      |              nan      |                   -0.0369 |          0.2870 | shadow 관찰       |
| shadow_component_weight_score | main_v5                           | all_market   | all        |           315 |              0.3238 |             0.0207 |      0.5845 |                0.1086 |                    0.0408 |        nan      | 메인 유지         |
| shadow_component_weight_score | shadow_component_weight           | all_market   | all        |           315 |              0.3196 |             0.0180 |      0.5864 |                0.1078 |                    0.0428 |        nan      | shadow 비교       |
| shadow_component_weight_score | main_v5                           | all_market   | last_60    |            60 |              0.3611 |             0.0760 |      0.6120 |                0.2857 |                    0.3129 |        nan      | 메인 유지         |
| shadow_component_weight_score | shadow_component_weight           | all_market   | last_60    |            60 |              0.3389 |             0.0628 |      0.6053 |                0.2710 |                    0.2959 |        nan      | shadow 비교       |
| shadow_component_weight_score | main_v5                           | all_market   | last_20    |            20 |              0.3833 |             0.0676 |      0.5989 |                0.2730 |                    0.4436 |        nan      | 메인 유지         |
| shadow_component_weight_score | shadow_component_weight           | all_market   | last_20    |            20 |              0.3000 |             0.0112 |      0.5669 |                0.0112 |                    0.1355 |        nan      | shadow 비교       |
| shadow_component_weight_score | main_v5                           | all_market   | last_10    |            10 |              0.4333 |             0.0841 |      0.6178 |                0.3230 |                    0.6604 |        nan      | 메인 유지         |
| shadow_component_weight_score | shadow_component_weight           | all_market   | last_10    |            10 |              0.3667 |             0.0035 |      0.5980 |                0.0843 |                    0.4304 |        nan      | shadow 비교       |
| shadow_component_weight_score | main_v5                           | all_market   | last_5     |             5 |              0.5333 |             0.1232 |      0.6084 |                0.6757 |                    0.6765 |        nan      | 메인 유지         |
| shadow_component_weight_score | shadow_component_weight           | all_market   | last_5     |             5 |              0.4667 |             0.1371 |      0.6384 |                0.7715 |                    0.7191 |        nan      | shadow 비교       |
| shadow_lgbm_ranker            | main_v5                           | all_market   | all        |            60 |              0.3667 |             0.0760 |      0.6212 |                0.4153 |                    0.3755 |        nan      | 메인 유지         |
| shadow_lgbm_ranker            | shadow_lgbm_ranker                | all_market   | all        |            60 |              0.2722 |            -0.0337 |      0.5710 |                0.0223 |                    0.0993 |        nan      | shadow 비교       |
| shadow_lgbm_ranker            | main_v5                           | all_market   | last_60    |            60 |              0.3667 |             0.0760 |      0.6212 |                0.4153 |                    0.3755 |        nan      | 메인 유지         |
| shadow_lgbm_ranker            | shadow_lgbm_ranker                | all_market   | last_60    |            60 |              0.2722 |            -0.0337 |      0.5710 |                0.0223 |                    0.0993 |        nan      | shadow 비교       |
| shadow_lgbm_ranker            | main_v5                           | all_market   | last_20    |            20 |              0.3833 |             0.0676 |      0.6175 |                0.7215 |                    0.4694 |        nan      | 메인 유지         |
| shadow_lgbm_ranker            | shadow_lgbm_ranker                | all_market   | last_20    |            20 |              0.3167 |            -0.0371 |      0.5811 |               -0.0996 |                    0.1762 |        nan      | shadow 비교       |
| shadow_lgbm_ranker            | main_v5                           | all_market   | last_10    |            10 |              0.4333 |             0.0841 |      0.6412 |                0.8560 |                    0.7120 |        nan      | 메인 유지         |
| shadow_lgbm_ranker            | shadow_lgbm_ranker                | all_market   | last_10    |            10 |              0.2667 |            -0.0713 |      0.5719 |               -0.3188 |                    0.1298 |        nan      | shadow 비교       |
| shadow_lgbm_ranker            | main_v5                           | all_market   | last_5     |             5 |              0.5333 |             0.1232 |      0.6393 |                0.9647 |                    0.6765 |        nan      | 메인 유지         |
| shadow_lgbm_ranker            | shadow_lgbm_ranker                | all_market   | last_5     |             5 |              0.2667 |            -0.0392 |      0.5767 |               -0.3984 |                   -0.1693 |        nan      | shadow 비교       |
| shadow_rank_label_v2          | main_v5                           | all_market   | all        |            60 |              0.3722 |             0.0760 |      0.5079 |                0.3864 |                    0.3636 |        nan      | 메인 유지         |
| shadow_rank_label_v2          | shadow_rank_label_v2              | all_market   | all        |            60 |              0.3000 |            -0.0031 |      0.4507 |                0.1200 |                    0.1187 |        nan      | shadow 비교       |
| shadow_rank_label_v2          | main_v5                           | all_market   | last_60    |            60 |              0.3722 |             0.0760 |      0.5079 |                0.3864 |                    0.3636 |        nan      | 메인 유지         |
| shadow_rank_label_v2          | shadow_rank_label_v2              | all_market   | last_60    |            60 |              0.3000 |            -0.0031 |      0.4507 |                0.1200 |                    0.1187 |        nan      | shadow 비교       |
| shadow_rank_label_v2          | main_v5                           | all_market   | last_20    |            20 |              0.4000 |             0.0676 |      0.4957 |                0.7347 |                    0.5377 |        nan      | 메인 유지         |
| shadow_rank_label_v2          | shadow_rank_label_v2              | all_market   | last_20    |            20 |              0.2500 |            -0.0276 |      0.3994 |               -0.1560 |                   -0.2177 |        nan      | shadow 비교       |
| shadow_rank_label_v2          | main_v5                           | all_market   | last_10    |            10 |              0.4667 |             0.0841 |      0.5679 |                0.9926 |                    0.8486 |        nan      | 메인 유지         |
| shadow_rank_label_v2          | shadow_rank_label_v2              | all_market   | last_10    |            10 |              0.1667 |            -0.0867 |      0.3263 |               -0.4875 |                   -0.7089 |        nan      | shadow 비교       |
| shadow_rank_label_v2          | main_v5                           | all_market   | last_5     |             5 |              0.5333 |             0.1232 |      0.5506 |                0.9647 |                    0.6765 |        nan      | 메인 유지         |
| shadow_rank_label_v2          | shadow_rank_label_v2              | all_market   | last_5     |             5 |              0.2667 |            -0.1357 |      0.4031 |               -0.9307 |                   -0.7195 |        nan      | shadow 비교       |
| shadow_rank_model_v6          | shadow_rank_v6_v4_stability_blend | live_pending | pending    |             0 |            nan      |           nan      |    nan      |              nan      |                  nan      |        nan      | 실전 결과 대기    |

## 해석

- `main_v5`보다 최근 구간에서 반복적으로 우수한 shadow가 나올 때만 교체 후보로 본다.
- 패닉장 반등 후보는 전체 시장 모델과 직접 비교하지 않고 `panic_only` 범위에서만 본다.
- `pending` 상태의 shadow는 실제 결과가 누적될 때까지 교체 판단에 사용하지 않는다.
