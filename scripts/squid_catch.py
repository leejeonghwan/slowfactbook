#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""오징어 어획량. 전국과 시도별.

  python3 scripts/squid_catch.py            # 미리보기
  python3 scripts/squid_catch.py --apply

국가데이터처 「어업생산동향조사」 품종별 표(101/DT_1EW0004)에서 받는다. 이 표는
축이 넷이다. objL1 어업별, objL2 품종별, objL3 행정구역별, objL4 판매형태별.
하나라도 빠뜨리면 err 20 이 돌아온다.

품종 코드는 어업별 접두사가 붙어 있다. 같은 이름이 어업마다 다른 코드다.

  140418 살오징어(오징어)  연근해어업
  340030 오징어류          원양어업
  140403 갑오징어류        연근해어업

검산은 시도별 생산량을 모두 더한 값이 전국값과 맞는지 해마다 본다.

시도 구분을 '그 바다에서 잡혔다' 로 읽으면 안 된다. 어획 해역 기준인지
양륙지 기준인지는 공표 자료에서 확인하지 못했다. 바다가 없는 서울특별시에도
1990년부터 1992년까지 세 해 동안 272톤, 110톤, 30톤이 잡혀 있다. 다만 세 해에
400톤 남짓이라 이것만으로 기준을 단정할 수는 없다.

경기도는 서해에 접해 있어 오징어가 잡힌다. 1973년에 1,387톤이었다. 그 시기
수치는 인천이 경기도에서 갈라지기 전이라 지금의 인천 몫이 섞여 있다. 인천은
1981년부터 따로 집계된다. 울산도 같다. 1998년부터 따로 집계되고 그 전에는
경상남도에 들어 있었다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_1EW0004"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=" + TBL
Y0 = 1970

# 역대 누적 상위 여섯 곳과, 최근 상위권으로 올라온 충청남도.
PICK = [("부산광역시", "부산", "#c0322f"),
        ("경상북도", "경상북도", "#2f5e8e"),
        ("강원특별자치도", "강원", "#e8820c"),
        ("경상남도", "경상남도", "#6a8f3c"),
        ("전라남도", "전라남도", "#7a5ea8"),
        ("울산광역시", "울산", "#8a8a8a"),
        ("충청남도", "충청남도", "#1f9ba4")]


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


KEY = None


def pull(fishery, species, area="00"):
    y1 = datetime.datetime.now(KST).year
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={KEY}&format=json&jsonVD=Y&orgId=101&tblId={TBL}&prdSe=Y"
         f"&startPrdDe={Y0}&endPrdDe={y1}&itmId=T01"
         f"&objL1={fishery}&objL2={species}&objL3={area}&objL4=0")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"{species} {area} 응답이 표가 아닙니다: {str(d)[:160]}")
    out = {}
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        out.setdefault(x.get("C3_NM") or "계", {})[int(x["PRD_DE"])] = float(x["DT"])
    if not out:
        raise SystemExit(f"{species} {area} 가 비었습니다.")
    return out


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    KEY = envkey("KOSIS_API_KEY")
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    coast = pull("1", "140418")["계"]        # 연근해 살오징어
    ocean = pull("3", "340030")["계"]        # 원양 오징어류
    cuttle = pull("1", "140403")["계"]       # 연근해 갑오징어류
    reg = pull("1", "140418", "ALL")
    reg.pop("계", None)
    print(f"  연근해 살오징어 {len(coast)}년, 원양 오징어류 {len(ocean)}년, "
          f"갑오징어류 {len(cuttle)}년, 시도 {len(reg)}곳")

    # 검산 1. 시도 합계가 전국과 맞는가
    bad = []
    for y in sorted(coast):
        s = sum(v.get(y, 0.0) for v in reg.values())
        if abs(s - coast[y]) > max(1.0, coast[y] * 0.001):
            bad.append((y, round(s, 1), round(coast[y], 1)))
    if bad:
        raise SystemExit(f"시도 합계가 전국과 어긋납니다: {bad[:5]}")
    print(f"    검산 시도 합계: {len(coast)}년 모두 전국값과 일치")

    # 검산 2. 고른 시도가 여전히 누적 상위인가
    cum = {k: sum(v.values()) for k, v in reg.items()}
    top6 = [k for k, _ in sorted(cum.items(), key=lambda x: -x[1])[:6]]
    want = [p[0] for p in PICK]
    if set(top6) - set(want):
        raise SystemExit(f"누적 상위 여섯 곳이 바뀌었습니다. 빠진 곳: "
                         f"{sorted(set(top6) - set(want))}. PICK 를 손봐야 합니다.")
    miss = [k for k in want if k not in reg]
    if miss:
        raise SystemExit(f"응답에 없는 시도: {miss}")
    print(f"    검산 계열 선정: 누적 상위 여섯 곳이 모두 들어 있습니다")

    ys = sorted(set(coast) | set(ocean))
    gy = lambda m: [m.get(y) for y in ys]
    pc = max(coast, key=coast.get)
    po = max(ocean, key=ocean.get)
    lo = min(coast, key=coast.get)
    last = ys[-1]

    out = []
    out.append({
        "slide": "manual-squid-catch",
        "category": "식량",
        "title": "오징어 어획량",
        "vizType": "line", "unit": "톤",
        "labels": [str(y) for y in ys],
        "series": [gy(coast), gy(ocean)],
        "seriesNames": ["연근해 살오징어", "원양 오징어류"],
        "seriesColors": ["#c0322f", "#2f5e8e"],
        "source": (f"국가데이터처 어업생산동향조사 품종별 생산량. {ys[0]}~{last}년. "
                   f"단위: 톤."),
        "sourceUrl": URL,
        "notes": [
            f"우리 바다에서 잡는 살오징어는 {pc}년 {coast[pc]:,.0f}톤이 가장 많았고 "
            f"{lo}년 {coast[lo]:,.0f}톤까지 내려갔습니다. 정점의 "
            f"{coast[lo] / coast[pc] * 100:.0f}% 입니다. {last}년은 "
            f"{coast[last]:,.0f}톤으로 올라왔습니다.",
            f"원양에서 잡는 오징어류는 {po}년 {ocean[po]:,.0f}톤에서 {last}년 "
            f"{ocean[last]:,.0f}톤입니다. {last}년에는 원양이 연근해보다 "
            f"{ocean[last] / coast[last]:.1f}배 많습니다. 시장에서 파는 오징어의 "
            "상당 부분이 먼바다에서 잡혀 들어온 것입니다.",
            "두 계열은 같은 오징어가 아닙니다. 연근해는 살오징어 한 종이고, "
            "원양 오징어류는 여러 종을 묶은 분류입니다. 잡는 곳도 포클랜드 "
            "근해와 남미 서쪽 등으로 서로 다릅니다. 더해서 '국내 오징어 "
            "공급량' 으로 읽으면 안 됩니다. 수입량은 이 통계에 없습니다.",
            f"갑오징어류는 따로입니다. 연근해 기준으로 "
            f"{max(cuttle, key=cuttle.get)}년 "
            f"{cuttle[max(cuttle, key=cuttle.get)]:,.0f}톤이 가장 많았고 {last}년 "
            f"{cuttle[last]:,.0f}톤입니다. 살오징어와 다른 동물이라 이 차트에는 "
            "넣지 않았습니다.",
            "한 해의 오르내림이 큽니다. 자원량만이 아니라 조업일수, 금어기, "
            "유가, 인력 사정이 함께 작용합니다. 한 해 반등을 회복으로 읽기에는 "
            "이릅니다.",
        ],
        "updated": ymd,
    })

    ry = sorted(set().union(*[set(reg[p[0]]) for p in PICK]))
    ser = [[reg[p[0]].get(y) for y in ry] for p in PICK]
    r25 = {p[1]: reg[p[0]].get(ry[-1], 0.0) for p in PICK}
    others = sorted(((k, v.get(ry[-1], 0.0)) for k, v in reg.items()
                     if k not in [p[0] for p in PICK]), key=lambda x: -x[1])
    out.append({
        "slide": "manual-squid-region",
        "category": "식량",
        "title": "시도별 오징어 어획량",
        "vizType": "line", "unit": "톤",
        "labels": [str(y) for y in ry],
        "series": ser,
        "seriesNames": [p[1] for p in PICK],
        "seriesColors": [p[2] for p in PICK],
        "source": (f"국가데이터처 어업생산동향조사 품종별 지역별 생산량, 연근해어업 "
                   f"살오징어. {ry[0]}~{ry[-1]}년. 단위: 톤."),
        "sourceUrl": URL,
        "notes": [
            f"{ry[-1]}년은 " + ", ".join(f"{k} {v:,.0f}톤" for k, v in
                                       sorted(r25.items(), key=lambda x: -x[1]))
            + " 입니다.",
            f"한때 압도적이던 세 곳이 함께 주저앉았습니다. 부산은 "
            f"{max(reg['부산광역시'], key=reg['부산광역시'].get)}년 "
            f"{max(reg['부산광역시'].values()):,.0f}톤, 경상북도는 "
            f"{max(reg['경상북도'], key=reg['경상북도'].get)}년 "
            f"{max(reg['경상북도'].values()):,.0f}톤, 강원은 "
            f"{max(reg['강원특별자치도'], key=reg['강원특별자치도'].get)}년 "
            f"{max(reg['강원특별자치도'].values()):,.0f}톤이 정점이었습니다.",
            "시도 구분을 '그 바다에서 잡혔다' 로 읽으면 안 됩니다. 어획 해역 "
            "기준인지 양륙지 기준인지 공표 자료에서 확인하지 못했습니다. 바다가 "
            "없는 서울특별시에도 1990년부터 1992년까지 세 해 동안 272톤, 110톤, "
            "30톤이 잡혀 있습니다. 다만 세 해에 400톤 남짓이라 이것만으로 기준을 "
            "단정할 수는 없습니다.",
            "행정구역이 갈라진 것도 계열에 섞여 있습니다. 울산은 1998년부터 따로 "
            "집계되고 그 전에는 경상남도에 들어 있었습니다. 1997년까지 울산 선이 "
            "비어 있는 것은 자료가 없다는 뜻입니다. 인천도 1981년부터 따로 "
            "집계됩니다. 경기도의 1970년대 물량(1973년 1,387톤)에는 지금의 인천 "
            "몫이 섞여 있습니다. 경기도는 서해에 접해 있어 오징어가 잡히지만 "
            "2000년대 이후로는 0톤입니다.",
            "역대 누적 생산량 상위 여섯 곳과, 최근 상위권으로 올라온 충청남도를 "
            "넣었습니다. 나머지는 "
            + ", ".join(f"{k.replace('특별자치도', '').replace('광역시', '').replace('특별시', '')}"
                        f" {v:,.0f}톤" for k, v in others)
            + f" 입니다({ry[-1]}년).",
        ],
        "updated": ymd,
    })

    for it in out:
        print(f"  {it['title']:18s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]} 계열 {len(it['series'])}")
        for n, s in zip(it["seriesNames"], it["series"]):
            v = [x for x in s if x is not None]
            print(f"    {n:12s} {len(v):2d}년 최고 {max(v):9,.0f} 끝 {s[-1]:,.0f}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        old = by.get(it["slide"])
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
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
