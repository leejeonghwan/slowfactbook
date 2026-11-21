#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""삼양식품과 엔비디아 주가(c1133).

고친 것 세 가지.

1. 삼양식품 계열이 통째로 한 달 밀려 있었다.
   옛 차트의 2020-01 은 101,500원인데 그건 2019년 12월 종가다.
   2020-01 부터 2025-08 까지 69점이 모두 '전달' 종가와 일치했다.
   불닭 급등 시점이 한 달 늦게 그려져 있었다.

2. 마지막 점이 월말 종가가 아니었다.
   옛 차트 2025-09 는 삼양 1,574,000원, 엔비디아 177.75달러인데
   그달 종가는 1,348,000원과 186.58달러다. 아직 안 끝난 달을 찍었다.
   그래서 진행 중인 달은 아예 뺀다.

3. 축이 둘이고 통화가 달랐다.
   왼쪽은 원, 오른쪽은 달러였다. 두 곡선이 어디서 만나고 갈라지는지가
   축 배율을 어떻게 잡느냐에 달려 있었다. 게다가 출처에는 '달러'만
   적혀 있어 삼양식품이 원이라는 말이 없었다. 그래서 축을 하나로 두고
   둘 다 기준달을 100 으로 맞춘다. 통화 문제가 사라지고, 배율을 고르는
   사람의 손도 빠진다. 실제 주가는 비고에 적는다.
"""
import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0"}

BASE = "2020-01"
SPECS = [("삼양식품", "003230.KS", "원", "#c0322f"),
         ("엔비디아", "NVDA", "달러", "#2a5ca8")]

# 옛 차트에 적혀 있던 값. 엔비디아는 그 달 종가와 같았고(계열이 맞음),
# 삼양식품은 '전달' 종가와 같았다(한 달 밀려 있었음). 그 진단이 지금도
# 성립하는지 해마다 다시 확인한다.
GATE_NV = {"2020-01": 5.91, "2020-06": 9.5, "2025-08": 174.18}
GATE_SY_SHIFT = {"2020-01": ("2019-12", 101500.0),
                 "2020-06": ("2020-05", 126000.0),
                 "2025-08": ("2025-07", 1566000.0)}


def get(sym, tries=5):
    last = None
    for i in range(tries):
        host = "query1" if i % 2 == 0 else "query2"
        u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
             f"?range=max&interval=1mo")
        try:
            req = urllib.request.Request(u, headers=UA)
            res = json.load(urllib.request.urlopen(req, timeout=40))
            res = res["chart"]["result"][0]
            ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
            rows = {}
            for t, c in zip(ts, cl):
                if c is None:
                    continue
                k = datetime.datetime.fromtimestamp(
                    t, datetime.timezone.utc).strftime("%Y-%m")
                rows[k] = round(float(c), 2)
            # 아직 안 끝난 달은 월말 종가가 아니다. 뺀다.
            now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
            rows = {k: v for k, v in rows.items() if k < now}
            if rows:
                return rows, (res.get("meta") or {}).get("currency")
        except Exception as e:                       # noqa: BLE001
            last = e
        time.sleep(2 + 2 * i)
    raise RuntimeError(f"{sym} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    data, cur = {}, {}
    for nm, sym, unit, _c in SPECS:
        data[nm], cur[nm] = get(sym)
        if cur[nm] not in ("KRW", "USD"):
            print(f"  검산 실패: {nm} 통화가 {cur[nm]} 다")
            return 1
    want = {"삼양식품": "KRW", "엔비디아": "USD"}
    if cur != want:
        print(f"  검산 실패: 통화가 {cur} 다 ({want} 여야 한다)")
        return 1
    print(f"    검산 통화: 삼양식품 {cur['삼양식품']}, "
          f"엔비디아 {cur['엔비디아']}")

    for k, v in GATE_NV.items():
        if data["엔비디아"].get(k) != v:
            print(f"  검산 실패: 엔비디아 {k} 가 {data['엔비디아'].get(k)} 다 "
                  f"(옛 차트 {v})")
            return 1
    print(f"    검산 엔비디아: {len(GATE_NV)}개 달이 옛 차트와 일치 "
          "(= 엔비디아 계열은 원래 맞았다)")
    for k, (pm, v) in GATE_SY_SHIFT.items():
        if data["삼양식품"].get(pm) != v:
            print(f"  검산 실패: 삼양식품 {pm} 가 "
                  f"{data['삼양식품'].get(pm)} 다 (옛 차트의 {k} 칸에 "
                  f"적혀 있던 {v})")
            return 1
    print(f"    검산 삼양식품: {len(GATE_SY_SHIFT)}개 달이 옛 차트의 "
          "'한 달 뒤' 칸과 일치 (= 옛 계열은 한 달 밀려 있었다)")

    months = sorted(set(data["삼양식품"]) & set(data["엔비디아"]))
    months = [m for m in months if m >= BASE]
    if not months or months[0] != BASE:
        print(f"  검산 실패: 기준달 {BASE} 가 없다")
        return 1
    base = {nm: data[nm][BASE] for nm, _, _, _ in SPECS}
    series = [[round(data[nm][m] / base[nm] * 100, 1) for m in months]
              for nm, _, _, _ in SPECS]
    if any(s[0] != 100.0 for s in series):
        print(f"  검산 실패: 기준달 값이 100 이 아니다 {[s[0] for s in series]}")
        return 1
    print(f"    검산 정렬: 두 계열 모두 {BASE} 에 100")

    last = months[-1]
    sy, nv = data["삼양식품"][last], data["엔비디아"][last]
    syi, nvi = series[0][-1], series[1][-1]
    pk_sy = max(months, key=lambda m: data["삼양식품"][m])
    pk_nv = max(months, key=lambda m: data["엔비디아"][m])

    it = {
        "id": "c1133", "category": "기업과 산업",
        "title": "삼양식품과 엔비디아 주가.",
        "vizType": "line", "unit": f"{BASE}=100",
        "labels": months, "series": series,
        "seriesNames": ["삼양식품", "엔비디아"],
        "seriesColors": [c for _, _, _, c in SPECS],
        "source": (f"야후 파이낸스 월말 종가. {BASE}을 100으로 맞췄습니다. "
                   f"{months[0]}~{last}. 삼양식품은 원, 엔비디아는 달러이고 "
                   f"환율은 반영하지 않았습니다. 단위: {BASE}=100."),
        "sourceUrl": "https://finance.yahoo.com/quote/003230.KS/",
        "notes": [
            f"{last} 기준으로 삼양식품은 {BASE} 대비 {syi:,.0f}, "
            f"엔비디아는 {nvi:,.0f}입니다. 실제 주가는 삼양식품 "
            f"{sy:,.0f}원, 엔비디아 {nv:,.2f}달러입니다.",
            f"삼양식품은 {pk_sy}에 {data['삼양식품'][pk_sy]:,.0f}원으로 "
            f"가장 높았고, 엔비디아는 {pk_nv}에 "
            f"{data['엔비디아'][pk_nv]:,.2f}달러로 가장 높았습니다.",
            "통화가 달라 둘을 같은 축에 원래 액수로 올릴 수 없습니다. "
            "전에는 축을 둘로 나눠 왼쪽에 원, 오른쪽에 달러를 두었는데, "
            "그러면 두 곡선이 어디서 만나고 갈라지는지가 축 배율을 어떻게 "
            "잡느냐에 달라집니다. 기준달을 100으로 맞추면 그 문제가 "
            "사라집니다.",
            "환율은 반영하지 않았습니다. 원화 투자자가 엔비디아를 샀을 때의 "
            "수익률은 이 선보다 환율 변동만큼 다릅니다.",
            "전에는 삼양식품 계열이 한 달씩 밀려 있었습니다. 2020년 1월 "
            "칸에 2019년 12월 종가 101,500원이 들어가는 식으로 69점이 "
            "모두 전달 값이었습니다. 불닭 급등 시점이 한 달 늦게 그려져 "
            "있었습니다. 마지막 점도 아직 끝나지 않은 달의 월중값이었습니다. "
            "둘 다 바로잡았습니다.",
        ],
        "updated": ymd,
    }

    print(f"  c1133 {len(months)}점 {months[0]}~{last} "
          f"(삼양 {syi:,.0f}, 엔비디아 {nvi:,.0f})")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    o.setdefault("c1133", {}).update(it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c1133 을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
