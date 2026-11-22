#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""축산물 소매가격 — 축산물품질평가원 축산유통정보(EKAPE).

주소 하나에 지역 열이 스무 개 넘게 붙어 나오는데 지역별은 쓰지 않고
'평균' 열만 쓴다. 열 자리를 숫자로 박지 않고 머리글에서 '평균'을
찾는다. 표 구조가 바뀌면 멈춘다.

축종(livestockType)과 부위(spec)
  4304 돼지   : 삼겹살 27, 목심 68, 갈비 28, 앞다리 25        원/100g
  4402 수입 돼지: 삼겹살 27 (화면 표기 '삼겹살(냉동)')          원/100g
  4301 소     : 안심 21, 등심 22, 양지 40, 갈비 50, 설도 36    원/100g
  4401 수입 소 : 갈비(냉동) 31, 갈비살(냉장) 37,
                척아이롤(냉장) 62, 척아이롤(냉동) 68,
                양지(냉장) 29                               원/100g
  9901 닭     : 육계 99                                     원/Kg
  9903 계란   : XL30구 23, XL10구 21                         원/30구
  9908 우유   : 흰우유 01                                    원/1L

단위가 축종마다 다르다. 쪽에 적힌 단위를 읽어 기대한 것과 같은지
확인하고, 다르면 멈춘다. 단위가 다른 것을 한 축에 올리지 않으려고
차트를 축종별로 나눈다.

부위마다 자료가 시작하는 때가 다르다. 한 장에 올리면 앞쪽은 선이
비어 있다.

표 맨 아래에 '평년' 행이 섞여 있다. 연월 꼴이 아닌 행은 버린다.
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

URL = ("https://www.ekapepia.com/v3/price/consumer/periodPrice.do"
       "?menuSn=40&boardInfoNo=&aggregationUnit=MONTH"
       "&livestockType={lt}&spec={sp}&grade="
       "&startDate=1979-01&endDate={end}&searchYn=Y")
SITE = "https://www.ekapepia.com/"
SRC = "축산물품질평가원 축산유통정보. 소비자가격 월평균, 전국 평균."
PAL = ["#c0322f", "#e8820c", "#6a8f3c", "#8a6fb0", "#2a5ca8", "#9a9a9a"]

# 차트마다: (슬라이드, 제목, 단위, [(계열명, 축종, 부위)])
CHARTS = [
    ("manual-pork-cuts", "돼지고기 부위별 소매가격", "원/100g", [
        ("삼겹살", "4304", "27"), ("목심", "4304", "68"),
        ("갈비", "4304", "28"), ("앞다리", "4304", "25"),
        ("수입 삼겹살(냉동)", "4402", "27")]),
    ("manual-beef-cuts", "국산 소고기 부위별 소매가격", "원/100g", [
        ("안심", "4301", "21"), ("등심", "4301", "22"),
        ("갈비", "4301", "50"), ("양지", "4301", "40"),
        ("설도", "4301", "36")]),
    ("manual-beef-import", "수입 소고기 부위별 소매가격", "원/100g", [
        ("갈비살(냉장)", "4401", "37"), ("양지(냉장)", "4401", "29"),
        ("척아이롤(냉장)", "4401", "62"), ("척아이롤(냉동)", "4401", "68"),
        ("갈비(냉동)", "4401", "31")]),
    ("manual-chicken-price", "닭고기 소매가격", "원/kg", [
        ("육계", "9901", "99")]),
    ("manual-egg-price", "계란 소매가격", "원/30구", [
        ("특란 30구", "9903", "23")]),
    ("manual-milk-price", "우유 소매가격", "원/L", [
        ("흰우유 1L", "9908", "01")]),
]
# 쪽에 적혀 있어야 하는 단위 문구
UNIT_MARK = {"원/100g": "원/100g", "원/kg": "원/Kg",
             "원/30구": "원/30구", "원/L": "원/1L"}


def txt(x):
    return html.unescape(re.sub("<[^>]+>", "", x)).replace("\xa0", " ").strip()


def get(lt, sp, mark, tries=3):
    end = datetime.datetime.now(KST).strftime("%Y-%m")
    u = URL.format(lt=lt, sp=sp, end=end)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers={"User-Agent":
                                                     "Mozilla/5.0"})
            s = urllib.request.urlopen(req, timeout=120).read() \
                .decode("utf-8", "replace")
            if mark not in s:
                raise RuntimeError(f"단위 '{mark}' 표기가 없다")
            tab = re.findall(r"<table[^>]*>(.*?)</table>", s, re.S | re.I)
            if not tab:
                raise RuntimeError("표가 없다")
            rows = [[txt(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)]
                    for r in re.findall(r"<tr[^>]*>(.*?)</tr>",
                                        tab[0], re.S | re.I)]
            hdr = [r for r in rows if r and r[0] == "구분"]
            if not hdr or "평균" not in hdr[0]:
                raise RuntimeError("머리글에서 '평균' 열을 못 찾았다")
            ai = hdr[0].index("평균")
            out = {}
            for r in rows:
                if not r or len(r) <= ai:
                    continue
                m = re.fullmatch(r"(\d{2})년\s*(\d{1,2})월", r[0])
                if not m:
                    continue          # '평년' 같은 행은 여기서 걸러진다
                v = r[ai].replace(",", "")
                if not re.fullmatch(r"\d+", v):
                    continue
                yy = int(m.group(1))
                year = 1900 + yy if yy >= 70 else 2000 + yy
                out[f"{year}-{int(m.group(2)):02d}"] = int(v)
            if out:
                return out
            raise RuntimeError("값이 하나도 없다")
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(3 + 3 * i)
    raise RuntimeError(f"{lt}/{sp} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="슬라이드 이름 조각")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    charts = [c for c in CHARTS if not a.only or a.only in c[0]]
    out, fail = [], 0
    for slide, title, unit, specs in charts:
        mark = UNIT_MARK[unit]
        d = {}
        try:
            for nm, lt, sp in specs:
                d[nm] = get(lt, sp, mark)
                time.sleep(1)
        except Exception as e:                       # noqa: BLE001
            print(f"  {title}: 실패 {e}")
            fail += 1
            continue
        print(f"    검산 단위 [{title}]: {len(specs)}개 계열 모두 쪽에 "
              f"'{mark}' 표기 확인")

        bad = [(nm, k, v) for nm in d for k, v in d[nm].items()
               if not 100 <= v <= 200000]
        if bad:
            print(f"  {title}: 검산 실패 — 말이 안 되는 값 {bad[:3]}")
            fail += 1
            continue
        # 한 달에 크게 튀는 일은 실제로 있다. 2017-01 계란은 조류
        # 인플루엔자로 37% 올랐고 2022-01 수입 갈비는 40% 올랐다.
        # 그래서 막는 문턱은 60%로 둔다. 단위가 바뀌거나 표를 바꿔
        # 집는 사고는 몇 배 단위로 튀므로 이 문턱에 걸린다.
        # 25%를 넘는 자리는 막지 않고 세어서 알려만 준다.
        big, huge = [], []
        for nm in d:
            ks = sorted(d[nm])
            for i in range(1, len(ks)):
                r = abs(d[nm][ks[i]] / d[nm][ks[i-1]] - 1)
                if r > 0.6:
                    huge.append((nm, ks[i], round(r, 2)))
                elif r > 0.25:
                    big.append((nm, ks[i]))
        if huge:
            print(f"  {title}: 검산 실패 — 한 달에 60% 넘게 튄 자리 "
                  f"{huge[:3]}")
            fail += 1
            continue
        print(f"    검산 연속 [{title}]: "
              f"{sum(len(x) for x in d.values())}칸 모두 범위와 "
              f"전달 대비 60% 안 (25% 넘는 달 {len(big)}개"
              + (f": {', '.join(f'{a} {b}' for a, b in big[:4])})" if big
                 else ")"))

        months = sorted({k for nm in d for k in d[nm]})
        last = months[-1]
        have = [(nm, d[nm][last]) for nm, _l, _s in specs if last in d[nm]]
        starts = sorted({sorted(d[nm])[0] for nm in d})
        notes = [
            f"{last} 기준으로 "
            + ", ".join(f"{nm} {v:,}원" for nm, v in have) + "입니다.",
        ]
        if len(specs) > 1:
            top = max(have, key=lambda x: x[1])
            bot = min(have, key=lambda x: x[1])
            notes.append(
                f"가장 비싼 {top[0]}이 가장 싼 {bot[0]}의 "
                f"{top[1]/bot[1]:.2f}배입니다.")
        if len(starts) > 1:
            notes.append(
                "부위마다 자료가 시작하는 때가 다릅니다. "
                + ", ".join(f"{nm}은 {sorted(d[nm])[0]}"
                            for nm, _l, _s in specs) +
                "부터입니다. 그 전은 선이 비어 있습니다.")
        else:
            notes.append(f"{months[0]}부터 {last}까지 "
                         f"{len(months)}개월입니다.")
        notes += [
            "전국 평균이고 지역별 값은 쓰지 않았습니다.",
            "소비자가격입니다. 도매나 산지 가격과는 다릅니다. "
            f"단위는 {unit}입니다.",
        ]
        if "수입" in title or any("수입" in nm for nm, _l, _s in specs):
            notes.append("수입육은 냉장과 냉동이 섞여 있습니다. 국산과 "
                         "조건이 같지 않아 그대로 견주면 안 됩니다.")
        out.append({
            "slide": slide, "category": "식량", "title": title,
            "vizType": "line", "unit": unit,
            "labels": list(months),
            "series": [[d[nm].get(k) for k in months]
                       for nm, _l, _s in specs],
            "seriesNames": [nm for nm, _l, _s in specs],
            "seriesColors": PAL[:len(specs)],
            "hideLegend": len(specs) == 1,
            "source": (f"{SRC} {months[0]}~{last}. 단위: {unit}."),
            "sourceUrl": SITE,
            "notes": notes,
            "updated": ymd,
        })

    # 국산 삼겹살과 수입 삼겹살의 배율(돼지를 받았을 때만)
    pork = next((x for x in out if x["slide"] == "manual-pork-cuts"), None)
    if pork:
        i1 = pork["seriesNames"].index("삼겹살")
        i2 = pork["seriesNames"].index("수입 삼겹살(냉동)")
        ks, r = [], []
        for j, k in enumerate(pork["labels"]):
            x, y = pork["series"][i1][j], pork["series"][i2][j]
            if x and y:
                ks.append(k)
                r.append(round(x / y, 2))
        under = [ks[j] for j, v in enumerate(r) if v <= 1]
        if len(under) > len(r) * 0.02:
            print(f"  검산 실패: 국산이 수입보다 싼 달이 {len(under)}개 "
                  f"— 계열을 바꿔 집었을 수 있다 {under[:3]}")
            return 1
        print(f"    검산 국산수입: 겹친 {len(r)}개월 중 국산이 수입보다 "
              f"싸거나 같은 달 {len(under)}개")
        hi, lo = ks[r.index(max(r))], ks[r.index(min(r))]
        out.append({
            "slide": "manual-pork-import-gap", "category": "식량",
            "title": "국산 삼겹살은 수입의 몇 배인가",
            "vizType": "line", "unit": "배",
            "labels": ks, "series": [r],
            "seriesNames": ["국산 나누기 수입"], "hideLegend": True,
            "source": (f"{SRC} 국산 삼겹살을 수입 삼겹살(냉동)로 나눈 값. "
                       f"{ks[0]}~{ks[-1]}. 단위: 배."),
            "sourceUrl": SITE,
            "notes": [
                f"{ks[-1]} 기준 {r[-1]:.2f}배입니다.",
                f"가장 벌어졌던 달은 {hi}로 {max(r):.2f}배, 가장 좁았던 "
                f"달은 {lo}로 {min(r):.2f}배입니다.",
                "수입은 냉동이고 국산은 냉장이라 같은 물건이 아닙니다. "
                "이 배율은 품질 차이와 가격 차이를 함께 담고 있습니다.",
                "두 선을 그대로 겹친 것은 「돼지고기 부위별 소매가격」에 "
                "있습니다.",
            ],
            "updated": ymd,
        })

    for x in out:
        print(f"  {x['title']:22s} {len(x['labels'])}점 "
              f"{x['labels'][0]}~{x['labels'][-1]} 계열 {len(x['series'])}")
    if fail:
        print(f"\n  실패 {fail}건 — 그 차트는 손대지 않았습니다.")
    if not out:
        return 1
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out:
        prev = idx.get(x["slide"])
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
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
