#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""남녀 평균 근속 연수(c0130)와 50~54세 남녀 평균 근속 연수(c0129).

  python3 scripts/tenure.py            # 미리보기
  python3 scripts/tenure.py --apply

고용노동부 고용형태별근로실태조사다. 같은 조사인데 KOSIS 표가 둘로 쪼개져 있다.

  DT_PAY0004       1993 ~ 2008
  DT_118N_PAY0004  2009 ~

refresh_api.py 는 표 하나를 통째로 다시 까는 방식이라, 새 표만 등록하면
1993~2008년 열여섯 해가 사라진다. 그래서 따로 둔다.

두 표는 분류 코드가 같고 항목 코드만 다르다(DURATION 앞자리). 겹치는 해를
전수 대조해 어긋나면 붙이지 않고 멈춘다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

P = "13102205067"                 # 분류 코드 앞자리(두 표가 같다)
TABLES = [("DT_PAY0004", "13103205067DURATION", "1993", "2008"),
          ("DT_118N_PAY0004", "13103205070DURATION", "2009", "2035")]
# 차트 id: (연령 코드, 제목, 출처에 적을 연령 설명)
CHARTS = {
    "c0130": ("00", "남녀 평균 근속 연수", ""),
    "c0129": ("09", "50~54세 남녀 평균 근속 연수", ", 50~54세"),
}
SEX = [("2", "여성"), ("1", "남성")]     # 차트의 계열 순서

# c2046 남녀 월 임금 총액. 같은 조사의 같은 표에서 '월임금총액'을 읽는다.
# 2009년부터만 다시 깐다. 1993~2008년은 옛 표의 '월급여총액'이라 정의가 달라
# (특별급여 처리가 다르다) 이어 붙이면 어긋난다. 그 구간은 손대지 않는다.
WAGE_CHART = "c2046"
WAGE_FROM = "2009"
WAGE_ITM = "16118DD_10"
# c2046 은 차트 계열이 남성 먼저다. 근속 차트(여성 먼저)와 순서가 반대라 따로 둔다.
WAGE_SEX = [("1", "남성"), ("2", "여성")]


def pull(tbl, itm, age, s, e, key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y&itmId=%s+"
           "&objL1=%sSIZES.00+&objL2=%sGRADES.0+&objL3=%sSEXS.2+%sSEXS.1+"
           "&objL4=%sAGEGRADE.%s+&startPrdDe=%s&endPrdDe=%s"
           % (key, tbl, itm, P, P, P, P, P, age, s, e))
    with urllib.request.urlopen(url, timeout=120) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        return {}
    out = {}
    for x in doc:
        if x.get("DT") in (None, ""):
            continue
        out.setdefault(x["C3"][-1], {})[x["PRD_DE"]] = round(float(x["DT"]), 2)
    return out


def series(age, key):
    """{'2': {연도: 값}, '1': {...}} — 두 표를 이어 붙인다."""
    merged = {}
    for tbl, itm, s, e in TABLES:
        got = pull(tbl, itm, age, s, e, key)
        for sx, m in got.items():
            merged.setdefault(sx, {}).update(m)
    return merged


def wage(key):
    """{'1': {연도: 만원}, '2': {...}} — 2009년 이후 월임금총액."""
    out = pull("DT_118N_PAY0004", WAGE_ITM, "00", WAGE_FROM, "2035", key)
    return {sx: {y: round(v / 10, 1) for y, v in m.items()} for sx, m in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    full = {}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and "items" in doc:
            for it in doc["items"]:
                if it.get("id") in CHARTS or it.get("id") == WAGE_CHART:
                    full[it["id"]] = it

    touched = 0
    for cid, (age, title, agenote) in CHARTS.items():
        got = series(age, key)
        if not got or len(got) != 2:
            print("  %s 자료를 받지 못했습니다." % cid)
            continue
        cur = {**full.get(cid, {}), **(ov.get(cid) or {})}
        lab = cur.get("labels") or []
        bad = 0
        for i, (code, _) in enumerate(SEX):
            old = cur.get("series", [[], []])[i] if i < len(cur.get("series", [])) else []
            for y, v in zip(lab, old):
                if v is None or y not in got[code]:
                    continue
                if abs(got[code][y] - v) > 0.051:
                    print("  어긋남 %s %s: 차트 %s / KOSIS %s" % (cid, y, v, got[code][y]))
                    bad += 1
        if bad:
            print("  %s 는 건드리지 않습니다(%d군데 어긋남)." % (cid, bad))
            continue
        years = sorted(set(got["1"]) | set(got["2"]))
        print("  %s %s: %s ~ %s (%d해), 최근 여성 %s 남성 %s — 겹치는 구간 일치"
              % (cid, title, years[0], years[-1], len(years),
                 got["2"].get(years[-1]), got["1"].get(years[-1])))
        ov[cid] = {
            **(ov.get(cid) or {}), "id": cid, "title": title,
            "source": ("고용노동부 고용형태별근로실태조사. 상용근로자 5인 이상 사업체%s. "
                       "단위: 년." % agenote),
            "sourceUrl": ("https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_PAY0004 "
                          "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_PAY0004"),
            "unit": "년", "labels": years,
            "series": [[got[c].get(y) for y in years] for c, _ in SEX],
            "seriesNames": [n for _, n in SEX],
            "seriesColors": ["#c0322f", "#2a5ca8"],
            "notes": [
                "고용노동부 고용형태별근로실태조사(옛 임금구조기본통계조사)입니다. "
                "상용근로자 5인 이상 사업체가 대상이라 5인 미만 사업장과 자영업자는 "
                "빠집니다. 근속이 짧은 쪽이 많이 빠지므로 전체 노동자 평균보다 "
                "길게 나옵니다.",
                "KOSIS 표가 둘로 쪼개져 있어 1993~2008년(DT_PAY0004)과 "
                "2009년 이후(DT_118N_PAY0004)를 이어 붙였습니다. 조사 체계가 "
                "2009년에 바뀌었으므로 그 앞뒤를 가로지르는 비교는 흐름으로만 "
                "읽는 것이 안전합니다.",
                "근속 연수는 지금 다니는 직장에서 일한 기간입니다. 평생 일한 "
                "기간이 아니고, 이직이 잦아지면 짧아집니다. 길다고 좋고 짧다고 "
                "나쁜 지표가 아닙니다.",
            ],
            "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        }
        touched += 1

    # ── c2046 남녀 월 임금 총액
    w = wage(key)
    if len(w) == 2:
        cur = {**full.get(WAGE_CHART, {}), **(ov.get(WAGE_CHART) or {})}
        lab = [str(x) for x in (cur.get("labels") or [])]
        ser = [list(s) for s in (cur.get("series") or [[], []])]
        bad = 0
        for j, (code, _) in enumerate(WAGE_SEX):
            for i, y in enumerate(lab):
                if y < WAGE_FROM or i >= len(ser[j]):
                    continue
                v, g = ser[j][i], w[code].get(y)
                if v is None or g is None:
                    continue
                if abs(g - v) > max(0.5, abs(v) * 0.004):
                    print("  어긋남 %s %s: 차트 %s / KOSIS %s" % (WAGE_CHART, y, v, g))
                    bad += 1
        if bad:
            print("  %s 는 건드리지 않습니다(%d군데)." % (WAGE_CHART, bad))
        else:
            years = sorted(set(lab) | set(w["1"]) | set(w["2"]))
            keep = {sx: {y: ser[j][lab.index(y)] for y in lab
                         if y < WAGE_FROM and lab.index(y) < len(ser[j])}
                    for j, (sx, _) in enumerate(WAGE_SEX)}
            new = []
            for j, (sx, _) in enumerate(WAGE_SEX):
                new.append([(w[sx].get(y) if y >= WAGE_FROM else keep[sx].get(y))
                            for y in years])
            print("  %s 남녀 월 임금 총액: %s ~ %s (%d해), 최근 여성 %s 남성 %s"
                  % (WAGE_CHART, years[0], years[-1], len(years),
                     w["2"].get(years[-1]), w["1"].get(years[-1])))
            ov[WAGE_CHART] = {
                **(ov.get(WAGE_CHART) or {}), "id": WAGE_CHART,
                "title": "남녀 월 임금 총액", "unit": "만 원",
                "source": ("고용노동부 고용형태별근로실태조사. 상용근로자 5인 이상 사업체의 "
                           "월 임금총액. 단위: 만 원."),
                "sourceUrl": ("https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_PAY0004 "
                              "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_PAY0004"),
                "labels": years, "series": new,
                "seriesNames": ["남성", "여성"],
                "seriesColors": ["#2a5ca8", "#c0322f"],
                "notes": [
                    "고용노동부 고용형태별근로실태조사(옛 임금구조기본통계조사)입니다. "
                    "상용근로자 5인 이상 사업체가 대상이라 5인 미만 사업장과 자영업자는 "
                    "빠집니다.",
                    "월 임금총액은 정액급여와 초과급여에 전년도 연간특별급여를 열두 달로 "
                    "나눈 몫을 더한 값입니다. 상여금이 많은 해에는 그만큼 올라갑니다.",
                    "2009년부터는 KOSIS 표에서 직접 받아 옵니다. 1993~2008년은 옛 표의 "
                    "'월급여총액' 기준이라 특별급여 처리가 달라 2009년 앞뒤를 바로 잇기 "
                    "어렵습니다. 장기 추세로만 읽으십시오.",
                    "같은 조사의 '전체근로자' 집계(비정규직 포함)는 이보다 낮습니다. "
                    "2025년 남성 450.3만원, 여성 295.9만원입니다. 다른 기사에서 본 숫자와 "
                    "다르면 어느 쪽 모집단인지 확인해야 합니다.",
                ],
                "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            }
            touched += 1

    if a.apply and touched:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("-> data/overrides.json 에 반영했습니다(%d장)." % touched)
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
