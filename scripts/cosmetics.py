#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""화장품 수출 차트.

KOSIS 145(식품의약품안전처)
  DT_145011_A006 화장품 수입 및 수출액 현황   1995~, 연간, 천 달러
  DT_145011_A008 화장품 수출액 상위 10개국     2016~, 연간, 천 달러

호출 규칙이 까다롭다. 두 표 모두 분류축 메타(getMeta type=OBJ)가 비어
있는데도 objL1 을 요구한다. A006 은 가상분류 코드 DATA 를, A008 은
순위 코드 A01~A10 을 objL1 으로 넣어야 한다. itmId 쪽이 수입액(T001),
수출액(T002)이다. 이걸 뒤집으면 전부 err 21 이 난다.

기준 주의 — 식약처 수출액은 화장품 책임판매업체가 보고한 실적이다.
관세청 수출입무역통계(HS 코드 기준)와 집계 방식이 달라 숫자가 다르다.
팩트북의 라면 수출 차트는 관세청 기준이므로 섞어 읽으면 안 된다.
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

ORG = "145"
SRC = "식품의약품안전처 화장품 생산수입수출 실적(KOSIS 145/DT_145011_A006, A008)"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=145&tblId=DT_145011_A006"

# 10년 내내 상위 10위 안에 든 나라만 쓴다. 중간에 빠지면 선이 끊긴다.
PICK = [("미국", "#2a5ca8"), ("중국", "#e8820c"), ("일본", "#c0322f"),
        ("홍콩", "#9a9a9a"), ("베트남", "#4a7c59")]
EOK = 100000.0   # 천 달러 -> 억 달러


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


def pull(key, tbl, itm, obj, tries=3):
    p = {"method": "getList", "apiKey": key, "itmId": itm, "objL1": obj,
         "format": "json", "jsonVD": "Y", "prdSe": "Y",
         "startPrdDe": "1990", "endPrdDe": "2030", "orgId": ORG, "tblId": tbl}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=45))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}: {d.get('errMsg')}")
            return d
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"받지 못했다({tbl}): {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # ── 1 수출입액 추이
    raw = pull(key, "DT_145011_A006", "T001+T002", "DATA")
    tot = {}
    for r in raw:
        if r.get("DT") in (None, "", "-"):
            continue
        tot.setdefault(r["PRD_DE"], {})[r["ITM_NM"]] = float(r["DT"])
    ys = sorted(y for y in tot if {"수입액", "수출액"} <= set(tot[y]))
    if len(ys) < 20:
        print(f"  검산 실패: 해가 {len(ys)}개뿐이다")
        return 1
    exp = [round(tot[y]["수출액"] / EOK, 1) for y in ys]
    imp = [round(tot[y]["수입액"] / EOK, 1) for y in ys]

    cross = [y for i, y in enumerate(ys) if exp[i] > imp[i]]
    if not cross:
        print("  검산 실패: 수출이 수입을 넘은 해가 없다")
        return 1
    first = cross[0]
    if ys.index(first) == 0 or any(y < first for y in cross):
        print(f"  검산 실패: 역전 해({first})보다 앞에 역전이 또 있다")
        return 1
    print(f"    검산 역전: {first}년에 수출이 수입을 처음 넘었고 그 전은 없음")
    if exp != sorted(exp)[:0] + exp:   # 형식만, 아래에서 실질 검사
        pass
    if exp[-1] <= 0 or imp[-1] <= 0:
        print("  검산 실패: 마지막 해 값이 0 이하")
        return 1

    trend = {
        "slide": "manual-cosmetics-trade",
        "category": "기업과 산업",
        "title": "화장품 수출과 수입",
        "vizType": "line", "unit": "억 달러",
        "labels": ys,
        "series": [exp, imp],
        "seriesNames": ["수출", "수입"],
        "seriesColors": ["#2a5ca8", "#9a9a9a"],
        "source": (f"{SRC}. {ys[0]}~{ys[-1]}년. 단위: 억 달러."),
        "sourceUrl": URL,
        "notes": [
            f"{ys[-1]}년 수출 {exp[-1]}억 달러, 수입 {imp[-1]}억 달러입니다. "
            f"수출이 수입의 {round(exp[-1]/imp[-1],1)}배입니다.",
            f"{first}년에 수출이 수입을 처음 넘어섰습니다. {ys[0]}년에는 "
            f"수출 {exp[0]}억 달러, 수입 {imp[0]}억 달러로 수입이 "
            f"{round(imp[0]/exp[0],1)}배였습니다.",
            "수입은 20년 가까이 10억 달러 안팎에서 거의 늘지 않았습니다. "
            "벌어진 격차는 수입이 줄어서가 아니라 수출이 늘어서입니다.",
            "식품의약품안전처 실적입니다. 화장품 책임판매업체가 보고한 "
            "수치라 관세청 수출입무역통계와 집계 방식이 다릅니다. 두 기준의 "
            "숫자를 섞어 읽으면 안 됩니다.",
        ],
        "updated": ymd,
    }

    # ── 2 주요국 수출액
    raw2 = pull(key, "DT_145011_A008", "T001+T002",
                "+".join(f"A{i:02d}" for i in range(1, 11)))
    tbl = {}
    for r in raw2:
        if r.get("DT") in (None, "", "-"):
            continue
        tbl.setdefault(r["PRD_DE"], {}).setdefault(r["C1_NM"], {})[r["ITM_NM"]] = r["DT"]
    ys2 = sorted(tbl)

    # 검산 ① 순위가 금액 순서와 맞는가 ② 상위10 합이 전체 수출액을 넘지 않는가
    for y in ys2:
        vals = []
        for i in range(1, 11):
            cell = tbl[y].get(f"{i}위")
            if cell and cell.get("수출액"):
                vals.append(float(cell["수출액"]))
        if vals != sorted(vals, reverse=True):
            print(f"  검산 실패 {y}년: 순위와 금액 순서가 어긋난다")
            return 1
        if y in tot and sum(vals) > tot[y]["수출액"] * 1.001:
            print(f"  검산 실패 {y}년: 상위10 합 {sum(vals):.0f} 이 "
                  f"전체 {tot[y]['수출액']:.0f} 보다 크다")
            return 1
    print(f"    검산 순위: {len(ys2)}개 해 모두 순위와 금액이 맞고 "
          "상위10 합이 전체 이하")

    by = {nm: [] for nm, _ in PICK}
    for y in ys2:
        found = {}
        for i in range(1, 11):
            cell = tbl[y].get(f"{i}위") or {}
            nm = (cell.get("국가명") or "").replace(" ", "")
            if cell.get("수출액"):
                found[nm] = round(float(cell["수출액"]) / EOK, 2)
        for nm, _ in PICK:
            by[nm].append(found.get(nm.replace(" ", "")))
    miss = [nm for nm in by if any(v is None for v in by[nm])]
    if miss:
        print(f"  검산 실패: {', '.join(miss)} 가 빠진 해가 있다")
        return 1
    print(f"    검산 계열: {len(PICK)}개 나라 모두 {len(ys2)}개 해가 다 있음")

    last = {nm: by[nm][-1] for nm, _ in PICK}
    top = max(last, key=last.get)
    prev = {nm: by[nm][-2] for nm, _ in PICK}
    ptop = max(prev, key=prev.get)

    byc = {
        "slide": "manual-cosmetics-dest",
        "category": "기업과 산업",
        "title": "주요국 화장품 수출액",
        "vizType": "line", "unit": "억 달러",
        "labels": ys2,
        "series": [by[nm] for nm, _ in PICK],
        "seriesNames": [nm for nm, _ in PICK],
        "seriesColors": [c for _, c in PICK],
        "source": (f"{SRC}. {ys2[0]}~{ys2[-1]}년. 수출액 상위 10개국 표에서 "
                   "뽑았습니다. 단위: 억 달러."),
        "sourceUrl": URL,
        "notes": [
            (f"{ys2[-1]}년에는 {top}이 {last[top]}억 달러로 가장 큽니다. "
             f"{ys2[-2]}년 1위는 {ptop}이었습니다."
             if top != ptop else
             f"{ys2[-1]}년에도 {top}이 {last[top]}억 달러로 가장 큽니다."),
            f"중국은 {ys2[-2]}년 {prev['중국']}억 달러에서 {ys2[-1]}년 "
            f"{last['중국']}억 달러로, 미국은 {prev['미국']}억 달러에서 "
            f"{last['미국']}억 달러로 움직였습니다.",
            "상위 10개국 표에서 뽑은 값이라, 10위 밖으로 밀린 해가 있는 "
            "나라는 넣지 않았습니다. 열 해 내내 10위 안에 든 나라만 "
            "골랐습니다.",
            "식품의약품안전처 실적입니다. 관세청 수출입무역통계와 집계 "
            "방식이 달라 숫자가 다릅니다.",
        ],
        "updated": ymd,
    }

    out = [trend, byc]
    for it in out:
        print(f"  {it['title']:16s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]} 계열 {len(it['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
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
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
