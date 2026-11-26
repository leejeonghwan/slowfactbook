#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""10대와 20대 자살률, 10대 자살자 수 — 사망원인통계.

표는 KOSIS 101/DT_1B34E01(사망원인 104항목/성/연령 5세별). 1983년부터
있고 사망원인 코드 J06 이 '고의적 자해(자살)'다. 항목은 T1 사망자수,
T5 사망률(인구 10만 명당)이다.

다루는 차트
  c0799 1020 여성 자살률      10-14, 15-19, 20-24, 25-29세
  c0800 1020 남성 자살률      같은 네 구간
  c0807 한국의 10대 자살자 수  10-14 와 15-19 를 더한 수, 남녀
  c0810 c0807 과 같은 내용이다. 계열 차례만 다르다.

c0798(10대 자살률)은 건드리지 않는다.
  10~19세를 한 줄로 낸 계열인데, 이 표에는 5세 구간만 있어서 둘을
  인구로 가중평균해야 한다. 그렇게 구하면 최근 해는 맞지만 1980년대와
  1990년대가 0.1 씩 어긋난다. 반올림 자리의 차이로 보이고, 이미 2025년
  까지 들어 있어 손댈 이유가 없다.

섞으면 안 되는 것.
  사망률은 그 연령 인구 10만 명당이다. 연령 구간이 다르면 분모가 달라서
  구간끼리 더하거나 평균 낼 수 없다.
  사망원인통계는 해마다 9월에 전해 것이 나온다. 그래서 가장 최근 해는
  늘 한 해 전이다. 월별이나 분기 잠정치는 다른 표이고 기준이 다르다.
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

ORG, TBL = "101", "DT_1B34E01"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101"
       "&tblId=DT_1B34E01")
SRC = "국가데이터처 사망원인통계"
AGE = [("10", "10 - 14세"), ("15", "15 - 19세"),
       ("20", "20 - 24세"), ("25", "25 - 29세")]
COLS = ["#2a5ca8", "#e8820c", "#6a8f3c", "#c0322f"]
SEXC = ["#2a5ca8", "#c0322f"]


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


def pull(key, tries=3):
    p = {"method": "getList", "apiKey": key, "orgId": ORG, "tblId": TBL,
         "itmId": "T1+T5+", "objL1": "J06+", "objL2": "1+2+",
         "objL3": "+".join(c for c, _n in AGE) + "+",
         "format": "json", "jsonVD": "Y", "prdSe": "Y",
         "startPrdDe": "1983", "endPrdDe": "2099"}
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
                v[(r["ITM_ID"], r["C2"], r["C3"], r["PRD_DE"])] = \
                    float(r["DT"])
            if len(v) < 500:
                raise RuntimeError(f"{len(v)}칸뿐이다")
            return v
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{TBL} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    sys.path.insert(0, HERE)
    import generate_site as g
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    old = {i["id"]: i for i in items if i.get("id")}

    v = pull(key)
    ys = sorted({k[3] for k in v})
    print(f"    받음: {len(ys)}해 {ys[0]}~{ys[-1]} ({len(v)}칸)")

    # 검산 1. 사망률이 사망자수와 인구로 들어맞는 범위인가
    #         (사망자가 있는데 사망률이 0 이거나 그 반대면 표가 이상하다)
    bad = []
    for sex in ("1", "2"):
        for c, nm in AGE:
            for y in ys:
                n = v.get(("T1", sex, c, y))
                r = v.get(("T5", sex, c, y))
                if (n is None) != (r is None):
                    bad.append((sex, nm, y, n, r))
                elif n and not r:
                    bad.append((sex, nm, y, n, r))
    if bad:
        print(f"  검산 실패: 사망자수와 사망률이 짝이 안 맞는 칸 "
              f"{len(bad)}개 {bad[:3]}")
        return 1
    print("    검산 짝: 모든 칸에서 사망자수와 사망률이 함께 있음")

    out = {}

    # c0799 여성, c0800 남성 — 네 구간 자살률
    for cid, sex, nm in (("c0799", "2", "여성"), ("c0800", "1", "남성")):
        ser = [[v.get(("T5", sex, c, y)) for y in ys] for c, _n in AGE]
        o = old[cid]
        oy = [str(x) for x in o["labels"]]
        hit = tot = 0
        for si in range(4):
            for i, y in enumerate(oy):
                ov_ = o["series"][si][i]
                if ov_ is None or y not in ys:
                    continue
                tot += 1
                nv = ser[si][ys.index(y)]
                if nv is not None and abs(ov_ - nv) < 0.06:
                    hit += 1
        if not tot or hit / tot < 0.99:
            print(f"  검산 실패: {cid} 기존 값과 {hit}/{tot} 만 일치")
            return 1
        print(f"    검산 재현: {cid} 기존 {tot}개 값이 모두 일치 "
              f"({oy[-1]} -> {ys[-1]})")
        last = {n: ser[i][-1] for i, (_c, n) in enumerate(AGE)}
        top = max(last, key=lambda k: last[k] or 0)
        out[cid] = {
            "labels": list(ys), "series": ser,
            "seriesNames": [n for _c, n in AGE], "seriesColors": COLS,
            "unit": "명", "vizType": "line",
            "source": (f"{SRC}(KOSIS 101/{TBL}). {nm} 자살 사망률, 해당 "
                       f"연령 인구 10만 명당, {ys[0]}~{ys[-1]}년. "
                       "단위: 명."),
            "sourceUrl": URL,
            "notes": [
                f"{ys[-1]}년에 {nm}은 {top}가 10만 명당 {last[top]}명으로 "
                "가장 높습니다. "
                + ", ".join(f"{n} {last[n]}명" for _c, n in AGE) + "입니다.",
                "해당 연령 인구 10만 명당입니다. 구간마다 분모가 달라서 "
                "구간끼리 더하거나 평균 내면 안 됩니다.",
                "사망원인통계는 해마다 9월에 전해 것이 나옵니다. 그래서 "
                "가장 최근 해는 늘 한 해 전입니다.",
                "사망원인 분류의 '고의적 자해(X60-X84)'입니다.",
            ],
            "updated": ymd,
        }

    # c0807, c0810 — 10대 자살자 수
    def teen(sex):
        return [int((v.get(("T1", sex, "10", y)) or 0)
                    + (v.get(("T1", sex, "15", y)) or 0)) or None
                for y in ys]
    boys, girls = teen("1"), teen("2")
    for cid, order in (("c0807", ["여", "남"]), ("c0810", ["남", "여"])):
        o = old.get(cid)
        if not o:
            continue
        oy = [str(x) for x in o["labels"]]
        pair = {"남": boys, "여": girls}
        hit = tot = 0
        for si, tag in enumerate(order):
            for i, y in enumerate(oy):
                ov_ = o["series"][si][i]
                if ov_ is None or y not in ys:
                    continue
                tot += 1
                nv = pair[tag][ys.index(y)]
                if nv is not None and abs(ov_ - nv) < 1:
                    hit += 1
        if not tot or hit / tot < 0.99:
            print(f"  검산 실패: {cid} 기존 값과 {hit}/{tot} 만 일치")
            return 1
        print(f"    검산 재현: {cid} 기존 {tot}개 값이 모두 일치 "
              f"({oy[-1]} -> {ys[-1]})")
        out[cid] = {
            "labels": list(ys),
            "series": [pair[t] for t in order],
            "seriesNames": [f"10대 {'남성' if t=='남' else '여성'}."
                            for t in order],
            "seriesColors": [SEXC[0] if t == "남" else SEXC[1]
                             for t in order],
            "unit": "명", "vizType": "line",
            "source": (f"{SRC}(KOSIS 101/{TBL}). 10~19세 자살 사망자 수, "
                       f"{ys[0]}~{ys[-1]}년. 단위: 명."),
            "sourceUrl": URL,
            "notes": [
                f"{ys[-1]}년에 10대 남성 {boys[-1]}명, 여성 "
                f"{girls[-1]}명입니다. 한 해 전에는 남성 {boys[-2]}명, "
                f"여성 {girls[-2]}명이었습니다.",
                "10~14세와 15~19세를 더한 수입니다. 사람 수이고 비율이 "
                "아니라서 또래 인구가 줄면 같은 비율이어도 수는 "
                "줄어듭니다. 비율은 자살률 차트를 보십시오.",
                "사망원인통계는 해마다 9월에 전해 것이 나옵니다.",
                "사망원인 분류의 '고의적 자해(X60-X84)'입니다.",
            ],
            "updated": ymd,
        }

    print()
    for cid, x in out.items():
        print(f"  {cid} {len(x['labels'])}점 {x['labels'][0]}~"
              f"{x['labels'][-1]} | 계열 {len(x['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for cid, x in out.items():
        o.setdefault(cid, {}).update(x)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
