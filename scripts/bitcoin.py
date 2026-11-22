#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비트코인 주간 가격(c1112).

옛 c1112 는 789점짜리 주간 계열인데 **라벨이 789개 중 16개만 차 있고
나머지는 빈 문자열**이었다. 해가 바뀌는 자리에만 연도를 찍고 나머지는
비워 둔 키노트식 축이다. 어느 점이 언제인지 데이터만으로는 알 수 없어
이어 붙일 수가 없었고, 2026년 2월에서 멈춰 있었다. 출처 문구도 비어
있었다.

날짜를 되살리려다 실패한 기록.
  옛 계열의 최댓값 124,752.1397 이 야후 BTC-USD 의 최고가 주
  2025-10-06 의 124,752.53 과 사실상 같아서, 그 점(770번째)을 닻으로
  삼고 한 주씩 세어 전체 날짜를 역산해 봤다. 0번째가 2011-01-03 에
  떨어지고 연도 표시 16자리도 모두 그해 첫 주에 맞아 그럴듯했다.
  그런데 겹치는 595주를 야후와 대조하니 47주만 맞았다. 2017-12-04
  자리의 11,685.7 은 야후에서 그 **다음 주** 값이다. 주 간격이 전
  구간에서 일정하지 않아 닻에서 멀어질수록 한 주씩 밀린다.
  그래서 역산한 날짜는 버렸다. 맞아 보이는 닻 하나로 전체를 되살릴
  수는 없다.

대신 야후 BTC-USD 로 통째로 다시 세운다. 날짜가 정확하고 해마다
저절로 따라간다. 대가는 2011년부터 2014년 9월까지가 빠지는 것이다.
야후에 그 구간이 없고, 옛 값의 날짜를 믿을 수 없어 가져올 수 없다.
옛 값 자체는 맞았다(2011년 1월 0.30달러, 2017년 1,022달러 등).
2014년 9월 이전이 필요하면 날짜가 붙은 다른 출처를 따로 구해야 한다.

주는 월요일에 시작하고, 그 주 월요일의 종가를 쓴다. 옛 계열도 그
방식이었다. 비트코인은 주말에도 거래되므로 한 주는 7일이고, 7일이
다 차지 않은 주는 뺀다.
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

SYM = "BTC-USD"
ANCHOR_IDX = 770
ANCHOR_WEEK = datetime.date(2025, 10, 6)
ANCHOR_VAL = 124752.1397          # 옛 계열의 최댓값
FIRST_WEEK = datetime.date(2011, 1, 3)
SITE = "https://finance.yahoo.com/quote/BTC-USD/"


def ep(d):
    return int(datetime.datetime.combine(d, datetime.time())
               .replace(tzinfo=datetime.timezone.utc).timestamp())


def weekly(tries=4):
    """월요일 시작 주의 마지막 종가. 7일이 안 찬 주는 뺀다."""
    last = None
    for i in range(tries):
        host = "query1" if i % 2 == 0 else "query2"
        u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{SYM}"
             f"?period1={ep(datetime.date(2014, 1, 1))}"
             f"&period2={int(time.time())}&interval=1d")
        try:
            req = urllib.request.Request(u, headers={"User-Agent":
                                                     "Mozilla/5.0"})
            res = json.load(urllib.request.urlopen(req, timeout=60))
            res = res["chart"]["result"][0]
            ts = res["timestamp"]
            cl = res["indicators"]["quote"][0]["close"]
            day = {}
            for t, c in zip(ts, cl):
                if c is None:
                    continue
                day[datetime.datetime.fromtimestamp(
                    t, datetime.timezone.utc).date()] = round(float(c), 4)
            # 그 주 '월요일'의 종가를 쓴다. 옛 계열도 그 방식이었다
            # (2025-10-06 월요일 종가 124,752 가 옛 차트의 최댓값).
            # 주의 마지막 종가를 쓰면 최고가 주가 한 주 앞으로 밀린다.
            wk, cnt = {}, {}
            for dte in sorted(day):
                mon = dte - datetime.timedelta(days=dte.weekday())
                if mon not in wk:
                    wk[mon] = day[dte]
                cnt[mon] = cnt.get(mon, 0) + 1
            full = {k: v for k, v in wk.items() if cnt[k] >= 7}
            if full:
                return full, len(wk) - len(full)
        except Exception as e:                       # noqa: BLE001
            last = e
        time.sleep(2 + 2 * i)
    raise RuntimeError(f"{SYM} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    wk, dropped = weekly()
    ks = sorted(wk)
    if len(ks) < 400:
        print(f"  검산 실패: {len(ks)}주뿐이다")
        return 1
    print(f"    받음: {len(ks)}주 {ks[0]}~{ks[-1]}"
          + (f" (7일 안 찬 주 {dropped}개 뺌)" if dropped else ""))

    # 검산 1. 최고가 주가 알려진 자리에 있는가
    pk0 = max(ks, key=lambda d: wk[d])
    if pk0 != ANCHOR_WEEK or abs(wk[pk0] - 124752.53) > 1:
        print(f"  검산 실패: 최고가가 {pk0} {wk[pk0]:,.2f} 다 "
              f"({ANCHOR_WEEK} 124,752.53 이어야 한다)")
        return 1
    print(f"    검산 최고: {pk0} {wk[pk0]:,.2f}달러")

    # 검산 2. 한 주에 60% 넘게 튀지 않는가
    jump = [(str(ks[i]), round(wk[ks[i]] / wk[ks[i-1]] - 1, 3))
            for i in range(1, len(ks))
            if abs(wk[ks[i]] / wk[ks[i-1]] - 1) > 0.6]
    if jump:
        print(f"  검산 실패: 한 주에 60% 넘게 튄 자리 {jump[:3]}")
        return 1
    print(f"    검산 연속: {len(ks)}주 모두 전주 대비 60% 안")

    # 검산 3. 모든 날짜가 월요일인가
    bad = [str(d) for d in ks if d.weekday() != 0]
    if bad:
        print(f"  검산 요일: 월요일이 아닌 주 {bad[:3]}")
        return 1
    print("    검산 요일: 모든 주가 월요일 시작")

    dates = ks
    labels = [d.isoformat() for d in dates]
    vals = [round(wk[d], 2) for d in dates]
    merged = {d: round(wk[d], 2) for d in dates}

    last, first = dates[-1], dates[0]
    pk = max(dates, key=lambda d: merged[d])
    it = {
        "id": "c1112", "category": "기업과 산업",
        "title": "비트코인 가격.",
        "vizType": "line", "unit": "달러",
        "labels": labels, "series": [vals],
        "seriesNames": ["비트코인"], "hideLegend": True,
        "source": (f"야후 파이낸스 BTC-USD 주간 종가. 각 주 월요일의 "
                   f"종가, {first}~{last}. 단위: 달러."),
        "sourceUrl": SITE,
        "notes": [
            f"{last} 주 {merged[last]:,.0f}달러입니다. 가장 높았던 주는 "
            f"{pk}로 {merged[pk]:,.0f}달러였고, 거기서 "
            f"{(1-merged[last]/merged[pk])*100:.0f}% 내렸습니다.",
            f"{first} 주에는 {merged[first]:,.0f}달러였습니다.",
            "전에는 라벨이 789칸 중 16칸만 차 있었습니다. 해가 바뀌는 "
            "자리에만 연도를 찍은 축이라 어느 점이 언제인지 알 수 없었고 "
            "2026년 2월에서 멈춰 있었습니다. 야후 자료로 통째로 다시 "
            "세웠습니다.",
            "그 과정에서 2011년부터 2014년 9월까지가 빠졌습니다. 야후에 "
            "그 구간이 없습니다. 옛 계열에는 있었지만(2011년 1월 0.30달러, "
            "2013년 13.55달러로 실제 가격과 맞습니다) 각 점의 날짜를 "
            "되살리려다 실패했습니다. 최고가 주를 닻으로 역산해 보니 "
            "겹치는 595주 중 47주만 맞았고, 닻에서 멀어질수록 한 주씩 "
            "밀렸습니다. 날짜를 믿을 수 없는 값은 가져오지 않았습니다.",
            "각 주 월요일의 종가입니다. 옛 계열도 그 방식이었습니다. "
            "비트코인은 주말에도 거래되므로 7일이 다 차지 않은 주는 "
            "뺍니다.",
        ],
        "updated": ymd,
    }

    print(f"  c1112 {len(labels)}점 {first}~{last} 끝값 "
          f"{merged[last]:,.0f}달러")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    o.setdefault("c1112", {}).update(it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c1112 를 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
