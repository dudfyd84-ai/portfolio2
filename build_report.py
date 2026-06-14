# portfolio/data/*.csv(합성 데이터)만으로 단일 정적 HTML 포트폴리오 리포트를 생성하는 빌더
"""DB 의존 없음. python portfolio/build_report.py → portfolio/index.html"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PALETTE = ["#4f46e5", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899"]


def style(fig, h=360, legend=True):
    fig.update_layout(template="plotly_white", height=h,
                      margin=dict(l=12, r=12, t=46, b=12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, sans-serif", size=12, color="#374151"),
                      title_font=dict(size=15, color="#111827"),
                      colorway=PALETTE,
                      legend=dict(orientation="h", y=-0.18, x=0) if legend else dict())
    fig.update_xaxes(gridcolor="#eef0f3", zeroline=False)
    fig.update_yaxes(gridcolor="#eef0f3", zeroline=False)
    return fig

_first = [True]
def div(fig, config=None):
    inc = "cdn" if _first[0] else False
    _first[0] = False
    return pio.to_html(fig, include_plotlyjs=inc, full_html=False,
                       config={"displayModeBar": False, "responsive": True, **(config or {})})

def won(v):
    v = float(v)
    if abs(v) >= 1e8: return f"₩{v/1e8:.1f}억"
    if abs(v) >= 1e4: return f"₩{v/1e4:,.0f}만"
    return f"₩{v:,.0f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sm = pd.read_csv(DATA / "sales_monthly.csv", parse_dates=["월"])
    pm = pd.read_csv(DATA / "prod_monthly.csv", parse_dates=["월"])
    fcm = pd.read_csv(DATA / "forecast_monthly.csv", parse_dates=["월"])
    acc = pd.read_csv(DATA / "accuracy.csv")
    mc = pd.read_csv(DATA / "model_comparison.csv")
    sj = pd.read_csv(DATA / "sojin.csv")
    bom = pd.read_csv(DATA / "bom.csv")

    figs = {}

    # ── 매출 KPI ──
    sm["year"] = sm["월"].dt.year
    cur_y = int(sm["year"].max()); prev_y = cur_y - 1
    cur_months = sorted(sm[sm["year"] == cur_y]["월"].dt.month.unique())
    tot_cur = sm[sm["year"] == cur_y]["매출"].sum()
    tot_prev = sm[(sm["year"] == prev_y) & (sm["월"].dt.month.isin(cur_months))]["매출"].sum()
    yoy = (tot_cur / tot_prev - 1) * 100 if tot_prev else 0
    online_share = sm[sm["카테고리"] == "온라인"]["매출"].sum() / sm["매출"].sum() * 100
    n_store = sm[sm["카테고리"] == "오프라인"]["매장"].nunique()

    # 1) 월별 매출 추이
    mser = sm.groupby("월")["매출"].sum().reset_index()
    f = go.Figure(go.Bar(x=mser["월"], y=mser["매출"], marker_color="#4f46e5",
                         hovertemplate="%{x|%Y-%m}<br>₩%{y:,.0f}<extra></extra>"))
    f.update_layout(title="월별 매출 추이")
    figs["rev_trend"] = div(style(f, 340, legend=False))

    # 2) 채널 비중 도넛
    ch = sm.groupby("카테고리")["매출"].sum().reset_index()
    f = go.Figure(go.Pie(labels=ch["카테고리"], values=ch["매출"], hole=.62,
                         marker_colors=["#4f46e5", "#06b6d4"]))
    f.update_layout(title="채널별 매출 비중")
    figs["channel"] = div(style(f, 340))

    # 3) 매장별 매출 Top 15
    st = (sm[sm["카테고리"] == "오프라인"].groupby("매장")["매출"].sum()
          .sort_values(ascending=True).tail(15).reset_index())
    f = go.Figure(go.Bar(x=st["매출"], y=st["매장"], orientation="h", marker_color="#06b6d4",
                         hovertemplate="%{y}<br>₩%{x:,.0f}<extra></extra>"))
    f.update_layout(title="매장별 매출 Top 15 (오프라인)")
    figs["stores"] = div(style(f, 460, legend=False))

    # 4) 카테고리별 판매량 추이
    catm = pm.groupby(["카테고리", "월"])["수량"].sum().reset_index()
    f = px.area(catm, x="월", y="수량", color="카테고리", color_discrete_sequence=PALETTE)
    f.update_layout(title="카테고리별 판매량 추이")
    figs["cat_trend"] = div(style(f, 380))

    # 5) 예측 vs 실적 (월별 총량)
    am = pm.groupby("월")["수량"].sum().reset_index().sort_values("월")
    last_x, last_y = am["월"].iloc[-1], am["수량"].iloc[-1]
    fc_sorted = fcm.sort_values("월")
    fx = [last_x] + list(fc_sorted["월"]); fy = [last_y] + list(fc_sorted["predicted_qty"])
    f = go.Figure()
    f.add_trace(go.Scatter(x=am["월"], y=am["수량"], mode="lines+markers", name="실적",
                           line=dict(color="#4f46e5", width=3)))
    f.add_trace(go.Scatter(x=fx, y=fy, mode="lines+markers", name="AI 예측",
                           line=dict(color="#f59e0b", width=3, dash="dash")))
    f.update_layout(title="월별 판매량 — 실적 vs AI 예측")
    figs["forecast"] = div(style(f, 380))

    # 6) 모델 비교 WAPE
    mc2 = mc.sort_values("backtest_wape")
    colors = ["#10b981" if m == "ens_xl" else "#cbd5e1" for m in mc2["model"]]
    f = go.Figure(go.Bar(x=mc2["model"], y=mc2["backtest_wape"], marker_color=colors,
                         text=mc2["backtest_wape"].round(1), textposition="outside",
                         hovertemplate="%{x}<br>WAPE %{y:.1f}%<extra></extra>"))
    f.update_layout(title="모델별 백테스트 WAPE (낮을수록 정확)")
    figs["models"] = div(style(f, 340, legend=False))

    # 7) 품목별 신뢰도 분포
    w = acc["wape"].dropna()
    f = go.Figure(go.Histogram(x=w.clip(upper=100), nbinsx=20, marker_color="#8b5cf6"))
    f.update_layout(title="품목별 예측 WAPE 분포", xaxis_title="WAPE(%)", yaxis_title="품목 수")
    figs["acc_hist"] = div(style(f, 340, legend=False))
    wape_med = w.median(); wape_mean = w.mean(); under50 = (w <= 50).mean() * 100

    # 8) 재고 상위
    stop = sj.sort_values("재고", ascending=True).tail(15)
    f = go.Figure(go.Bar(x=stop["재고"], y=stop["품명"], orientation="h", marker_color="#ef4444",
                         hovertemplate="%{y}<br>%{x:,.0f}개<extra></extra>"))
    f.update_layout(title="완제품 현재고 상위 15")
    figs["stock"] = div(style(f, 460, legend=False))

    # 9) BOM 트리맵
    b = bom.copy(); b["parent"] = b["parent"].astype(str); b["child"] = b["child"].astype(str)
    top_parents = b.groupby("parent")["unit_qty"].sum().sort_values(ascending=False).head(12).index
    b = b[b["parent"].isin(top_parents)]
    f = px.treemap(b, path=[px.Constant("전체"), "parent", "child"], values="unit_qty",
                   color="unit_qty", color_continuous_scale="Purples")
    f.update_layout(title="제품별 BOM(부자재) 구조 — 상위 12개 제품")
    figs["bom"] = div(style(f, 460, legend=False))

    period = f"{pm['월'].min():%Y.%m}–{pm['월'].max():%Y.%m}"
    kpis = dict(wape_med=wape_med, wape_mean=wape_mean, under50=under50,
                n_prod=acc["품명"].nunique(), n_store=n_store, period=period,
                tot_cur=tot_cur, yoy=yoy, online_share=online_share)

    html = render(figs, kpis)
    (BASE / "index.html").write_text(html, encoding="utf-8")
    print("OK — portfolio/index.html 생성 (", len(html) // 1024, "KB )")


# ══════════════════════════════════════════════════════════════
def kpi_card(label, value, sub=""):
    return f'<div class="kpi"><div class="kpi-l">{label}</div><div class="kpi-v">{value}</div><div class="kpi-s">{sub}</div></div>'

def render(figs, k):
    CSS = """
    :root{--bg:#f6f7f9;--card:#fff;--ink:#111827;--mut:#6b7280;--bd:#e5e7eb;--pri:#4f46e5;--pri2:#eef2ff}
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,'Segoe UI','Malgun Gothic',sans-serif;background:var(--bg);color:var(--ink);line-height:1.55}
    a{color:inherit;text-decoration:none}
    header.nav{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.85);backdrop-filter:blur(10px);
      border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:22px;padding:12px 28px}
    header.nav .brand{font-weight:700;color:var(--pri)}
    header.nav nav{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;font-weight:500;color:var(--mut)}
    header.nav nav a:hover{color:var(--pri)}
    .wrap{max-width:1180px;margin:0 auto;padding:0 24px}
    section{padding:54px 0 10px;scroll-margin-top:70px}
    .eyebrow{color:var(--pri);font-weight:700;font-size:13px;letter-spacing:.06em;text-transform:uppercase}
    h1{font-size:40px;margin:.2em 0 .15em;letter-spacing:-.02em}
    h2{font-size:26px;margin:.1em 0 .1em;letter-spacing:-.01em}
    .lead{color:var(--mut);font-size:17px;max-width:760px}
    .chips{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}
    .chip{background:var(--pri2);color:var(--pri);font-size:13px;font-weight:600;padding:5px 12px;border-radius:20px}
    .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:26px 0}
    .kpi{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px 20px}
    .kpi-l{color:var(--mut);font-size:13px;font-weight:600}
    .kpi-v{font-size:28px;font-weight:700;margin:6px 0 2px;letter-spacing:-.02em}
    .kpi-s{color:var(--mut);font-size:12px}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
    .grid3{display:grid;grid-template-columns:1.4fr 1fr;gap:20px}
    .card{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:14px 16px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
    .panel{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:22px 24px}
    .panel h3{margin:.1em 0 .5em;font-size:17px}
    .panel ul{margin:.4em 0;padding-left:18px;color:#374151}
    .panel li{margin:.3em 0}
    .impact{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:8px}
    .impact .b{background:var(--pri2);border-radius:14px;padding:18px 20px}
    .impact .n{font-size:24px;font-weight:700;color:var(--pri)}
    .flow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0;font-size:14px}
    .flow .node{background:var(--pri2);color:var(--pri);font-weight:600;padding:10px 14px;border-radius:10px}
    .flow .arr{color:var(--mut)}
    .note{color:var(--mut);font-size:13px;border-top:1px solid var(--bd);margin-top:40px;padding:22px 0 50px}
    @media(max-width:860px){.kpis,.impact{grid-template-columns:1fr 1fr}.grid2,.grid3{grid-template-columns:1fr}h1{font-size:30px}}
    """
    nav = """<header class="nav"><span class="brand">화장품 수요예측 BI</span>
      <nav><a href="#overview">개요</a><a href="#dashboard">대시보드</a><a href="#sales">매출</a>
      <a href="#ai">AI 예측</a><a href="#inventory">재고·발주</a><a href="#arch">아키텍처</a></nav></header>"""

    overview = f"""<section id="overview"><div class="wrap">
      <div class="eyebrow">Full-Stack Data Analytics Portfolio</div>
      <h1>생산–재고–판매를 잇는<br>수요예측 BI 대시보드</h1>
      <p class="lead">화장품 브랜드의 밸류체인 데이터를 ML 수요예측과 BI로 연결해, 수기 발주를 자동화하고
      과재고·결품을 줄이는 의사결정 도구. 데이터 수집부터 모델링·대시보드·배포·자동 재학습까지 직접 구축.</p>
      <div class="chips">
        <span class="chip">Python</span><span class="chip">XGBoost · LightGBM 앙상블</span>
        <span class="chip">Supabase / PostgreSQL</span><span class="chip">Streamlit · Plotly</span>
        <span class="chip">GitHub Actions (일일 재학습)</span><span class="chip">Docker · HF Spaces</span>
      </div>
      <div class="kpis">
        {kpi_card("예측 정확도 (WAPE 중앙값)", f"{k['wape_med']:.1f}%", f"평균 {k['wape_mean']:.1f}% · 발주 기준")}
        {kpi_card("분석 품목", f"{k['n_prod']}종", "예측·신뢰도 산출")}
        {kpi_card("오프라인 매장", f"{k['n_store']}곳", "전국 백화점 채널")}
        {kpi_card("데이터 기간", k['period'].replace('–',' ~ '), "월 단위 집계")}
      </div>
      <div class="impact">
        <div class="b"><div class="n">70% → 7.8%</div>저물량 품목 월단위 전환·앙상블로 발주 기준 WAPE 대폭 개선</div>
        <div class="b"><div class="n">188 → 16종</div>악성재고 판정 로직 정교화로 오탐 제거</div>
        <div class="b"><div class="n">수기 → 자동</div>시트 동기화·예측·발주 리스트까지 파이프라인 자동화</div>
      </div>
    </div></section>"""

    dashboard = f"""<section id="dashboard"><div class="wrap">
      <div class="eyebrow">Executive Dashboard</div><h2>핵심 지표 한눈에</h2>
      <div class="kpis">
        {kpi_card("매출 (당해 YTD)", won(k['tot_cur']), "동기간 기준")}
        {kpi_card("전년 동기 대비", f"{k['yoy']:+.1f}%", "YoY 성장률")}
        {kpi_card("온라인 비중", f"{k['online_share']:.1f}%", "채널 믹스")}
        {kpi_card("오프라인 매장", f"{k['n_store']}곳", "유통 커버리지")}
      </div>
      <div class="grid3">
        <div class="card">{figs['rev_trend']}</div>
        <div class="card">{figs['channel']}</div>
      </div>
    </div></section>"""

    sales = f"""<section id="sales"><div class="wrap">
      <div class="eyebrow">Sales Analytics</div><h2>채널·매장·카테고리 심층</h2>
      <div class="grid2">
        <div class="card">{figs['stores']}</div>
        <div class="card">{figs['cat_trend']}</div>
      </div>
    </div></section>"""

    ai = f"""<section id="ai"><div class="wrap">
      <div class="eyebrow">AI Demand Forecast</div><h2>향후 3개월 수요예측 · 신뢰도</h2>
      <div class="grid2">
        <div class="card">{figs['forecast']}</div>
        <div class="card">{figs['models']}</div>
      </div>
      <div class="grid3" style="margin-top:20px">
        <div class="card">{figs['acc_hist']}</div>
        <div class="panel">
          <h3>모델링 방법론</h3>
          <ul>
            <li><b>앙상블</b> — XGBoost + LightGBM. 약한 ETS/SWMA는 백테스트로 가지치기.</li>
            <li><b>데이터 누수 방지</b> — Time Series Split 백테스트, 미래 정보 차단.</li>
            <li><b>발주 기준 평가</b> — 일단위 노이즈 대신 <b>월단위 WAPE</b>로 공정 비교, 품목별 최적 방식 자동 선택.</li>
            <li><b>저물량·간헐 품목</b> — 월평균 기반으로 전환해 WAPE 폭증 회피.</li>
            <li><b>결측·이상치</b> — 결측 0 처리, IQR 상한 클리핑.</li>
          </ul>
        </div>
      </div>
    </div></section>"""

    inventory = f"""<section id="inventory"><div class="wrap">
      <div class="eyebrow">Inventory & Procurement</div><h2>재고 건전성 · 자재 소요(BOM)</h2>
      <div class="grid2">
        <div class="card">{figs['stock']}</div>
        <div class="card">{figs['bom']}</div>
      </div>
    </div></section>"""

    arch = f"""<section id="arch"><div class="wrap">
      <div class="eyebrow">Architecture & Roadmap</div><h2>데이터 파이프라인 · 확장 계획</h2>
      <div class="panel">
        <h3>엔드투엔드 데이터 흐름</h3>
        <div class="flow">
          <span class="node">Google Sheets (현업 입력)</span><span class="arr">→</span>
          <span class="node">Supabase / PostgreSQL</span><span class="arr">→</span>
          <span class="node">ML 엔진 (앙상블 예측)</span><span class="arr">→</span>
          <span class="node">집계 테이블 사전계산</span><span class="arr">→</span>
          <span class="node">Streamlit · Plotly 대시보드</span>
        </div>
        <div class="flow">
          <span class="node">GitHub Actions — 매일 03:00 자동 재학습</span><span class="arr">↺</span>
          <span class="node">Docker · Hugging Face Spaces 배포</span>
        </div>
      </div>
      <div class="grid2" style="margin-top:20px">
        <div class="panel"><h3>기술 스택</h3>
          <ul><li><b>모델링</b> — pandas, numpy, scikit-learn, XGBoost, LightGBM, statsmodels</li>
          <li><b>데이터</b> — Supabase(PostgreSQL), SQLAlchemy 배치 적재</li>
          <li><b>BI</b> — Streamlit, Plotly, 집계 테이블 사전계산으로 콜드 로딩 단축</li>
          <li><b>운영</b> — GitHub Actions 스케줄 재학습, Docker, HF Spaces</li></ul>
        </div>
        <div class="panel"><h3>다음 단계 (로드맵)</h3>
          <ul><li><b>원가·마진</b> — 부자재 단가 + BOM으로 제조원가 산출 → 채널별 순마진</li>
          <li><b>발주 자동화</b> — 부자재 리드타임·MOQ·미입고 발주 반영한 입고 데드라인</li>
          <li><b>마케팅 ROI</b> — 채널·캠페인 광고비 결합한 ROAS·기여도 분석</li>
          <li><b>프로모션 효과</b> — 할인 실적으로 가격 민감도 학습</li></ul>
        </div>
      </div>
    </div></section>"""

    note = """<div class="wrap"><div class="note">
      ⚠ 본 리포트의 모든 매장명·제품명·부자재명은 <b>가명</b>이며, 매출·물량은 추세·비율을 보존한 채
      배수·노이즈·연도 시프트로 <b>변형된 합성 데이터</b>입니다. 실제 기업 데이터가 아니며 포트폴리오 시연 목적입니다.
      모델 구조·방법론·아키텍처는 실제 구현과 동일합니다.
    </div></div>"""

    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>화장품 수요예측 BI · 데이터 분석 포트폴리오</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap' rel='stylesheet'>"
            f"<style>{CSS}</style></head><body>"
            f"{nav}{overview}{dashboard}{sales}{ai}{inventory}{arch}{note}"
            "</body></html>")


if __name__ == "__main__":
    main()
