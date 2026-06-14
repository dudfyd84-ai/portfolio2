# Supabase 실데이터를 가명·수치변형해 정적 포트폴리오용 합성 CSV로 내보내는 스크립트
"""
실명(매장·완제품·부자재)을 가명으로, 매출·물량을 결정적 배수·노이즈·연도시프트로 변형해
portfolio/data/*.csv 로 저장한다. 추세·계절성·비율은 보존하고 절대값/실명/기간은 가린다.
한 번만 실행하면 이후 build_report.py 는 DB 없이 이 CSV만으로 리포트를 만든다.
"""
from __future__ import annotations
import sys, hashlib, urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

BASE = Path(__file__).resolve().parent
OUT = BASE / "data"
OUT.mkdir(exist_ok=True)
SECRETS = BASE.parent / ".streamlit" / "secrets.toml"
YEAR_SHIFT = 3            # 2025→2028, 2026→2029
NOISE = np.random.default_rng(42)


def engine():
    import tomllib
    sb = tomllib.load(open(SECRETS, "rb"))["supabase"]
    pwd = urllib.parse.quote(str(sb["db_pass"]))
    url = f"postgresql+psycopg2://{sb['db_user']}:{pwd}@{sb['db_host']}:{sb['db_port']}/{sb['db_name']}"
    return create_engine(url, connect_args={"connect_timeout": 30})


def _seed(s: str) -> int:
    return int(hashlib.md5(s.encode("utf-8")).hexdigest(), 16) % (2**32)

def mult(name: str, lo=0.65, hi=1.4) -> float:
    """원본명에 결정적인 배수 — 같은 제품은 어느 테이블에서도 동일 배수."""
    return float(np.random.default_rng(_seed("m|" + str(name))).uniform(lo, hi))

def noise(n: int) -> np.ndarray:
    return NOISE.uniform(0.92, 1.08, n)

def shift_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s) + pd.DateOffset(years=YEAR_SHIFT)

def parse_kdate(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(" ", ""), format="%Y.%m.%d", errors="coerce")


# ── 가명 매핑 ───────────────────────────────────────────────
def build_store_map(stores) -> dict:
    brands = ["한빛", "가온", "서래", "노을", "수려", "라온", "해담", "온유", "다정", "미르", "별솔"]
    cities = ["강남", "판교", "송도", "센텀", "일산", "수원", "대전", "광주", "울산", "청라",
              "평촌", "목동", "잠실", "동탄", "분당", "인천", "창원", "부산", "노원", "미아"]
    combos = [f"{b}백화점 {c}점" for c in cities for b in brands]
    out = {}
    for i, s in enumerate(sorted(map(str, stores))):
        out[s] = combos[i % len(combos)] if "온라인" not in s else "온라인 채널"
    return out

def build_product_map(prod_cat: dict) -> dict:
    """원본 완제품명 → '{카테고리} NN'. 카테고리별 일련번호."""
    cat_items: dict[str, list] = {}
    for p in sorted(prod_cat):
        cat_items.setdefault(prod_cat[p] or "기타", []).append(p)
    out = {}
    for cat, items in cat_items.items():
        for i, p in enumerate(items, 1):
            out[p] = f"{cat} {i:02d}"
    return out

_MAT_TYPES = ["원액", "공병", "뚜껑", "샘플 카드", "쇼카드", "리드스틱", "용기", "캡", "라벨",
              "스티커", "박스", "쇼핑백", "파우치", "리필", "심지", "왁스", "향료", "단상자"]
def build_material_map(children) -> dict:
    cnt: dict[str, int] = {}
    out = {}
    for c in sorted(map(str, set(children))):
        mtype = next((m for m in _MAT_TYPES if m.replace(" ", "") in c.replace(" ", "")), "부자재")
        cnt[mtype] = cnt.get(mtype, 0) + 1
        out[c] = f"{mtype} {cnt[mtype]:02d}"
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    eng = engine()

    # 1) 완제품 월별 수량 (agg_qty_monthly)
    q = pd.read_sql('SELECT "품명", "카테고리", "월", "수량" FROM agg_qty_monthly', eng)
    q["월"] = pd.to_datetime(q["월"])
    prod_cat = q.groupby("품명")["카테고리"].agg(lambda s: s.mode().iat[0]).to_dict()

    # 예측·정확도에만 있는 품목까지 매핑에 포함
    fc = pd.read_sql('SELECT product_name, category, forecast_date, predicted_qty FROM demand_forecasts', eng)
    acc = pd.read_sql('SELECT product_name, category, actual_sum, pred_sum, wape, mape, method FROM forecast_accuracy', eng)
    for _, r in pd.concat([fc[["product_name", "category"]], acc[["product_name", "category"]]]).iterrows():
        prod_cat.setdefault(str(r["product_name"]), r["category"] if pd.notna(r["category"]) else "기타")

    pmap = build_product_map(prod_cat)

    # 제품 배수 + 노이즈 적용해 월별 수량 저장
    base = pd.read_sql('SELECT "품명" AS orig, "카테고리", "월", "수량" FROM agg_qty_monthly', eng)
    base["월"] = shift_dt(base["월"])
    base["품명"] = base["orig"].map(pmap)
    base["수량"] = (pd.to_numeric(base["수량"], errors="coerce").fillna(0).values
                    * base["orig"].map(mult).values * noise(len(base))).round(0)
    base[["카테고리", "품명", "월", "수량"]].to_csv(OUT / "prod_monthly.csv", index=False, encoding="utf-8-sig")

    # 2) 매출 월별 (raw_sales 25/26 → 카테고리·매장·월 집계)
    sa = pd.concat([pd.read_sql(f'SELECT "날짜","카테고리","채널/주차","매출" FROM {t}', eng)
                    for t in ["raw_sales_25", "raw_sales_26"]], ignore_index=True)
    sa["dt"] = parse_kdate(sa["날짜"])
    sa = sa.dropna(subset=["dt"])
    sa["매출"] = pd.to_numeric(sa["매출"], errors="coerce").fillna(0)
    smap = build_store_map(sa["채널/주차"].dropna().unique())
    sa["매장"] = sa["채널/주차"].astype(str).map(smap)
    sa["월"] = shift_dt(sa["dt"].dt.to_period("M").dt.to_timestamp())
    sa["매출"] = (sa["매출"].values * sa["채널/주차"].astype(str).map(mult).values * noise(len(sa)))
    sm = sa.groupby(["카테고리", "매장", "월"], as_index=False)["매출"].sum()
    sm["매출"] = sm["매출"].round(0)
    sm.to_csv(OUT / "sales_monthly.csv", index=False, encoding="utf-8-sig")

    # 3) 예측 월별 (제품 배수 동일 적용 → 실적과 정합)
    fc["forecast_date"] = pd.to_datetime(fc["forecast_date"])
    fc["월"] = shift_dt(fc["forecast_date"].dt.to_period("M").dt.to_timestamp())
    fc["predicted_qty"] = (pd.to_numeric(fc["predicted_qty"], errors="coerce").fillna(0).values
                           * fc["product_name"].astype(str).map(mult).values)
    fcm = fc.groupby("월", as_index=False)["predicted_qty"].sum()
    fcm["predicted_qty"] = fcm["predicted_qty"].round(0)
    fcm.to_csv(OUT / "forecast_monthly.csv", index=False, encoding="utf-8-sig")

    # 4) 정확도 (가명 + 실적/예측만 배수, WAPE/MAPE는 비율이라 유지)
    acc["품명"] = acc["product_name"].astype(str).map(pmap)
    acc["actual_sum"] = (pd.to_numeric(acc["actual_sum"], errors="coerce").fillna(0).values
                         * acc["product_name"].astype(str).map(mult).values).round(0)
    acc["pred_sum"] = (pd.to_numeric(acc["pred_sum"], errors="coerce").fillna(0).values
                       * acc["product_name"].astype(str).map(mult).values).round(0)
    acc[["품명", "category", "actual_sum", "pred_sum", "wape", "mape", "method"]].to_csv(
        OUT / "accuracy.csv", index=False, encoding="utf-8-sig")

    # 5) 모델 비교 (비민감 — 유지)
    pd.read_sql("SELECT model, backtest_wape FROM forecast_model_comparison", eng).to_csv(
        OUT / "model_comparison.csv", index=False, encoding="utf-8-sig")

    # 6) 소진/재고 (raw_sojin col18=품명, col19=재고)
    so = pd.read_sql("SELECT * FROM raw_sojin", eng)
    so.columns = range(so.shape[1])
    s = so.iloc[:, [18, 19]].copy(); s.columns = ["품명", "재고"]
    s = s.dropna(subset=["품명"])
    s["품명"] = s["품명"].astype(str).str.strip()
    s = s[~s["품명"].isin(["품명", "nan", ""])]
    excl = ['dp', '비품', '부자재', '증정', '샘플', '키링', '파우치', '시향', '테스터', '리필', 'gift', '쇼카드']
    s = s[~s["품명"].str.contains('|'.join(excl), case=False, na=False)]
    s["재고"] = pd.to_numeric(s["재고"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    s = s.groupby("품명", as_index=False)["재고"].sum()
    s["orig"] = s["품명"]
    # 판매맵과 표기가 달라 매칭이 적음 → 재고용 깔끔한 순번 가명
    sojin_map = {o: f"완제품 {i:03d}" for i, o in enumerate(sorted(s["orig"]), 1)}
    s["품명"] = s["orig"].map(sojin_map)
    s["재고"] = (s["재고"].values * s["orig"].map(mult).values * noise(len(s))).round(0)
    s[["품명", "재고"]].to_csv(OUT / "sojin.csv", index=False, encoding="utf-8-sig")

    # 7) BOM (parent 완제품·child 부자재 가명)
    bom = pd.read_sql('SELECT "BOM RAW DATA 구분" parent, "품명" child, " BOM" u FROM raw_mrp_bom', eng)
    bom = bom.dropna(subset=["parent", "child"])
    bom["parent"] = bom["parent"].astype(str).str.strip()
    bom["child"] = bom["child"].astype(str).str.strip()
    bom = bom[~bom["child"].isin(["nan", ""])]
    # parent 가명: 완제품맵 우선, 없으면 형태기반
    def pfake(x):
        if x in pmap:
            return pmap[x]
        for f in ["오일 퍼퓸", "디퓨저", "캔들", "핸드", "카 디퓨저"]:
            if f.replace(" ", "") in x.replace(" ", ""):
                return f"{f} {abs(_seed(x))%90+10}"
        return f"제품 {abs(_seed(x))%900+100}"
    mmap = build_material_map(bom["child"])
    bom["parent"] = bom["parent"].map(pfake)
    bom["child"] = bom["child"].map(mmap)
    bom["unit_qty"] = pd.to_numeric(bom["u"], errors="coerce").fillna(0)
    bom = bom[bom["unit_qty"] > 0]
    bom[["parent", "child", "unit_qty"]].to_csv(OUT / "bom.csv", index=False, encoding="utf-8-sig")

    print("OK — 합성 CSV 저장:", [p.name for p in sorted(OUT.glob("*.csv"))])
    print(f"   완제품 {len(pmap)}종 · 매장 {len(smap)}곳 · 부자재 {len(mmap)}종 가명화")


if __name__ == "__main__":
    main()
