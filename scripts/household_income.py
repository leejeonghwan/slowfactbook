#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""소득 분위별 가구 월평균 소득 — 가계동향조사.

표 둘을 쓴다. 둘 다 전국, 1인 이상 가구, 명목 소득이다.
  새 조사  KOSIS 101/DT_1L9U103  2019년 1분기부터
  옛 조사  KOSIS 101/DT_1L9E006  2006년 1분기부터 2019년 4분기까지
가계수지항목 A 가 '소득'이고 항목 코드는 새 표가 T110, 옛 표가 T1 이다.

이어 붙이면 안 된다 — 이 어댑터가 지키는 선이다.
  2019년이 두 표에 모두 있는데 값이 크게 다르다. 2019년 1분기 전체가
  옛 조사 395만 원, 새 조사 427만 원으로 8.1% 차이고, 1분위는 66만 원과
  86만 원으로 30.6% 차이다. 2019년에 조사 방식을 바꾸면서 표본과 조사
  방법이 달라진 결과다. 한 선으로 이으면 2019년에 소득이 갑자기 뛴 것처럼
  보인다. 그래서 장기 차트에서도 두 구간을 다른 계열로 둔다.
  검산으로 해마다 차이를 확인하고, 차이가 사라지면(= 표가 바뀌면) 멈춘다.

  2017년과 2018년 상반기는 새 표에 없다. 그 무렵 소득 부문 조사가
  중단됐다가 2019년에 되살아났다. 옛 표에는 그 구간이 있다.

섞으면 안 되는 것.
  c0207(소득 5분위 소득)은 가계금융복지조사의 연간 소득이다. 여기는
  가계동향조사의 분기별 월평균이다. 조사도 주기도 다르다.
  실질 소득은 다른 표(DT_1L9U122)다. 여기는 명목이다.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

ORG = "101"
NEW, NEW_ITM = "DT_1L9U103", "T110"
OLD, OLD_ITM = "DT_1L9E006", "T1"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101"
       "&tblId=DT_1L9U103")
SRC = "국가데이터처 가계동향조사"
QS = ["Q1", "Q2", "Q3", "Q4", "Q5"]
COLS = ["#2a5ca8", "#5b8bc9", "#9b9b9b", "#e8a05a", "#e8820c"]
# 보도된 2026년 3분기 값(만 원)과 전년 동기 대비
GATE = {"Q0": (548.0, 0.008), "Q1": (127.7, -0.027), "Q5": (1174.6, 0.014)}


def envkey(k):
    v = os.environ.get(k)
    if v:
        return v
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def pull(key, tbl, itm, start, tries=3):
    p = {"method": "getList", "apiKey": key, "orgId": ORG, "tblId": tbl,
         "itmId": itm + "+", "objL1": "Q0+" + "+".join(QS) + "+",
         "objL2": "A+", "format": "json", "jsonVD": "Y", "prdSe": "Q",
         "startPrdDe": start, "endPrdDe": "209904"}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p, safe="+"))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=120))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}")
            v = {}
            for r in d:
                if r.get("DT") in (None, "", "-"):
                    continue
                v.setdefault(r["C1"], {})[r["PRD_DE"]] = float(r["DT"])
            if len(v.get("Q0", {})) < 20:
                raise RuntimeError("분기가 모자라다")
            return v
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{tbl} 를 받지 못했다: {last}")


def lab(q):
    return f"{q[:4]}-Q{int(q[4:])}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    new = pull(key, NEW, NEW_ITM, "201901")
    time.sleep(0.4)
    old = pull(key, OLD, OLD_ITM, "200601")
    nq = sorted(new["Q0"])
    oq = sorted(old["Q0"])
    print(f"    받음: 새 조사 {len(nq)}분기 {nq[0]}~{nq[-1]}, "
          f"옛 조사 {len(oq)}분기 {oq[0]}~{oq[-1]}")

    # 검산 1. 보도된 2026년 3분기 값과 맞는가
    end = nq[-1]
    prev = f"{int(end[:4]) - 1}{end[4:]}"
    bad = []
    for q, (amt, yoy) in GATE.items():
        cur = new[q][end] / 10000
        chg = new[q][end] / new[q][prev] - 1
        if abs(cur - amt) > 0.6 or abs(chg - yoy) > 0.002:
            bad.append((q, round(cur, 1), amt, round(chg, 3), yoy))
    if bad:
        print(f"  검산 실패: 보도된 값과 다르다 {bad}")
        return 1
    print(f"    검산 보도: {lab(end)} 전체 {new['Q0'][end]/10000:,.0f}만 원"
          f"({new['Q0'][end]/new['Q0'][prev]-1:+.1%}), 1분위 "
          f"{new['Q1'][end]/10000:,.0f}만 원"
          f"({new['Q1'][end]/new['Q1'][prev]-1:+.1%}), 5분위 "
          f"{new['Q5'][end]/10000:,.0f}만 원"
          f"({new['Q5'][end]/new['Q5'][prev]-1:+.1%}) 으로 일치")

    # 검산 2. 분위 다섯의 평균이 전체와 가까운가(분위는 가구를 5등분한다)
    bad = []
    for q in nq:
        m = sum(new[k][q] for k in QS) / 5
        if abs(m / new["Q0"][q] - 1) > 0.02:
            bad.append((q, round(m), round(new["Q0"][q])))
    if bad:
        print(f"  검산 실패: 다섯 분위 평균이 전체와 다르다 {bad[:3]}")
        return 1
    print(f"    검산 분위: {len(nq)}분기 모두 다섯 분위 평균 = 전체 평균")

    # 검산 3. 두 조사가 겹치는 구간이 정말 어긋나는가
    ov = sorted(set(nq) & set(oq))
    if not ov:
        print("  검산 실패: 두 조사가 겹치는 분기가 없다")
        return 1
    gaps = [(q, new["Q0"][q] / old["Q0"][q] - 1,
             new["Q1"][q] / old["Q1"][q] - 1) for q in ov]
    if min(abs(g[1]) for g in gaps) < 0.03:
        print(f"  검산 실패: 겹치는 구간이 비슷하다. 두 표가 바뀌었는지 "
              f"확인해야 한다 {[(q, round(a,3)) for q,a,_b in gaps]}")
        return 1
    print(f"    검산 단절: 겹치는 {len(ov)}분기에서 전체 "
          f"{min(g[1] for g in gaps):+.1%}~{max(g[1] for g in gaps):+.1%}, "
          f"1분위 {min(g[2] for g in gaps):+.1%}~"
          f"{max(g[2] for g in gaps):+.1%} 차이 — 이어 붙이지 않는다")

    out = []

    # 1. 현행 조사 기준 분위별 월평균 소득
    out.append({
        "slide": "manual-income-quintile", "category": "젠더와 격차",
        "title": "소득 분위별 가구 월평균 소득.",
        "vizType": "line", "unit": "만 원",
        "labels": [lab(q) for q in nq],
        "series": [[round(new[k][q] / 10000, 1) for q in nq] for k in QS],
        "seriesNames": [f"{i}분위" for i in range(1, 6)],
        "seriesColors": COLS,
        "source": (f"{SRC}(KOSIS 101/{NEW}). 전국 1인 이상 가구의 월평균 "
                   f"명목 소득, {lab(nq[0])}~{lab(end)}. 단위: 만 원."),
        "sourceUrl": URL,
        "notes": [
            f"{lab(end)}에 1분위는 {new['Q1'][end]/10000:,.0f}만 원, "
            f"5분위는 {new['Q5'][end]/10000:,.0f}만 원입니다. 전체 평균은 "
            f"{new['Q0'][end]/10000:,.0f}만 원입니다.",
            f"한 해 전과 견주면 1분위는 "
            f"{new['Q1'][end]/new['Q1'][prev]-1:+.1%}, 5분위는 "
            f"{new['Q5'][end]/new['Q5'][prev]-1:+.1%}입니다. 아래쪽은 "
            "물가를 빼기 전 명목 소득부터 줄었습니다.",
            "명목 소득입니다. 물가를 반영한 실질 소득은 다른 표입니다.",
            "분위는 그 분기의 소득으로 가구를 다섯으로 나눈 것입니다. "
            "같은 가구가 계속 같은 분위에 있는 것이 아니라 분기마다 다시 "
            "나눕니다.",
            "2019년에 조사 방식이 바뀌어 그 전과 이어지지 않습니다. "
            "이 차트는 2019년 1분기부터입니다.",
        ],
        "updated": ymd,
    })

    # 2. 조사 개편 전후를 끊어서 보여주는 장기 추이
    allq = sorted(set(oq) | set(nq))
    labs = [lab(q) for q in allq]

    def ser(src, keys, qs):
        return [round(src[keys][q] / 10000, 1) if q in src[keys] else None
                for q in allq] if False else [
            round(src[keys][q] / 10000, 1) if q in qs and q in src[keys]
            else None for q in allq]
    oqs, nqs = set(oq), set(nq)
    out.append({
        "slide": "manual-income-gap-long", "category": "젠더와 격차",
        "title": "소득 1분위와 5분위 가구의 월평균 소득.",
        "vizType": "line", "unit": "만 원",
        "labels": labs,
        "series": [ser(old, "Q1", oqs), ser(old, "Q5", oqs),
                   ser(new, "Q1", nqs), ser(new, "Q5", nqs)],
        "seriesNames": ["1분위 (2019년 개편 전)", "5분위 (2019년 개편 전)",
                        "1분위 (개편 후)", "5분위 (개편 후)"],
        "seriesColors": ["#9bb8d8", "#f3cb9e", "#2a5ca8", "#e8820c"],
        "source": (f"{SRC}. 전국 1인 이상 가구의 월평균 명목 소득. "
                   f"{lab(oq[0])}~{lab(oq[-1])}는 개편 전 표"
                   f"(KOSIS 101/{OLD}), {lab(nq[0])}~{lab(end)}는 개편 후 "
                   f"표(KOSIS 101/{NEW}). 단위: 만 원."),
        "sourceUrl": URL,
        "notes": [
            "선이 둘로 갈라진 것은 2019년에 조사 방식이 바뀌었기 "
            "때문입니다. 두 조사가 겹치는 2019년 네 분기에서 전체 평균이 "
            f"{min(g[1] for g in gaps):.0%} 안팎, 1분위는 "
            f"{min(g[2] for g in gaps):.0%} 넘게 차이 납니다. 한 선으로 "
            "이으면 2019년에 소득이 갑자기 뛴 것처럼 보이므로 "
            "나눠 그렸습니다. 옅은 선이 개편 전입니다.",
            f"개편 후 기준으로 {lab(end)}에 1분위 "
            f"{new['Q1'][end]/10000:,.0f}만 원, 5분위 "
            f"{new['Q5'][end]/10000:,.0f}만 원입니다. 5분위가 1분위의 "
            f"{new['Q5'][end]/new['Q1'][end]:.1f}배입니다.",
            "2017년과 2018년 상반기는 개편 후 표에 없습니다. 그 무렵 소득 "
            "부문 조사가 중단됐다가 2019년에 되살아났습니다. 개편 전 "
            "표에는 그 구간이 있습니다.",
            "명목 소득입니다. 물가를 반영하지 않았으므로 오래 전 금액과 "
            "지금 금액의 구매력은 다릅니다.",
        ],
        "updated": ymd,
    })

    print()
    for x in out:
        print(f"  {x['slide']} {len(x['labels'])}점 {x['labels'][0]}~"
              f"{x['labels'][-1]} | 계열 {len(x['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out:
        prev_it = idx.get(x["slide"])
        if prev_it:
            keep = {k: prev_it[k] for k in ("id",) if k in prev_it}
            prev_it.clear()
            prev_it.update(x)
            prev_it.update(keep)
        else:
            doc["items"].append(x)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
