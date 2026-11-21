#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""산업도시 성비 — 인구총조사와 주민등록, 두 기준.

원래 c1962 는 출처가 "2022년 기준" 한 줄뿐이었다. 두 통계로 되짚어
보니 2022년이 아니라 **2020년 인구총조사 등록센서스의 내국인 성비**
였다. 전국 109.7, 울산 136.2, 여수 153.7, 거제 153.3 이 소수점까지
맞는다. 그걸 GATE_2020 으로 박아 두고, 기준이 흔들리면 멈춘다.

두 기준은 다른 것을 센다.
  인구총조사(등록센서스) DT_1IN1503, 2015~  : 상주인구. 외국인 포함
      (T03 총인구 성비)과 내국인(T13 성비)이 따로 나온다.
  주민등록           DT_1B04006, 2008~     : 내국인만. 대신 18년치다.
산업도시는 외국인 노동자가 많아 두 기준의 차이가 바로 그 몫이다.

함정 — 행정구역 코드가 표마다 다르다.
  DT_1IN1503: 울산 26, 여수 36020, 포항 37010, 거제 38090, 창원 38110
  DT_1B04006: 울산 31, 여수 46130, 포항 47110, 거제 48310, 창원 48120
한쪽 코드를 다른 쪽에 쓰면 엉뚱한 지역이 조용히 돌아온다. 실제로
울산 자리에 31 을 넣었더니 성비 111.8 인 다른 지역이 왔다. 그래서
받아 온 지역 이름을 반드시 대조한다.
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CEN = ("DT_1IN1503", {"전국": "00", "울산광역시": "26", "여수시": "36020",
                      "포항시": "37010", "거제시": "38090",
                      "통합창원시": "38110"})
REG = ("DT_1B04006", {"전국": "00", "울산광역시": "31", "여수시": "46130",
                      "포항시": "47110", "거제시": "48310",
                      "통합창원시": "48120"})
ORDER = ["전국", "울산광역시", "여수시", "포항시", "거제시", "통합창원시"]
COLS = ["#9a9a9a", "#2a5ca8", "#4a7c59", "#e8820c", "#c0322f", "#8a6fb0"]
SRC_C = "국가데이터처 인구총조사(등록센서스, KOSIS 101/DT_1IN1503)"
SRC_R = "행정안전부 주민등록인구현황(KOSIS 101/DT_1B04006)"
URL_C = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1IN1503"
URL_R = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B04006"

# 2020년 인구총조사 내국인 성비, 20~24세. 기존 차트에 적혀 있던 값이다.
GATE_2020 = {"전국": 109.7, "울산광역시": 136.2, "여수시": 153.7,
             "거제시": 153.3}
BAND20 = "20 - 24세"
# 받아 온 지역 이름을 대조할 때 쓸 조각. '통합창원시' 처럼 팩트북에서
# 부르는 이름과 통계의 이름이 다른 경우가 있다.
NAMECHK = {"전국": "전국", "울산광역시": "울산", "여수시": "여수",
           "포항시": "포항", "거제시": "거제", "통합창원시": "창원"}


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


def get(url, tries=3, timeout=120):
    last = None
    for i in range(tries):
        try:
            d = json.load(urllib.request.urlopen(url, timeout=timeout))
            if isinstance(d, dict):
                raise RuntimeError(f"KOSIS err {d.get('err')}: {d.get('errMsg')}")
            return d
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"받지 못했다: {last}")


def band_of(name):
    """연령 이름을 5세 구간 시작 나이로 바꾼다. 아니면 None."""
    s = str(name)
    if "합계" in s or s == "계":
        return None
    if "100" in s and "이상" in s:
        return 100
    m = re.match(r"(\d+)\s*[~\-]\s*(\d+)\s*세$", s.replace(" ", ""))
    if m and int(m.group(2)) - int(m.group(1)) == 4:
        return int(m.group(1))
    m = re.match(r"(\d+)세$", s)        # 1세별 표는 합쳐서 쓴다
    if m:
        return int(m.group(1)) // 5 * 5
    return None


def label(b):
    return "100세이상" if b == 100 else f"{b} - {b+4}세"


def census(key, y0, y1):
    """{(연도, 지역, 밴드): (총인구성비, 내국인성비)}"""
    tbl, area = CEN
    out = {}
    for nm, cd in area.items():
        p = {"method": "getList", "apiKey": key, "itmId": "T03+T13",
             "objL1": cd, "objL2": "ALL", "format": "json", "jsonVD": "Y",
             "prdSe": "Y", "startPrdDe": str(y0), "endPrdDe": str(y1),
             "orgId": "101", "tblId": tbl}
        d = get("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
                + urllib.parse.urlencode(p))
        got = {str(r.get("C1_NM")) for r in d}
        if not any(NAMECHK[nm] in g for g in got):
            raise RuntimeError(f"{nm}({cd}) 자리에 {sorted(got)[:3]} 가 왔다")
        for r in d:
            if r.get("DT") in (None, "", "-"):
                continue
            b = band_of(r.get("C2_NM"))
            if b is None or len(str(r.get("C2"))) > 3:
                continue
            k = (r["PRD_DE"], nm, b)
            cur = list(out.get(k, (None, None)))
            cur[0 if r["ITM_ID"] == "T03" else 1] = round(float(r["DT"]), 1)
            out[k] = tuple(cur)
        time.sleep(0.6)
    return out


def resident(key, y0, y1):
    """{(연도, 지역, 밴드): 성비} — 남/여 를 직접 나눈다."""
    tbl, area = REG
    raw = {}
    for nm, cd in area.items():
        p = {"method": "getList", "apiKey": key, "itmId": "T3+T4",
             "objL1": cd, "objL2": "ALL", "format": "json", "jsonVD": "Y",
             "prdSe": "Y", "startPrdDe": str(y0), "endPrdDe": str(y1),
             "orgId": "101", "tblId": tbl}
        d = get("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
                + urllib.parse.urlencode(p), timeout=240)
        got = {str(r.get("C1_NM")) for r in d}
        if not any(NAMECHK[nm] in g for g in got):
            raise RuntimeError(f"{nm}({cd}) 자리에 {sorted(got)[:3]} 가 왔다")
        for r in d:
            if r.get("DT") in (None, "", "-"):
                continue
            b = band_of(r.get("C2_NM"))
            if b is None:
                continue
            k = (r["PRD_DE"], nm, b, r["ITM_ID"])
            raw[k] = raw.get(k, 0) + int(float(r["DT"]))
        time.sleep(0.6)
    out = {}
    for (y, nm, b, it) in list(raw):
        if it != "T3":
            continue
        m, f = raw.get((y, nm, b, "T3")), raw.get((y, nm, b, "T4"))
        if m and f:
            out[(y, nm, b)] = round(m / f * 100, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    if not key:
        print("KOSIS_API_KEY 가 없다")
        return 2
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    print("  인구총조사 받는 중...")
    cen = census(key, 2015, 2025)
    print("  주민등록 받는 중...")
    reg = resident(key, 2008, 2025)

    cy = sorted({k[0] for k in cen})
    ry = sorted({k[0] for k in reg})
    bands = sorted({k[2] for k in cen})
    last_c, last_r = cy[-1], ry[-1]

    # ── 검산 1. 2020년 내국인 성비가 옛 차트 값과 같은가
    for nm, want in GATE_2020.items():
        got = (cen.get(("2020", nm, 20)) or (None, None))[1]
        if got != want:
            print(f"  검산 실패 2020 {nm} 20~24세: 옛 차트 {want} vs {got}")
            return 1
    print(f"    검산 기준: 2020년 내국인 성비 {len(GATE_2020)}곳이 "
          "옛 차트 값과 일치(= 옛 차트는 2020년 등록센서스였다)")

    # ── 검산 2. 지역 이름 확인은 받을 때 했고, 여기서는 값의 상식 범위
    # 100세 이상은 사람 수가 몇 명이라 성비가 0 이나 55.6 처럼 튄다.
    # 실제 값이므로 막지 않되, 범위 검산에서는 빼고 따로 센다.
    # 고령 구간은 성비가 원래 낮다(90대는 20 아래). 100세 이상은 사람
    # 수가 몇 명이라 0 이나 55.6 처럼 튄다. 둘 다 실제 값이므로 막지
    # 않고, 전 구간은 0~400 으로만 거르고 20~24세만 따로 조인다.
    bad = [(y, nm, b, v[1]) for (y, nm, b), v in cen.items()
           if v[1] is not None and not 0 <= v[1] <= 400]
    if bad:
        print(f"  검산 실패: 말이 안 되는 성비 {bad[:3]}")
        return 1
    bad20 = [(y, nm, v[1]) for (y, nm, b), v in cen.items()
             if b == 20 and v[1] is not None and not 80 <= v[1] <= 300]
    if bad20:
        print(f"  검산 실패: 20~24세 성비가 범위 밖 {bad20[:3]}")
        return 1
    n100 = sum(1 for (y, nm, b), v in cen.items()
               if b == 100 and v[1] == 0)
    print(f"    검산 범위: 전 구간 0~400 안, 20~24세는 80~300 안 "
          f"(100세 이상은 남성이 0명인 칸이 {n100}개)")

    # ── 검산 3. 두 기준이 같은 해에 터무니없이 다르지 않은가
    gap = []
    for nm in ORDER:
        for y in ("2020", last_c):
            c = (cen.get((y, nm, 20)) or (None, None))[1]
            r = reg.get((y, nm, 20))
            if c and r:
                gap.append((nm, y, round(abs(c - r), 1)))
    # 둘 다 '내국인'인데도 산업도시에서는 크게 벌어진다. 주민등록은
    # 주소지를, 등록센서스는 상주인구를 센다. 조선소 도시에는 주소를
    # 옮기지 않고 와서 사는 사람이 많다. 그 몫이 그대로 격차가 된다.
    # 그래서 막지 않고 적어 둔다. 다만 60 을 넘으면 코드를 잘못 넣어
    # 엉뚱한 지역을 받아 온 쪽을 의심해야 하므로 멈춘다.
    worst = max(gap, key=lambda x: x[2])
    if worst[2] > 60:
        print(f"  검산 실패: 두 기준 차이가 {worst} 로 너무 크다")
        return 1
    nat = [g for g in gap if g[0] == "전국"]
    print(f"    검산 대조: 두 기준의 20~24세 차이는 전국이 "
          f"{min(n[2] for n in nat)}~{max(n[2] for n in nat)}, "
          f"가장 큰 곳이 {worst[0]} {worst[1]}년 {worst[2]}")

    out, ovr = [], {}

    # ── 1 c1962 연령대별 성비(인구총조사 내국인, 최신 연도)
    ser = [[(cen.get((last_c, nm, b)) or (None, None))[1] for b in bands]
           for nm in ORDER]
    g = {nm: (cen.get((last_c, nm, 20)) or (None, None))[1] for nm in ORDER}
    top = max((nm for nm in ORDER if nm != "전국"), key=lambda n: g[n] or 0)
    ovr["c1962"] = {
        "id": "c1962", "category": "지역",
        "title": "산업도시의 연령대별 남녀 성비",
        "vizType": "line", "unit": "여자 100명당 남자",
        "labels": [label(b) for b in bands],
        "series": ser, "seriesNames": list(ORDER), "seriesColors": COLS,
        "highlight": "거제시",
        "source": (f"{SRC_C}. {last_c}년, 내국인 기준. 여자 100명당 남자 수. "
                   "조선, 석유화학, 철강 산업도시 다섯 곳과 전국 비교."),
        "sourceUrl": URL_C,
        "notes": [
            f"{last_c}년 20~24세 성비는 {top} 가 {g[top]} 로 가장 높습니다. "
            f"전국은 {g['전국']} 입니다.",
            "20대에 솟았다가 30대부터 내려오는 모양이 다섯 도시에 "
            "공통으로 나타납니다. 조선소와 공장이 젊은 남성을 끌어모으고, "
            "여성은 같은 나이대에 그만큼 들어오지 않습니다.",
            "거제시는 40대 후반과 50대 초반에서도 전국보다 높습니다. "
            "다른 네 도시는 그 구간에서 전국과 비슷하거나 낮습니다.",
            "내국인 기준입니다. 외국인을 넣으면 산업도시의 성비는 더 "
            "올라갑니다. 「산업도시 성비, 내국인과 외국인 포함」을 "
            "함께 보십시오.",
            "전에는 '2022년 기준'이라고 적혀 있었는데 2020년 값이었습니다. "
            f"2020년 20~24세 성비가 전국 {GATE_2020['전국']}, 거제 "
            f"{GATE_2020['거제시']} 로 옛 차트와 소수점까지 같습니다. "
            f"{last_c}년으로 다시 세웠습니다.",
        ],
        "updated": ymd,
    }

    # ── 2 20대 초반 성비 추이(인구총조사 내국인)
    t2 = [[(cen.get((y, nm, 20)) or (None, None))[1] for y in cy]
          for nm in ORDER]
    out.append({
        "slide": "manual-sexratio-trend", "category": "지역",
        "title": "산업도시 20대 초반 성비 추이",
        "vizType": "line", "unit": "여자 100명당 남자",
        "labels": list(cy), "series": t2,
        "seriesNames": list(ORDER), "seriesColors": COLS,
        "source": (f"{SRC_C}. {cy[0]}~{cy[-1]}년, 20~24세, 내국인 기준. "
                   "여자 100명당 남자 수."),
        "sourceUrl": URL_C,
        "notes": [
            f"거제시는 {cy[0]}년 {t2[ORDER.index('거제시')][0]} 에서 "
            f"{cy[-1]}년 {t2[ORDER.index('거제시')][-1]} 로 올랐습니다. "
            f"전국은 {t2[0][0]} 에서 {t2[0][-1]} 로 거의 그대로입니다.",
            "전국이 평평한데 산업도시만 올라갑니다. 성비가 전국적으로 "
            "벌어진 것이 아니라 이 도시들에서 벌어졌다는 뜻입니다.",
            "20~24세만 잘라 본 것입니다. 연령대별 모양은 「산업도시의 "
            "연령대별 남녀 성비」에 있습니다.",
            "내국인 기준입니다.",
        ],
        "updated": ymd,
    })

    # ── 3 내국인과 외국인 포함
    gj = "거제시"
    tot = [(cen.get((y, gj, 20)) or (None, None))[0] for y in cy]
    dom = [(cen.get((y, gj, 20)) or (None, None))[1] for y in cy]
    out.append({
        "slide": "manual-sexratio-foreign", "category": "지역",
        "title": "거제시 20대 초반 성비, 내국인과 외국인 포함",
        "vizType": "line", "unit": "여자 100명당 남자",
        "labels": list(cy), "series": [tot, dom],
        "seriesNames": ["외국인 포함", "내국인만"],
        "seriesColors": ["#c0322f", "#9a9a9a"],
        "source": (f"{SRC_C}. {cy[0]}~{cy[-1]}년, 20~24세. "
                   "여자 100명당 남자 수."),
        "sourceUrl": URL_C,
        "notes": [
            f"{cy[-1]}년 외국인을 넣으면 {tot[-1]}, 내국인만 보면 "
            f"{dom[-1]} 입니다. 차이가 {round(tot[-1]-dom[-1],1)} 입니다.",
            f"{cy[0]}년에는 차이가 {round(tot[0]-dom[0],1)} 였습니다. "
            "두 선이 벌어진 만큼이 외국인 노동자의 몫입니다.",
            "주민등록 통계는 내국인만 세기 때문에 이 격차가 보이지 "
            "않습니다. 산업도시를 볼 때 기준을 고르는 일이 그대로 "
            "결론을 바꿉니다.",
            "등록센서스의 상주인구 기준입니다.",
        ],
        "updated": ymd,
    })

    # ── 4 주민등록 기준 연령대별(더 긴 시계열의 기준)
    rb = sorted({k[2] for k in reg})
    out.append({
        "slide": "manual-sexratio-reg", "category": "지역",
        "title": "산업도시의 연령대별 남녀 성비(주민등록)",
        "vizType": "line", "unit": "여자 100명당 남자",
        "labels": [label(b) for b in rb],
        "series": [[reg.get((last_r, nm, b)) for b in rb] for nm in ORDER],
        "seriesNames": list(ORDER), "seriesColors": COLS,
        "highlight": "거제시",
        "source": (f"{SRC_R}. {last_r}년. 여자 100명당 남자 수. "
                   "주민등록은 내국인만 집계합니다."),
        "sourceUrl": URL_R,
        "notes": [
            "주민등록 기준입니다. 인구총조사로 그린 「산업도시의 "
            "연령대별 남녀 성비」와 같은 해라도 숫자가 다릅니다. "
            "주민등록은 주소지를 세고 등록센서스는 상주인구를 셉니다.",
            "주민등록에는 외국인이 들어가지 않습니다. 산업도시에서는 "
            "그 몫이 작지 않습니다.",
            "대신 주민등록은 2008년부터 해마다 있어 시계열이 깁니다. "
            "「산업도시 20대 초반 성비 추이(주민등록)」를 보십시오.",
        ],
        "updated": ymd,
    })

    # ── 5 주민등록 기준 20대 초반 추이(2008~)
    t5 = [[reg.get((y, nm, 20)) for y in ry] for nm in ORDER]
    gi = ORDER.index("거제시")
    low = min((v, ry[i]) for i, v in enumerate(t5[gi]) if v)
    high = max((v, ry[i]) for i, v in enumerate(t5[gi]) if v)
    out.append({
        "slide": "manual-sexratio-reg-trend", "category": "지역",
        "title": "산업도시 20대 초반 성비 추이(주민등록)",
        "vizType": "line", "unit": "여자 100명당 남자",
        "labels": list(ry), "series": t5,
        "seriesNames": list(ORDER), "seriesColors": COLS,
        "source": (f"{SRC_R}. {ry[0]}~{ry[-1]}년, 20~24세. "
                   "여자 100명당 남자 수. 내국인만."),
        "sourceUrl": URL_R,
        "notes": [
            f"거제시는 {low[1]}년 {low[0]} 이 가장 낮고 {high[1]}년 "
            f"{high[0]} 이 가장 높습니다. {ry[-1]}년은 {t5[gi][-1]} 입니다.",
            f"{ry[0]}년부터 {ry[-1]}년까지 18년입니다. 2016년 조선업 "
            "구조조정 전후가 모두 들어갑니다.",
            "주민등록 기준이라 외국인은 빠져 있습니다. 같은 기간을 "
            "외국인까지 넣어 보려면 「거제시 20대 초반 성비, 내국인과 "
            "외국인 포함」을 보십시오. 그쪽은 2015년부터입니다.",
        ],
        "updated": ymd,
    })

    print(f"  c1962 {len(bands)}칸 {last_c}년 (overrides)")
    for it in out:
        print(f"  {it['title'][:28]:30s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    o = json.load(open(ovp, encoding="utf-8"))
    for k, v in ovr.items():
        o.setdefault(k, {}).update(v)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(o, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(ovp, encoding="utf-8"))
    print(f"-> data/overrides.json 에 {', '.join(ovr)} 를 반영했습니다.")

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
