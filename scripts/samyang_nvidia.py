#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""삼양식품과 엔비디아 주가(c1133, 그리고 AI 열풍 이후 일별 한 장).

함정 — 야후 월별 봉은 쓰지 않는다.
  월별 봉 timestamp 의 기준 시각이 거래소마다 다르다. 한국거래소는
  UTC 로 라벨을 붙이면 2월 봉이 1월로 밀리고(2020-02-01 00:00 KST =
  2020-01-31 15:00 UTC), 미국 거래소는 gmtoffset 을 더하면 오히려
  4월 봉이 3월로 밀린다. 어느 쪽에 맞추든 다른 쪽이 깨진다.
  그래서 월별 봉을 아예 받지 않고, **일별 종가에서 월말 값을 직접
  계산**한다. 일별 라벨은 두 거래소 모두 UTC 로 맞는다.

  이 함정을 2026-11-21 에 한 번 밟았다. 밀린 것은 원본 차트가 아니라
  내가 받아 온 쪽이었는데, 반대로 진단하고 원본을 '고쳐' 버렸다.
  게다가 그 틀린 진단을 검산으로 박아 넣어서, 검산이 버그를 정답으로
  확인해 줬다. 자기가 만든 값끼리 맞추는 검산은 아무것도 보증하지
  않는다. 지금 검산은 옛 차트에 적혀 있던 값과 맞춘다.

고친 것 하나 더 — 마지막 점이 월말 종가가 아니었다.
  옛 차트 2025-09 는 삼양 1,574,000원, 엔비디아 177.75달러인데 그달
  종가는 1,529,000원과 186.58달러다. 아직 안 끝난 달을 찍었다.
  진행 중인 달은 아예 뺀다.

고친 것 또 하나 — 축이 둘이고 통화가 달랐다.
  왼쪽 원, 오른쪽 달러였다. 두 곡선이 어디서 만나고 갈라지는지가 축
  배율에 달려 있었고, 출처에는 '달러'만 적혀 있었다. 축을 하나로 두고
  기준달을 100 으로 맞춘다. 실제 주가는 비고에 적는다.

기준달이 곧 결론이라는 점.
  2026-10 에 삼양을 엔비디아로 나눈 값이 2020-01 기준 0.42배,
  2023-01 기준 1.00배, 2024-01 기준 2.20배로 뒤집힌다. 그래서 한 장만
  두지 않고 2020-01 기준(c1133, 월별)과 2023-01 기준(일별) 두 장을
  함께 만든다. 고점이 찍히는 '날짜'는 기준을 바꿔도 안 바뀐다.
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
DBASE = "2023-01"
SPECS = [("삼양식품", "003230.KS", "원", "#c0322f"),
         ("엔비디아", "NVDA", "달러", "#2a5ca8")]

# 옛 차트에 적혀 있던 값. 일별 종가로 따로 검산해 보니 **옛 차트가
# 맞았다**. 월별 수집이 이 값을 그대로 돌려주는지로 밀림을 잡는다.
GATE_OLD = {
    "삼양식품": {"2020-01": 101500.0, "2020-06": 126000.0,
                 "2025-08": 1566000.0},
    "엔비디아": {"2020-01": 5.91, "2020-06": 9.5, "2025-08": 174.18},
}


def ep(d):
    return int(datetime.datetime.strptime(d, "%Y-%m-%d")
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def fetch(sym, params, tries=5):
    last = None
    for i in range(tries):
        host = "query1" if i % 2 == 0 else "query2"
        u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?"
             + params)
        try:
            req = urllib.request.Request(u, headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=45))
            return d["chart"]["result"][0]
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{sym} 를 받지 못했다: {last}")


def rows_of(res, fmt, drop_live=True):
    """거래소 현지 시각으로 라벨을 붙인다. gmtoffset 을 꼭 더한다."""
    meta = res.get("meta") or {}
    ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        k = datetime.datetime.fromtimestamp(
            t, datetime.timezone.utc).strftime(fmt)
        out[k] = round(float(c), 2)
    if drop_live and out:
        end = ((meta.get("currentTradingPeriod") or {})
               .get("regular") or {}).get("end")
        mt = meta.get("regularMarketTime")
        if end and mt and mt < end:
            del out[max(out)]
    return out, meta.get("currency")


def monthly_from_daily(day):
    """일별 종가에서 월말 값을 직접 만든다. 끝난 달만 남긴다."""
    out = {}
    for d in sorted(day):
        out[d[:7]] = day[d]
    now = datetime.datetime.now(KST).strftime("%Y-%m")
    return {k: v for k, v in out.items() if k < now}


def daily(sym, start):
    res = fetch(sym, f"period1={ep(start)}&period2={int(time.time())}"
                     "&interval=1d")
    return rows_of(res, "%Y-%m-%d")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    mon, cur, day = {}, {}, {}
    for nm, sym, _u, _c in SPECS:
        res = fetch(sym, f"period1={ep('2019-11-01')}"
                         f"&period2={int(time.time())}&interval=1d")
        day[nm], cur[nm] = rows_of(res, "%Y-%m-%d")
        mon[nm] = monthly_from_daily(day[nm])
    if cur != {"삼양식품": "KRW", "엔비디아": "USD"}:
        print(f"  검산 실패: 통화가 {cur} 다")
        return 1
    print(f"    검산 통화: 삼양식품 {cur['삼양식품']}, "
          f"엔비디아 {cur['엔비디아']}")

    # ── 검산 1. 옛 차트 값과 같은가(옛 차트가 맞았다는 확인)
    for nm, want in GATE_OLD.items():
        for k, v in want.items():
            if mon[nm].get(k) != v:
                print(f"  검산 실패: {nm} {k} 가 {mon[nm].get(k)} 다 "
                      f"(옛 차트 {v})")
                return 1
    print(f"    검산 원본: 두 종목 {len(GATE_OLD['삼양식품'])}개 달이 "
          "옛 차트 값과 일치 (= 옛 차트는 맞았다)")

    # ── 월별 장(c1133)
    months = [m for m in sorted(set(mon["삼양식품"]) & set(mon["엔비디아"]))
              if m >= BASE]
    if not months or months[0] != BASE:
        print(f"  검산 실패: 기준달 {BASE} 가 없다")
        return 1
    base = {nm: mon[nm][BASE] for nm, _s, _u, _c in SPECS}
    series = [[round(mon[nm][m] / base[nm] * 100, 1) for m in months]
              for nm, _s, _u, _c in SPECS]
    if any(s[0] != 100.0 for s in series):
        print("  검산 실패: 기준달 값이 100 이 아니다")
        return 1
    print(f"    검산 정렬: 월별 두 계열 모두 {BASE} 에 100")

    last = months[-1]
    syi, nvi = series[0][-1], series[1][-1]
    pk_sy = max(months, key=lambda m: mon["삼양식품"][m])
    pk_nv = max(months, key=lambda m: mon["엔비디아"][m])
    it = {
        "id": "c1133", "category": "기업과 산업",
        "title": "삼양식품과 엔비디아 주가.",
        "vizType": "line", "unit": f"{BASE}=100",
        "labels": months, "series": series,
        "seriesNames": ["삼양식품", "엔비디아"],
        "seriesColors": [c for _n, _s, _u, c in SPECS],
        "source": (f"야후 파이낸스 월말 종가. {BASE}을 100으로 맞췄습니다. "
                   f"{months[0]}~{last}. 삼양식품은 원, 엔비디아는 달러이고 "
                   f"환율은 반영하지 않았습니다. 단위: {BASE}=100."),
        "sourceUrl": "https://finance.yahoo.com/quote/003230.KS/",
        "notes": [
            f"{last} 기준으로 삼양식품은 {BASE} 대비 {syi:,.0f}, "
            f"엔비디아는 {nvi:,.0f}입니다. 실제 주가는 삼양식품 "
            f"{mon['삼양식품'][last]:,.0f}원, 엔비디아 "
            f"{mon['엔비디아'][last]:,.2f}달러입니다.",
            f"삼양식품은 {pk_sy}에 {mon['삼양식품'][pk_sy]:,.0f}원, "
            f"엔비디아는 {pk_nv}에 {mon['엔비디아'][pk_nv]:,.2f}달러로 "
            "각각 가장 높았습니다.",
            "통화가 달라 둘을 같은 축에 원래 액수로 올릴 수 없습니다. "
            "전에는 축을 둘로 나눠 왼쪽에 원, 오른쪽에 달러를 두었는데, "
            "그러면 두 곡선이 어디서 만나고 갈라지는지가 축 배율을 어떻게 "
            "잡느냐에 달라집니다. 기준달을 100으로 맞추면 그 문제가 "
            "사라집니다.",
            f"기준달이 곧 결론입니다. {BASE} 기준으로는 엔비디아가 크게 "
            "앞서지만 2024년 1월을 기준으로 잡으면 삼양식품이 앞섭니다. "
            "「삼양식품과 엔비디아 주가, AI 열풍 이후」를 함께 보십시오.",
            "환율은 반영하지 않았습니다. 원화 투자자가 엔비디아를 샀을 때의 "
            "수익률은 이 선보다 환율 변동만큼 다릅니다.",
            "전에는 마지막 점이 아직 끝나지 않은 달의 월중값이었습니다. "
            "진행 중인 달은 빼도록 고쳤습니다.",
        ],
        "updated": ymd,
    }

    # ── 일별 장(AI 열풍 이후)
    dd = {nm: daily(sym, "2022-12-01") for nm, sym, _u, _c in SPECS}
    both = [d for d in sorted(set(dd["삼양식품"]) & set(dd["엔비디아"]))
            if d >= DBASE]
    if not both:
        print("  검산 실패: 두 종목이 함께 거래된 날이 없다")
        return 1
    b0 = both[0]
    axis = sorted({d for nm in dd for d in dd[nm] if d >= b0})
    filled, dser = {}, []
    for nm, _s, _u, _c in SPECS:
        src, cur_v, vals, nf = dd[nm], None, [], 0
        for d in axis:
            if d in src:
                cur_v = src[d]
            else:
                nf += 1
            vals.append(cur_v)
        if vals[0] is None:
            print(f"  검산 실패: {nm} 의 {b0} 값이 없다")
            return 1
        filled[nm] = nf
        dser.append([round(v / vals[0] * 100, 1) for v in vals])
    if any(x[0] != 100.0 for x in dser):
        print("  검산 실패: 기준일 값이 100 이 아니다")
        return 1
    print(f"    검산 일별: {len(axis)}일, 기준일 {b0} 에 둘 다 100 "
          f"(휴장 메움 삼양 {filled['삼양식품']}일, "
          f"엔비디아 {filled['엔비디아']}일)")

    dlast = axis[-1]
    prev = [d for d in axis if d[:7] < dlast[:7]]
    mtd = {}
    if prev:
        j = axis.index(prev[-1])
        for i, (nm, _s, _u, _c) in enumerate(SPECS):
            mtd[nm] = round((dser[i][-1] / dser[i][j] - 1) * 100, 1)

    def eun(w):
        """받침이 있으면 '은', 없으면 '는'."""
        return "은" if (ord(w[-1]) - 0xAC00) % 28 else "는"

    def mtd_txt():
        if not mtd:
            return "이달 수치는 다음 달 초에 채워집니다."
        out = []
        for nm, _s, _u, _c in SPECS:
            v = mtd[nm]
            out.append(f"{nm}{eun(nm)} {abs(v):,.1f}% "
                       f"{'내렸고' if v < 0 else '올랐고'}")
        txt = " ".join(out)
        return (f"{dlast[:7]} 들어 " + txt).rstrip("고") + "습니다."

    it2 = {
        "slide": "manual-samyang-nvidia-ai",
        "category": "기업과 산업",
        "title": "삼양식품과 엔비디아 주가, AI 열풍 이후",
        "vizType": "line", "unit": f"{b0}=100",
        "labels": list(axis), "series": dser,
        "seriesNames": ["삼양식품", "엔비디아"],
        "seriesColors": [c for _n, _s, _u, c in SPECS],
        "source": (f"야후 파이낸스 일별 종가. {b0}을 100으로 맞췄습니다. "
                   f"{b0}~{dlast}. 삼양식품은 원, 엔비디아는 달러이고 "
                   f"환율은 반영하지 않았습니다. 단위: {b0}=100."),
        "sourceUrl": "https://finance.yahoo.com/quote/003230.KS/",
        "notes": [
            f"{dlast} 기준으로 삼양식품 {dser[0][-1]:,.0f}, 엔비디아 "
            f"{dser[1][-1]:,.0f}입니다. 실제 주가는 삼양식품 "
            f"{dd['삼양식품'][max(dd['삼양식품'])]:,.0f}원, 엔비디아 "
            f"{dd['엔비디아'][max(dd['엔비디아'])]:,.2f}달러입니다.",
            mtd_txt(),
            "두 종목이 각자 폭등하기 직전인 2023년 초를 기준으로 "
            f"잡았습니다. {BASE}을 기준으로 두면 엔비디아가 크게 앞서고 "
            "2024년 1월로 두면 삼양식품이 앞섭니다. 기준을 어디에 두느냐가 "
            "곧 결론입니다.",
            "고점이 찍히는 날짜는 기준을 바꿔도 달라지지 않습니다. 지수는 "
            "전 구간에 같은 수를 곱하는 것이라 순서가 흐트러지지 않습니다. "
            "달라지는 것은 고점의 숫자와 둘 중 어느 쪽이 위에 있는지입니다.",
            f"한국장과 미국장은 쉬는 날이 다릅니다. 한쪽이 쉰 날은 직전 "
            f"종가로 채웠습니다. 채운 날이 삼양식품 {filled['삼양식품']}일, "
            f"엔비디아 {filled['엔비디아']}일입니다.",
            "환율은 반영하지 않았습니다.",
        ],
        "updated": ymd,
    }

    print(f"  c1133 {len(months)}점 {months[0]}~{last} "
          f"(삼양 {syi:,.0f}, 엔비디아 {nvi:,.0f})")
    print(f"  {it2['title'][:30]:32s} {len(axis)}일 {b0}~{dlast} "
          f"(삼양 {dser[0][-1]:,.0f}, 엔비디아 {dser[1][-1]:,.0f})")
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

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    old = idx.get(it2["slide"])
    if old:
        keep = {k: old[k] for k in ("id",) if k in old}
        old.clear()
        old.update(it2)
        old.update(keep)
    else:
        doc["items"].append(it2)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print("-> data/manual.json 에 1장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
