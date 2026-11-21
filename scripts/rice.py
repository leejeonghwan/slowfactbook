#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국의 소매 쌀값(c0359) — KAMIS 농산물유통정보.

출처 주소 하나에 표가 넷 들어 있다.
  도매(중도매인 판매가격) 상품 / 도매 중품 / 소매 상품 / 소매 중품
네 표 모두 같은 모양이라 한꺼번에 긁으면 서로 덮어쓴다. 실제로 한 번
그렇게 섞였다. 그래서 각 표 바로 앞의 문맥에서 '소매가격'과 '등급 :
상품'을 확인하고 그 표만 쓴다.

c0359 가 이 표라는 근거: 겹치는 363개월 중 362개월이 값까지 같았다.
나머지 한 달(2026-03)은 KAMIS 가 뒤에 고친 값이다.

한 번 틀린 기록 — 엑셀 출력 파일의 머리글은 품목을 말해 주지 않는다.
KAMIS 엑셀 출력은 소매든 도매든 "가격정보 - 친환경농산물 - 품목별
엑셀 출력"이라는 같은 템플릿 제목을 단다. 그걸 보고 친환경 계열이라고
짐작했는데, 실제로는 그냥 중도매인 판매가격이었다. 소매보다 도매가
싼 것은 설명이 필요 없는 일인데 엉뚱한 설명을 붙였다. 품목은 표 앞의
문맥으로만 가린다.
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

URL = ("https://www.kamis.or.kr/customer/price/product/period.do"
       "?action=monthly&yyyy={yyyy}&period=31&countycode="
       "&itemcategorycode=100&itemcode=111&kindcode=01"
       "&productrankcode=&convert_kg_yn=N")
SITE = "https://www.kamis.or.kr/"
# 표 앞 문맥으로 고른다. (있어야 하는 말, 없어야 하는 말)
KINDS = {
    "소매": (("소매가격", "상품"), ("중도매인", "중품")),
    "도매": (("중도매인", "상품"), ("소매가격", "중품")),
}


def txt(x):
    return html.unescape(re.sub("<[^>]+>", "", x)).replace("\xa0", " ")


def fetch(tries=3):
    u = URL.format(yyyy=datetime.datetime.now(KST).year)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers={"User-Agent":
                                                     "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=90).read() \
                .decode("utf-8", "replace")
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(3 + 3 * i)
    raise RuntimeError(f"KAMIS 를 받지 못했다: {last}")


def pick(s, kind):
    """그 종류의 상품 등급 표 하나만 고른다. 둘 이상이면 멈춘다."""
    want, avoid = KINDS[kind]
    tables = re.findall(r"<table[^>]*>(.*?)</table>", s, re.S | re.I)
    pos = [m.start() for m in re.finditer(r"<table[^>]*>", s, re.I)]
    hits = []
    for t, p in zip(tables, pos):
        ctx = " ".join(txt(s[max(0, p - 900):p]).split())[-160:]
        if not all(w in ctx for w in want):
            continue
        if any(w in ctx for w in avoid):
            continue
        d = {}
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I):
            c = [txt(x).strip() for x in
                 re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)]
            if len(c) >= 13 and re.fullmatch(r"(19|20)\d\d", c[0]):
                for j in range(1, 13):
                    v = c[j].replace(",", "")
                    if re.fullmatch(r"\d+", v):
                        d[f"{c[0]}-{j:02d}"] = int(v)
        if d:
            hits.append((ctx, d))
    if len(hits) != 1:
        raise RuntimeError(f"{kind} 상품 표가 {len(hits)}개다 — 쪽 구조가 "
                           "바뀌었을 수 있으니 확인해야 한다")
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    page = fetch()
    ctx, d = pick(page, "소매")
    wctx, w = pick(page, "도매")
    print(f"    검산 표: 소매 상품 20kg 과 도매 상품 20kg 을 하나씩 집음")
    ks = sorted(d)

    fp = os.path.join(DATA, "full.json")
    fl = json.load(open(fp, encoding="utf-8"))
    full = {i.get("id"): i for i in (fl.get("items") or fl)}
    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    cur = dict(full.get("c0359") or {})
    cur.update(o.get("c0359") or {})
    old = dict(zip(cur.get("labels") or [], (cur.get("series") or [[]])[0]))

    ov = [k for k in ks if k in old]
    same = sum(1 for k in ov if old[k] == d[k])
    if not ov or same / len(ov) < 0.95:
        diff = [(k, old[k], d[k]) for k in ov if old[k] != d[k]][:4]
        print(f"  검산 실패: 겹친 {len(ov)}개월 중 {same}개만 일치 {diff}")
        return 1
    print(f"    검산 대조: 겹친 {len(ov)}개월 중 {same}개 일치 "
          f"({len(ov)-same}개는 KAMIS 개정분)")

    jump = [(ks[i], round(d[ks[i]] / d[ks[i-1]] - 1, 3))
            for i in range(1, len(ks))
            if abs(d[ks[i]] / d[ks[i-1]] - 1) > 0.15]
    if jump:
        print(f"  검산 실패: 한 달에 15% 넘게 튄 자리 {jump[:3]}")
        return 1
    print(f"    검산 연속: {len(ks)}개월 모두 전달 대비 15% 안")

    last, first = ks[-1], ks[0]
    pk = max(ks, key=lambda k: d[k])
    lo = min(ks, key=lambda k: d[k])
    it = {
        "id": "c0359", "category": "식량",
        "title": "한국의 소매 쌀값.",
        "vizType": "line", "unit": "원",
        "labels": list(ks), "series": [[d[k] for k in ks]],
        "seriesNames": ["20kg 소매가격"], "hideLegend": True,
        "source": ("KAMIS 농산물유통정보. 쌀 20kg 소매가격, 등급 상품. "
                   f"{first}~{last}. 단위: 원."),
        "sourceUrl": SITE,
        "notes": [
            f"{last} 기준 {d[last]:,}원입니다. {first} {d[first]:,}원에서 "
            f"{d[last]/d[first]:.2f}배가 됐습니다. 같은 기간 물가는 "
            "반영하지 않은 명목 금액입니다.",
            f"가장 비쌌던 달은 {pk} {d[pk]:,}원, 가장 쌌던 달은 "
            f"{lo} {d[lo]:,}원입니다.",
            "소매가격이고 등급은 상품입니다. 같은 쪽에 도매(중도매인 "
            "판매가격)와 중품 등급도 함께 나오는데 값이 다릅니다. "
            "섞어 읽으면 안 됩니다.",
            "같은 사이트의 친환경농산물 쌀값은 또 다른 계열입니다. 품목과 "
            "단위가 같아 보여도 값이 전혀 다르니 함께 쓰지 마십시오.",
            "KAMIS 가 최근 달을 뒤에 고치는 일이 있습니다. 개정된 값을 "
            "따릅니다.",
        ],
        "updated": ymd,
    }

    # ── 소매와 도매 비교
    both = [k for k in ks if k in w]
    if len(both) < len(ks) * 0.95:
        print(f"  검산 실패: 도매가 {len(both)}개월만 겹친다({len(ks)} 중)")
        return 1
    under = [k for k in both if d[k] < w[k]]
    if len(under) > len(both) * 0.02:
        print(f"  검산 실패: 소매가 도매보다 싼 달이 {len(under)}개나 된다 "
              f"— 표를 거꾸로 집었을 수 있다 {under[:3]}")
        return 1
    print(f"    검산 상하: 겹친 {len(both)}개월 중 소매가 도매보다 싼 달은 "
          f"{len(under)}개({', '.join(under) if under else '없음'})")

    gap = [d[k] - w[k] for k in both]
    med = sorted(gap)[len(gap) // 2]
    gl, gh = both[gap.index(min(gap))], both[gap.index(max(gap))]
    pair = {
        "slide": "manual-rice-retail-wholesale", "category": "식량",
        "title": "쌀값, 소매와 도매",
        "vizType": "line", "unit": "원",
        "labels": list(both),
        "series": [[d[k] for k in both], [w[k] for k in both]],
        "seriesNames": ["소매", "도매(중도매인 판매가격)"],
        "seriesColors": ["#c0322f", "#9a9a9a"],
        "source": ("KAMIS 농산물유통정보. 쌀 20kg, 등급 상품. "
                   f"{both[0]}~{both[-1]}. 단위: 원."),
        "sourceUrl": SITE,
        "notes": [
            f"{both[-1]} 기준 소매 {d[both[-1]]:,}원, 도매 "
            f"{w[both[-1]]:,}원입니다. 차이가 "
            f"{d[both[-1]]-w[both[-1]]:,}원입니다.",
            f"{len(both)}개월 동안 두 값의 차이는 중앙값이 {med:,}원이고, "
            f"가장 좁았던 달이 {gl}({min(gap):,}원), 가장 넓었던 달이 "
            f"{gh}({max(gap):,}원)입니다.",
            "도매는 중도매인 판매가격이고 소매는 소비자가 사는 값입니다. "
            "둘 다 20kg, 등급 상품 기준입니다. 차이가 그대로 유통 "
            "마진인 것은 아니고 포장과 운송 같은 비용도 들어 있습니다.",
            "KAMIS 엑셀 출력 파일의 머리글은 소매든 도매든 같은 문구가 "
            "찍혀 나옵니다. 어느 쪽인지는 파일 제목이 아니라 표의 "
            "설명으로 가려야 합니다.",
        ],
        "updated": ymd,
    }

    gseries = [d[k] - w[k] for k in both]
    g2 = {
        "slide": "manual-rice-margin", "category": "식량",
        "title": "쌀 소매가격과 도매가격의 차이",
        "vizType": "column", "unit": "원",
        "labels": list(both), "series": [gseries],
        "seriesNames": ["소매 빼기 도매"],
        "seriesColors": ["#2a5ca8"], "hideLegend": True,
        "source": ("KAMIS 농산물유통정보. 쌀 20kg 소매가격에서 도매(중도매인 "
                   f"판매가격)를 뺀 값, 등급 상품. {both[0]}~{both[-1]}. "
                   "단위: 원."),
        "sourceUrl": SITE,
        "notes": [
            f"{both[-1]} 기준 {gseries[-1]:,}원입니다. 중앙값은 "
            f"{med:,}원입니다.",
            f"0 아래로 내려간 달은 {len(under)}개입니다"
            + (f"({', '.join(under)})." if under else "."),
            "20kg 한 포대에 유통 단계에서 얼마가 붙는지를 보여 줍니다. "
            "포장과 운송 비용이 함께 들어 있어 이 액수가 곧 이윤은 "
            "아닙니다.",
            "소매와 도매가 늘 같은 방향으로 움직이지는 않습니다. 막대가 "
            "길어지는 구간은 둘이 벌어진 때입니다.",
        ],
        "updated": ymd,
    }

    print(f"  c0359 {len(ks)}점 {first}~{last} 끝값 {d[last]:,}원 "
          f"(전에는 {len(old)}점, {max(old) if old else '-'} 까지)")
    for x in (pair, g2):
        print(f"  {x['title']:22s} {len(x['labels'])}점 "
              f"{x['labels'][0]}~{x['labels'][-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    o.setdefault("c0359", {}).update(it)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print("-> data/overrides.json 에 c0359 를 반영했습니다.")

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in (pair, g2):
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
    print("-> data/manual.json 에 2장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
