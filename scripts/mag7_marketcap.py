#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매그니피센트 7 분기별 시가총액.

  python3 scripts/mag7_marketcap.py            # 미리보기
  python3 scripts/mag7_marketcap.py --apply

시가총액 시계열을 그대로 주는 공개 소스가 없어서 두 곳을 곱한다.

  발행주식수  미국 증권거래위원회(SEC) XBRL companyfacts. 분기마다 보고된다.
  주가        야후 파이낸스 월말 종가.

주의할 점이 둘 있다.

1. 야후 주가는 액면분할을 소급 반영한 값인데 SEC 주식수는 보고 당시 값이다.
   그대로 곱하면 분할 이전 구간이 통째로 틀린다(엔비디아는 2021년 4대 1,
   2024년 10대 1을 했다). 그래서 각 분기 이후에 일어난 분할의 배수를 주식수에
   곱해 같은 기준으로 맞춘다.
2. 주식수 태그가 회사마다 다르다. 알파벳과 메타는 주식이 두 종류라
   dei 태그에 값이 없다. 아래 순서로 찾아 가장 오래 이어지는 것을 쓴다.
   보통주발행주식수가 없으면 가중평균주식수를 쓰는데, 자사주를 많이 사들인
   회사는 기말보다 조금 작게 잡힌다.

알파벳은 2015년 지주사 전환 전 구글 법인(CIK 1288776)까지 이어 붙인다.
"""
import argparse, collections, datetime, gzip, json, os, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
SLIDE = "manual-mag7-marketcap"
KST = datetime.timezone(datetime.timedelta(hours=9))

SEC_H = {"User-Agent": "slowfactbook research top@leejeonghwan.com",
         "Accept-Encoding": "gzip"}
YH_H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# 이름, 야후 심볼, SEC CIK 목록(옛 법인부터)
FIRMS = [
    ("애플", "AAPL", [320193]),
    ("마이크로소프트", "MSFT", [789019]),
    ("알파벳", "GOOGL", [1288776, 1652044]),
    ("아마존", "AMZN", [1018724]),
    ("엔비디아", "NVDA", [1045810]),
    ("메타", "META", [1326801]),
    ("테슬라", "TSLA", [1318605]),
]
CHAIN = [("us-gaap", "CommonStockSharesOutstanding"),
         ("dei", "EntityCommonStockSharesOutstanding"),
         ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic")]


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    return body


CACHE = os.path.join(ROOT, ".cache", "sec")
CACHE_DAYS = 7


def _facts(cik):
    """companyfacts 는 회사당 10MB 안팎이라 이레 동안 받아 둔 것을 쓴다."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "CIK%010d.json" % cik)
    fresh = (os.path.exists(path)
             and time.time() - os.path.getmtime(path) < CACHE_DAYS * 86400)
    if not fresh:
        body = _get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % cik, SEC_H)
        open(path, "wb").write(body)
    return json.load(open(path, encoding="utf-8"))


def shares(ciks):
    """{분기말: 주식수} — 가장 많은 분기를 담은 태그를 고른다."""
    best = (None, {})
    for ns, tag in CHAIN:
        m = {}
        for cik in ciks:
            try:
                doc = _facts(cik)
            except Exception:
                continue
            rows = doc.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {}).get("shares")
            for r in rows or []:
                # 같은 분기가 여러 보고서에 나온다. 가장 늦게 제출된 보고서의 값을
                # 쓰고, 그 제출일을 함께 들고 있는다 — 액면분할을 소급해야 하는지
                # 가리는 데 쓴다. 회사는 분할 뒤에 내는 보고서에서 과거 분기
                # 주식수를 분할 기준으로 다시 적는다. 제출일만 보면 그 값이
                # 이미 분할을 반영한 것인지 아닌지 알 수 있다.
                # 같은 보고서 안에 종류별로 쪼갠 줄이 있으면 합계 줄이 가장 크다.
                filed = r.get("filed", "")
                cur = m.get(r["end"])
                if cur is None or filed > cur[1] or (filed == cur[1] and r["val"] > cur[0]):
                    m[r["end"]] = (r["val"], filed)
        if len(m) > len(best[1]):
            best = (tag, dict(m))
    return best


def splits(sym):
    doc = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/"
                          "%s?interval=1d&range=40y&events=split" % sym, YH_H))
    ev = doc["chart"]["result"][0].get("events", {}).get("splits", {}) or {}
    return sorted((time.strftime("%Y-%m-%d", time.gmtime(int(k))),
                   v["numerator"] / v["denominator"]) for k, v in ev.items())


def prices(sym):
    now = int(time.time())
    doc = json.loads(_get("https://query1.finance.yahoo.com/v8/finance/chart/"
                          "%s?interval=1mo&period1=0&period2=%d" % (sym, now + 86400), YH_H))
    r = doc["chart"]["result"][0]
    cl = r["indicators"]["quote"][0]["close"]
    return {time.strftime("%Y-%m", time.gmtime(t)): c
            for t, c in zip(r["timestamp"], cl) if c}


def caps():
    out, tags = {}, {}
    for name, sym, ciks in FIRMS:
        tag, sh = shares(ciks)
        if not sh:
            raise SystemExit("%s 주식수를 받지 못했습니다." % name)
        sp, px = splits(sym), prices(sym)
        m = {}
        for end, (n, filed) in sh.items():
            f = 1.0
            # 보고서가 나온 뒤에 일어난 분할만 소급한다. 보고서보다 앞선 분할은
            # 그 보고서의 주식수에 이미 반영돼 있다. 여기를 '분기말 뒤'로 잡으면
            # 분할을 두 번 곱하게 된다(애플 2018년이 네 배로 부풀었다).
            for dt, ratio in sp:
                if dt > (filed or end):
                    f *= ratio
            p = px.get(end[:7])
            if p:
                m[end] = round(n * f * p / 1e12, 3)
        out[name], tags[name] = m, tag
    return out, tags


def quarters(all_caps):
    """세로축에 세울 분기. 한 회사라도 값이 있는 분기를 모은다."""
    ends = sorted({e for m in all_caps.values() for e in m})
    seen = {}
    for e in ends:                        # 회사마다 결산일이 며칠씩 달라 분기로 묶는다
        q = "%sQ%d" % (e[:4], (int(e[5:7]) - 1) // 3 + 1)
        seen.setdefault(q, []).append(e)
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    all_caps, tags = caps()
    qmap = quarters(all_caps)
    labels = sorted(qmap)
    series = []
    for name, _, _ in FIRMS:
        m = all_caps[name]
        row = []
        for q in labels:
            vals = [m[e] for e in qmap[q] if e in m]
            row.append(vals[-1] if vals else None)
        series.append(row)

    TAGNAME = {"CommonStockSharesOutstanding": "보통주발행주식수",
               "EntityCommonStockSharesOutstanding": "표지 기재 발행주식수",
               "WeightedAverageNumberOfSharesOutstandingBasic": "가중평균주식수"}
    notes = ["회사별 발행주식수 출처와 마지막으로 반영한 분기입니다."]
    for (name, sym, _), row in zip(FIRMS, series):
        got = [(labels[i], v) for i, v in enumerate(row) if v is not None]
        print("  %-8s 분기 %3d개, 최근 %.3f조 달러 (%s)"
              % (name, len(got), got[-1][1], tags[name]))
        notes.append("%s(%s) — %s 기준. %s ~ %s, %d분기. 최근 %.2f조 달러."
                     % (name, sym, TAGNAME.get(tags[name], tags[name]),
                        got[0][0], got[-1][0], len(got), got[-1][1]))
    notes.append("가중평균주식수를 쓴 회사는 분기 평균이라 기말 기준보다 조금 "
                 "작게 잡힙니다. 자사주를 많이 사들인 회사일수록 차이가 큽니다.")
    notes.append("액면분할은 소급 반영했습니다. 야후 주가가 분할을 소급 반영한 "
                 "값이라, 각 분기 뒤에 일어난 분할 배수를 주식수에 곱해 기준을 "
                 "맞췄습니다.")
    print("  가로축 %s ~ %s (%d분기)" % (labels[0], labels[-1], len(labels)))

    item = {
        "slide": SLIDE,
        "title": "매그니피센트 7 시가총액",
        "category": "세계 경제",
        "source": ("미국 증권거래위원회(SEC) XBRL 보고서의 분기별 발행주식수와 "
                   "야후 파이낸스 월말 주가를 곱해 구했다. 액면분할은 소급 반영했다. "
                   "알파벳은 2015년 지주사 전환 전 구글 법인까지 이어 붙였다. "
                   "보통주발행주식수를 보고하지 않는 회사는 가중평균주식수를 썼고, "
                   "그 경우 자사주 매입분만큼 기말 기준보다 조금 작게 잡힌다. "
                   "단위: 조 달러."),
        "sourceUrl": "https://www.sec.gov/edgar/sec-api-documentation",
        "notes": notes,
        "vizType": "line",
        "unit": "조 달러",
        "labels": labels,
        "series": series,
        "seriesNames": [n for n, _, _ in FIRMS],
        "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    if cur:
        if cur.get("id"):
            item["id"] = cur["id"]
        doc["items"][doc["items"].index(cur)] = item
    else:
        doc["items"].append(item)
    if a.apply:
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print("-> data/manual.json 에 반영했습니다.")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
