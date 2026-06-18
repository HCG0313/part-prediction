# 문제 해결 기록

최근 업데이트: 2026-06-19 개선 기준

> 이 문서는 `파트 예측` 프로젝트에서 발견한 데이터 수집, 전처리, 모델, 문서화 문제를 하나씩 기록한 로그이다.  
> 포트폴리오 관점에서 단순 결과보다 "문제 정의 - 원인 - 해결 - 검증" 흐름을 보여주는 것이 목적이다.

## 작성 기준

- 문제를 숨기지 않고 기록한다.
- 해결 여부보다 어떤 판단을 했는지 남긴다.
- 같은 문제가 반복되면 새 문제로 만들지 않고 기존 항목에 검증 내용을 추가한다.
- README에는 핵심 요약만 두고, 자세한 내용은 이 문서에 누적한다.

## 요약 표

| 날짜 | 문제 | 원인 | 해결 방향 | 상태 |
| --- | --- | --- | --- | --- |
| 2026-06-04 | 휴장일 데이터 중복 수집 | API가 휴장일에 직전 거래일 데이터를 반환할 수 있음 | 한국 거래일 캘린더, 기준일 검증, 비거래일 수집 차단 | 개선 완료 |
| 2026-06-04 | 환율 수집 상태 불명확 | 환율은 주식시장 휴장일과 달리 별도 고시 일정이 있음 | ECOS 수집 구조와 상태값 분리 | 개선 완료 |
| 2026-06-04 | 결측치와 이상치 처리 기준 혼재 | 원시 스케일, 고결측, 저분산 변수가 학습에 섞임 | 전처리 단계에서 제거 기준 분리 | 개선 완료 |
| 2026-06-05 | 급락장 신규 진입 위험 | 전 섹터 약세에서 섹터 후보가 의미를 잃음 | capitulation, weak breadth, no-trade gate 강화 | 개선 중 |
| 2026-06-08 | 급락 후 반등을 지나치게 보수적으로 봄 | 회피 게이트가 반등 후보까지 낮춰버림 | 장중 반등 모델과 일봉 모델을 분리해 관찰 | 개선 중 |
| 2026-06-12 | 모델 확률 과신 | raw probability가 실제 적중률보다 높음 | calibrated probability와 decision layer 추가 | 개선 완료 |
| 2026-06-12 | 후보 선별과 상승 여부 예측이 혼동됨 | 랭킹 모델 출력과 행동 라벨의 목적이 다름 | 후보 랭킹, 보정 확률, 최종 행동 라벨 분리 | 개선 완료 |
| 2026-06-15 | GitHub 첫 화면 설득력 부족 | README가 기능 설명 중심이고 증거 링크가 늦게 나옴 | 5초 요약, 증거 링크, Mermaid 흐름도, 문제 해결 기록 전면 배치 | 개선 완료 |
| 2026-06-15 | 일기와 오류 해결 기록이 흩어짐 | 일일 일기, 예측 기록, 문제점이 한 곳에서 추적되지 않음 | `docs/daily-prediction-diary.md`와 본 문서 역할 분리 | 개선 완료 |
| 2026-06-15 | 한글 깨짐과 물음표 표시 위험 | Windows 셸 인코딩 또는 GitHub 업로드 메시지 인코딩 문제 | 파일은 UTF-8, GitHub 업로드 메시지는 가능한 ASCII 또는 UTF-8 JSON 사용 | 개선 중 |
| 2026-06-15 | 핵심 관찰은 실패했지만 보조 관찰은 성공 | 반도체/전자 랭킹 신호가 실제 순환매 이동을 놓침 | 핵심 1개와 보조 후보군의 검증 지표를 분리 | 개선 중 |
| 2026-06-16~2026-06-17 | 장마감 자동화 후 GitHub 기록 누락 | 수집·학습 산출물은 생성됐지만 원격 일기 파일 반영 확인이 빠짐 | 날짜별 일기, README, 인덱스, 문제 해결 기록의 원격 반영 여부를 별도 검증 | 개선 완료 |
| 2026-06-17 | KRX 공식 데이터 partial 수집 | 일부 KRX 엔드포인트 지연 또는 요청 제한 | KIS 장마감 스냅샷, pykrx 보조 데이터, KRX 상태값을 함께 기록 | 관리 중 |
| 2026-06-17 | 장중 반등 신호와 다음날 예측 레이어 괴리 | 바이오·게임/엔터 장중 반등은 포착했지만 일봉 최종 라벨은 회피로 남음 | 장중 반등 score를 다음날 decision layer에 연결하는 구조 검토 | 개선 중 |
| 2026-06-19 | Top1/Top3 후보 신뢰도 낮음 | 점수 상위 후보가 실제 상위 섹터와 충분히 겹치지 않음 | RankIC, NDCG@3/5, Top3 겹침률, Top3-Bottom3 spread 운영 리포트 추가 | 개선 완료 |
| 2026-06-19 | 점수 상위 후보를 과신하는 문제 | 랭킹 품질이 약한 구간에도 행동 라벨이 강하게 나올 수 있음 | 랭킹 품질 기반 soft gate로 핵심/보조 행동을 한 단계 보수화 | 개선 완료 |
| 2026-06-19 | 정책 버전별 실전 성과 추적 부족 | 최신 final_action 정책과 과거 tomorrow_action 평가가 섞일 수 있음 | 실제 예측 당시 정책 버전 기준 live 성과 로그 분리 | 개선 완료 |
| 2026-06-19 | 전 섹터 회피 속 방어 후보가 숨겨지는 문제 | 시장 패닉 게이트가 전 섹터를 회피로 만들면 상대적으로 강한 섹터도 함께 묻힘 | 회피 결론은 유지하고 회피 압력과 방어 추적 후보를 별도 진단 컬럼으로 분리 | 개선 완료 |
| 2026-06-19 | 방어 추적 후보를 행동 승격으로 오해할 위험 | 후보 컬럼이 최신 예측부터 생겨 실제 수익률 검증 표본이 아직 없음 | `panic_watch_action`을 별도 추적 라벨로 분리하고 승격 가능성 검증 리포트 추가 | 개선 완료 |

## 1. 휴장일 데이터 중복 수집

### 문제

국내장이 휴장인 날에도 일부 가격 API는 직전 거래일 데이터를 반환할 수 있다. 이 값을 그대로 오늘 데이터로 저장하면 같은 가격 데이터가 다른 날짜로 중복 학습된다.

### 영향

- 모델이 실제로는 존재하지 않는 거래일을 학습한다.
- 전일 데이터가 오늘 데이터처럼 들어가 과대적합이 생길 수 있다.
- 다음 거래일 예측과 검증 날짜가 밀릴 수 있다.

### 해결

- 한국 거래일 캘린더를 기준으로 오늘이 실제 거래일인지 확인한다.
- API가 반환한 기준일과 수집 기준일이 다르면 가격 학습 데이터에서 제외한다.
- 다음 거래일이 휴장일이면 전날 예측과 일기 작성 후 장중 수집을 멈춘다.

### 검증

2026-06-03 휴장일 이후 같은 문제가 다시 생기지 않도록 장중 모니터에도 "실제 거래일에만 실행" 조건을 추가했다.

## 2. 환율 수집 상태 분리

### 문제

환율은 주식시장과 달리 공휴일 개념이 완전히 같지 않다. 주식 휴장일 제어변수를 그대로 환율에 적용하면 필요한 환율 데이터까지 잘못 차단할 수 있다.

### 해결

- 환율은 ECOS 수집 상태값을 별도로 기록한다.
- 주식시장 거래일 여부와 환율 데이터 고시 여부를 분리한다.
- 환율 결측은 무조건 실패가 아니라 `latest_available`, `stale`, `missing` 같은 상태로 해석한다.

## 3. KIS 타임아웃과 Naver realtime fallback

### 문제

KIS 실시간 API가 장중 타임아웃 또는 연결 실패를 보이는 경우가 있었다. 이때 수집 파이프라인이 멈추면 장중 차트와 반등 모델이 비게 된다.

### 해결

- KIS 실패 시 Naver realtime fallback을 사용한다.
- fallback을 사용한 경우 데이터 출처를 명확히 표시한다.
- intraday snapshot, rebound signal, learning state 갱신 여부를 따로 점검한다.

### 검증

2026-06-15 장중에는 KIS 회복 이후에도 2차전지 반등 신호가 반복적으로 포착됐다. 장중 모델은 2차전지 강세를 보조적으로 잘 잡았다.

## 4. 결측치와 이상치 처리 기준

### 문제

수집 데이터에는 고결측 변수, 원시 금액 스케일 변수, 저분산 변수, 지연 데이터가 섞일 수 있다. 이 값을 그대로 학습하면 특정 큰 숫자나 결측 패턴에 모델이 끌릴 수 있다.

### 해결

- 고결측 변수 제거 기준을 명확히 둔다.
- 원시 금액 변수는 그대로 넣지 않고 log, z-score, rolling mean 같은 안정화 변수를 우선 사용한다.
- 저분산 변수와 leakage 가능성이 있는 변수는 학습 전 제거한다.

### 검증

V2 학습 리포트에서 고결측, 원시 스케일, 저분산 제거 컬럼을 기록하도록 했다.

## 5. 급락장 신규 진입 위험

### 문제

2026-06-05처럼 전 섹터가 약세인 날에는 섹터 랭킹이 높아도 실제 신규 진입 후보로 보기 어렵다.

### 해결

- capitulation 국면을 별도 시장 상태로 분류한다.
- 약한 시장 폭, 하락 섹터 비율, 평균 수익률을 함께 봐서 회피 게이트를 강화한다.
- 강한 후보가 있더라도 시장 전체가 무너지면 행동 라벨을 낮춘다.

## 6. 급락 후 반등 포착 지연

### 문제

2026-06-08에는 모델이 급락 이후 반등 가능성을 지나치게 보수적으로 봤다. 회피 게이트가 손실 방어에는 유효했지만, 반등 초입에서는 기회를 늦게 잡을 수 있었다.

### 해결

- 일봉 기반 회피 게이트와 장중 반등 모델을 분리한다.
- intraday rebound score, sector advancers ratio, delta return을 별도 신호로 본다.
- 급락 이후에는 "회피 유지"와 "반등 관찰"을 동시에 표시한다.

## 7. 확률 과신

### 문제

모델이 출력하는 상승 확률이 실제 적중률보다 높게 나오는 구간이 있었다. 특히 의미 있는 상승, 초과 상승, 거래 가능한 상승 확률에서 과신이 나타났다.

### 해결

- 백테스트 기반 확률 보정 레이어를 추가했다.
- `calibrated_absolute_up_proba`, `calibrated_quality_adjusted_up_proba`, `calibrated_excess_up_proba`, `calibrated_tradeable_up_proba`를 생성했다.
- 최종 판단은 raw probability가 아니라 보정 확률과 리스크 게이트를 함께 본다.

## 8. 후보 선별과 상승 여부 예측 혼동

### 문제

섹터 랭킹 모델은 "다음 날 가장 강할 후보"를 고르는 모델이고, 상승 여부 모델은 "양수 수익률 가능성"을 보는 모델이다. 두 출력을 섞어 설명하면 모델 목적이 흐려진다.

### 해결

- `rank_model_score`: 상대 강도 후보 선별
- `combined_up_proba`: 절대 상승 가능성
- `calibrated_*_proba`: 보정된 신뢰도
- `final_action`: 사용자에게 보여줄 단일 최종 행동 라벨
- `tomorrow_action`: 기존 평가/자동화 호환을 위해 `final_action`과 같은 값으로 유지
- `score_action`: 점수 기반 1차 행동 라벨
- `decision_action`: 리스크와 신뢰도 게이트를 통과한 내부 의사결정 라벨

이렇게 출력 목적을 분리했다.

## 9. GitHub 첫 화면 설득력 부족

### 문제

기존 README는 프로젝트 설명은 있었지만, 처음 5초 안에 목적, 역할, 결과, 증거 링크가 바로 보이기에는 약했다.

### 해결

포트폴리오 자료 기준에 맞춰 README 상단을 다음 구조로 바꿨다.

- 5초 요약
- 최신 운영 기록
- 프로젝트 의미
- 전체 파이프라인 Mermaid
- 데이터 수집 구조
- 모델 구조
- 최신 모델 성능
- 일일 예측 일기
- 문제 해결 기록

## 10. 일기와 문제 해결 기록 분리

### 문제

날짜별 일기에는 그날의 시장 검증과 예측이 들어가고, 문제 해결 내용은 여러 날짜에 걸쳐 반복된다. 이 둘을 한 문서에만 두면 시간이 지나면서 읽기 어려워진다.

### 해결

- `docs/daily-prediction-diary.md`: 날짜별 일기 인덱스와 요약
- `docs/diary/YYYY-MM-DD.md`: 하루 단위 상세 일기
- `docs/problem-solving-log.md`: 문제별 원인, 해결, 검증 기록

## 11. 한글 깨짐과 GitHub 물음표 표시

### 문제

Windows PowerShell, 로컬 파일 인코딩, GitHub API 업로드 과정에서 한글 커밋 메시지나 파일명이 물음표로 깨져 보일 수 있다.

### 해결

- Markdown 파일은 UTF-8로 저장한다.
- GitHub API 업로드 시 파일 내용은 base64로 보내 인코딩 손상을 줄인다.
- 커밋 메시지는 필요하면 ASCII 문장으로 사용해 목록 화면 깨짐을 방지한다.

### 남은 확인

GitHub 웹 화면에서 README, 문서 링크, 날짜별 일기 파일명이 한글 깨짐 없이 보이는지 최종 확인해야 한다.

## 12. 2026-06-15 핵심 관찰 실패와 보조 관찰 성공

### 문제

2026-06-12 기준 예측에서 반도체/전자는 핵심 관찰이었지만, 실제 2026-06-15에는 -0.17%로 약했다. 반면 자동차, 금융, 조선/방산, 2차전지는 보조 관찰이었고 모두 양수 수익률을 기록했다.

### 해석

모델이 반등 후보군은 잡았지만, 가장 강한 섹터를 고르는 Top1 판단은 틀렸다. 이 경우 전체 예측 실패로만 기록하면 모델의 부분 성과가 사라지고, 성공으로만 기록하면 핵심 판단 오류가 숨겨진다.

### 해결 방향

- Top1 핵심 관찰 적중률과 보조 관찰 후보군 적중률을 분리한다.
- 실제 Top3 겹침, 핵심·보조 양수 비율, 기대수익률 오차를 함께 기록한다.
- 다음 모델 개선에서는 반도체/전자처럼 랭킹 점수가 남아 있지만 실제 약세로 전환되는 섹터의 페널티를 강화한다.

## 13. 2026-06-16~2026-06-17 GitHub 일기 업로드 누락

### 문제

2026-06-16 장마감 기준 데이터 수집, 모델 학습, 2026-06-17 예측 산출물은 생성됐지만, GitHub 원격 저장소에는 `docs/diary/2026-06-16.md` 파일이 올라가지 않았다. README의 최신 운영 기록과 일일 예측 일기 인덱스도 2026-06-15에서 멈춰 있었다.

### 영향

- 포트폴리오에서 날짜별 진행 기록이 끊긴다.
- 장마감 자동화가 실제로 수행됐는지 GitHub만 보고는 확인하기 어렵다.
- 예측 결과와 문제 해결 기록이 분리되어, 강의에서 요구한 "기간이 보이는 문제 해결 기록" 증거가 약해진다.

### 해결

- GitHub 원격 저장소의 `docs/diary` 목록을 확인해 2026-06-16 파일이 없음을 검증했다.
- 로컬 산출물의 `prediction_accuracy_summary.json`, `prediction_accuracy_log.csv`, `tomorrow_sector_prediction.csv`, `sector_rank_model_v5_metrics.json`을 기준으로 2026-06-16 일기를 다시 작성했다.
- README, `docs/daily-prediction-diary.md`, `docs/diary/README.md`, 본 문제 해결 기록을 같은 날짜 기준으로 업데이트했다.
- 문제 해결 항목 제목에 `2026-06-16~2026-06-17` 기간을 표시해, 언제 발견했고 언제 복구했는지 보이도록 했다.

### 검증

2026-06-17에 GitHub 저장소를 확인한 결과 2026-06-16 일기가 없었고, 이후 날짜별 일기와 인덱스를 다시 생성했다. 앞으로 장마감 자동화 이후에는 수집 성공 여부뿐 아니라 GitHub 원격 반영 여부까지 확인해야 한다.

## 14. 2026-06-17 KRX 공식 데이터 partial 수집

### 문제

2026-06-17 장마감 수집에서 KRX 공식 데이터 수집은 `partial` 상태로 끝났다. 일부 지수 데이터는 2026-06-16 기준, 일부 주식 데이터는 2026-06-15 기준으로 반환됐고, KOSDAQ/ETF/base 정보 일부는 비어 있었다.

### 영향

- KRX 공식 데이터만 보면 최신 장마감 데이터가 완전히 들어왔다고 보기 어렵다.
- 공식 데이터 지연을 모델 실패로 오해할 수 있다.
- 데이터 출처별 기준일을 기록하지 않으면 어떤 값이 최신이고 어떤 값이 보조인지 구분하기 어렵다.

### 해결

- KRX 공식 데이터 상태를 `partial`로 그대로 기록했다.
- KIS 장마감 스냅샷은 240개 종목 모두 성공했으므로 당일 섹터 수익률 검증에는 KIS 값을 우선 사용했다.
- pykrx 보조 데이터와 기존 KRX normalized stock rows를 함께 유지해 학습 파이프라인은 중단하지 않았다.
- 일기에는 KRX 상태와 KIS 성공 여부를 분리해서 적었다.

### 남은 확인

KRX 공식 데이터 지연이 반복되면 `KRX_MAX_RUNTIME_SECONDS`를 늘릴지, 장마감 자동화에서는 KIS/pykrx 우선 구조를 공식 정책으로 둘지 결정해야 한다.

## 15. 2026-06-17 장중 반등 신호와 다음날 예측 레이어 괴리

### 문제

2026-06-17 장중 모니터는 바이오와 게임/엔터의 반등 진행 신호를 여러 번 포착했다. 실제 종가 기준으로도 바이오는 +3.07%, 게임/엔터는 +1.78%로 강했다. 그러나 전일 기준 다음날 예측에서는 두 섹터가 대부분 회피 우선으로 남아 있었다.

### 영향

- 장중 반등 모델은 좋은 신호를 냈지만, 일봉 기반 다음날 예측에는 충분히 반영되지 않았다.
- 사용자가 보는 최종 일일 예측은 실제 주도 섹터를 늦게 따라갈 수 있다.
- 회피 게이트가 손실 방어에는 유효하지만, 반등 초입 포착에는 과도하게 보수적일 수 있다.

### 해결 방향

- 장중 rebound score, sector advancers ratio, intraday delta를 다음날 decision layer의 보조 변수로 연결한다.
- 단순히 장중 강세였다고 추격하지 않고, 2회 이상 연속 포착된 강한 반등 신호만 별도 가산한다.
- 바이오와 게임/엔터처럼 실제 종가로 검증된 사례를 반등 모델 학습 데이터에 누적한다.

### 검증 계획

2026-06-18에는 반도체/전자 방어 관찰과 함께 바이오·게임/엔터의 후속 확산 여부를 장중 모니터로 추적한다. 만약 바이오·게임/엔터가 다시 강하게 이어진다면 장중 반등 신호 가중치를 상향하는 근거로 삼는다.

## 16. 2026-06-17 예측 신뢰도 라벨이 모두 low로 고정되는 문제

### 문제

다음날 섹터 상승 여부와 예상 수익률을 함께 예측하도록 모델을 확장했지만, 최종 예측표의 `decision_confidence_label`은 대부분 또는 전부 `low`로 남았다. 기존 라벨은 현재 점수, 리스크 게이트, 예측 신뢰 점수만 보는 규칙형 구조였기 때문에, 과거에 비슷한 예측 조건이 실제로 얼마나 맞았는지 반영하지 못했다.

### 영향

- 사용자는 점수 상위 섹터와 신뢰도 라벨 사이의 차이를 해석하기 어렵다.
- 모델이 조선/방산, 반도체/전자처럼 상대적으로 나은 후보를 골라도 모두 `low`로 표시되면 우선순위 판단 근거가 약해진다.
- 반대로 단순히 임계값만 낮추면 검증되지 않은 과신 라벨이 생길 수 있다.

### 해결

- `sector_model_v2_backtest_predictions.csv`의 워크포워드 백테스트 2,268개 샘플을 신뢰도 기준 데이터로 사용했다.
- 현재 예측과 비슷한 `primary_return_pred`, `calibrated_quality_adjusted_up_proba`, `expected_return_signal_to_noise`, `expected_return_error_p80_pct` 구간을 찾아 과거 적중률, 평균 수익률, 하락 위험률을 계산했다.
- 표본 수가 작은 구간은 전체 평균 쪽으로 수축시키는 방식으로 과신을 줄였다.
- 기존 규칙 기반 라벨은 `rule_confidence_label`로 보존하고, 최종 `decision_confidence_label`은 백테스트 기반 경험 신뢰도로 다시 산정했다.

### 검증

2026-06-17 기준 재생성 결과, 기존 규칙 라벨은 12개 섹터 모두 `low`였지만 백테스트 기반 보정 후에는 조선/방산과 반도체/전자가 `medium`, 나머지 10개 섹터가 `low`로 분리됐다. 최종 행동 컬럼은 계속 `final_action = tomorrow_action`으로 유지되어 기존 평가 자동화와 충돌하지 않는다.

## 17. 2026-06-18 예상 수익률 단일값 과신 문제

### 문제

모델은 섹터별 `primary_next_return_pred`를 산출하지만, 대부분의 예측값은 +0.0%~+0.2% 근처에 몰려 있고 예상 오차폭은 약 ±2%~±4%로 훨씬 컸다. 따라서 `+0.16% 상승 예상`처럼 단일 숫자만 보여주면 실제 불확실성보다 모델이 더 정확해 보이는 문제가 있었다.

### 영향

- 예상 수익률 숫자만 보고 섹터를 고르면 오차폭이 큰 후보를 과대평가할 수 있다.
- 상승 가능성은 있어도 하락 위험이 큰 섹터와, 상승폭은 작지만 위험 대비 보상이 나은 섹터를 구분하기 어렵다.
- 포트폴리오 설명에서 “얼마나 오를 것인가”와 “그 예측이 믿을 만한가”가 섞여 보인다.

### 해결

- `expected_return_risk_adjusted_score`를 추가해 예상 수익률, 오차폭, 백테스트 경험 평균수익, 경험 하락위험, 리스크 게이트를 함께 반영했다.
- `expected_return_grade`를 추가해 단일 숫자 대신 `상승 우위`, `제한적 상승`, `약한 상승/오차 큼`, `중립/오차 큼`, `하락 위험`처럼 해석 가능한 등급으로 표시했다.
- `return_risk_score_adjustment`를 도입하되 최종 점수에는 최대 약 ±0.04 이내로만 반영해 기존 모델 구조가 갑자기 흔들리지 않도록 했다.
- 최종 행동은 계속 `final_action` 보수 게이트를 통과해야 하므로, 수익률 등급이 좋아도 리스크 모델이 회피를 요구하면 `회피 우선`으로 남게 했다.

### 검증

2026-06-18 예측표 재생성 결과, 수익률 등급은 `상승 우위` 4개, `제한적 상승` 1개, `약한 상승/오차 큼` 5개, `중립/오차 큼` 2개로 분리됐다. 점수 조정폭은 -0.013~+0.009 수준으로 작았고, 최종 행동 분포는 `회피 우선` 9개, `관망` 2개, `방어 관찰` 1개로 유지됐다.

## 18. 2026-06-18 상승 신호와 회피 신호가 동시에 보이는 문제

### 문제

수익률 등급과 장중 반등 신호는 좋은데 최종 행동은 `회피 우선` 또는 `관망`으로 나오는 섹터가 생겼다. 예를 들어 바이오는 예상 수익률 등급이 `상승 우위`이고 장중 브릿지도 양호했지만, 최종 행동은 `회피 우선`으로 남았다. 사용자가 보기에는 모델이 같은 섹터를 동시에 좋다고도 하고 나쁘다고도 말하는 것처럼 보일 수 있었다.

### 영향

- 상승 후보와 회피 후보의 차이를 사람이 해석하기 어려웠다.
- 실제 구조는 `알파 신호`와 `리스크 게이트`가 분리된 정상적인 포트폴리오 판단인데, 출력에는 그 이유가 충분히 드러나지 않았다.
- GitHub 포트폴리오 관점에서도 “모델이 왜 그렇게 판단했는가”를 설명하는 증거가 부족했다.

### 해결

- `signal_conflict_type`을 추가해 `상승신호-리스크충돌`, `상승신호-보수관찰`, `약신호-회피일치`, `진입 후보`, `중립 관찰`로 상태를 나누었다.
- `positive_signal_count`와 `risk_block_count`를 추가해 상승 근거와 차단 근거가 각각 몇 개인지 보이게 했다.
- `signal_conflict_score`를 추가해 상승 근거와 리스크 차단이 동시에 강한 섹터를 우선 점검할 수 있게 했다.
- `final_decision_explanation`과 `entry_condition_note`를 추가해 최종 판단 이유와 다음 진입 확인 조건을 문장으로 남겼다.
- 기존 `final_action`과 `tomorrow_action`은 유지해 기존 평가 자동화와 호환되도록 했다.

### 검증 계획

2026-06-18 예측부터 바이오, 조선/방산, 반도체/전자를 중심으로 `상승신호-리스크충돌` 또는 `상승신호-보수관찰`이 실제 다음 거래일 성과와 어떻게 이어지는지 확인한다. 충돌 섹터가 반복적으로 상승한다면 리스크 게이트 완화 조건을 조정하고, 반대로 충돌 섹터가 자주 실패한다면 현재 보수 판단이 유효하다고 본다.

## 19. 2026-06-18 최종 행동 임계값이 성과 기준으로 검증되지 않은 문제

### 문제

`tomorrow_total_score`와 `tomorrow_action`은 만들어지고 있었지만, `핵심 관찰`, `보조 관찰`, `관망`, `회피 우선` 같은 행동 라벨이 실제 다음 거래일 수익률에서 얼마나 유효했는지 별도 리포트로 확인하지 못했다. 따라서 점수 0.62 이상을 보조 관찰로 보는 기준이 맞는지, 회피 우선이 진짜 손실 방어에 도움이 되는지 판단하기 어려웠다.

### 점검

- `prediction_accuracy_log.csv`에 2026-05-12부터 2026-06-17까지 25거래일, 300개 평가 행이 존재했다.
- 각 행에는 `tomorrow_action`, `tomorrow_total_score`, `actual_sector_return`이 함께 있어 행동 라벨별 백테스트는 가능했다.
- 다만 최신 `final_action`, `signal_conflict_type` 정책은 2026-06-18 예측부터 본격적으로 기록되므로, 새 정책을 곧바로 과거 전체에 대해 최적화하기에는 표본이 부족했다.

### 해결

- `scripts/analyze_action_thresholds.py`를 추가해 행동 라벨별 성과, 점수 임계값 후보, Top-K 전략 성과를 분리해서 계산하도록 했다.
- `reports/action_label_performance.csv`, `reports/action_threshold_grid.csv`, `reports/action_topk_backtest.csv`를 생성했다.
- 요약 리포트 `reports/action_threshold_backtest_report.md`와 `reports/action_threshold_backtest_summary.json`을 생성했다.
- 예측 로직 자체는 바꾸지 않고, 임계값 조정을 위한 진단 자료만 먼저 만들었다.

### 확인 결과

기존 `tomorrow_action` 기준으로는 `핵심 관찰`의 평균 수익률이 가장 나았지만 표본은 19개로 작았다. `보조 관찰`은 평균 수익률과 하락 위험이 좋지 않았고, `회피 우선`도 일부 상승 섹터를 놓친 사례가 있었다. 점수 임계값만 단독으로 낮추거나 올리는 방식은 일관된 해결책으로 보기 어려웠다.

### 다음 단계

행동 기준을 바로 수정하지 않고, 후보 임계값을 walk-forward 방식으로 검증한다. 이전 구간에서 고른 임계값이 다음 구간에서도 성과를 내는지 확인한 뒤에만 `assign_actions` 또는 `final_action` 게이트를 조정한다.

## 20. 2026-06-18 최신 행동 정책을 과거 데이터에 재현 검증하기 어려운 문제

### 문제

최신 `final_action` 정책은 `expected_return_grade`, 백테스트 기반 신뢰도, 장중 브릿지, `signal_conflict_type` 같은 최근 컬럼을 사용한다. 하지만 과거 `tomorrow_sector_prediction_history.csv`에는 이 컬럼들이 전체 기간에 남아 있지 않다. 따라서 최신 정책을 과거 25거래일 전체에 그대로 재적용하면 완전한 point-in-time 재현이 아니라 일부 컬럼을 기본값으로 보정한 제한적 replay가 된다.

### 점검

- 과거 예측 히스토리는 336행, 28개 타깃 날짜가 있었다.
- 실제 수익률과 연결 가능한 평가 행은 300개, 25거래일이었다.
- `v4_action`은 252행, `v5_action`은 192행에 남아 있었다.
- `decision_score`, `risk_control_score`, 예상 수익률 구간 컬럼은 48행에만 남아 있었다.
- `intraday_bridge_score`, `signal_conflict_type`, `final_action`은 최신 12행에만 남아 있었고, 아직 실제 수익률 검증 대상이 아니었다.

### 해결

- `scripts/replay_final_action_policy.py`를 추가했다.
- 과거 예측 점수를 다시 학습하지 않고, 저장된 과거 점수와 사용 가능한 V4/V5 리스크 컬럼에 현재 `decision_layer_v8_signal_conflict_explain` 행동 정책을 제한적으로 재적용했다.
- 결과는 `reports/policy_replay_backtest.csv`, `reports/policy_replay_action_performance.csv`, `reports/policy_replay_action_comparison.csv`, `reports/policy_replay_backtest_report.md`, `reports/policy_replay_backtest_summary.json`에 저장했다.
- 입력 품질을 `rank_risk_snapshot`, `legacy_score_proxy`, `v4_risk_snapshot`, `decision_return_snapshot`으로 나누어 해석 시 주의할 수 있게 했다.

### 확인 결과

300개 평가 행 전체를 replay할 수 있었고, 기존 행동과 replay 행동이 다른 행은 115개로 변경률은 38.3%였다. replay 정책은 `회피 우선` 228개, `관망` 68개, `보조 관찰` 2개, `방어 관찰` 2개로 매우 보수적으로 쏠렸다. 이는 최신 정책이 과거 로그에 그대로 적용되면 상승 후보를 과도하게 줄일 수 있음을 보여준다.

### 다음 단계

이 replay 결과만으로 최종 행동 기준을 바꾸지 않는다. 최신 정책이 며칠 더 자연스럽게 누적된 뒤 실제 v8 스냅샷 기준 성과를 분리해서 본다. 동시에 과거 로그에는 미래 누수 없이 당시 사용 가능했던 컬럼만 표시하는 `replay_input_quality`를 계속 유지해, walk-forward 검증에서 표본 품질별로 성과를 따로 비교한다.

## 21. 2026-06-18 예측 당시 입력과 중간 결과 스냅샷 보존 부족 문제

### 문제

다음 거래일 섹터 상승 여부와 예상 수익률을 예측한 뒤 `tomorrow_sector_prediction.csv`와 요약 JSON은 갱신되지만, 그 예측이 만들어질 당시의 입력 파일, 모델 산출물, 판단 정책 상태가 날짜별로 따로 보존되지 않았다. 이 상태에서는 며칠 뒤 특정 예측을 다시 설명하려고 할 때 당시 어떤 데이터와 정책 버전으로 판단했는지 추적하기 어렵다.

### 점검

- 최신 예측 파일 `reports/tomorrow_sector_prediction.csv`와 `reports/tomorrow_sector_prediction_summary.json`은 정상 존재했다.
- 최신 요약 기준 기준일은 2026-06-17, 예측 대상일은 2026-06-18, 정책 버전은 `decision_layer_v8_signal_conflict_explain`이었다.
- `reports/prediction_snapshots/` 날짜별 보존 폴더는 아직 없었다.
- 장마감 파이프라인은 내일 예측 생성 직후 평가와 진단으로 넘어가고 있어, 그 사이에 스냅샷 보존 단계를 넣어도 기존 학습과 예측 점수에는 영향을 주지 않는 구조였다.

### 해결

- `scripts/create_prediction_snapshot.py`를 추가했다.
- 스크립트는 예측 대상일별로 `reports/prediction_snapshots/YYYY-MM-DD/` 폴더를 만들고, 그 안에 `prediction.csv`, `summary.json`, `input_manifest.json`, `model_manifest.json`, `decision_manifest.json`, `run_manifest.json`, `README.md`를 저장한다.
- manifest에는 주요 입력 파일과 모델 산출물의 존재 여부, 수정 시각, 파일 크기, SHA-256 해시를 기록한다.
- `decision_manifest.json`에는 정책 버전, 최종 행동 분포, 판단 신뢰도, 예상 수익률 등급, 신호 충돌 유형, 상위 예측 섹터를 함께 남긴다.
- `reports/prediction_snapshots/latest_snapshot.json`을 갱신해 가장 최근 스냅샷 위치를 빠르게 확인할 수 있게 했다.
- `scripts/run_daily_collection.ps1`에 `prediction snapshot archive` 단계를 추가해 장마감 예측 생성 직후 자동 보존되도록 연결했다.

### 확인 결과

2026-06-18 예측에 대해 스냅샷 폴더가 생성되었고, 예측 결과와 요약 JSON이 정상 복사되었다. 입력 manifest와 모델 manifest도 생성되어 나중에 “그날 어떤 파일 상태로 예측했는가”를 날짜별로 재현할 수 있게 되었다.

### 다음 단계

며칠간 스냅샷을 누적한 뒤, 실제 수익률 평가와 스냅샷을 연결해 `final_action`, `decision_confidence`, `signal_conflict_type`별 성과를 분리해서 본다. 이 결과가 쌓이면 행동 기준을 감으로 조정하지 않고, 날짜별 보존 증거를 기준으로 walk-forward 검증을 진행한다.

## 22. 2026-06-19 절대 상승 예측과 상대 강도 예측이 섞이는 문제

### 문제

우리 모델은 다음 거래일 섹터의 상승 가능성과 예상 수익률을 예측하는 것을 목표로 한다. 그런데 실제 시장이 전체적으로 급락하는 날에는 어떤 섹터가 -0.3%로 마감해도 절대 수익률 기준으로는 실패지만, 전체 섹터 평균이 -3%대라면 상대 강도 기준으로는 매우 강한 섹터가 된다. 기존 `direction_hit`만 보면 이런 차이가 한 줄로 섞여서, 모델이 완전히 틀린 것인지 아니면 하락장 속 방어 섹터를 잡은 것인지 구분하기 어려웠다.

### 점검

- `prediction_accuracy_log.csv`에는 2026-05-12부터 2026-06-18까지 26거래일, 312개 평가 행이 존재했다.
- 모든 거래일에 12개 섹터가 채워져 있었고 실제 수익률 결측은 없었다.
- 따라서 학습 로직이나 예측 점수를 바로 바꾸지 않고, 평가 로그에 절대 상승과 상대 강도를 분리하는 지표를 추가해도 기존 파이프라인을 깨지 않는다고 판단했다.

### 해결

- `scripts/evaluate_prediction_accuracy.py`에 상대 강도 평가 레이어를 추가했다.
- `actual_market_avg_return`, `actual_excess_return`, `actual_return_rank`, `predicted_score_rank`를 계산하도록 했다.
- `absolute_return_hit`, `relative_excess_hit`, `actual_top3_flag`, `predicted_top3_flag`, `predicted_top3_actual_top3_hit`을 추가해 절대 상승, 시장 대비 초과수익, Top3 적중을 분리했다.
- `reports/relative_strength_evaluation_summary.json`, `reports/relative_strength_by_date.csv`, `reports/relative_strength_action_performance.csv`를 생성하도록 했다.
- 예측 모델 자체와 최종 행동 기준은 아직 바꾸지 않고, 평가 체계만 먼저 정리했다.

### 확인 결과

2026-06-18까지 재평가한 결과 전체 절대 상승률은 40.4%, 상대 초과수익률은 45.8%였다. 점수 Top1의 절대 상승률은 34.6%였지만 상대 초과수익률은 46.2%로 더 높게 나왔다. 점수 Top3 평균 실제 수익률은 -0.35%였지만 평균 초과수익은 +0.06%였다. 즉 현재 모델은 아직 매수 신호로 보기에는 약하지만, 장이 나쁜 날 상대적으로 덜 빠지는 섹터를 일부 포착하는 성격이 있음을 확인했다.

### 다음 단계

이제 예측 결과를 볼 때 `상승 성공/실패`와 `상대 강도 성공/실패`를 따로 판단한다. 표본이 더 쌓이면 `final_action`을 절대 상승형, 방어 상대강도형, 회피형으로 분리할지 검토한다.

## 23. 2026-06-19 최근 실전 성능이 약해지는 문제

### 문제

전체 백테스트에서는 V5 랭킹 모델의 Top1, Top3 성과가 의미 있게 보였지만, 최근 실제 예측 로그에서는 Top1 절대 상승률과 Top3 평균 수익률이 약해지는 구간이 있었다. 이 상태에서 과거 전체 평균만 보고 행동 기준을 조정하면, 최근 시장 국면 변화나 모델 과신을 놓칠 수 있다.

### 외부 사례 기준

Qlib, Kaggle JPX, FinRL, 확률 보정 문서와 concept drift 사례를 확인한 결과, 금융 예측 모델은 최근 성능 약화를 바로 새 모델로 덮기보다 최근 구간별 성능 감시, 순위 기반 평가, 리스크 게이트, 확률 보정을 먼저 분리해 관리하는 방식이 일반적이었다. 따라서 우리 프로젝트도 행동 기준을 바로 바꾸기 전에 최근 5/10/20거래일 성능을 따로 남기는 진단 체계를 우선 추가하기로 했다.

### 점검

- `build_tomorrow_prediction.py`에는 이미 최근 섹터 신뢰도 보정이 일부 들어가 있었다.
- 하지만 `prediction_accuracy_log.csv`를 기준으로 최근 5/10/20거래일 성능을 날짜별로 비교하는 별도 리포트는 없었다.
- 최근 평가 로그는 26거래일, 312개 행으로 구성되어 있었고 모든 거래일에 12개 섹터가 존재했다.
- 따라서 예측 산식이나 `final_action`을 바로 바꾸지 않고, 평가 파이프라인에 최근 성능 감시 산출물을 추가하는 것은 안전하다고 판단했다.

### 해결

- `scripts/evaluate_prediction_accuracy.py`에 최근 성능 감시 레이어를 추가했다.
- `reports/recent_window_performance_summary.json`, `reports/recent_window_performance.csv`, `reports/recent_sector_window_performance.csv`를 생성하도록 했다.
- 각 창에는 최근 5/10/20거래일과 전체 기간의 시장 평균 수익률, 시장 양수 비율, 점수 Top1/Top3 절대 수익률, 초과수익률, Top3 겹침률, Top3-Bottom3 spread를 기록했다.
- 이 리포트는 감시 신호일 뿐이며, 단독으로 `final_action`을 바꾸지 않도록 명시했다.

### 확인 결과

2026-06-18 기준 최근 5거래일 Top3 평균 수익률은 +1.01%, 평균 초과수익은 +0.40%, Top3-Bottom3 spread는 +0.73%로 단기 성능은 회복되는 모습을 보였다. 반면 최근 10거래일 Top1 평균 수익률은 -0.88%, Top3-Bottom3 spread는 -0.07%로 여전히 불안정한 구간이 남아 있었다. 즉 “최근 성능 약화”는 전 구간이 계속 나쁜 것이 아니라, 10거래일 구간에서 흔들리고 5거래일 구간에서 일부 회복되는 국면으로 분리해서 볼 수 있게 되었다.

### 다음 단계

최근 창이 2~3회 더 누적된 뒤에도 10거래일 또는 20거래일 Top3 spread가 음수로 유지되면, 그때 `final_action`의 진입 게이트를 더 보수적으로 조정한다. 반대로 최근 5거래일만 강하고 10/20거래일이 약하면 단기 반등 신호로만 해석하고 핵심 진입 신호로는 올리지 않는다.

## 24. 2026-06-19 Top1/Top3 후보 신뢰도 낮음 문제

### 문제

현재 모델은 다음 거래일 섹터의 상승 가능성과 예상 수익률을 계산하지만, 실제 투자 판단에서는 점수 상위 1개 또는 상위 3개 섹터가 중요하다. 그런데 최근 평가에서 점수 Top1이 실제 Top3에 들어간 비율은 26.9%, 점수 Top3가 실제 Top3와 겹친 비율은 28.2%에 그쳤다. 이 상태에서는 방향 정확도만 보면 후보 선별력이 얼마나 약한지 숨겨질 수 있다.

### 외부 사례 기준

Qlib, Kaggle JPX, LightGBM LambdaRank, 주식 ranking loss 사례를 확인한 결과, 섹터나 종목을 고르는 모델은 단순 상승/하락 정확도만 보지 않고 `RankIC`, `NDCG@K`, Top-K 겹침률, Top-Bottom spread 같은 랭킹 품질 지표를 함께 본다. 따라서 우리 프로젝트도 행동 기준을 바로 바꾸기 전에 운영 예측 점수인 `tomorrow_total_score`가 실제 수익률 순위를 얼마나 잘 정렬하는지부터 별도 리포트로 남기기로 했다.

### 점검

- `scripts/train_sector_rank_model_v4.py`, `scripts/train_sector_rank_model_v5.py`에는 학습 단계의 `ndcg@3` 또는 RankIC 계열 검증이 일부 존재했다.
- 하지만 실제 운영 예측 로그인 `prediction_accuracy_log.csv` 기준으로 `tomorrow_total_score`의 일별 랭킹 품질을 기록하는 산출물은 없었다.
- 평가 로그는 2026-05-12부터 2026-06-18까지 26거래일, 312개 행으로 구성되어 있었고, 날짜별 12개 섹터가 정상 채워져 있었다.
- 따라서 예측 점수 산식이나 `final_action`은 건드리지 않고, 평가 리포트만 추가하는 것은 안전하다고 판단했다.

### 해결

- `scripts/evaluate_prediction_accuracy.py`에 `write_ranking_quality_reports`를 추가했다.
- 일별 `rank_ic_spearman`, `rank_ic_pearson`, `ndcg_at_3`, `ndcg_at_5`, Top1 실제 순위, Top3 실제 Top3 겹침률, Top3-Bottom3 spread를 계산하도록 했다.
- `reports/ranking_quality_summary.json`, `reports/ranking_quality_by_date.csv`, `reports/ranking_quality_window_summary.csv`를 새로 생성하도록 했다.
- 기존 `prediction_accuracy_summary.json`에도 `rank_ic_spearman_avg`, `ndcg_at_3_avg`, `ranking_quality_warnings`를 함께 넣어 장마감 평가 결과에서 바로 확인할 수 있게 했다.
- 이 변경은 평가 레이어만 추가한 것이며, 예측 점수나 최종 행동 라벨은 변경하지 않았다.

### 확인 결과

2026-06-18까지 재평가한 결과 전체 RankIC Spearman 평균은 +0.0506, Pearson 평균은 +0.0789로 약한 양의 순위 상관만 보였다. 전체 NDCG@3 평균은 0.5803, NDCG@5 평균은 0.6324였고, Top1 실제 Top3 비율은 26.9%, Top3 실제 Top3 겹침률은 28.2%였다. 최근 5거래일은 RankIC Spearman 평균 +0.0755, Top3-Bottom3 spread +0.73으로 단기 회복 조짐이 있었지만, 최근 10거래일은 RankIC Spearman 평균 -0.0206, Top3-Bottom3 spread -0.07로 아직 불안정했다.

### 다음 단계

이 리포트를 며칠 더 누적한 뒤, `top3_overlap_below_30pct` 또는 최근 `rank_ic_spearman` 음수 경고가 반복되면 점수 상위 후보를 그대로 행동 후보로 올리지 않는다. 그때는 `tomorrow_total_score`에 최근 섹터 신뢰도, 신호 충돌, 예상 수익률 오차 패널티를 더 강하게 반영하는 방향으로 다음 개선을 진행한다.

## 25. 2026-06-19 점수 상위 후보를 과신하는 문제

### 문제

운영 예측 점수인 `tomorrow_total_score`는 섹터 후보의 상대 우선순위를 보여준다. 하지만 최근 랭킹 품질 리포트에서 Top3 실제 Top3 겹침률이 28.2%로 낮고, 최근 10거래일 RankIC와 Top3-Bottom3 spread가 음수로 나온 구간이 있었다. 이 상태에서 점수 상위 후보가 나오면 모델이 아직 충분히 검증되지 않은 후보를 `핵심 관찰` 또는 `보조 관찰`로 강하게 보여줄 위험이 있다.

### 외부 사례 기준

Qlib의 포트폴리오 전략 구조는 예측 모델 점수와 실제 포트폴리오 행동을 분리한다. Kaggle JPX와 learning-to-rank 사례도 상위 후보의 NDCG, RankIC, Top-Bottom spread를 따로 검증한 뒤 전략에 연결한다. 따라서 우리 프로젝트도 예측 점수 자체를 바로 고치기보다, 점수와 최종 행동 사이에 랭킹 품질 기반 게이트를 두는 것이 더 안전하다고 판단했다.

### 점검

- `reports/ranking_quality_summary.json`은 정상 생성되어 있었다.
- 최신 게이트 기준은 `caution`이었다.
- 전체 RankIC Spearman은 +0.0506, 전체 Top3 겹침률은 28.2%였다.
- 최근 5거래일은 RankIC +0.0755, Top3-Bottom3 spread +0.73으로 회복 신호가 있었다.
- 반면 최근 10거래일은 RankIC -0.0206, Top3-Bottom3 spread -0.07로 아직 불안정했다.
- 따라서 `severe` 차단이 아니라 `caution` 단계의 soft downgrade만 적용하는 것이 적절하다고 판단했다.

### 해결

- `scripts/build_tomorrow_prediction.py`의 정책 버전을 `decision_layer_v9_ranking_quality_soft_gate`로 올렸다.
- `load_ranking_quality_gate`와 `apply_ranking_quality_gate`를 추가했다.
- 랭킹 품질 리포트가 없거나 읽기 실패하면 `normal`로 처리해 예측 파이프라인이 멈추지 않도록 했다.
- `caution` 단계에서는 `핵심 관찰`을 `보조 관찰`로, `보조 관찰`을 `관망`으로 한 단계 낮춘다.
- `severe` 단계에서는 `핵심 관찰`, `보조 관찰`, `방어 관찰`을 `관망`으로 낮추도록 했다.
- 이미 `회피 우선`인 섹터는 그대로 두어 리스크 회피 판단을 되돌리지 않도록 했다.
- 결과 CSV와 요약 JSON에 `ranking_quality_gate_level`, `ranking_quality_gate_reason`, `ranking_quality_gate_downgrade_count`, 최근 RankIC와 spread 지표를 함께 남기도록 했다.

### 확인 결과

2026-06-19 대상 예측을 다시 생성한 결과 게이트 레벨은 `caution`으로 표시되었다. 최신 예측은 전 섹터가 이미 `회피 우선`이었기 때문에 실제 다운그레이드 수는 0개였고, 최종 행동 분포도 `회피 우선` 12개로 유지되었다. 즉 이번 변경은 현재 결과를 억지로 바꾸지 않고, 앞으로 `핵심 관찰` 또는 `보조 관찰` 후보가 다시 나올 때 랭킹 품질이 약하면 행동 강도를 자동으로 낮추는 안전장치로 작동한다.

### 다음 단계

며칠간 `ranking_quality_gate_downgrade_count`가 실제로 발생하는지 확인한다. 다운그레이드 이후 성과가 좋아지면 soft gate를 유지하고, 반대로 좋은 후보까지 지나치게 낮춘다면 `caution` 기준을 최근 5거래일보다 10/20거래일 중심으로 재조정한다.

## 26. 2026-06-19 정책 버전별 실전 성과 추적 부족 문제

### 문제

최신 예측 정책은 `decision_layer_v9_ranking_quality_soft_gate`까지 발전했지만, 기존 성과 평가는 주로 `prediction_accuracy_log.csv`의 `tomorrow_action` 기준으로 이루어졌다. 이 상태에서는 과거 행동 라벨, 최신 `final_action`, 제한적 replay 결과가 섞여 보일 수 있고, v8에서 v9로 넘어간 것이 실제 성과 개선인지 판단하기 어렵다.

### 외부 사례 기준

Qlib Recorder, MLflow Tracking, FinRL paper/live trading 구조는 모두 실행 단위로 모델 버전, 정책 버전, 입력, 출력, 실제 결과를 분리해서 기록한다. Kaggle JPX 같은 time-series 평가도 미래 데이터를 보지 않는 순차 예측 구조를 강조한다. 따라서 우리 프로젝트도 최신 정책을 과거에 억지로 재현하기보다, 실제 그날 생성된 정책 결과가 나중에 어떤 성과를 냈는지 따로 누적하는 구조가 필요했다.

### 점검

- `tomorrow_sector_prediction_history.csv`에는 전체 348개 예측 행이 있었다.
- `decision_policy_version`과 `final_action`이 남아 있는 실제 정책 행은 24개였다.
- 그중 실제 수익률과 연결 가능한 행은 12개였다.
- 2026-06-18 대상 예측은 `decision_layer_v8_signal_conflict_explain`로 실제 수익률 평가가 가능했다.
- 2026-06-19 대상 예측은 `decision_layer_v9_ranking_quality_soft_gate`로 기록되어 있지만, 아직 실제 수익률이 없어 성과 로그에서는 제외하는 것이 맞다고 판단했다.

### 해결

- `scripts/evaluate_prediction_accuracy.py`에 `write_policy_live_performance_reports`를 추가했다.
- `reports/policy_live_performance_log.csv`를 생성해 실제 정책 버전, 최종 행동, 신호 충돌 유형, 랭킹 품질 게이트, 실제 수익률, 초과수익, Top3 여부를 한 행 단위로 남기도록 했다.
- `reports/policy_live_version_performance.csv`를 생성해 정책 버전별 평균 수익률, 초과수익률, 절대 상승률, 상대 초과수익률, 실제 Top3 비율을 비교할 수 있게 했다.
- `reports/policy_live_action_performance.csv`를 생성해 같은 정책 버전 안에서도 `방어 관찰`, `관망`, `회피 우선` 같은 최종 행동별 성과를 분리했다.
- `reports/policy_live_performance_summary.json`을 생성해 최신 평가된 정책 버전과 산출물 위치를 요약했다.
- 이 리포트는 실제 예측 히스토리에 `decision_policy_version`과 `final_action`이 남아 있고, 실제 수익률까지 연결된 행만 사용한다. replay-only 행과 아직 결과가 나오지 않은 target date는 의도적으로 제외했다.

### 확인 결과

첫 생성 결과 `policy_live_performance_log.csv`에는 12개 행이 기록되었다. 현재 평가 가능한 정책 버전은 `decision_layer_v8_signal_conflict_explain` 1개이고, 평가 대상일은 2026-06-18 하루다. 이날은 전체 섹터가 모두 하락해 절대 상승률은 0%였지만, 상대 초과수익률은 50%였다. `방어 관찰`로 남은 반도체/전자는 실제 수익률 -0.32%였지만 시장 평균 대비 초과수익 +2.84%로 실제 1위 섹터였다. v9 정책은 2026-06-19 실제 결과가 붙는 다음 평가부터 자동으로 이 로그에 들어간다.

### 다음 단계

v9 정책이 최소 5거래일 이상 쌓이면 v8과 v9를 바로 비교하지 않고, 먼저 행동 라벨별 성과와 랭킹 품질 게이트 발생 여부를 본다. 표본이 충분히 쌓이면 `policy_live_version_performance.csv`를 기준으로 정책 버전별 평균 수익률, 초과수익률, Top3 포착률을 비교해 다음 행동 기준 조정 여부를 판단한다.

## 27. 2026-06-19 전 섹터 회피 속 방어 후보가 숨겨지는 문제

### 문제

2026-06-19 대상 예측에서 `final_action`이 12개 섹터 모두 `회피 우선`으로 나왔다. 시장 전체가 `capitulation`에 가까운 패닉 구간이고 V5 no-trade 게이트가 전 섹터에 켜졌기 때문에 회피 판단 자체는 타당했다. 하지만 이 구조에서는 반도체/전자, 금융처럼 시장 평균 대비 방어력이 있거나 예상 수익률 등급이 상대적으로 나은 섹터도 화면상으로는 똑같이 `회피 우선`으로만 보인다. 즉 매수 신호를 풀면 위험하고, 그대로 두면 후보 해석력이 떨어지는 문제가 있었다.

### 외부 사례 확인

FinRL의 turbulence gate는 극단적 시장 위험 구간에서 매수를 중단하거나 보유 비중을 줄이는 방식으로 리스크를 먼저 통제한다. Qlib은 예측 점수와 실제 포트폴리오 전략을 분리하고, TopkDropout처럼 상위 후보를 유지하되 약한 후보만 교체하는 방식을 제공한다. 현금 비중 overlay, regime-aware allocation, confidence threshold 사례도 공통적으로 예측 신호와 행동 신호를 바로 동일시하지 않고, 시장 국면과 신뢰도에 따라 행동 강도를 조절한다.

따라서 우리 프로젝트에서는 no-trade 게이트를 제거하지 않고 유지하는 쪽이 맞다. 대신 회피 결론 안에서도 상대적으로 강한 후보를 따로 표시해 다음 장 실시간 확인 대상으로 남기는 구조가 더 안전하다고 판단했다.

### 점검

- 최신 예측 파일 기준 `final_action`, `score_action`, `decision_action`은 모두 `회피 우선` 12개였다.
- `v5_no_trade_flag`는 12개 섹터 모두 1이었고, 사유는 모두 `시장 패닉 국면`이었다.
- `market_regime_risk_v4`는 0.85로 높았고, `decision_confidence_label`도 12개 모두 `low`였다.
- 이 상태에서 `final_action`을 `관망`이나 `방어 관찰`로 완화하는 것은 아직 안전하지 않다고 판단했다.

### 해결

- `scripts/build_tomorrow_prediction.py`에 `add_avoid_pressure_diagnostics`를 연결했다.
- 결과 CSV에 `avoid_gate_count`, `avoid_pressure_score`, `avoid_pressure_note`를 추가해 왜 회피가 유지되는지 볼 수 있게 했다.
- `defensive_watch_candidate_flag`, `defensive_watch_candidate_score`, `defensive_watch_candidate_rank`를 추가해 회피 속에서도 상대강도 기준 방어 후보를 분리했다.
- 요약 JSON에는 `defensive_watch_candidate_count`, `defensive_watch_candidate_sectors`, `avoid_pressure_top_sectors`를 추가했다.
- 최종 행동인 `final_action`은 변경하지 않았다. 즉 이 개선은 매수 신호 강화가 아니라 해석력 강화다.

### 확인 결과

2026-06-19 대상 예측을 다시 생성한 결과 최종 행동 분포는 여전히 `회피 우선` 12개로 유지되었다. 방어 추적 후보는 4개로 분리되었고, 순위는 반도체/전자, 금융, 바이오, 유통/소비 순이었다. 반대로 회피 압력이 가장 큰 섹터는 철강/소재, 자동차, 2차전지, 화학/정유, 조선/방산 순으로 나타났다.

검증으로 `python -m py_compile scripts\build_tomorrow_prediction.py`, `python scripts\build_tomorrow_prediction.py`, `python scripts\evaluate_prediction_accuracy.py`, `python scripts\diagnose_prediction_issues.py`, `python scripts\analyze_action_thresholds.py`를 실행했고 모두 정상 종료되었다.

## 28. 2026-06-19 방어 추적 후보를 행동 승격으로 오해할 위험

### 문제

시장 패닉 구간에서 반도체/전자, 금융, 바이오, 유통/소비처럼 상대적으로 나은 후보가 `방어 추적` 대상으로 분리되었다. 하지만 이 후보를 바로 `방어 관찰` 또는 `관망`으로 승격하면 문제가 생길 수 있다. `defensive_watch_candidate_flag`는 최신 예측부터 생성된 컬럼이라 아직 실제 다음날 수익률과 충분히 연결되지 않았고, 과거 전체에 같은 기준을 완전히 재현할 수 없기 때문이다.

### 외부 사례 확인

FinRL은 turbulence 구간에서 매수 중단이나 포지션 정리처럼 리스크 게이트를 먼저 유지한다. Qlib은 예측 점수와 포트폴리오 전략을 분리하고, JPX Kaggle식 평가는 상위 후보가 실제 상위 수익률을 냈는지 순위 기반으로 확인한다. selective classification과 meta-labeling도 확신이 낮거나 표본이 부족할 때는 행동을 거절하거나 2차 필터로 실행 여부를 따로 판단한다.

따라서 우리 프로젝트에서도 방어 후보를 찾는 것과 실제 행동으로 승격하는 것을 분리하는 것이 맞다고 판단했다.

### 점검

- `tomorrow_sector_prediction_history.csv`에는 348개 예측 행, 29개 대상일이 있었다.
- 실제 수익률과 연결 가능한 행은 312개, 26개 대상일이었다.
- `defensive_watch_candidate_flag`는 12개 행에만 존재했고, 모두 2026-06-19 대상 예측이라 아직 실제 수익률 검증 행은 0개였다.
- 과거 proxy 기준인 `panic_gate + 점수 Top3`도 평가 가능일이 4일뿐이고 평균 초과수익률은 -0.28% 수준이라 승격 근거로 쓰기 부족했다.

### 해결

- `scripts/build_tomorrow_prediction.py`에 `panic_watch_action`을 추가했다.
- 이 라벨은 `방어 추적`, `회피 유지`, `강한 회피`로 나뉘며 `final_action`을 바꾸지 않는다.
- `scripts/backtest_panic_watch_policy.py`를 추가해 방어 추적 후보와 과거 proxy 후보의 실제 성과를 따로 검증하도록 했다.
- 산출물은 `reports/panic_watch_policy_backtest.csv`, `reports/panic_watch_policy_strategy_performance.csv`, `reports/panic_watch_policy_summary.json`, `reports/panic_watch_policy_report.md`로 남긴다.

### 확인 결과

2026-06-19 대상 최신 예측에서 `final_action`은 여전히 12개 섹터 모두 `회피 우선`으로 유지되었다. 별도 추적 라벨은 `방어 추적` 4개, `회피 유지` 2개, `강한 회피` 6개로 나뉘었다. `방어 추적` 후보는 반도체/전자, 금융, 바이오, 유통/소비였다.

검증 리포트의 결론은 `safe_to_change_final_action=false`, `safe_to_add_monitor_label=true`, `recommendation=hold_final_action`이었다. 즉 지금은 행동 승격이 아니라 장중 확인 대상 표시까지만 허용한다.

### 다음 단계

strict 방어 추적 후보가 최소 5거래일 이상 실제 수익률과 연결되면 평균 초과수익률, 실제 Top3 포착률, -1% 이하 하락률을 함께 보고 제한적 승격 여부를 다시 판단한다. 그 전까지는 `panic_watch_action=방어 추적`을 매매 신호가 아니라 관찰 신호로만 사용한다.
