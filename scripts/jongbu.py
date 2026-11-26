#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주택분 종합부동산세 — 개인과 법인.

표는 국세청 국세통계 7.2.1 주택분 종합부동산세 현황Ⅰ
(KOSIS 133/TX_13301_A063). 2005년부터이고 납세자유형이 개인과 법인으로
갈려 있다. 인원은 명, 세액은 백만 원이라 억 원으로 고쳐 쓴다.

고지와 결정을 섞지 않는다 — 이 차트가 다루는 핵심이다.
  해마다 11월에 재정경제부가 '고지' 인원과 세액을 발표하고, 이듬해에
  국세청이 '결정' 값을 낸다. 고지한 뒤 합산배제 같은 특례 신청을 받으면
  줄어들기 때문에 결정이 고지보다 작다. 2025년 주택분이 고지 1조 7,136억,
  결정 1조 3,089억이다. 4천억 넘게 차이 난다.
  이 차트는 전 구간이 결정 기준이다. 그래서 가장 최근 해는 늘 한 해 전이다.
  올해 고지 숫자는 비고에만 적는다.

c0270 과 무엇이 다른가.
  c0270 은 주택분과 토지분을 합친 것이고 마지막 해만 고지 기준이다.
  여기는 주택분만, 전 구간 결정 기준이다. 두 차트의 숫자를 견주면 안 된다.
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

ORG, TBL = "133", "TX_13301_A063"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=133"
       "&tblId=TX_13301_A063")
SRC = "국세청 국세통계 주택분 종합부동산세 현황"
OBJ = {"합계": "15133GBB002", "개인": "15133GBB1402",
       "법인": "15133GBB1401"}
ITM = {"인원": "16133AAD1", "결정세액": "16133AAD7"}
UP, ORANGE = "#2a5ca8", "#e8820c"

# 알려진 값으로 거는 빗장. 2021년 주택분 결정세액 4.41조.
GATE21 = 4408532          # 백만 원
# 2026년 11월 26일 고지 (재정경제부). 비고에만 쓴다.
N26 = {"인원": 726000, "세액": 23185, "개인세액": 13330,
       "법인세액": 9855, "개인평균": 1994000, "작년개인평균": 1606000,
       "1주택인원": 231000, "1주택세액": 3660}


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


def pull(key, obj, tries=3):
    p = {"method": "getList", "apiKey": key, "orgId": ORG, "tblId": TBL,
         "itmId": "+".join(ITM.values()) + "+", "objL1": obj + "+",
         "format": "json", "jsonVD": "Y", "prdSe": "Y",
         "startPrdDe": "2005", "endPrdDe": "2099"}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + urllib.parse.urlencode(p, safe="+"))
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(u, timeout=90))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}")
            out = {}
            for r in d:
                if r.get("DT") in (None, "", "-"):
                    continue
                out.setdefault(r["ITM_ID"], {})[r["PRD_DE"]] = float(r["DT"])
            if len(out) < 2:
                raise RuntimeError("항목이 모자라다")
            return out
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"{TBL} {obj} 를 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    got = {}
    for nm, obj in OBJ.items():
        d = pull(key, obj)
        got[nm] = {k2: d[v] for k2, v in ITM.items() if v in d}
        time.sleep(0.4)
    ys = sorted(got["합계"]["인원"])
    print(f"    받음: {len(ys)}해 {ys[0]}~{ys[-1]}")

    # 검산 1. 2021년 결정세액이 알려진 값과 같은가
    v21 = got["합계"]["결정세액"].get("2021")
    if not v21 or abs(v21 - GATE21) > 1:
        print(f"  검산 실패: 2021년 결정세액이 {v21} 다 ({GATE21} 여야 한다)")
        return 1
    print(f"    검산 빗장: 2021년 주택분 결정세액 {v21/1e6:.2f}조로 일치")

    # 검산 2. 개인 + 법인 = 합계
    bad = []
    for key2 in ITM:
        for y in ys:
            s = (got["개인"][key2].get(y, 0) + got["법인"][key2].get(y, 0))
            t = got["합계"][key2].get(y, 0)
            if t and abs(s - t) > max(t * 0.001, 1):
                bad.append((y, key2, s, t))
    if bad:
        print(f"  검산 실패: 개인+법인이 합계와 다르다 {bad[:3]}")
        return 1
    print(f"    검산 합계: {len(ys)}해 모두 개인+법인 = 합계")

    # 검산 3. 지난해 개인 결정세액이 올해 발표의 역산과 가까운가
    #         (고지와 결정은 다르지만 개인 쪽은 특례가 적어 비슷해야 한다)
    prev = str(int(ys[-1]))
    ind_now = got["개인"]["결정세액"][prev] / 100        # 억 원
    ind_notice = N26["개인세액"] / 1.727                 # 올해 발표의 역산
    gap = abs(ind_now / ind_notice - 1)
    if gap > 0.05:
        print(f"  검산 실패: {prev}년 개인 결정 {ind_now:,.0f}억이 "
              f"고지 역산 {ind_notice:,.0f}억과 {gap:.1%} 차이")
        return 1
    print(f"    검산 교차: {prev}년 개인 결정세액 {ind_now:,.0f}억이 "
          f"올해 발표로 역산한 고지 {ind_notice:,.0f}억과 {gap:.1%} 차이")

    ind = [round(got["개인"]["결정세액"][y] / 100) for y in ys]
    cor = [round(got["법인"]["결정세액"][y] / 100) for y in ys]
    ppl = [int(got["합계"]["인원"][y]) for y in ys]
    last = ys[-1]
    print(f"    {last}년: 개인 {ind[-1]:,}억, 법인 {cor[-1]:,}억, "
          f"인원 {ppl[-1]:,}명")

    item = {
        "slide": "manual-jongbu-house", "category": "조세와 재정",
        "title": "주택분 종합부동산세, 개인과 법인.",
        "vizType": "combo", "stacked": True, "unit": "억 원, 명",
        "labels": list(ys),
        "series": [ind, cor, ppl],
        "seriesNames": ["개인 결정세액(억 원).", "법인 결정세액(억 원).",
                        "인원(명)."],
        "seriesKinds": ["bar", "bar", "line"],
        "seriesAxes": [0, 0, 1],
        "seriesColors": [UP, ORANGE, "#9b9b9b"],
        "source": (f"{SRC}(KOSIS 133/{TBL}). 결정 기준, "
                   f"{ys[0]}~{last}년. 단위: 억 원, 명."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년 주택분 결정세액은 개인 {ind[-1]:,}억 원, 법인 "
            f"{cor[-1]:,}억 원입니다. 인원은 {ppl[-1]:,}명입니다.",
            "법인은 수가 5만 명대로 거의 늘지 않는데 세액은 개인과 맞먹는 "
            "해가 많습니다. 2021년에는 법인이 1조 2,103억 원으로 전체의 "
            "27%였습니다. 인원과 세액을 같은 눈으로 보면 안 되는 이유입니다.",
            "결정 기준입니다. 해마다 11월에 고지한 뒤 합산배제 같은 특례 "
            "신청을 받으면 줄어들기 때문에 결정이 고지보다 작습니다. "
            f"{last}년 주택분이 고지 1조 7,136억 원, 결정 "
            f"{ind[-1]+cor[-1]:,}억 원입니다.",
            f"2026년은 아직 결정 전입니다. 2026년 11월 26일 고지 기준으로 "
            f"주택분은 {N26['인원']:,}명에 {N26['세액']:,}억 원이고, "
            f"그 가운데 개인이 {N26['개인세액']:,}억 원, 법인이 "
            f"{N26['법인세액']:,}억 원입니다. 개인 세액은 한 해 전보다 "
            "72.7% 늘었고 법인은 4.6% 느는 데 그쳤습니다.",
            f"2026년 고지 기준 개인 1인당 평균은 "
            f"{N26['개인평균']:,}원으로 한 해 전 "
            f"{N26['작년개인평균']:,}원보다 높습니다. 1세대 1주택자는 "
            f"{N26['1주택인원']:,}명에 {N26['1주택세액']:,}억 "
            "원입니다.",
            "토지분은 들어 있지 않습니다. 주택분과 토지분을 합친 추이는 "
            "따로 있습니다.",
        ],
        "updated": ymd,
    }

    print(f"\n  {item['slide']} {len(ys)}점 {ys[0]}~{last} | 계열 3")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    prev_it = idx.get(item["slide"])
    if prev_it:
        keep = {k: prev_it[k] for k in ("id",) if k in prev_it}
        prev_it.clear()
        prev_it.update(item)
        prev_it.update(keep)
    else:
        doc["items"].append(item)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print("-> data/manual.json 에 1장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
