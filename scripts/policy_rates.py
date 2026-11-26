#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국과 미국의 기준금리(c2310).

  python3 scripts/policy_rates.py            # 미리보기
  python3 scripts/policy_rates.py --apply

무엇을 그리는가 — 둘 다 중앙은행이 정하는 정책금리다.
  한국  한국은행 기준금리 (ECOS 722Y001 0101000, 일별에서 월말)
  미국  연방기금금리 목표 (FRED, 일별에서 월말)
          1982-09 ~ 2008-12  DFEDTAR   단일 목표
          2008-12 ~          DFEDTARU  목표 범위의 위쪽 끝

미국 계열을 바꿨다.
  전에는 FEDFUNDS, 곧 실효 연방기금금리의 월평균이었다. 그건 연준이 정한
  숫자가 아니라 시장에서 실제로 거래된 금리를 한 달 평균한 값이라, 금리를
  바꾸지 않은 달에도 조금씩 움직이고 한 달 안에서도 오르내린다. 제목이
  '기준금리'인데 기준금리가 아니었고, 계단으로 그릴 수도 없었다.
  목표금리로 바꾸면 둘 다 중앙은행이 정한 값이라 계단으로 그릴 수 있고
  제목과도 맞는다. 대신 숫자가 달라진다. 2026년 10월이 실효 3.88%,
  목표 위쪽 끝 4.00% 다.

  2008년 12월부터 연준은 하나의 숫자가 아니라 범위를 정한다. 여기서는
  위쪽 끝을 쓴다. 아래쪽 끝은 보통 0.25%포인트 낮다.

월말을 쓰는 이유.
  정책금리는 다음 결정 때까지 유지된다. 달의 평균을 내면 금리를 바꾼
  달에 실제로는 없던 중간값이 생긴다. 그래서 그달 마지막 날의 값을 쓴다.
  한국도 같은 방식으로 일별에서 뽑는다. 그러면 ECOS 월별 표가 아직
  올라오지 않은 이번 달도 바로 들어온다.

겹치는 달을 전수 대조해 어긋나면 손대지 않는다.
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g                            # noqa: E402
import fred_update as fr                             # noqa: E402

CID = "c2310"
CID_EFF = "c1822"                  # 미국 실효 연방기금금리(FEDFUNDS)
SLIDE_TGT = "manual-us-target-rate"  # 미국 목표금리 단독 차트
TITLE_EFF = "미국 실효 연방기금금리"
KST = datetime.timezone(datetime.timedelta(hours=9))
SPLIT = "2008-12"          # 목표 한 값에서 목표 범위로 바뀐 달
# 널리 알려진 목표금리로 거는 빗장
GATE_US = {"2000-05": 6.5, "2007-06": 5.25, "2008-12": 0.25,
           "2018-12": 2.5, "2020-04": 0.25, "2023-08": 5.5}
GATE_KR = {"2008-08": 5.25, "2020-05": 0.5, "2023-02": 3.5}


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


def ecos(key, cyc, s, e):
    u = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/"
         f"20000/722Y001/{cyc}/{s}/{e}/0101000")
    r = json.load(urllib.request.urlopen(u, timeout=150))
    rows = (r.get("StatisticSearch") or {}).get("row")
    if not rows:
        raise RuntimeError(
            f"ECOS: {json.dumps(r, ensure_ascii=False)[:160]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("ECOS_API_KEY")
    if not key:
        print("ECOS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # 한국 — 일별에서 월말
    day = sorted((x["TIME"], float(x["DATA_VALUE"]))
                 for x in ecos(key, "D", "19990101", "20991231"))
    kr = {}
    for t, v in day:
        kr[f"{t[:4]}-{t[4:6]}"] = round(v, 2)
    mon = {f"{x['TIME'][:4]}-{x['TIME'][4:6]}": round(float(x["DATA_VALUE"]), 2)
           for x in ecos(key, "M", "199901", "209912")}
    print(f"    받음: 한국 일별 {len(day)}일 -> {len(kr)}개월 "
          f"{min(kr)}~{max(kr)} (월별 표는 {max(mon)} 까지)")

    # 검산 1. 일별에서 뽑은 월말이 ECOS 월별 표와 같은가
    bad = [(m, kr[m], mon[m]) for m in sorted(set(kr) & set(mon))
           if abs(kr[m] - mon[m]) > 0.001]
    if bad:
        print(f"  검산 실패: 일별 월말이 월별 표와 다르다 {bad[:4]}")
        return 1
    print(f"    검산 한국: 겹치는 {len(set(kr)&set(mon))}개월 모두 "
          "일별 월말 = 월별 표")

    # 미국 — 목표금리, 일별에서 월말
    oldt = fr.bucket(fr.fetch_rows("DFEDTAR"), "month", "last", 0, 2)
    newt = fr.bucket(fr.fetch_rows("DFEDTARU"), "month", "last", 0, 2)
    us = {m: v for m, v in oldt.items() if m < SPLIT}
    us.update(newt)
    print(f"    받음: 미국 목표금리 {len(us)}개월 {min(us)}~{max(us)} "
          f"(단일 목표 {min(oldt)}~{SPLIT}, 목표 범위 {SPLIT}~)")

    # 검산 2. 널리 알려진 값과 맞는가
    bad = [(m, us.get(m), v) for m, v in GATE_US.items()
           if us.get(m) != v]
    bad += [(m, kr.get(m), v) for m, v in GATE_KR.items()
            if kr.get(m) != v]
    if bad:
        print(f"  검산 실패: 알려진 금리와 다르다 {bad}")
        return 1
    print(f"    검산 빗장: 미국 {len(GATE_US)}개, 한국 {len(GATE_KR)}개 "
          "시점이 알려진 금리와 일치")

    # 검산 3. 계단인가 — 한 달에 2%포인트 넘게 움직인 자리가 있나
    for nm, src in (("한국", kr), ("미국", us)):
        ks = sorted(src)
        jump = [(ks[i], src[ks[i-1]], src[ks[i]]) for i in range(1, len(ks))
                if abs(src[ks[i]] - src[ks[i-1]]) > 2.0]
        if jump:
            print(f"  검산 실패: {nm}이 한 달에 2%포인트 넘게 움직였다 "
                  f"{jump[:3]}")
            return 1
    print("    검산 연속: 두 계열 모두 한 달에 2%포인트 안에서 움직임")

    start = min(kr)
    months = [m for m in sorted(set(kr) | set(us)) if m >= start]
    series = [[kr.get(m) for m in months], [us.get(m) for m in months]]
    last = months[-1]
    print(f"    {last}: 한국 {kr.get(last)}%, 미국 {us.get(last)}%")

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    it = {x["id"]: x for x in items if x.get("id")}.get(CID)
    if not it:
        print(f"{CID} 차트를 찾지 못했습니다.")
        return 1

    # 검산 4. 한국 계열은 기존 차트와 그대로 맞아야 한다
    old = {str(l): it["series"][0][i]
           for i, l in enumerate(str(x) for x in it["labels"])}
    pos = {m: i for i, m in enumerate(months)}
    bad = [(m, v, series[0][pos[m]]) for m, v in old.items()
           if v is not None and m in pos
           and series[0][pos[m]] is not None
           and abs(v - series[0][pos[m]]) > 0.011]
    if bad:
        print(f"  검산 실패: 한국 계열이 기존 차트와 다르다 {bad[:4]}")
        return 1
    print(f"    검산 재현: 한국 계열이 기존 차트의 {len(old)}개 값과 일치")

    out = {
        "labels": months, "series": series,
        "seriesNames": ["한국", "미국"],
        "seriesColors": ["#2a5ca8", "#c0322f"],
        "stepped": True, "unit": "%", "vizType": "line",
        "source": ("한국은행 ECOS 기준금리와 세인트루이스 연은 FRED 연방"
                   "기금금리 목표. 둘 다 월말 기준이고 미국은 2008년 12월"
                   "부터 목표 범위의 위쪽 끝입니다. 단위: 연 %."),
        "sourceUrl": "https://fred.stlouisfed.org/series/DFEDTARU",
        "notes": [
            f"{last} 기준 한국 {kr.get(last)}%, 미국 {us.get(last)}%입니다.",
            "둘 다 중앙은행이 정하는 정책금리입니다. 다음 결정 때까지 "
            "값이 그대로 유지되므로 계단으로 그립니다.",
            "전에는 미국 쪽이 실효 연방기금금리(FEDFUNDS)의 월평균이었습니다. "
            "시장에서 실제로 거래된 금리를 평균한 값이라 연준이 정한 숫자가 "
            "아니었고, 금리를 바꾸지 않은 달에도 조금씩 움직였습니다. "
            "제목에 맞게 목표금리로 바꿨습니다. 그래서 과거 숫자도 "
            "달라집니다. 2026년 10월이 실효 3.88%, 목표 위쪽 끝 4.00%입니다.",
            "2008년 12월부터 연준은 하나의 숫자가 아니라 범위를 정합니다. "
            "여기서는 위쪽 끝을 씁니다. 아래쪽 끝은 보통 0.25%포인트 "
            "낮습니다.",
            "월말 기준입니다. 달의 평균을 내면 금리를 바꾼 달에 실제로는 "
            "없던 중간값이 생깁니다.",
        ],
        "updated": ymd,
    }

    # 미국 목표금리 단독 차트
    uq = sorted(us)
    tgt = {
        "slide": SLIDE_TGT, "category": "세계 경제",
        "title": "미국 연방기금금리 목표.",
        "vizType": "line", "unit": "%", "stepped": True,
        "labels": list(uq), "series": [[us[m] for m in uq]],
        "seriesNames": ["연방기금금리 목표"], "hideLegend": True,
        "seriesColors": ["#c0322f"],
        "source": ("세인트루이스 연은 FRED 연방기금금리 목표. 월말 기준, "
                   f"{uq[0]}~{uq[-1]}. 1982년 9월부터 2008년 12월까지는 "
                   "단일 목표(DFEDTAR), 그 뒤로는 목표 범위의 위쪽 끝"
                   "(DFEDTARU)입니다. 단위: 연 %."),
        "sourceUrl": "https://fred.stlouisfed.org/series/DFEDTARU",
        "notes": [
            f"{uq[-1]} 기준 {us[uq[-1]]}%입니다. 가장 높았던 때는 "
            f"{max(us, key=us.get)}의 {max(us.values())}%입니다.",
            "연준이 정하는 목표금리입니다. 다음 결정 때까지 값이 그대로 "
            "유지되므로 계단으로 그립니다.",
            "2008년 12월부터 연준은 하나의 숫자가 아니라 범위를 정합니다. "
            "여기서는 위쪽 끝을 씁니다. 아래쪽 끝은 보통 0.25%포인트 "
            "낮습니다.",
            "시장에서 실제로 거래된 실효 연방기금금리는 다른 차트입니다. "
            "목표를 바꾸지 않은 달에도 조금씩 움직이고, 목표 범위 안에서 "
            "오르내립니다.",
            "월말 기준입니다. 달의 평균을 내면 금리를 바꾼 달에 실제로는 "
            "없던 중간값이 생깁니다.",
        ],
        "updated": ymd,
    }

    # 실효 금리 차트는 제목만 바로잡는다. 값은 fred_update.py 가 맡는다.
    eff = {
        "title": TITLE_EFF,
        "source": ("세인트루이스 연은 FRED 실효 연방기금금리"
                   "(FEDFUNDS) 월평균. 1954년 7월부터. 단위: %."),
        "sourceUrl": "https://fred.stlouisfed.org/series/FEDFUNDS",
        "notes": [
            "연준이 정한 목표가 아니라 은행들이 서로 하룻밤 돈을 빌릴 때 "
            "실제로 거래된 금리의 월평균입니다. 목표를 바꾸지 않은 달에도 "
            "조금씩 움직이고, 2008년 12월부터는 목표 범위 안에서 "
            "오르내립니다.",
            "연준이 정하는 목표금리는 따로 있습니다. 제목이 '미국 "
            "기준금리'였는데 값은 실효 금리라서 제목을 바로잡았습니다.",
            "월평균입니다. 금리를 바꾼 달에는 바꾸기 전과 뒤가 섞입니다.",
        ],
        "revised": ymd,
    }

    print(f"\n  {CID} {len(months)}점 {months[0]}~{last}")
    print(f"  {SLIDE_TGT} {len(uq)}점 {uq[0]}~{uq[-1]} (목표금리)")
    print(f"  {CID_EFF} 제목 -> {TITLE_EFF}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    o.setdefault(CID, {}).update(out)
    o[CID].pop("revised", None)
    o.setdefault(CID_EFF, {}).update(eff)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))

    # 제목을 바꿔도 주소가 유지되도록 열쇠를 묶어 둔다
    idp = os.path.join(DATA, "ids.json")
    ids = json.load(open(idp, encoding="utf-8"))
    for k in ("S\x1fslide-795\x1f" + TITLE_EFF,
              "세계 경제\x1f" + TITLE_EFF):
        ids[k] = CID_EFF
    with open(idp, "w", encoding="utf-8") as fh:
        json.dump(ids, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    prev_it = idx.get(SLIDE_TGT)
    if prev_it:
        keep = {k: prev_it[k] for k in ("id",) if k in prev_it}
        prev_it.clear()
        prev_it.update(tgt)
        prev_it.update(keep)
    else:
        doc["items"].append(tgt)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print(f"-> {CID}, {CID_EFF} 제목, 그리고 목표금리 차트를 "
          "반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
