#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사이드카와 주가 등락(c2155) — 코스피 일별 등락률을 발동 여부로 가른다.

자료는 data/src/kospi_daily_2026.csv 다. 칸은
  date, close, change_pct, sidecar(buy|sell|빈칸), circuit_breaker(CB|빈칸)
한국거래소가 사이드카를 연도별로 모아 내놓지 않아서 사용자가 발동일을
직접 확인해 만든 파일이다. 갱신본을 같은 자리에 덮어쓰고 다시 돌리면 된다.

하루에 막대 하나만 선다. 그날 매도 사이드카가 걸렸으면 등락률을 '매도'
계열에 넣고 나머지 두 계열은 0으로 둔다. 쌓기 막대지만 실제로 쌓이지는
않고 색만 갈린다. 매도는 빨강, 매수는 파랑, 발동이 없던 날은 회색이다.

섞으면 안 되는 것.
  등락률은 전 거래일 종가 대비다. 파일의 change_pct 가 종가로 계산한
  값과 맞는지 검산한 뒤에 쓴다.
  circuit_breaker 칸은 여기서 쓰지 않는다. 서킷브레이커는 c2432 다.
"""
import argparse
import csv
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SRC = os.path.join(DATA, "src", "kospi_daily_2026.csv")
CID = "c2155"
COL = ["#c0322f", "#2a5ca8", "#c9c9c9"]      # 매도, 매수, 없었던 날
NAMES = ["매도 사이드카. ", "매수 사이드카. ", "사이드카 없었던 날. "]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    if not os.path.exists(SRC):
        print(f"{SRC} 가 없다")
        return 2
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    rows = [r for r in rows if r.get("date") and r.get("close")]
    rows.sort(key=lambda r: r["date"])
    print(f"    받음: {len(rows)}거래일 {rows[0]['date']}~"
          f"{rows[-1]['date']}")

    # 검산 1. 등락률이 종가로 계산한 값과 맞는가
    bad = []
    for i in range(1, len(rows)):
        prev = float(rows[i - 1]["close"])
        cur = float(rows[i]["close"])
        want = (cur / prev - 1) * 100
        got = float(rows[i]["change_pct"])
        if abs(want - got) > 0.02:
            bad.append((rows[i]["date"], got, round(want, 2)))
    if bad:
        print(f"  검산 실패: 등락률이 종가와 맞지 않는 날 {len(bad)}개 "
              f"{bad[:3]}")
        return 1
    print(f"    검산 등락률: {len(rows)-1}일 모두 전 거래일 종가로 "
          "계산한 값과 일치")

    # 검산 2. 사이드카 칸에 낯선 값이 없는가
    odd = sorted({(r.get("sidecar") or "").strip() for r in rows}
                 - {"", "buy", "sell"})
    if odd:
        print(f"  검산 실패: 사이드카 칸에 낯선 값 {odd}")
        return 1
    sell = sum(1 for r in rows if (r.get("sidecar") or "").strip() == "sell")
    buy = sum(1 for r in rows if (r.get("sidecar") or "").strip() == "buy")
    print(f"    검산 값: 매도 {sell}일, 매수 {buy}일, 합 {sell+buy}일")

    labels, s_sell, s_buy, s_non = [], [], [], []
    for r in rows:
        labels.append(r["date"][5:])
        v = float(r["change_pct"])
        k = (r.get("sidecar") or "").strip()
        s_sell.append(v if k == "sell" else 0.0)
        s_buy.append(v if k == "buy" else 0.0)
        s_non.append(v if k == "" else 0.0)

    # 검산 3. 기존 차트와 겹치는 날이 같은가
    sys.path.insert(0, HERE)
    import generate_site as g
    it = g.load_items(DATA)
    g.assign_ids(it, os.path.join(DATA, "ids.json"))
    old = {i["id"]: i for i in it if i.get("id")}.get(CID)
    if old:
        oy = [str(x) for x in old["labels"]]
        pos = {l: i for i, l in enumerate(labels)}
        hit = tot = 0
        gap = []
        for i, l in enumerate(oy):
            if l not in pos:
                continue
            tot += 1
            j = pos[l]
            o3 = [old["series"][k][i] or 0 for k in range(3)]
            n3 = [[s_sell, s_buy, s_non][k][j] for k in range(3)]
            if all(abs(o3[k] - n3[k]) < 0.02 for k in range(3)):
                hit += 1
            else:
                tag = lambda t: ("매도" if t[0] else
                                 "매수" if t[1] else "없음")
                gap.append(f"{l} {tag(o3)} {max(o3, key=abs):+.2f}"
                           f" -> {tag(n3)} {max(n3, key=abs):+.2f}")
        # 자료 쪽은 종가로 계산한 등락률과 전부 맞는다(검산 1). 기존 차트가
        # 어긋나는 자리는 그쪽이 옛 값이라고 보고 자료를 쓰되, 어디가
        # 달라지는지 남긴다. 많이 어긋나면 멈춘다.
        if not tot or hit / tot < 0.9:
            print(f"  검산 실패: 기존 차트와 {hit}/{tot} 만 일치 "
                  f"{gap[:4]}")
            return 1
        print(f"    검산 재현: 기존 {tot}일 가운데 {hit}일 일치 "
              f"({oy[-1]} -> {labels[-1]})")
        if gap:
            print(f"    달라지는 날 {len(gap)}개: " + ", ".join(gap))

    yr = rows[0]["date"][:4]
    last = rows[-1]["date"]
    it_new = {
        "labels": labels, "series": [s_sell, s_buy, s_non],
        "seriesNames": list(NAMES), "seriesColors": list(COL),
        "unit": "%", "vizType": "stacked_bar",
        "source": (f"한국거래소 사이드카 발동일과 코스피 일별 등락률. "
                   f"{yr}년 {rows[0]['date'][5:7].lstrip('0')}월 "
                   f"{rows[0]['date'][8:].lstrip('0')}일부터 "
                   f"{last[5:7].lstrip('0')}월 "
                   f"{last[8:].lstrip('0')}일까지. 단위: %."),
        "sourceUrl": "",
        "notes": [
            f"{yr}년 {len(rows)}거래일 가운데 사이드카가 걸린 날은 "
            f"{sell+buy}일입니다. 매도가 {sell}일, 매수가 {buy}일입니다.",
            "막대 하나가 하루입니다. 그날 걸린 사이드카의 종류에 따라 "
            "색이 갈립니다. 매도는 빨강, 매수는 파랑, 걸리지 않은 날은 "
            "회색입니다.",
            "높이는 그날 코스피 등락률입니다. 사이드카는 선물 가격을 "
            "보고 걸리므로 현물 지수의 등락률과 정확히 같이 움직이지는 "
            "않습니다.",
            "한국거래소가 발동할 때마다 알리지만 날짜를 모아 놓은 표는 "
            "따로 내놓지 않습니다. 발표를 모아 정리한 자료입니다.",
        ],
        "updated": ymd,
    }

    print(f"\n  {CID} {len(labels)}점 {labels[0]}~{labels[-1]} | 계열 3")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    o.setdefault(CID, {}).update(it_new)
    o[CID].pop("revised", None)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {CID} 를 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
