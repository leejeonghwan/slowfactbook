#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미국 주식 종가 차트 갱신(야후 파이낸스).

manual.json 의 manual-px-<티커>-d(일별), manual-px-<티커>-m(월말) 을 다시 쓴다.

주의 — 장중값이 종가로 들어가는 사고를 막는다.
야후는 요청이 닿는 캐시에 따라 같은 주소로도 장중 스냅샷을 돌려줄 때가 있다.
2026-11-18 에 한쪽은 21:00 UTC 마감값 150.96, 다른 쪽은 15:52 UTC 장중값
152.821 을 줬다. 그래서 meta.regularMarketTime 이 그 날 정규장 마감
시각에 닿았는지 보고, 아니면 마지막 봉을 통째로 버린다.
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

# 티커: (슬라이드 이름 조각, 차트 제목)
NAMES = {
    "AAPL": ("aapl", "애플"),
    "MSFT": ("msft", "마이크로소프트"),
    "GOOGL": ("googl", "알파벳"),
    "AMZN": ("amzn", "아마존"),
    "NVDA": ("nvda", "엔비디아"),
    "META": ("meta", "메타"),
    "TSLA": ("tsla", "테슬라"),
}
DAILY_FROM = "2025-01-02"   # 일별 차트가 시작하는 날
TOL = 0.0005                # 겹치는 구간 허용 오차(0.05%)


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"받지 못했다: {url} ({last})")


def settled(res):
    """정규장 마감 시각에 닿은 응답인가."""
    meta = res.get("meta") or {}
    end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    mt = meta.get("regularMarketTime")
    return not (end and mt and mt < end)


def chart(sym, rng, iv, want_settled=True, tries=6):
    """캐시에 따라 장중 스냅샷이 올 때가 있어 마감된 응답을 찾아 다시 받는다."""
    last = None
    for i in range(tries):
        host = "query1" if i % 2 == 0 else "query2"
        u = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
             f"?range={rng}&interval={iv}")
        res = get(u)["chart"]["result"][0]
        last = res
        if not want_settled or settled(res):
            return res
        time.sleep(2 + 2 * i)
    return last


def closes(res, fmt):
    """(날짜, 종가) 목록. 아직 안 끝난 마지막 봉은 뺀다."""
    ts = res.get("timestamp") or []
    cl = res["indicators"]["quote"][0]["close"]
    rows = []
    for t, c in zip(ts, cl):
        if c is None:
            continue
        d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
        rows.append((d.strftime(fmt), round(float(c), 2)))
    if not rows:
        return rows
    meta = res.get("meta") or {}
    end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    mt = meta.get("regularMarketTime")
    # 마감 시각에 닿지 않은 응답이면 마지막 봉은 장중값이다. 버린다.
    if end and mt and mt < end:
        hhmm = datetime.datetime.fromtimestamp(mt, datetime.timezone.utc)
        print(f"    (장중 응답 {hhmm:%H:%M UTC} — 마지막 봉 {rows[-1][0]} "
              f"{rows[-1][1]} 을 버린다)")
        rows = rows[:-1]
    return rows


def check_overlap(old_l, old_s, new):
    """이미 있던 값과 겹치는 구간이 어긋나면 멈춘다."""
    have = dict(new)
    n = bad = 0
    for lab, v in zip(old_l, old_s):
        if lab not in have or not isinstance(v, (int, float)):
            continue
        n += 1
        if abs(have[lab] - v) > max(abs(v) * TOL, 0.01):
            bad += 1
            if bad <= 5:
                print(f"    어긋남 {lab}: 기존 {v} vs 새로 {have[lab]}")
    return n, bad


def build(sym, a):
    slug, kor = NAMES[sym]
    out = []
    d = chart(sym, "5y", "1d")
    rows = [r for r in closes(d, "%Y-%m-%d") if r[0] >= DAILY_FROM]
    if not rows:
        raise RuntimeError(f"{sym}: 일별 값이 비었다")
    out.append(("d", rows, f"{kor} 주가",
                "야후 파이낸스 종가. 일별 종가, "
                f"{DAILY_FROM[:4]}년 {int(DAILY_FROM[5:7])}월 "
                f"{int(DAILY_FROM[8:])}일부터. 단위: 달러."))
    m = chart(sym, "max", "1mo")
    mrows = closes(m, "%Y-%m")
    # 아직 안 끝난 달은 '월말 종가'가 아니다. 뺀다.
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    if mrows and mrows[-1][0] >= now:
        print(f"    (진행 중인 달 {mrows[-1][0]} 은 월말 종가가 아니라 뺀다)")
        mrows = [r for r in mrows if r[0] < now]
    if not mrows:
        raise RuntimeError(f"{sym}: 월별 값이 비었다")
    out.append(("m", mrows, f"{kor} 주가 (월간)",
                "야후 파이낸스 종가. 월말 종가. 단위: 달러."))
    return slug, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="쉼표로 티커 지정(기본: 전부)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    syms = [s.strip().upper() for s in a.only.split(",") if s.strip()] or list(NAMES)
    bad = [s for s in syms if s not in NAMES]
    if bad:
        print(f"모르는 티커: {', '.join(bad)}")
        return 2

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    pend, fail = [], 0
    for sym in syms:
        print(f"  {sym}")
        try:
            slug, parts = build(sym, a)
        except Exception as e:                      # noqa: BLE001
            print(f"    실패: {e}")
            fail += 1
            continue
        for kind, rows, title, src in parts:
            slide = f"manual-px-{slug}-{kind}"
            old = by.get(slide)
            if old is None:
                print(f"    {slide} 가 manual.json 에 없다 — 건너뛴다")
                fail += 1
                continue
            n, nbad = check_overlap(old.get("labels") or [],
                                    (old.get("series") or [[]])[0], rows)
            if nbad:
                print(f"    검산 실패: 겹친 {n}점 중 {nbad}점 어긋남 — 안 쓴다")
                fail += 1
                continue
            # 통째로 갈아끼우지 않고 병합한다. 야후의 max 범위가 해마다
            # 조금씩 달라져서, 덮어쓰면 예전 점이 소리 없이 사라진다.
            merged = {}
            for lab, v in zip(old.get("labels") or [],
                              (old.get("series") or [[]])[0]):
                if isinstance(v, (int, float)):
                    merged[lab] = round(float(v), 2)
            merged.update(dict(rows))
            rows = sorted(merged.items())
            added = len(rows) - len(old.get("labels") or [])
            print(f"    {title:18s} {len(rows)}점 "
                  f"{rows[0][0]}~{rows[-1][0]} (겹친 {n}점 일치, {added:+d}점, "
                  f"끝값 {rows[-1][1]})")
            pend.append((old, rows, title, src))

    if fail:
        print(f"\n  실패 {fail}건 — 그 차트는 손대지 않았습니다.")
    if not pend:
        return 1 if fail else 0
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    for old, rows, title, src in pend:
        old["labels"] = [r[0] for r in rows]
        old["series"] = [[r[1] for r in rows]]
        old["title"] = title
        old["source"] = src
        old["updated"] = ymd
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(p, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(pend)}장을 반영했습니다.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
