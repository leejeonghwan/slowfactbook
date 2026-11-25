#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""월별 출생과 혼인 — 인구동향조사에서 네 장을 다시 세운다.

출처는 c0094 와 같은 표다(KOSIS 101/DT_1B8000G, 월별 인구동향). c0094 는
api_map.json 에 올라 있어 자동으로 갱신되는데, 같은 표에서 파생된 아래
넷은 어댑터가 없어 키노트에서 넘어온 채로 멈춰 있었다.

  c0142 전년 대비 월별 출생아 증감   2025-10 에서 멈춤
  c0140 월별 혼인 건수 비율          2023년에서 멈춤
  c0139 월별 출생아 비율             2025년
  c0116 출산과 혼인 건수(월 평균)    1981~2023년 평균

c0116 은 계열이 뒤바뀌어 있었다.
  '혼인'으로 적힌 계열의 1월 값 54,248 은 1981~2023년 1월 출생아 평균이고,
  '출산'으로 적힌 54,248 자리의 짝인 30,370 이 혼인 평균이다. 열두 달이
  모두 그렇다. 이름만 맞바꿔 바로잡고, 평균 구간도 2025년까지 늘린다.

c0142 는 전년 같은 달과의 차이다. 늘어난 달과 줄어든 달을 두 계열로 나눠
쌓는다. 0을 넘나드는 지표라 선이 아니라 막대이고, 늘어난 쪽이 파랑,
줄어든 쪽이 빨강이다.

연중 비율(c0139, c0140)은 열두 달이 다 찬 해만 쓴다. 올해는 아직 달이
덜 찼으므로 넣지 않는다.

섞으면 안 되는 것.
  월별 수치는 잠정치로 먼저 나왔다가 나중에 확정된다. 2023년 이후 몇 달이
  예전에 그려 둔 값과 조금씩 다른 것은 그 때문이다. 확정치 쪽으로 다시
  세운다.
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

ORG, TBL = "101", "DT_1B8000G"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101"
       "&tblId=DT_1B8000G")
SRC = "국가데이터처 인구동향조사"
KIND = {"출생": "10", "혼인": "20"}
UP, DOWN = "#2a5ca8", "#c0322f"
MONTHS = [f"{i:02d}" for i in range(1, 13)]


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
    end = datetime.datetime.now(KST).strftime("%Y12")
    p = {"method": "getList", "apiKey": key, "orgId": ORG, "tblId": TBL,
         "itmId": "T1+", "objL1": "00+", "objL2": "10+20+",
         "format": "json", "jsonVD": "Y", "prdSe": "M",
         "startPrdDe": "198101", "endPrdDe": end}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p, safe="+"))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=120))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}")
            out = {}
            for r in d:
                if r.get("DT") in (None, "", "-"):
                    continue
                out.setdefault(r["C2"], {})[r["PRD_DE"]] = float(r["DT"])
            if out.get("10") and out.get("20"):
                return {n: out[c] for n, c in KIND.items()}
            raise RuntimeError("출생이나 혼인이 비었다")
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

    d = pull(key)
    B, M = d["출생"], d["혼인"]
    ks = sorted(B)
    print(f"    받음: {len(ks)}개월 {ks[0]}~{ks[-1]} "
          f"(끝달 출생 {B[ks[-1]]:,.0f}명, 혼인 {M[ks[-1]]:,.0f}건)")

    # 검산 1. 자동 갱신되는 c0094 와 같은 표에서 나온 같은 값인가
    c94 = old["c0094"]
    L94 = [str(x) for x in c94["labels"]]
    bad, seen = [], 0
    for i, lab in enumerate(L94):
        k = lab.replace("-", "")
        for j, src in ((0, B), (1, M)):
            v = c94["series"][j][i]
            if v is None or k not in src:
                continue
            seen += 1
            if abs(src[k] - v) > 1:
                bad.append((lab, j, v, src[k]))
    if seen < 1000 or len(bad) > seen * 0.01:
        print(f"  검산 실패: c0094 와 {len(bad)}/{seen} 어긋난다 "
              f"{bad[:3]}")
        return 1
    print(f"    검산 교차: 자동 갱신 차트 c0094 의 {seen}개 값 가운데 "
          f"{seen-len(bad)}개 일치")

    # 열두 달이 다 찬 해만 비율을 낸다
    full = [y for y in sorted({k[:4] for k in ks})
            if all(f"{y}{m}" in B and f"{y}{m}" in M for m in MONTHS)]
    print(f"    열두 달이 찬 해: {full[0]}~{full[-1]} ({len(full)}해)")

    out = {}

    # c0139, c0140 — 연중 비율
    for cid, src, nm, names in (
            ("c0139", B, "출생아", [f"{i}월" for i in range(1, 13)]),
            ("c0140", M, "혼인 건수", list(MONTHS))):
        ser = []
        for mi, m in enumerate(MONTHS):
            ser.append([round(src[f"{y}{m}"]
                              / sum(src[f"{y}{x}"] for x in MONTHS)
                              * 100, 1) for y in full])
        # 검산: 해마다 열두 달 비율 합이 100 인가
        bad = [(full[i], round(sum(s[i] for s in ser), 1))
               for i in range(len(full))
               if abs(sum(s[i] for s in ser) - 100) > 0.35]
        if bad:
            print(f"  검산 실패: {cid} 연중 비율 합이 100이 아니다 "
                  f"{bad[:3]}")
            return 1
        # 검산: 기존 차트와 겹치는 구간이 같은가
        o = old[cid]
        oy = [str(x) for x in o["labels"]]
        hit = tot = 0
        for mi in range(12):
            for yi, y in enumerate(oy):
                v = o["series"][mi][yi]
                if v is None or y not in full:
                    continue
                tot += 1
                if abs(ser[mi][full.index(y)] - v) < 0.15:
                    hit += 1
        if not tot or hit / tot < 0.98:
            print(f"  검산 실패: {cid} 기존 값과 {hit}/{tot} 만 일치")
            return 1
        print(f"    검산 재현: {cid} 기존 {tot}개 값 가운데 {hit}개 일치 "
              f"({oy[-1]} -> {full[-1]})")
        out[cid] = {
            "labels": list(full), "series": ser, "seriesNames": names,
            "unit": "%", "vizType": "line",
            "source": (f"{SRC}(KOSIS 101/{TBL}). 한 해 {nm} 가운데 그 달이 "
                       f"차지하는 비율, {full[0]}~{full[-1]}년. 단위: %."),
            "sourceUrl": URL,
            "notes": [
                f"열두 달을 더하면 100%가 됩니다. {full[-1]}년에 가장 "
                f"{'많은' if True else ''} 달은 "
                + ", ".join(
                    f"{names[i]} {ser[i][-1]}%" for i in
                    sorted(range(12), key=lambda x: -ser[x][-1])[:3])
                + " 순입니다.",
                "열두 달이 다 찬 해만 그립니다. 올해는 아직 달이 덜 차서 "
                "넣지 않았습니다.",
                "월별 수치는 잠정치로 먼저 나왔다가 나중에 확정됩니다. "
                "예전에 그려 둔 값과 최근 몇 달이 조금 다를 수 있습니다.",
            ],
            "updated": ymd,
        }

    # c0142 — 전년 같은 달 대비 증감
    labs, up, dn = [], [], []
    for k in ks:
        prev = f"{int(k[:4]) - 1}{k[4:]}"
        if prev not in B:
            continue
        diff = B[k] - B[prev]
        labs.append(f"{k[:4]}-{k[4:]}")
        up.append(round(max(diff, 0)))
        dn.append(round(min(diff, 0)))
    o = old["c0142"]
    oL = [str(x) for x in o["labels"]]
    pos = {l: i for i, l in enumerate(labs)}
    hit = tot = 0
    for i, l in enumerate(oL):
        if l not in pos:
            continue
        tot += 1
        j = pos[l]
        if (abs((o["series"][0][i] or 0) - up[j]) < 1
                and abs((o["series"][1][i] or 0) - dn[j]) < 1):
            hit += 1
    if not tot or hit / tot < 0.9:
        print(f"  검산 실패: c0142 기존 값과 {hit}/{tot} 만 일치")
        return 1
    print(f"    검산 재현: c0142 기존 {tot}개 달 가운데 {hit}개 일치 "
          f"(확정치로 바뀐 달 {tot-hit}개, {oL[-1]} -> {labs[-1]})")
    big = max(range(len(labs)), key=lambda i: abs(up[i] + dn[i]))
    out["c0142"] = {
        "labels": labs, "series": [up, dn],
        "seriesNames": ["증가", "감소"],
        "seriesColors": [UP, DOWN], "hideLegend": False,
        "unit": "명", "vizType": "stacked_bar",
        "source": (f"{SRC}(KOSIS 101/{TBL}). 전년 같은 달과 견준 출생아 수 "
                   f"증감, {labs[0]}~{labs[-1]}. 단위: 명."),
        "sourceUrl": URL,
        "notes": [
            f"{labs[-1]}은 한 해 전 같은 달보다 "
            f"{abs(up[-1] + dn[-1]):,.0f}명 "
            f"{'늘었습니다' if up[-1] else '줄었습니다'}.",
            f"가장 크게 움직인 달은 {labs[big]}으로 "
            f"{abs(up[big] + dn[big]):,.0f}명 "
            f"{'늘었습니다' if up[big] else '줄었습니다'}.",
            "전년 같은 달과 견준 것이라 계절 차이는 지워집니다. 늘어난 "
            "달은 파랑, 줄어든 달은 빨강입니다.",
            "월별 수치는 잠정치로 먼저 나왔다가 나중에 확정됩니다. "
            "2023년 이후 몇 달이 예전 값과 조금 다른 것은 확정치로 다시 "
            "세웠기 때문입니다.",
        ],
        "updated": ymd,
    }

    # c0116 — 월 평균. 계열이 뒤바뀌어 있었다
    def avg(src, m):
        v = [src[f"{y}{m}"] for y in full]
        return round(sum(v) / len(v), 1)
    mar = [avg(M, m) for m in MONTHS]
    bir = [avg(B, m) for m in MONTHS]
    o = old["c0116"]
    swapped = sum(1 for i in range(12)
                  if abs(o["series"][0][i] - bir[i]) < 1200)
    straight = sum(1 for i in range(12)
                   if abs(o["series"][0][i] - mar[i]) < 1200)
    if swapped < 10 or straight > 2:
        print(f"  검산 실패: c0116 이 뒤바뀐 것이 아닌 듯하다 "
              f"(뒤바뀜 {swapped}/12, 그대로 {straight}/12)")
        return 1
    print(f"    검산 뒤바뀜: c0116 의 '혼인' 계열이 열두 달 가운데 "
          f"{swapped}달에서 출생아 평균과 맞고 혼인 평균과는 "
          f"{12-straight}달이 다름 — 이름이 맞바뀐 것이 맞습니다")
    out["c0116"] = {
        "labels": [f"{i}월" for i in range(1, 13)],
        "series": [mar, bir], "seriesNames": ["혼인", "출생"],
        "seriesColors": [UP, "#e8820c"],
        "unit": "건, 명", "vizType": "column",
        "source": (f"{SRC}(KOSIS 101/{TBL}). {full[0]}~{full[-1]}년 월 "
                   "평균. 혼인은 건, 출생은 명입니다."),
        "sourceUrl": URL,
        "notes": [
            f"혼인은 12월이 {mar[11]:,.0f}건으로 가장 많고 "
            f"{MONTHS[mar.index(min(mar))].lstrip('0')}월이 "
            f"{min(mar):,.0f}건으로 가장 적습니다. 출생은 "
            f"{MONTHS[bir.index(max(bir))].lstrip('0')}월이 "
            f"{max(bir):,.0f}명으로 가장 많습니다.",
            "전에는 두 계열의 이름이 서로 뒤바뀌어 있었습니다. '혼인'으로 "
            "적힌 1월 값 54,248은 1월 출생아 평균이었고 혼인 평균은 "
            "30,370건이었습니다. 열두 달이 모두 그랬습니다. 이름을 "
            "바로잡고 평균 구간도 2023년까지에서 "
            f"{full[-1]}년까지로 늘렸습니다.",
            f"{full[0]}년부터 {full[-1]}년까지 {len(full)}해의 달별 "
            "평균입니다. 이 기간에 출생아 수가 크게 줄었으므로 평균은 "
            "지금의 수준이 아니라 계절의 모양을 보는 값입니다.",
        ],
        "updated": ymd,
    }

    print()
    for cid, v in out.items():
        print(f"  {cid} {len(v['labels'])}점 | 계열 "
              f"{len(v['series'])} | {v['labels'][-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for cid, v in out.items():
        o.setdefault(cid, {}).update(v)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
