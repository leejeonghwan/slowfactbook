#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연천군 청산면의 연령대별 주민등록인구(c0758).

  KOSIS_API_KEY=... python3 scripts/cheongsan_pop.py            # 미리보기
  KOSIS_API_KEY=... python3 scripts/cheongsan_pop.py --apply

행정안전부 주민등록인구현황의 읍면동 5세별 표(KOSIS DT_1B04005N)에서
청산면(4180032000) 한 곳을 뽑아 열 살 단위로 묶는다.

청산면은 경기도 연천군의 농어촌 기본소득 시범 지역이다. 전국 인구와 달리
한 면 단위라 숫자가 작고, 몇십 명의 전입과 전출로도 선이 흔들린다.

대조해서 어긋나면 아무것도 쓰지 않고 멈춘다.
"""
import argparse, datetime, json, os, re, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CID = "c0758"
ORG, TBL, AREA = "101", "DT_1B04005N", "4180032000"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B04005N")
# 보여 줄 차례. 차트에 이미 들어 있는 순서를 그대로 쓴다.
BANDS = ["9세 이하", "10대", "20대", "30대", "40대", "50대", "60대", "70대 이상"]


def band_of(low):
    """5세 구간의 아래 나이를 열 살 단위 이름으로."""
    if low < 10:
        return "9세 이하"
    if low >= 70:
        return "70대 이상"
    return "%d대" % (low // 10 * 10)


def pull(key):
    q = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": ORG, "tblId": TBL, "itmId": "T2+", "objL1": AREA, "objL2": "ALL",
         "prdSe": "M", "startPrdDe": "201101",
         "endPrdDe": datetime.datetime.now(KST).strftime("%Y%m")}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{a}={urllib.parse.quote(str(b), safe='+')}" for a, b in q.items()))
    d = json.loads(urllib.request.urlopen(u, timeout=150).read().decode("utf-8"))
    if isinstance(d, dict):
        raise SystemExit("KOSIS: " + str(d)[:140])
    out, total = {}, {}
    for r in d:
        ym = r["PRD_DE"][:4] + "-" + r["PRD_DE"][4:6]
        nm = str(r["C2_NM"]).strip()
        v = float(r["DT"])
        if nm in ("계", "Total"):
            total[ym] = v
            continue
        m = re.match(r"(\d+)", nm)
        if not m:
            continue
        out.setdefault(ym, {}).setdefault(band_of(int(m.group(1))), 0.0)
        out[ym][band_of(int(m.group(1)))] += v
    return out, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    raw, total = pull(key)
    years = sorted(y for y, v in raw.items() if len(v) == len(BANDS))
    if len(years) < 24:
        raise SystemExit(f"받은 달이 {len(years)}개뿐입니다 — 쓰지 않습니다.")
    # 열 살 단위를 더하면 표의 '계' 와 맞아야 한다.
    bad = [(y, sum(raw[y].values()), total.get(y)) for y in years
           if total.get(y) is not None and sum(raw[y].values()) != total[y]]
    if bad:
        raise SystemExit(f"구간 합이 계와 어긋납니다: {bad[:5]}")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    full = {i["id"]: i for i in
            json.load(open(os.path.join(DATA, "full.json"), encoding="utf-8"))["items"]
            if i.get("id")}
    cur = {**full.get(CID, {}), **(ov.get(CID) or {})}
    old_lab = [str(x) for x in (cur.get("labels") or [])]
    old_nm = [str(n).strip().rstrip(".") for n in (cur.get("seriesNames") or [])]
    # 기존 계열 이름은 '10세 이하' 였다. 5세 구간으로 다시 묶으면 0~9세여서
    # 이름이 맞지 않는다. 자리만 맞춰 대조한다.
    pos = {("9세 이하" if n == "10세 이하" else n): i for i, n in enumerate(old_nm)}
    miss = [b for b in BANDS if b not in pos]
    if miss:
        raise SystemExit(f"차트에 없는 구간: {miss} (차트 계열 {old_nm})")

    mism = []
    for y in years:
        if y not in old_lab:
            continue
        i = old_lab.index(y)
        for b in BANDS:
            o = (cur["series"][pos[b]] or [])[i]
            if o is not None and round(o) != round(raw[y][b]):
                mism.append((y, b, o, raw[y][b]))
    print(f"KOSIS {TBL} 청산면 — {years[0]} ~ {years[-1]} ({len(years)}개월)")
    print(f"  구간 합과 계 대조 — 일치")
    if mism:
        print(f"  어긋남 {len(mism)}곳 — 아무것도 쓰지 않습니다.")
        for y, b, o, n in mism[:15]:
            print(f"    {y} {b}: 차트 {o} / KOSIS {n}")
        return 1
    print(f"  겹치는 구간 대조 — 일치 (차트 {len(old_lab)}개월)")
    add = [y for y in years if y > (old_lab[-1] if old_lab else "")]
    print(f"  새로 붙는 달 {len(add)}개: {add[:3]}{' …' if len(add) > 3 else ''} -> {add[-1] if add else '-'}")
    last = years[-1]
    print(f"  {last} 인구 {int(total[last])}명 — "
          + ", ".join(f"{b} {int(raw[last][b])}" for b in BANDS))

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0

    o = ov.setdefault(CID, {})
    o["id"] = CID
    o["title"] = "연천군 청산면 연령대별 인구"
    o["category"] = "지역"
    o["labels"] = years
    o["series"] = [[raw[y][b] for y in years] for b in BANDS]
    o["seriesNames"] = BANDS
    o["unit"] = "명"
    o["source"] = ("행정안전부 주민등록인구현황, 읍면동 5세별(KOSIS 표 DT_1B04005N) "
                   "가운데 연천군 청산면. 5세 구간을 열 살 단위로 더했다. "
                   f"{years[0]}~{last}. 단위: 명.")
    o["sourceUrl"] = URL
    o["notes"] = [
        "경기도 연천군 청산면입니다. 농어촌 기본소득 시범 지역이어서 "
        "인구가 어떻게 움직이는지를 보려고 그린 차트입니다.",
        "한 면 단위라 숫자가 작습니다. 20대가 400명대인데, 몇십 명이 들고 나는 "
        "것만으로도 선이 눈에 띄게 흔들립니다. 한두 달의 등락보다 방향을 "
        "보는 편이 낫습니다.",
        "5세 구간을 열 살 단위로 더한 값입니다. 더한 값이 표의 '계' 와 맞는 것을 "
        "모든 달에서 확인했습니다.",
        "첫 계열 이름을 '10세 이하'에서 '9세 이하'로 고쳤습니다. 원자료가 "
        "0~4세와 5~9세로 나뉘어 있어 실제로 담긴 것은 9세까지입니다.",
        "주민등록 기준입니다. 실제로 살고 있는 사람과 다를 수 있습니다. "
        "기본소득 같은 현금 지급 사업은 주소를 옮길 유인을 만들기도 해서, "
        "이 지표만으로 정책 효과를 판단하기는 어렵습니다.",
        "군 전체 인구는 따로 있습니다. 기본소득 실험 지자체의 인구 차트에서 "
        "연천군을 보면 됩니다.",
    ]
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
