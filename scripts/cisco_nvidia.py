#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시스코와 엔비디아, 정점을 맞춘 주가 비교.

떠도는 원본 그림은 축이 둘이다. 시스코는 왼쪽 0~90, 엔비디아는 오른쪽
0~160. 두 곡선이 포개지는 것은 그 배율을 그렇게 골랐기 때문이다.
배율을 바꾸면 겹침도 달라진다. 그래서 여기서는 축을 하나로 두고
각자의 정점을 100으로 맞춘다. 가로축은 정점 기준 거래일이다.

이렇게 하면 '얼마나 올랐다가 얼마나 내렸나'를 같은 자로 잴 수 있다.
배율을 고르는 사람의 손이 빠진다.

주가는 수정종가(adjclose)를 쓴다. 시스코는 1990년대에 액면분할이
여러 번 있어 원종가로는 비율 비교가 안 된다.
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

BEFORE, AFTER = 756, 635      # 정점 기준 거래일 범위(3년 전 ~ 시스코 바닥)
SPECS = [
    ("시스코", "CSCO", "1990-01-01", "2004-12-31", "#2a5ca8"),
    ("엔비디아", "NVDA", "2019-01-01", None, "#c0322f"),
]
# 시스코는 역사가 끝난 계열이라 값이 바뀌면 안 된다. 바뀌면 멈춘다.
GATE_CSCO_PEAK = "2000-03-27"
GATE_CSCO_AFTER = {10: 90.6, 21: 83.4, 31: 73.1, 252: 22.6, 635: 10.7}


def ep(s):
    return int(datetime.datetime.strptime(s, "%Y-%m-%d")
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def closes(sym, start, end, tries=4):
    p1, p2 = ep(start), ep(end) if end else int(time.time())
    last = None
    for i in range(tries):
        host = "query1" if i % 2 == 0 else "query2"
        u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
             f"?period1={p1}&period2={p2}&interval=1d")
        try:
            req = urllib.request.Request(u, headers=UA)
            res = json.load(urllib.request.urlopen(req, timeout=40))
            res = res["chart"]["result"][0]
            cl = res["indicators"]["adjclose"][0]["adjclose"]
            ts = res["timestamp"]
            rows = [(datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
                     .strftime("%Y-%m-%d"), float(c))
                    for t, c in zip(ts, cl) if c is not None]
            meta = res.get("meta") or {}
            endt = ((meta.get("currentTradingPeriod") or {})
                    .get("regular") or {}).get("end")
            mt = meta.get("regularMarketTime")
            if rows and endt and mt and mt < endt:
                rows = rows[:-1]      # 장중 스냅샷은 종가가 아니다
            if rows:
                return rows
        except Exception as e:                       # noqa: BLE001
            last = e
        time.sleep(2 + 2 * i)
    raise RuntimeError(f"{sym} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    xs = list(range(-BEFORE, AFTER + 1))
    series, info = [], {}
    for nm, sym, s0, s1, _col in SPECS:
        rows = closes(sym, s0, s1)
        pi = max(range(len(rows)), key=lambda i: rows[i][1])
        pk = rows[pi][1]
        info[nm] = {"peak_date": rows[pi][0], "peak": pk,
                    "last_date": rows[-1][0], "last": rows[-1][1],
                    "after": len(rows) - 1 - pi, "rows": rows, "pi": pi}
        series.append([round(rows[pi + d][1] / pk * 100, 2)
                       if 0 <= pi + d < len(rows) else None for d in xs])

    c = info["시스코"]
    if c["peak_date"] != GATE_CSCO_PEAK:
        print(f"  검산 실패: 시스코 정점이 {c['peak_date']} 다 "
              f"({GATE_CSCO_PEAK} 여야 한다)")
        return 1
    for d, want in GATE_CSCO_AFTER.items():
        got = round(c["rows"][c["pi"] + d][1] / c["peak"] * 100, 1)
        if abs(got - want) > 0.2:
            print(f"  검산 실패: 시스코 정점+{d}일 {got} != {want}")
            return 1
    print(f"    검산 시스코: 정점 {c['peak_date']}, "
          f"{len(GATE_CSCO_AFTER)}개 시점 모두 일치")

    zero = [s[xs.index(0)] for s in series]
    if any(abs(v - 100) > 0.01 for v in zero):
        print(f"  검산 실패: 0일 값이 100 이 아니다 {zero}")
        return 1
    print("    검산 정렬: 두 계열 모두 0일에 100")

    n = info["엔비디아"]
    nd = n["after"]
    cv = round(c["rows"][c["pi"] + nd][1] / c["peak"] * 100, 1)
    nv = round(n["last"] / n["peak"] * 100, 1)
    trough = min(range(c["pi"], len(c["rows"])),
                 key=lambda i: c["rows"][i][1])
    tv = round(c["rows"][trough][1] / c["peak"] * 100, 1)
    td = trough - c["pi"]

    def mult(d):
        i = n["pi"] - d
        return round(n["peak"] / n["rows"][i][1], 1) if i >= 0 else None

    def multc(d):
        i = c["pi"] - d
        return round(c["peak"] / c["rows"][i][1], 1) if i >= 0 else None

    it = {
        "slide": "manual-cisco-nvidia",
        "category": "주식",
        "title": "시스코와 엔비디아, 정점을 맞춘 주가",
        "vizType": "line", "unit": "정점=100",
        "labels": [str(x) for x in xs],
        "series": series,
        "seriesNames": [f"시스코({c['peak_date'][:4]}년 정점)",
                        f"엔비디아({n['peak_date'][:4]}년 정점)"],
        "seriesColors": [s[4] for s in SPECS],
        "source": ("야후 파이낸스 수정종가. 각자의 정점을 100으로 맞추고 "
                   "가로축을 정점 기준 거래일로 놓았습니다. 시스코 정점 "
                   f"{c['peak_date']}, 엔비디아 정점 {n['peak_date']}. "
                   "단위: 정점=100."),
        "sourceUrl": "https://finance.yahoo.com/quote/NVDA/",
        "notes": [
            f"엔비디아는 정점에서 {nd}거래일 지나 {nv}%입니다. 시스코는 "
            f"같은 {nd}거래일에 {cv}% 였습니다.",
            f"시스코는 정점 뒤 {td}거래일에 걸쳐 {tv}%까지 내려갔습니다. "
            f"{round(100-tv,1)}% 빠진 것이고, 그 바닥은 "
            f"{c['rows'][trough][0]} 입니다. 엔비디아는 아직 "
            f"{nd}거래일째입니다.",
            f"올라간 폭은 많이 다릅니다. 정점까지 3년 동안 시스코는 "
            f"{multc(756)}배, 엔비디아는 {mult(756)}배 올랐습니다. "
            f"1년으로 좁히면 {multc(252)}배와 {mult(252)}배입니다.",
            "떠도는 원본 그림은 세로축이 둘입니다. 두 곡선이 포개져 "
            "보이는 것은 그 배율을 그렇게 고른 결과이고, 배율을 바꾸면 "
            "겹침도 달라집니다. 여기서는 축을 하나로 두고 각자의 정점을 "
            "100으로 맞췄습니다.",
            "모양이 닮았다는 것이 같은 일이 벌어진다는 뜻은 아닙니다. "
            "정점 뒤 한 달은 어느 하락장에서나 비슷해 보입니다. 시스코의 "
            "본격적인 붕괴는 정점 뒤 6개월에서 1년 사이였습니다. 두 회사의 "
            "실적은 「엔비디아 분기 매출과 영업이익」을 함께 보십시오.",
            "액면분할을 소급 반영한 수정종가입니다. 시스코는 1990년대에 "
            "분할이 여러 번 있어 원종가로는 비율을 견줄 수 없습니다.",
        ],
        "updated": ymd,
    }

    print(f"  {it['title']} {len(xs)}점 "
          f"({xs[0]} ~ {xs[-1]} 거래일)")
    print(f"    엔비디아 정점 {n['peak_date']} {n['peak']:.2f} -> "
          f"{n['last_date']} {nv}% (정점+{nd}일)")
    print(f"    시스코 같은 시점 {cv}%, 바닥 {tv}% (정점+{td}일)")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    old = idx.get(it["slide"])
    if old:
        keep = {k: old[k] for k in ("id",) if k in old}
        old.clear()
        old.update(it)
        old.update(keep)
    else:
        doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(p, encoding="utf-8"))
    print("-> data/manual.json 에 1장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
