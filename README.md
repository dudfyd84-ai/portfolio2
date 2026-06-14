# 화장품 수요예측 BI · 데이터 분석 포트폴리오

생산–재고–판매 밸류체인 데이터를 **ML 수요예측 + BI 대시보드**로 연결한 풀스택 데이터 분석 프로젝트입니다.
데이터 수집 → 전처리 → 앙상블 모델링 → 대시보드 → 자동 재학습·배포까지 직접 구축했습니다.

🔗 **라이브 리포트**: https://dudfyd84-ai.github.io/portfolio2/

## 하이라이트
- **앙상블 수요예측** — XGBoost + LightGBM. 발주 기준(월단위) WAPE로 품목별 최적 방식 자동 선택.
- **데이터 누수 방지** — Time Series Split 백테스트, 저물량·간헐 품목 월단위 전환.
- **운영 자동화** — Google Sheets → Supabase → ML → 대시보드, GitHub Actions 일일 재학습, Docker·HF Spaces 배포.
- **성능 최적화** — 집계 테이블 사전계산으로 대시보드 콜드 로딩 단축.

## 기술 스택
`Python` `pandas/numpy` `scikit-learn` `XGBoost` `LightGBM` `statsmodels`
`Supabase(PostgreSQL)` `SQLAlchemy` `Streamlit` `Plotly` `GitHub Actions` `Docker`

## 구성
- `index.html` — 단일 정적 리포트 (서버·DB 불필요, 그대로 GitHub Pages 배포).
- `anonymize.py` — 원본 DB를 가명·수치변형해 합성 CSV로 내보내는 익명화 파이프라인.
- `build_report.py` — 합성 CSV만으로 `index.html`을 생성하는 빌더.
- `data/` — 익명 합성 데이터.

재현: `python anonymize.py`(원본 DB 필요) 또는 동봉된 `data/`로 바로 `python build_report.py`.

## ⚠ 데이터 고지
모든 **매장명·제품명·부자재명은 가명**이며, 매출·물량은 추세·비율을 보존한 채
**배수·노이즈·연도 시프트로 변형된 합성 데이터**입니다. 실제 기업 데이터가 아니며 포트폴리오 시연용입니다.
모델 구조·방법론·아키텍처는 실제 구현과 동일합니다.
