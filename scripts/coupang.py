#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿠팡 분기별 매출(c1122)과 영업이익(c1123)을 SEC 공시에서 받는다.

  python3 scripts/coupang.py            # 미리보기
  python3 scripts/coupang.py --apply

쿠팡(Coupang, Inc.)은 뉴욕증권거래소 상장사여서 분기마다 10-Q 를 낸다.
SEC XBRL(CIK 1834584)에서 바로 받으면 기사마다 다른 환율과 증가율 기준에
휘둘리지 않는다. 달러 원값을 그대로 쓴다.

4분기는 공시에 따로 나오지 않는다. 연간 수치에서 9개월 누계를 빼서 만든다.

대조해서 어긋나면 그 차트는 손대지 않고 어디가 어긋났는지 적는다. 다만
--force-fix 를 주면 SEC 값으로 덮는다. 손으로 넣다가 틀린 값이 들어간 적이
있어서(2025년 영업이익) 덮어쓸 길을 따로 뒀다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CIK = "0001834584"
UA = "slowfactbook research (top@leejeonghwan.com)"
SRC = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001834584&type=10-Q"
CHARTS = {
    "c1122": ("RevenueFromContractWithCustomerExcludingAssessedTax", "매출",
              "쿠팡 분기별 매출"),
    "c1123": ("OperatingIncomeLoss", "영업이익", "쿠팡 분기별 영업이익"),
}


def mo(a, b):
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def quarters(tag):
    u = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{CIK}/us-gaap/{tag}.json"
    r = subprocess.run(["curl", "-sS", "--max-time", "90", "-A", UA, u],
                       capture_output=True, text=True)
    rows = json.loads(r.stdout)["units"]["USD"]
    q, cum = {}, {}
    for x in rows:
        n = mo(x["start"], x["end"])
        tgt = q if n in (2, 3) else (cum if n in (5, 6, 8, 9, 11, 12) else None)
        if tgt is None:
            continue
        k = (x["start"][:7], x["end"][:7])
        # 같은 구간이 여러 번 공시된다. 가장 나중에 낸 것을 쓴다(수정 반영).
        if k not in tgt or x.get("filed", "") > tgt[k].get("filed", ""):
            tgt[k] = x
    out = {}
    for (s, e), v in q.items():
        y, m = int(e[:4]), int(e[5:7])
        out[f"{y}-Q{(m - 1) // 3 + 1}"] = round(v["val"] / 1e6)
    # 4분기는 연간에서 9개월 누계를 뺀다.
    for (s, e), v in cum.items():
        if mo(s, e) < 11:
            continue
        y = e[:4]
        nine = [w for (s2, e2), w in cum.items() if e2[:4] == y and 8 <= mo(s2, e2) <= 9]
        if nine:
            out[f"{y}-Q4"] = round((v["val"] - nine[0]["val"]) / 1e6)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force-fix", action="store_true",
                    help="겹치는 구간이 어긋나도 SEC 값으로 덮는다")
    a = ap.parse_args()

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    full = {i["id"]: i for i in
            json.load(open(os.path.join(DATA, "full.json"), encoding="utf-8"))["items"]
            if i.get("id")}
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    wrote = 0

    for cid, (tag, nm, title) in CHARTS.items():
        got = quarters(tag)
        ks = sorted(got)
        cur = {**full.get(cid, {}), **(ov.get(cid) or {})}
        old = dict(zip([str(x) for x in (cur.get("labels") or [])],
                       (cur.get("series") or [[]])[0]))
        bad = [(k, old[k], got[k]) for k in ks
               if old.get(k) is not None and round(old[k]) != got[k]]
        add = [k for k in ks if k not in old]
        print(f"== {cid} {title} — SEC {len(ks)}분기 {ks[0]} ~ {ks[-1]}")
        if bad:
            print(f"   어긋남 {len(bad)}곳:")
            for k, o, n in bad:
                print(f"     {k}: 차트 {o} / SEC {n}")
            if not a.force_fix:
                print("   --force-fix 가 없어 손대지 않습니다.")
                continue
            print("   --force-fix — SEC 값으로 덮습니다.")
        if add:
            print(f"   새로 붙는 분기: {add}")
        if not bad and not add:
            print("   이미 최신")
            continue
        print(f"   최근: " + ", ".join(f"{k} {got[k]:,}" for k in ks[-3:]))
        if not a.apply:
            continue
        o = ov.setdefault(cid, {})
        o["id"] = cid
        o["title"] = title
        o["labels"] = ks
        o["series"] = [[got[k] for k in ks]]
        o["seriesNames"] = [nm]
        o["unit"] = "100만 달러"
        o["source"] = ("쿠팡(Coupang, Inc.) SEC 10-Q 와 10-K. 달러 원값이고 "
                       "환율로 바꾸지 않았다. 4분기는 연간에서 9개월 누계를 뺀 값. "
                       "단위: 100만 달러.")
        o["sourceUrl"] = SRC
        # 0 을 넘나드는 지표만 부호로 색을 가른다. 매출은 늘 양수라 뜻이 없다.
        if cid == "c1123":
            o["signColors"] = {"plus": "#2a5ca8", "minus": "#c0322f"}
        o["notes"] = [
            "쿠팡은 뉴욕증권거래소 상장사여서 분기마다 미국 증권거래위원회(SEC)에 "
            "10-Q 를 냅니다. 그 공시에서 바로 받은 값입니다.",
            "달러 원값입니다. 원화로 바꾸지 않았습니다. 기사마다 적용한 환율이 "
            "달라 원화 환산액이 제각각이고, 환율이 움직인 분기는 원화로 보면 "
            "실적과 다른 방향으로 보이기도 합니다.",
            "증가율도 기준이 둘입니다. 달러 기준과 환율 변동을 뺀 고정환율 기준이 "
            "다릅니다. 2026년 3분기 매출은 달러 기준으로 7.5% 늘었지만 "
            "고정환율 기준으로는 11%로 발표됐습니다. 이 차트는 달러 기준입니다.",
            "4분기 값은 공시에 따로 나오지 않습니다. 연간 수치에서 9개월 누계를 "
            "빼서 만들었습니다.",
            "0을 넘나드는 지표라 오른 분기는 파랑, 내린 분기는 빨강으로 "
            "색을 갈랐습니다.",
        ] if cid == "c1123" else [
            "쿠팡은 뉴욕증권거래소 상장사여서 분기마다 미국 증권거래위원회(SEC)에 "
            "10-Q 를 냅니다. 그 공시에서 바로 받은 값입니다.",
            "달러 원값입니다. 원화로 바꾸지 않았습니다. 기사마다 적용한 환율이 "
            "달라 원화 환산액이 제각각입니다.",
            "증가율은 기준이 둘입니다. 2026년 3분기는 달러 기준 7.5%, "
            "고정환율 기준 11%로 발표됐습니다. 이 차트는 달러 기준이라 "
            "앞의 숫자에 해당합니다.",
            "4분기 값은 공시에 따로 나오지 않습니다. 연간 수치에서 9개월 누계를 "
            "빼서 만들었습니다.",
        ]
        o["updated"] = stamp
        wrote += 1

    if a.apply and wrote:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"\n-> data/overrides.json 에 {wrote}건 반영했습니다.")
    elif not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
