#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주종별 국내판매액. 식품의약품안전처 생산실적.

  python3 scripts/liquor_sales.py            # 미리보기
  python3 scripts/liquor_sales.py --apply

국가데이터처 포털 145/DT_145003_A027 「주류 품목별 국내판매액 변동현황」.
원천은 식품의약품안전처 「식품및식품첨가물생산실적」 이다. 2018년부터 있다.

조심할 것이 둘이다.

하나. 국내에서 만든 술만 잡힌다. 수입 주류는 빠진다. 그래서 위스키 점유율이
0.2% 안팎으로 나오는데, 이것은 국내 제조 위스키만이고 최근 몇 해의 위스키
수요와는 다른 이야기다.

둘. '주정' 이 계에 들어 있다. 주정은 희석식 소주의 원료다. 소주 판매액과
겹치는 성격이 있어 주종별 비중을 읽을 때 주의해야 한다. 이 어댑터는 주정을
따로 떼어 보여 준다.

검산은 품목을 모두 더한 값이 표의 '계' 와 맞는지 해마다 본다. 표가 함께 주는
점유율과 판매액으로 따로 계산한 점유율이 맞는지도 본다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_145003_A027"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=145&tblId=" + TBL
PARTS = ["탁주", "약주", "청주", "맥주", "과실주", "소주", "위스키",
         "브랜디", "일반증류주", "리큐르", "기타주류", "주정"]
STACK = [("맥주", "#d4a15c"), ("소주", "#2a5ca8"), ("탁주", "#6a8f3c"),
         ("주정", "#9a9a9a"), ("그 밖의 주종", "#c0322f")]
LINES = [("맥주", "#d4a15c"), ("소주", "#2a5ca8"), ("탁주", "#6a8f3c")]


def envkey(name):
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{name} 가 필요합니다(환경변수 또는 .env).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId=145&tblId={TBL}&prdSe=Y"
         f"&startPrdDe=2018&endPrdDe={now.year}&itmId=T001+T002&objL1=ALL")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"응답이 표가 아닙니다: {str(d)[:160]}")
    sale, share, unit = {}, {}, None
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        tgt = sale if x["ITM_NM"] == "국내판매액" else share
        tgt.setdefault(x["C1_NM"], {})[int(x["PRD_DE"])] = float(x["DT"])
        if x["ITM_NM"] == "국내판매액":
            unit = x.get("UNIT_NM")
    if unit != "천원":
        raise SystemExit(f"판매액 단위가 '천원' 이 아닙니다: {unit!r}")
    miss = [k for k in PARTS + ["계"] if k not in sale]
    if miss:
        raise SystemExit(f"응답에 없는 품목: {miss}")
    ys = sorted(set.intersection(*[set(sale[k]) for k in PARTS + ["계"]]))
    if len(ys) < 5:
        raise SystemExit(f"받은 해가 {len(ys)}년뿐입니다.")

    # 검산 1. 품목 합계가 '계' 와 맞는가
    bad = [(y, round(sum(sale[k][y] for k in PARTS) / 1e6, 1), round(sale["계"][y] / 1e6, 1))
           for y in ys
           if abs(sum(sale[k][y] for k in PARTS) - sale["계"][y]) > sale["계"][y] * 0.002]
    if bad:
        raise SystemExit(f"품목 합계가 '계' 와 어긋납니다: {bad[:4]}")
    print(f"    검산 합계: {len(ys)}년 모두 품목 합이 '계' 와 0.2% 안")

    # 검산 2. 표가 주는 점유율과 직접 계산한 점유율이 맞는가
    bad2 = []
    for k in PARTS:
        for y in ys:
            if y in (share.get(k) or {}):
                got = sale[k][y] / sale["계"][y] * 100
                if abs(got - share[k][y]) > 0.06:
                    bad2.append((k, y, share[k][y], round(got, 2)))
    if bad2:
        raise SystemExit(f"점유율이 계산값과 어긋납니다: {bad2[:4]}")
    print(f"    검산 점유율: 표의 값과 직접 계산한 값이 모두 0.06%p 안")

    jo = lambda k, y: round(sale[k][y] / 1e9, 2)            # 천원 -> 조 원
    etc = {y: round((sale["계"][y] - sum(sale[k][y] for k, _ in STACK[:-1])) / 1e9, 2)
           for y in ys}
    last = ys[-1]
    tot = {y: round(sale["계"][y] / 1e9, 2) for y in ys}
    liq = share["리큐르"]

    out = [{
        "slide": "manual-liquor-sales",
        "category": "소비와 물가",
        "title": "주종별 국내 주류 판매액",
        "vizType": "stacked_bar", "unit": "조 원",
        "labels": [str(y) for y in ys],
        "series": [[jo(k, y) for y in ys] if k != "그 밖의 주종"
                   else [etc[y] for y in ys] for k, _ in STACK],
        "seriesNames": [k for k, _ in STACK],
        "seriesColors": [c for _, c in STACK],
        "source": (f"국가데이터처 주류 품목별 국내판매액 변동현황(식품의약품안전처 "
                   f"식품및식품첨가물생산실적). {ys[0]}~{last}년. 단위: 조 원."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년 전체 {tot[last]}조 원입니다. 맥주 {jo('맥주', last)}조 원, "
            f"소주 {jo('소주', last)}조 원, 탁주 {jo('탁주', last)}조 원 순입니다. "
            f"{ys[0]}년 {tot[ys[0]]}조 원에서 "
            f"{(tot[last] / tot[ys[0]] - 1) * 100:+.0f}% 입니다.",
            "국내에서 만든 술만 잡힙니다. 수입 주류는 빠집니다. 위스키 판매액이 "
            f"{last}년 {sale['위스키'][last] / 1e6:,.0f}억 원으로 작게 나오는 것은 "
            "국내 제조 위스키만 세기 때문입니다. 최근 몇 해의 위스키 수요와는 "
            "다른 이야기입니다.",
            "'주정' 이 따로 들어 있습니다. 주정은 희석식 소주의 원료라 소주 "
            "판매액과 겹치는 성격이 있습니다. 더해서 '국민이 마신 술의 값' 으로 "
            "읽으면 안 됩니다.",
            "제조사가 판 금액이지 소비자가 낸 값이 아닙니다. 음식점과 소매점의 "
            "마진과 세금이 더 붙습니다. 명목 금액이라 물가 영향도 들어 있습니다.",
            f"작지만 빠르게 큰 주종이 있습니다. 리큐르는 {ys[0]}년 "
            f"{sale['리큐르'][ys[0]] / 1e6:,.0f}억 원에서 "
            f"{last}년 {sale['리큐르'][last] / 1e6:,.0f}억 원이 됐습니다. "
            "일반증류주도 같은 기간 "
            f"{sale['일반증류주'][ys[0]] / 1e6:,.0f}억 원에서 "
            f"{sale['일반증류주'][last] / 1e6:,.0f}억 원으로 늘었습니다.",
        ],
        "updated": ymd,
    }, {
        "slide": "manual-liquor-share",
        "category": "소비와 물가",
        "title": "주종별 국내 주류 판매액 비중",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in ys],
        "series": [[round(share[k][y], 2) for y in ys] for k, _ in LINES],
        "seriesNames": [k for k, _ in LINES],
        "seriesColors": [c for _, c in LINES],
        "source": (f"국가데이터처 주류 품목별 국내판매액 변동현황(식품의약품안전처 "
                   f"식품및식품첨가물생산실적). {ys[0]}~{last}년. 단위: %."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년 맥주 {share['맥주'][last]}%, 소주 {share['소주'][last]}%, "
            f"탁주 {share['탁주'][last]}% 입니다. {ys[0]}년에는 각각 "
            f"{share['맥주'][ys[0]]}%, {share['소주'][ys[0]]}%, "
            f"{share['탁주'][ys[0]]}% 였습니다. 맥주가 벌리고 소주가 좁히는 "
            "모양입니다.",
            "분모에 주정이 들어 있습니다. 주정은 희석식 소주의 원료로 전체의 "
            f"{share['주정'][last]}%를 차지합니다. 주정을 빼고 계산하면 세 주종의 "
            "비중은 이보다 조금씩 높아집니다.",
            "국내에서 만든 술만 잡힙니다. 수입 주류는 빠집니다.",
            "금액 기준입니다. 마신 양이 아닙니다. 주종마다 단가가 달라 양으로 "
            "보면 순서가 달라질 수 있습니다.",
        ],
        "updated": ymd,
    }]

    for it in out:
        print(f"\n  {it['title']} ({it['vizType']}) {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]}")
        for nm, s in zip(it["seriesNames"], it["series"]):
            print(f"    {nm:12s} {s[0]} ... {s[-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        o = by.get(it["slide"])
        if o:
            keep = {k: o[k] for k in ("id",) if k in o}
            o.clear(); o.update(it); o.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
