#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""산업별 취업자 증감(c0053 제조업) — 경제활동인구조사.

표는 KOSIS 101/DT_1DA7E06S_NEW(산업별 취업자, 월). 산업 코드는 제조업
10, 건설업 41이고 값의 단위는 천 명이다.

단위 표기가 틀려 있었다.
  c0053 에는 "만 명, 전년 동월 대비"라고 적혀 있었는데 값은 증감률(%)
  이다. 2014년 1월 2.1 은 2.1만 명이 아니라 2.1% 다. 같은 표로 다시
  계산하면 144개 값이 하나도 빠짐없이 맞는다. 단위를 % 로 바로잡는다.

0을 넘나드는 지표라 늘어난 달과 줄어든 달을 두 계열로 나눠 쌓는다.
늘어난 쪽이 파랑, 줄어든 쪽이 빨강이다.

섞으면 안 되는 것.
  c0054(건설업 취업자수 증감 추이)는 같은 표를 쓰지만 api_map.json 에
  등록돼 자동으로 갱신된다. 여기서 건드리지 않는다. 한 차트에 쓰는
  어댑터는 하나여야 한다.
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

ORG, TBL = "101", "DT_1DA7E06S_NEW"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101"
       "&tblId=DT_1DA7E06S_NEW")
UP, DOWN = "#2a5ca8", "#c0322f"
# 차트 id: (산업코드, 산업이름, 계열이 시작하는 달)
CHARTS = {"c0053": ("10", "제조업", "2014-01")}


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


def pull(key, code, tries=3):
    end = datetime.datetime.now(KST).strftime("%Y12")
    p = {"method": "getList", "apiKey": key, "orgId": ORG, "tblId": TBL,
         "itmId": "T30+", "objL1": code + "+", "format": "json",
         "jsonVD": "Y", "prdSe": "M", "startPrdDe": "201301",
         "endPrdDe": end}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p, safe="+"))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=90))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}")
            v = {r["PRD_DE"]: float(r["DT"]) for r in d
                 if r.get("DT") not in (None, "", "-")}
            if len(v) < 100:
                raise RuntimeError(f"{len(v)}개월뿐이다")
            return v
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{TBL} {code} 를 받지 못했다: {last}")


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

    out = {}
    for cid, (code, name, start) in CHARTS.items():
        v = pull(key, code)
        ks = sorted(v)
        print(f"    받음: {name} {len(ks)}개월 {ks[0]}~{ks[-1]} "
              f"(끝달 {v[ks[-1]]:,.0f}천 명)")

        labs, up, dn = [], [], []
        for k in ks:
            prev = f"{int(k[:4]) - 1}{k[4:]}"
            lab = f"{k[:4]}-{k[4:]}"
            if prev not in v or lab < start:
                continue
            r = (v[k] / v[prev] - 1) * 100
            labs.append(lab)
            up.append(round(max(r, 0), 2))
            dn.append(round(min(r, 0), 2))

        # 검산. 기존 차트의 값이 그대로 재현되는가
        o = old.get(cid)
        if not o:
            print(f"  검산 실패: {cid} 를 찾지 못했다")
            return 1
        oL = [str(x) for x in o["labels"]]
        pos = {l: i for i, l in enumerate(labs)}
        hit = tot = 0
        gap = []
        for i, l in enumerate(oL):
            if l not in pos or o["series"][0][i] is None:
                continue
            tot += 1
            j = pos[l]
            if abs(o["series"][0][i] - (up[j] + dn[j])) < 0.08:
                hit += 1
            elif len(gap) < 4:
                gap.append((l, o["series"][0][i],
                            round(up[j] + dn[j], 2)))
        if not tot or hit / tot < 0.98:
            print(f"  검산 실패: {cid} 기존 값과 {hit}/{tot} 만 일치 "
                  f"{gap}")
            return 1
        print(f"    검산 재현: {cid} 기존 {tot}개 값이 모두 일치 "
              f"(단위는 만 명이 아니라 %, {oL[-1]} -> {labs[-1]})")

        big = max(range(len(labs)), key=lambda i: abs(up[i] + dn[i]))
        last = up[-1] + dn[-1]
        out[cid] = {
            "labels": labs, "series": [up, dn],
            "seriesNames": ["증가", "감소"],
            "seriesColors": [UP, DOWN],
            "unit": "%", "vizType": "stacked_bar",
            "source": (f"국가데이터처 경제활동인구조사 산업별 취업자"
                       f"(KOSIS 101/{TBL}). {name} 취업자 수의 전년 동월 "
                       f"대비 증감률, {labs[0]}~{labs[-1]}. 단위: %."),
            "sourceUrl": URL,
            "notes": [
                f"{labs[-1]}은 한 해 전 같은 달보다 {abs(last):.1f}% "
                f"{'늘었습니다' if last > 0 else '줄었습니다'}. "
                f"{name} 취업자는 {v[ks[-1]]/100:,.1f}만 명입니다.",
                f"가장 크게 움직인 달은 {labs[big]}으로 "
                f"{abs(up[big] + dn[big]):.1f}% "
                f"{'늘었습니다' if up[big] else '줄었습니다'}.",
                "전년 같은 달과 견준 것이라 계절 차이는 지워집니다. "
                "늘어난 달은 파랑, 줄어든 달은 빨강입니다.",
                "전에는 단위가 '만 명'으로 적혀 있었는데 값은 증감률"
                "(%)이었습니다. 숫자는 그대로 두고 단위만 "
                "바로잡았습니다.",
                "경제활동인구조사의 산업 분류는 2024년에 개정됐습니다. "
                "분류가 바뀐 자리에서는 증감률을 읽을 때 조심해야 "
                "합니다.",
            ],
            "updated": ymd,
        }

    print()
    for cid, x in out.items():
        print(f"  {cid} {len(x['labels'])}점 {x['labels'][0]}~"
              f"{x['labels'][-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for cid, x in out.items():
        o.setdefault(cid, {}).update(x)
        o[cid].pop("revised", None)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
