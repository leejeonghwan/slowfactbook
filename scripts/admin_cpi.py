#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역대 정부 임기 중 누적 물가 상승률(c1977)을 한국은행 소비자물가지수로 다시 그린다.

정부마다 취임한 달의 지수를 0으로 두고 달마다 누적 상승률을 쌓는다.
가로축은 날짜가 아니라 '취임 뒤 몇 번째 달'이라서 ecos_update.py 의
라벨 맞추기로는 안 되고, 그래서 따로 둔다.

퇴임한 달은 넣지 않는다. 그 달은 두 정부가 나눠 쓰기 때문이다.
임기 중인 정부는 가장 최근 달까지 이어 그린다.

  ECOS_API_KEY=... python3 scripts/admin_cpi.py            미리보기
  ECOS_API_KEY=... python3 scripts/admin_cpi.py --apply
"""
import argparse, datetime, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

KST = datetime.timezone(datetime.timedelta(hours=9))
KEY = os.environ.get("ECOS_API_KEY", "")
CID = "c1977"

# (이름, 취임월, 퇴임월). 퇴임월은 그래프에 넣지 않는다. None 은 임기 중.
#   이명박 2008-02-25 ~ 2013-02-24
#   박근혜 2013-02-25 ~ 2017-03-10 (탄핵)
#   문재인 2017-05-10 ~ 2022-05-09
#   윤석열 2022-05-10 ~ 2025-04-04 (파면)
#   이재명 2025-06-04 ~
TERMS = [("이명박", "200802", "201302"),
         ("박근혜", "201302", "201703"),
         ("문재인", "201705", "202205"),
         ("윤석열", "202205", "202504"),
         ("이재명", "202506", None)]

SOURCE = ("한국은행 ECOS 소비자물가지수 총지수(2020=100)로 슬로우뉴스가 계산. "
          "각 정부 취임한 달을 0으로 두고 퇴임한 달 직전까지 누적 상승률. 단위: %.")


def cpi():
    u = ("https://ecos.bok.or.kr/api/StatisticSearch/" + KEY +
         "/json/kr/1/100000/901Y009/M/200501/"
         + str(datetime.datetime.now(KST).year + 1) + "12/0")
    with urllib.request.urlopen(u, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "RESULT" in d:
        raise RuntimeError(d["RESULT"].get("MESSAGE", "")[:80])
    out = {}
    for row in d.get("StatisticSearch", {}).get("row", []):
        v = row.get("DATA_VALUE")
        if v not in (None, "", "."):
            out[str(row["TIME"])] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not KEY:
        print("ECOS_API_KEY 가 없습니다."); return 1

    m = cpi()
    ks = sorted(m)
    print(f"소비자물가지수 {ks[0]} ~ {ks[-1]} ({len(ks)}개월)\n")

    names, cols = [], []
    for nm, start, end in TERMS:
        if start not in m:
            print(f"  ! {nm}: {start} 지수가 없습니다"); continue
        i0 = ks.index(start)
        i1 = (ks.index(end) - 1) if (end and end in m) else len(ks) - 1
        base = m[start]
        cols.append([round(100 * (m[ks[i]] / base - 1), 2)
                     for i in range(i0, i1 + 1)])
        names.append(nm)
        print(f"  {nm:4s} {start} ~ {ks[i1]}  {len(cols[-1]):2d}개월  "
              f"누적 {cols[-1][-1]:+.2f}%")

    n = max(len(c) for c in cols)
    series = [c + [None] * (n - len(c)) for c in cols]
    labels = [""] * n
    for y in range(5):
        if y * 12 < n:
            labels[y * 12] = f"{y + 1}년차"
    if n >= 60:
        labels[59] = "퇴임"

    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)"); return 0

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    o = ov.setdefault(CID, {})
    o["id"] = CID
    o["title"] = "역대 정부 누적 물가 상승률"
    o["labels"] = labels
    o["series"] = series
    o["seriesNames"] = names
    o["unit"] = "%"
    o["source"] = SOURCE
    o["sourceUrl"] = "https://ecos.bok.or.kr/"
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n-> data/overrides.json 의 {CID} 반영.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
