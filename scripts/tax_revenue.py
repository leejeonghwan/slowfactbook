#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국세 징수 현황. 국세청 국세통계의 '연도별 세목별 세수 현황' 한 표로 통일한다.

  python3 scripts/tax_revenue.py            # 미리보기
  python3 scripts/tax_revenue.py --apply

원천은 국세청 국세통계 133/TX_13301_A075 '2.1.2 연도별 세목별 세수 현황'
이다. 1981년부터 세목별로 들어 있고 해마다 갱신된다.

손보는 차트
  c0301 국세 징수 현황(소득세·법인세·부가가치세·종합부동산세)
  c0302 법인세 징수 현황
  c0306 법인세와 근로소득세 추이
  c0307 국세 징수 현황(법인세와 근로소득세)
  c0310 국세 징수 현황(소득세·법인세·부가가치세·기타)
  c0320 국세 징수 현황(최근 7년, 가로 누적)

손대지 않는 차트가 있다. c0276, c0277, c0283, c0299 는 관세를 포함한
'총국세'(기획재정부 국세수입) 기준이라 이 표와 기준이 다르다. 섞으면 안 된다.

이 표는 국세청 소관 세수다. 관세청이 걷는 관세가 빠져 있어 총국세보다
해마다 몇 조 원 적다.

고친 것 두 가지.

첫째, c0310 의 '기타' 가 2019년까지는 총국세에서 세 세목을 뺀 값이고
2020년부터는 국세청 세수에서 뺀 값이었다. 한 누적 막대 안에서 기준이
2020년에 갈려, 막대 높이가 1990년 26.8조 대 국세청 세수 22.7조처럼
어긋났다. 전부 국세청 세수 기준으로 다시 세운다.

둘째, c0306 과 c0307 의 근로소득세가 법인세와 다른 기준이었다. 법인세는
이 표와 전 구간이 정확히 맞는데 근로소득세는 겹치는 14개 해 가운데 12개가
어긋났다(2016년 차트 30.9조 대 표 31.97조). 둘 다 이 표로 맞춘다.
"""
import argparse, collections, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

ORG, TBL, ITM = "133", "TX_13301_A075", "16133AAB1"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=133&tblId=TX_13301_A075"

# 이름이 겹치는 행이 있어(현년도분·과년도분에 같은 세목 이름이 또 나온다)
# 반드시 분류 코드로 집는다.
C = {
    "세수": "15133SMB00",
    "총징수액": "15133SMB000",
    "내국세": "15133SMB0001",
    "소득세": "15133SMB00010101",
    "법인세": "15133SMB00010102",
    "부가가치세": "15133SMB00010201",
    "종합부동산세": "15133SMB0007",
    "근로소득세": "15133SMB000101010204",      # 2012년부터
    "근로소득세갑": "15133SMB0001010102001",    # 2011년까지, 같은 계열의 옛 이름
    "근로소득세_원천분": "15133SMB00010100204B",
    "근로소득세_납세조합분": "15133SMB00010100204",
    "종합소득세": "15133SMB000101010101",
    "양도소득세": "15133SMB000101010103",
    "상속세": "15133SMB00010105",
    "증여세": "15133SMB00010106",
}


def fetch():
    key = None
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith("KOSIS_API_KEY"):
            key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise SystemExit(".env 에 KOSIS_API_KEY 가 없습니다.")
    now = datetime.datetime.now(KST).year
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId={ORG}&tblId={TBL}"
         f"&prdSe=Y&startPrdDe=1981&endPrdDe={now}&itmId={ITM}&objL1=ALL")
    r = subprocess.run(["curl", "-sS", "--max-time", "150", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit("KOSIS 응답이 표가 아닙니다: " + str(d)[:160])
    T = collections.defaultdict(dict)
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        T[x["C1"]][x["PRD_DE"]] = float(x["DT"]) / 1e6      # 백만원 -> 조 원
    miss = [k for k, c in C.items() if c not in T]
    if miss:
        raise SystemExit(f"표에서 못 찾은 항목: {miss}")
    return T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    T = fetch()
    V = {k: T[c] for k, c in C.items()}
    yrs = sorted(V["세수"])
    last = yrs[-1]
    print(f"국세청 국세통계 세목별 세수 {yrs[0]}~{last} ({len(yrs)}개 해)")

    # ── 검산 1. 근로소득세는 원천분과 납세조합분의 합이어야 한다.
    bad = [(y, round(V["근로소득세"][y], 3),
            round(V["근로소득세_원천분"][y] + V["근로소득세_납세조합분"][y], 3))
           for y in sorted(V["근로소득세"])
           if y in V["근로소득세_원천분"] and y in V["근로소득세_납세조합분"]
           and abs(V["근로소득세"][y] - V["근로소득세_원천분"][y]
                   - V["근로소득세_납세조합분"][y]) > 0.02]
    if bad:
        raise SystemExit(f"근로소득세가 원천분+납세조합분과 어긋납니다: {bad[:5]}")

    # 근로소득세는 2011년까지 '근로소득세(갑)' 이라는 이름으로 들어 있다.
    wage = dict(V["근로소득세갑"])
    ovl = set(wage) & set(V["근로소득세"])
    if ovl:
        raise SystemExit(f"근로소득세 두 이름이 겹칩니다: {sorted(ovl)[:5]}")
    wage.update(V["근로소득세"])
    print(f"  근로소득세: {min(wage)}~{max(wage)} ({len(wage)}개 해). "
          f"2011년까지는 '근로소득세(갑)' 이름으로 들어 있어 이어 붙였습니다.")

    # ── 검산 2. 세수는 세 세목의 합보다 커야 하고, 소득세는 근로소득세보다 커야 한다.
    bad = [y for y in yrs
           if V["세수"][y] < V["소득세"].get(y, 0) + V["법인세"].get(y, 0)
           + V["부가가치세"].get(y, 0)]
    if bad:
        raise SystemExit(f"세수가 세 세목의 합보다 작습니다: {bad[:5]}")
    bad = [y for y in wage if y in V["소득세"] and wage[y] > V["소득세"][y]]
    if bad:
        raise SystemExit(f"근로소득세가 소득세보다 큽니다: {bad[:5]}")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    base = {}
    for f in ("full.json", "manual.json"):
        for i in json.load(open(os.path.join(DATA, f), encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)

    def cur(cid):
        return {**base.get(cid, {}), **(ov.get(cid) or {})}

    # ── 검산 3. 기존 차트 값이 표와 맞아야 한다. 어긋나면 쓰지 않는다.
    #    근로소득세는 기준이 다른 것이 이미 드러났으므로 여기서 빼고 따로 알린다.
    CHECK = {"c0301": ["소득세", "법인세", "부가가치세", "종합부동산세"],
             "c0310": ["소득세", "법인세", "부가가치세"],
             "c0302": ["법인세"], "c0306": ["법인세"], "c0307": ["법인세"]}
    n_ok = 0
    for cid, keys in CHECK.items():
        c = cur(cid)
        lab = [str(x) for x in c["labels"]]
        names = [str(n).strip().rstrip(".") for n in c["seriesNames"]]
        for k in keys:
            if k not in names:
                continue
            s = c["series"][names.index(k)]
            diff = [(y, s[i], round(V[k][y], 3)) for i, y in enumerate(lab)
                    if s[i] is not None and y in V[k]
                    and abs(s[i] - V[k][y]) > max(0.06, abs(V[k][y]) * 0.004)]
            if diff:
                raise SystemExit(f"{cid} {k} 가 표와 어긋납니다: {diff[:6]}")
            n_ok += sum(1 for i, y in enumerate(lab) if s[i] is not None and y in V[k])
    print(f"  기존 차트 대조: 소득세·법인세·부가가치세·종합부동산세 {n_ok}개 값이 모두 일치")

    # 근로소득세가 어긋나는 폭을 알린다.
    c = cur("c0306")
    lab = [str(x) for x in c["labels"]]
    names = [str(n).strip().rstrip(".") for n in c["seriesNames"]]
    s = c["series"][names.index("근로소득세")]
    wdiff = [(y, s[i], round(wage[y], 2)) for i, y in enumerate(lab)
             if s[i] is not None and y in wage and abs(s[i] - wage[y]) > 0.06]
    print(f"  ※ c0306/c0307 의 근로소득세는 {len(wdiff)}개 해가 어긋납니다 — "
          f"이 표로 맞춥니다. 예: {wdiff[:3]}")

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    SRC = (f"국세청 국세통계 '연도별 세목별 세수 현황'. 국세청 소관 세수, "
           f"{yrs[0]}~{last}년. 단위: 조 원.")
    BASIS = ("국세청이 걷는 세금만 담은 표입니다. 관세청이 걷는 관세가 빠져 있어 "
             "기획재정부가 내는 '총국세' 보다 해마다 몇 조 원 적습니다. 총국세로 "
             "그린 차트와 높이를 견주면 안 됩니다.")
    LAG = ("국세통계는 이듬해에 확정됩니다. 가장 최근 해의 값은 뒤에 조금 "
           "고쳐지는 일이 있고, 이 차트는 받을 때마다 과거 값까지 덮습니다.")

    def ser(key, lab):
        return [round(V[key][y], 2) if y in V[key] else None for y in lab]

    out = {}

    # ── c0301 소득세·법인세·부가가치세·종합부동산세
    c = cur("c0301")
    lab = [str(y) for y in range(int(str(c["labels"][0])), int(last) + 1)]
    out["c0301"] = {
        "id": "c0301", "title": "국세 징수 현황", "vizType": "stacked_bar",
        "unit": "조 원", "labels": lab,
        "series": [ser(k, lab) for k in ("소득세", "법인세", "부가가치세", "종합부동산세")],
        "seriesNames": ["소득세", "법인세", "부가가치세", "종합부동산세"],
        "source": SRC, "sourceUrl": URL,
        "notes": [
            f"{last}년 소득세 {V['소득세'][last]:.1f}조 원, 법인세 "
            f"{V['법인세'][last]:.1f}조 원, 부가가치세 {V['부가가치세'][last]:.1f}조 원, "
            f"종합부동산세 {V['종합부동산세'][last]:.1f}조 원입니다.",
            "네 세목만 쌓은 그림이라 막대 높이가 국세 전체가 아닙니다. 교통에너지"
            "환경세, 교육세, 농어촌특별세, 개별소비세, 주세, 증권거래세, 상속세, "
            "증여세 등이 빠져 있습니다.",
            "종합부동산세는 2005년에 생겨 그 전에는 막대가 없습니다.",
            f"법인세가 2022년 {V['법인세']['2022']:.1f}조 원에서 2024년 "
            f"{V['법인세']['2024']:.1f}조 원으로 주저앉았다가 {last}년 "
            f"{V['법인세'][last]:.1f}조 원으로 돌아왔습니다. 2023년 기업 실적이 "
            "나빴던 몫이 이듬해 세금에 나타난 것입니다. 법인세는 전년도 실적에 "
            "매기므로 한 해 늦게 움직입니다.",
            BASIS, LAG,
        ],
        "updated": now,
    }

    # ── c0310 소득세·법인세·부가가치세·기타
    c = cur("c0310")
    first = max(int(str(c["labels"][0])), min(int(y) for y in V["세수"]))
    lab = [str(y) for y in range(first, int(last) + 1)]
    etc = [round(V["세수"][y] - V["소득세"][y] - V["법인세"][y] - V["부가가치세"][y], 2)
           if all(y in V[k] for k in ("세수", "소득세", "법인세", "부가가치세")) else None
           for y in lab]
    out["c0310"] = {
        "id": "c0310", "title": "국세 징수 현황", "vizType": "stacked_bar",
        "unit": "조 원", "labels": lab,
        "series": [ser("소득세", lab), ser("법인세", lab), ser("부가가치세", lab), etc],
        "seriesNames": ["소득세", "법인세", "부가가치세", "기타"],
        "source": SRC + " 기타는 국세청 세수에서 앞의 세 세목을 뺀 값.",
        "sourceUrl": URL,
        "notes": [
            f"막대 전체 높이가 국세청 세수입니다. {last}년 "
            f"{V['세수'][last]:.1f}조 원이고, 소득세 {V['소득세'][last]:.1f}조, "
            f"법인세 {V['법인세'][last]:.1f}조, 부가가치세 "
            f"{V['부가가치세'][last]:.1f}조, 나머지 {etc[-1]:.1f}조입니다.",
            "'기타' 는 국세청 세수에서 세 세목을 뺀 값입니다. 교통에너지환경세, "
            "교육세, 농어촌특별세, 종합부동산세, 개별소비세, 주세, 증권거래세, "
            "상속세, 증여세, 인지세, 과년도 수입이 모두 여기 들어갑니다.",
            "기준이 갈려 있던 차트를 다시 세웠습니다. 전에는 2019년까지는 총국세"
            "에서 세 세목을 뺀 값을, 2020년부터는 국세청 세수에서 뺀 값을 "
            "'기타' 에 넣고 있었습니다. 한 누적 막대 안에서 기준이 2020년에 "
            "갈려 1990년 막대 높이가 26.8조로 나왔는데 같은 해 국세청 세수는 "
            "22.7조였습니다. 전부 국세청 세수로 통일했고, 그만큼 2019년 이전 "
            "막대가 낮아졌습니다.",
            f"소득세가 전체에서 차지하는 몫이 {lab[0]}년 "
            f"{V['소득세'][lab[0]] / V['세수'][lab[0]] * 100:.0f}% 에서 {last}년 "
            f"{V['소득세'][last] / V['세수'][last] * 100:.0f}% 로 커졌습니다. "
            "같은 기간 법인세 몫은 "
            f"{V['법인세'][lab[0]] / V['세수'][lab[0]] * 100:.0f}% 에서 "
            f"{V['법인세'][last] / V['세수'][last] * 100:.0f}% 입니다.",
            BASIS, LAG,
        ],
        "updated": now,
    }

    # ── c0320 최근 7년 가로 누적
    nlab = [str(y) for y in range(int(last) - 6, int(last) + 1)]
    out["c0320"] = {
        "id": "c0320", "title": "국세 징수 현황", "vizType": "stacked_bar_h",
        "unit": "조 원", "labels": [y + "년" for y in nlab],
        "series": [ser("소득세", nlab), ser("법인세", nlab), ser("부가가치세", nlab),
                   ser("종합부동산세", nlab),
                   [round(V["세수"][y] - V["소득세"][y] - V["법인세"][y]
                          - V["부가가치세"][y] - V["종합부동산세"][y], 2) for y in nlab]],
        "seriesNames": ["소득세", "법인세", "부가가치세", "종합부동산세", "기타"],
        "source": SRC + " 기타는 국세청 세수에서 앞의 네 세목을 뺀 값.",
        "sourceUrl": URL,
        "notes": [
            f"막대 전체 높이가 국세청 세수입니다. {nlab[0]}년 "
            f"{V['세수'][nlab[0]]:.1f}조 원에서 {last}년 {V['세수'][last]:.1f}조 "
            "원입니다.",
            f"2022년 {V['세수']['2022']:.1f}조 원을 정점으로 2023년 "
            f"{V['세수']['2023']:.1f}조, 2024년 {V['세수']['2024']:.1f}조로 두 해 "
            f"내리 줄었다가 {last}년 {V['세수'][last]:.1f}조로 돌아왔습니다. "
            "두 해의 감소는 법인세가 끌어내린 몫이 가장 큽니다.",
            "'기타' 에는 교통에너지환경세, 교육세, 농어촌특별세, 개별소비세, 주세, "
            "증권거래세, 상속세, 증여세, 인지세, 과년도 수입이 들어갑니다.",
            BASIS, LAG,
        ],
        "updated": now,
    }

    # ── c0302 법인세
    c = cur("c0302")
    lab = [str(y) for y in range(int(str(c["labels"][0])), int(last) + 1)]
    out["c0302"] = {
        "id": "c0302", "title": "법인세 징수 현황", "vizType": "column",
        "unit": "조 원", "labels": lab, "series": [ser("법인세", lab)],
        "seriesNames": ["법인세"], "source": SRC, "sourceUrl": URL,
        "notes": [
            f"{last}년 {V['법인세'][last]:.1f}조 원입니다. 가장 많았던 해는 2022년의 "
            f"{V['법인세']['2022']:.1f}조 원입니다.",
            "법인세는 전년도 실적에 매기므로 경기보다 한 해 늦게 움직입니다. "
            f"2023년 기업 실적이 나빴던 몫이 2024년 세수 {V['법인세']['2024']:.1f}조 "
            "원으로 나타났습니다.",
            "세율 인하도 겹칩니다. 2023년에 과세표준 구간별 세율이 1%포인트씩 "
            "내려갔습니다. 다만 이 차트만으로 세율과 실적 가운데 어느 쪽이 얼마나 "
            "작용했는지는 가려낼 수 없습니다.",
            BASIS, LAG,
        ],
        "updated": now,
    }

    # ── c0306, c0307 법인세와 근로소득세
    wyrs = sorted(wage)
    for cid, viz in (("c0306", "line"), ("c0307", "column")):
        c = cur(cid)
        # 법인세 역사를 잘라내지 않는다. 근로소득세는 2004년 전이 비어 있을 뿐이다.
        lab = [str(y) for y in range(int(str(c["labels"][0])), int(last) + 1)]
        out[cid] = {
            "id": cid, "title": "법인세와 근로소득세",
            "vizType": viz, "unit": "조 원", "labels": lab,
            "series": [ser("법인세", lab),
                       [round(wage[y], 2) if y in wage else None for y in lab]],
            "seriesNames": ["법인세", "근로소득세"],
            "seriesColors": ["#2f5e8e", "#c0322f"],
            "source": SRC, "sourceUrl": URL,
            "notes": [
                f"{last}년 법인세 {V['법인세'][last]:.1f}조 원, 근로소득세 "
                f"{wage[last]:.1f}조 원입니다. {wyrs[0]}년에는 법인세 "
                f"{V['법인세'][wyrs[0]]:.1f}조 원, 근로소득세 "
                f"{wage[wyrs[0]]:.1f}조 원이었습니다.",
                "두 계열의 기준을 맞춘 차트입니다. 전에는 법인세만 국세청 "
                "국세통계를 쓰고 근로소득세는 다른 자료에서 와서, 겹치는 14개 해 "
                "가운데 12개가 어긋났습니다. 2016년이 차트 30.9조 원 대 국세통계 "
                "32.0조 원이었습니다. 지금은 둘 다 같은 표에서 받습니다.",
                f"근로소득세 선이 {wyrs[0]}년에서 시작하는 것은 국세통계가 "
                "근로소득세를 따로 내놓는 첫 해이기 때문입니다. 2011년까지는 '근로소득세(갑)' 이라는 "
                "이름으로 들어 있어 이어 붙였습니다. 그 시절 이름에는 납세조합이 "
                "걷어 내는 몫이 빠져 있는데, 그 몫은 연 0.1~0.2조 원 수준입니다.",
                "법인세는 해마다 크게 흔들리고 근로소득세는 거의 한 방향으로만 "
                "올라갑니다. 근로소득세는 임금에서 원천징수해 경기를 덜 타고, "
                "법인세는 전년도 실적에 매겨 경기를 크게 탑니다.",
                "근로소득세는 국세청이 걷은 금액이고, 연말정산으로 돌려준 환급액이 "
                "반영된 뒤의 값입니다. 근로장려금과 자녀장려금은 소득세에서 빼는 "
                "방식이라 이 수치에 영향을 줍니다.",
                BASIS, LAG,
            ],
            "updated": now,
        }

    for cid, o in out.items():
        lab = o["labels"]
        print(f"  {cid} {o['title']:18s} {o['vizType']:14s} {len(lab):3d}개 해 "
              f"{lab[0]}~{lab[-1]}  계열 {len(o['series'])}")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
