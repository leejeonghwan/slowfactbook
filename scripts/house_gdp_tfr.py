#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GDP 대비 주택 시가총액과 합계출산율(c0739).

  python3 scripts/house_gdp_tfr.py            # 미리보기
  python3 scripts/house_gdp_tfr.py --apply

두 기관에서 따로 받아 한 장에 겹친다.

  주택 시가총액  한국은행 국민대차대조표(ECOS 291Y501 자산별 순자본스톡, 명목,
                 연말 기준)의 주거용건물과 주거용건물 부속토지를 더한 값.
  명목 GDP       한국은행 국민계정(ECOS 200Y113 국내총생산과 지출, 명목, 연간).
  합계출산율     국가데이터처 인구동향조사(KOSIS DT_1B81A17, 전국).

부속토지가 1995년부터라 비율도 1995년부터다. 합계출산율은 KOSIS 표가 2000년
부터여서 그 앞 다섯 해(1995~1999)는 차트에 담겨 있던 값을 그대로 둔다.

겹치는 해를 전수 대조해 어긋나면 붙이지 않고 멈춘다. 한국은행은 국민계정을
기준년 개편 때 소급 수정하므로 비율도 그때 조금씩 바뀐다. 그래서 허용 오차를
0.02배로 둔다 — 그보다 크게 벌어지면 계열을 잘못 집은 것이다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
CHART = "c0739"
TOL = 0.02
KST = datetime.timezone(datetime.timedelta(hours=9))


def _json(url):
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def ecos(stat, item, key):
    url = ("https://ecos.bok.or.kr/api/StatisticSearch/%s/json/kr/1/400/%s/A/1970/2035/%s"
           % (key, stat, item))
    rows = _json(url).get("StatisticSearch", {}).get("row", [])
    return {x["TIME"]: float(x["DATA_VALUE"]) for x in rows if x.get("DATA_VALUE")}


def tfr(key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=101&tblId=DT_1B81A17&prdSe=Y"
           "&itmId=T1+&objL1=00+&startPrdDe=1990&endPrdDe=2035" % key)
    rows = _json(url)
    if isinstance(rows, dict):
        raise SystemExit("KOSIS 합계출산율을 받지 못했습니다: %s" % rows)
    return {x["PRD_DE"]: round(float(x["DT"]), 3) for x in rows if x.get("DT")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    ek, kk = os.environ.get("ECOS_API_KEY"), os.environ.get("KOSIS_API_KEY")
    if not ek or not kk:
        raise SystemExit("ECOS_API_KEY 와 KOSIS_API_KEY 가 필요합니다(.env).")

    bld = ecos("291Y501", "101010101", ek)      # 주거용건물
    lnd = ecos("291Y501", "1020101", ek)        # 주거용건물 부속토지
    gdp = ecos("200Y113", "10106", ek)          # 명목 국내총생산
    ratio = {y: round((bld[y] + lnd[y]) / gdp[y], 3)
             for y in sorted(set(bld) & set(lnd) & set(gdp))}
    births = tfr(kk)
    if not ratio or not births:
        raise SystemExit("원천 자료를 받지 못했습니다.")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    cur = ov.get(CHART) or {}
    # 원본은 data/full.json 에 있고 overrides 는 고친 부분만 담는다. 처음 돌릴 때는
    # overrides 에 labels 가 없어서, 대조할 것이 없다고 착각하기 쉽다(실제로 그랬다).
    base = {}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and "items" in doc:
            for it in doc["items"]:
                if it.get("id") == CHART:
                    base = it
    merged = {**base, **cur}
    old_lab = merged.get("labels") or []
    old = merged.get("series") or [[], []]
    old_ratio = {y: v for y, v in zip(old_lab, old[0]) if v is not None}
    old_tfr = {y: v for y, v in zip(old_lab, old[1]) if v is not None}

    bad = [y for y in sorted(set(old_ratio) & set(ratio))
           if abs(old_ratio[y] - ratio[y]) > TOL]
    bad += [y for y in sorted(set(old_tfr) & set(births))
            if abs(old_tfr[y] - births[y]) > 0.011]
    if bad:
        for y in bad[:10]:
            print("  어긋남 %s" % y)
        raise SystemExit("겹치는 해가 어긋나 멈춥니다(%d개)." % len(bad))
    print("  비율 대조 %d해, 출산율 대조 %d해 — 일치"
          % (len(set(old_ratio) & set(ratio)), len(set(old_tfr) & set(births))))

    # 합계출산율은 KOSIS 가 2000년부터라, 그 앞은 차트에 있던 값을 물려받는다.
    years = sorted(set(ratio) | {y for y in old_tfr if y in ratio})
    tfr_all = dict(old_tfr); tfr_all.update(births)
    print("  가로축 %s ~ %s (%d해)" % (years[0], years[-1], len(years)))
    print("  최근: 주택/GDP %.3f배, 합계출산율 %s"
          % (ratio[years[-1]], tfr_all.get(years[-1], "-")))

    ov[CHART] = {
        **cur, "id": CHART,
        "title": "GDP 대비 주택 시가총액과 합계출산율",
        "source": ("한국은행 국민대차대조표와 국민계정, 국가데이터처 인구동향조사. "
                   "주택 시가총액은 주거용건물과 그 부속토지를 더한 값이고, "
                   "명목 국내총생산으로 나눴다. 단위: 배, 명."),
        "sourceUrl": ("https://ecos.bok.or.kr/ https://kosis.kr/statHtml/statHtml.do"
                      "?orgId=101&tblId=DT_1B81A17"),
        "unit": "배",
        "vizType": "combo",
        "seriesKinds": ["line", "line"],
        "seriesAxes": [0, 1],
        "seriesNames": ["GDP 대비 주택 시가총액(배)", "합계출산율(명)"],
        "seriesColors": ["#2a5ca8", "#c0322f"],
        "labels": years,
        "series": [[ratio.get(y) for y in years], [tfr_all.get(y) for y in years]],
        "notes": [
            "주택 시가총액은 한국은행 국민대차대조표의 주거용건물과 주거용건물 "
            "부속토지를 더한 값입니다. 연말 기준 명목 가격이며, 그해 명목 "
            "국내총생산으로 나눴습니다.",
            "1995년부터 그렸습니다. 부속토지 계열이 1995년부터라 그 앞은 비율을 "
            "구할 수 없습니다.",
            "합계출산율은 국가데이터처 인구동향조사입니다. KOSIS 표가 2000년부터여서 "
            "1995년부터 1999년까지는 이전 자료에 담겨 있던 값을 그대로 두었습니다.",
            "한국은행은 기준년을 개편할 때 국민계정을 소급 수정합니다. 과거 비율도 "
            "그때마다 조금씩 바뀌므로 소수점 둘째 자리까지 따지는 비교는 피하는 것이 "
            "안전합니다.",
            "두 계열은 축이 다릅니다. 왼쪽이 배수, 오른쪽이 명입니다. 나란히 움직인다고 "
            "해서 한쪽이 다른 쪽의 원인이라는 뜻은 아닙니다.",
        ],
        "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
    ov[CHART].pop("drop", None)
    if a.apply:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("-> data/overrides.json 에 반영했습니다.")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
