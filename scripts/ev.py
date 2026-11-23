#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전기차 판매 비중 — Ember EV Sales Data Tracker.

자료: https://ember-energy.org/data/ev-sales-tracker/
파일: files.ember-energy.org/public-downloads/transport/outputs/
      monthly_ev_sales.csv (7.7MB, 56개국, 2005-01~)

쪽에는 내려받기 단추가 안 보이고 CSV 주소도 링크로 걸려 있지 않다.
쪽이 뒤에서 같은 폴더의 ev_sales_country_notes.csv 를 불러오는 걸 보고
폴더를 찾았다. 본 파일 이름은 monthly_ev_sales.csv 다.

칸 구성
  Area / ISO 3 code / Area type(Country or economy | Region)
  Date / Data frequency(Monthly | Quarterly)
  Drivetrain / Is aggregate drivetrain
  Registrations / Share of registrations (%) / Rolling 12-month ...

주의할 것 세 가지.
  1) Data frequency 에 월간과 분기가 섞여 있다. 월간만 골라야 한다.
  2) Drivetrain 에 합계 항목이 섞여 있다. 'All drivetrains' 와
     'Electric vehicle (BEV+PHEV)' 는 Is aggregate drivetrain=True 다.
     이것들을 부분 항목과 같이 더하면 두 번 센다.
  3) 나라마다 자료가 시작하는 때가 다르고, 끝나는 때도 다르다. 한국은
     다른 나라보다 한 달 늦게 올라온다. 한 장에 올리면 오른쪽 끝이
     들쭉날쭉하다.
"""
import argparse
import csv
import datetime
import io
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

URL = ("https://files.ember-energy.org/public-downloads/transport/outputs/"
       "monthly_ev_sales.csv")
SITE = "https://ember-energy.org/data/ev-sales-tracker/"
SRC = "Ember EV Sales Data Tracker"
EV = "Electric vehicle (BEV+PHEV)"
ALL = "All drivetrains"

# 나라 색: 일본과 중국이 함께 나오므로 중국은 주황
PICK = [("세계", "World", "#1a1a1a"), ("중국", "China", "#e8820c"),
        ("독일", "Germany", "#6a8f3c"), ("한국", "South Korea", "#2a5ca8"),
        ("미국", "United States", "#9a9a9a"),
        ("일본", "Japan", "#c0322f")]
# 한국 동력원별
MIX = [("배터리 전기", "Battery electric", "#2a5ca8"),
       ("플러그인 하이브리드", "Plug-in hybrid", "#5b8bc9"),
       ("하이브리드", "Hybrid", "#6a8f3c"),
       ("내연기관", "Combustion (unspecified)", "#9a9a9a"),
       ("휘발유", "Petrol", "#c9a08f"), ("경유", "Diesel", "#8a6fb0"),
       ("기타", "Other", "#d0d0d0")]


def grab(tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent":
                                                       "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=300).read()
            rows = list(csv.DictReader(
                io.StringIO(raw.decode("utf-8", "replace"))))
            if len(rows) > 10000:
                return rows
            raise RuntimeError(f"{len(rows)}행뿐이다")
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(5 + 5 * i)
    raise RuntimeError(f"Ember 를 받지 못했다: {last}")


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    rows = [r for r in grab() if r["Data frequency"] == "Monthly"]
    print(f"    받음: 월간 {len(rows)}행")

    # 검산 1. 'All drivetrains' 비중은 100이어야 한다
    bad = [(r["Area"], r["Date"]) for r in rows
           if r["Drivetrain"] == ALL
           and num(r["Share of registrations (%)"]) not in (None, 100.0)]
    if bad:
        print(f"  검산 실패: 'All drivetrains' 비중이 100이 아닌 자리 "
              f"{bad[:3]}")
        return 1
    print("    검산 합계: 'All drivetrains' 비중이 모두 100")

    # 검산 2. 배터리전기 + 플러그인하이브리드 = 전기차 합계
    idx = {}
    for r in rows:
        idx.setdefault((r["Area"], r["Date"]), {})[r["Drivetrain"]] = r
    off = []
    for k, v in idx.items():
        b, p, e = (num((v.get("Battery electric") or {}).get("Registrations")),
                   num((v.get("Plug-in hybrid") or {}).get("Registrations")),
                   num((v.get(EV) or {}).get("Registrations")))
        if None in (b, p, e):
            continue
        if abs(b + p - e) > 1:
            off.append((k[0], k[1], b, p, e))
    if off:
        print(f"  검산 실패: 배터리전기+플러그인 != 전기차 합계 {off[:3]}")
        return 1
    print(f"    검산 항등: {len(idx)}개 나라-달에서 "
          "배터리전기 + 플러그인하이브리드 = 전기차 합계")

    out = []

    # ── 1 주요국 전기차 판매 비중
    ser, span = {}, {}
    for nm, area, _c in PICK:
        s = {r["Date"][:7]: num(r["Share of registrations (%)"])
             for r in rows if r["Area"] == area and r["Drivetrain"] == EV
             and num(r["Share of registrations (%)"]) is not None}
        if not s:
            print(f"  검산 실패: {nm}({area}) 자료가 없다")
            return 1
        ser[nm] = s
        span[nm] = (min(s), max(s))
    bad = [(nm, k, v) for nm in ser for k, v in ser[nm].items()
           if not 0 <= v <= 100]
    if bad:
        print(f"  검산 실패: 비중이 0~100 밖 {bad[:3]}")
        return 1
    months = sorted({k for nm in ser for k in ser[nm]})
    print(f"    검산 범위: {len(PICK)}개 나라 모두 0~100% 안")

    last = months[-1]
    now = {nm: ser[nm].get(span[nm][1]) for nm, _a, _c in PICK}
    out.append({
        "slide": "manual-ev-share", "category": "기업과 산업",
        "title": "전기차 판매 비중",
        "vizType": "line", "unit": "%",
        "labels": list(months),
        "series": [[ser[nm].get(m) for m in months] for nm, _a, _c in PICK],
        "seriesNames": [nm for nm, _a, _c in PICK],
        "seriesColors": [c for _n, _a, c in PICK],
        "source": (f"{SRC}. 신차 등록에서 전기차(배터리 전기와 플러그인 "
                   f"하이브리드)가 차지하는 비중, 월간. {months[0]}~{last}. "
                   "단위: %."),
        "sourceUrl": SITE,
        "notes": [
            "가장 최근 달 기준으로 "
            + ", ".join(f"{nm} {now[nm]:.1f}%" for nm, _a, _c in PICK)
            + "입니다.",
            f"한국은 세계 평균보다 낮습니다. 차와 배터리를 만드는 "
            f"나라인데 {now['한국']:.1f}%로 세계 {now['세계']:.1f}%에 "
            "못 미칩니다.",
            "나라마다 자료가 시작하는 때가 다릅니다. "
            + ", ".join(f"{nm}은 {span[nm][0]}" for nm, _a, _c in PICK)
            + "부터입니다. 끝나는 때도 달라서 오른쪽 끝이 들쭉날쭉합니다. "
            "한국은 다른 나라보다 한 달 늦게 올라옵니다.",
            "월간이라 들쭉날쭉합니다. 연말에 밀어내기가 몰리고 보조금 "
            "제도가 바뀌는 달에 크게 튑니다. 흐름만 보려면 12개월 "
            "이동평균이 낫습니다.",
            "신차 등록 기준입니다. 판매 계약이나 생산 대수와는 다릅니다.",
        ],
        "updated": ymd,
    })

    # ── 2 한국 동력원별 비중
    kr = {}
    for nm, dr, _c in MIX:
        s = {r["Date"][:7]: num(r["Share of registrations (%)"])
             for r in rows if r["Area"] == "South Korea"
             and r["Drivetrain"] == dr
             and num(r["Share of registrations (%)"]) is not None}
        if s:
            kr[nm] = s
    use = [(nm, c) for nm, _d, c in MIX if nm in kr]
    km = sorted({k for nm in kr for k in kr[nm]})
    tot = {m: sum(kr[nm].get(m, 0) for nm, _c in use) for m in km}
    wonky = [(m, round(tot[m], 1)) for m in km if abs(tot[m] - 100) > 1.5]
    if wonky:
        print(f"  검산 실패: 한국 동력원 비중 합이 100이 아닌 달 "
              f"{wonky[:3]}")
        return 1
    print(f"    검산 한국: {len(km)}개월 모두 동력원 비중 합이 100 ± 1.5")

    klast = km[-1]
    out.append({
        "slide": "manual-ev-korea-mix", "category": "기업과 산업",
        "title": "한국 신차 등록, 동력원별 비중",
        "vizType": "stacked_bar", "unit": "%",
        "labels": list(km),
        "series": [[kr[nm].get(m) for m in km] for nm, _c in use],
        "seriesNames": [nm for nm, _c in use],
        "seriesColors": [c for _n, c in use],
        "source": (f"{SRC}. 한국 신차 등록의 동력원별 비중, 월간. "
                   f"{km[0]}~{klast}. 단위: %."),
        "sourceUrl": SITE,
        "notes": [
            f"{klast} 기준으로 "
            + ", ".join(f"{nm} {kr[nm][klast]:.1f}%"
                        for nm, _c in use if klast in kr[nm]) + "입니다.",
            "하이브리드가 배터리 전기차보다 큽니다. 전기차로 바로 "
            "가지 않고 하이브리드를 거치는 모양입니다.",
            "막대 전체가 100%입니다. 합이 100에서 1.5%포인트 넘게 "
            "벗어나는 달이 없는지 확인했습니다.",
            "신차 등록 기준입니다.",
        ],
        "updated": ymd,
    })

    # ── 3 한국 전기차 등록 대수
    reg = {r["Date"][:7]: num(r["Registrations"])
           for r in rows if r["Area"] == "South Korea"
           and r["Drivetrain"] == EV and num(r["Registrations"]) is not None}
    rm = sorted(reg)
    pk = max(rm, key=lambda m: reg[m])
    out.append({
        "slide": "manual-ev-korea-count", "category": "기업과 산업",
        "title": "한국 전기차 신규 등록 대수",
        "vizType": "line", "unit": "대",
        "labels": list(rm), "series": [[int(reg[m]) for m in rm]],
        "seriesNames": ["전기차(배터리 전기와 플러그인 하이브리드)"],
        "hideLegend": True,
        "source": (f"{SRC}. 한국 월별 전기차 신규 등록 대수. "
                   f"{rm[0]}~{rm[-1]}. 단위: 대."),
        "sourceUrl": SITE,
        "notes": [
            f"{rm[-1]} {int(reg[rm[-1]]):,}대입니다. 가장 많았던 달은 "
            f"{pk}로 {int(reg[pk]):,}대입니다.",
            "비중이 아니라 대수입니다. 전체 신차 시장이 줄면 비중이 "
            "올라도 대수는 줄 수 있습니다. 비중은 「전기차 판매 비중」을 "
            "함께 보십시오.",
            "연말과 연초에 크게 튑니다. 보조금이 해마다 다시 풀리는 "
            "구조 때문입니다.",
        ],
        "updated": ymd,
    })

    for x in out:
        print(f"  {x['title']:24s} {len(x['labels'])}점 "
              f"{x['labels'][0]}~{x['labels'][-1]} 계열 {len(x['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx2 = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out:
        prev = idx2.get(x["slide"])
        if prev:
            keep = {k: prev[k] for k in ("id",) if k in prev}
            prev.clear()
            prev.update(x)
            prev.update(keep)
        else:
            doc["items"].append(x)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
