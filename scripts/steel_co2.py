#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""철강 1톤을 만들 때 나오는 이산화탄소. 제법별 비교.

  python3 scripts/steel_co2.py            # 미리보기
  python3 scripts/steel_co2.py --apply

제법별 값은 포스코 뉴스룸의 포스코경영연구원(POSRI) 특별기고에 실린
'조강 생산제법별 탄소배출량 비교' 그래프에서 가져왔다. 그래프에 적힌 출처는
'OECD, BNP Paribas 및 POSRI 자료 종합' 이다. 일곱 공정이 한 자료에서 나와
막대 길이를 그대로 견줄 수 있다. 그림 안의 숫자라 자동으로 갱신할 수 없어
상수로 둔다. 기고가 바뀌면 손으로 고쳐야 한다.

포스코 실적만 자동으로 갱신한다. 포스코가 해마다 내는 ESG 팩트북에
'직/간접 배출량 집약도(조강생산량 기준, Scope 1&2)' 가 실린다. 그 값이
(Scope 1 + Scope 2) / 조강생산량 과 맞는지 확인하고 쓴다.

주의할 점이 있다. 포스코 실적은 제법별 값과 성격이 다르다. 제법별 값은
기술 하나의 표준적인 수준이고, 포스코 값은 한 회사가 한 해 동안 낸 배출량을
그 해 조강생산량으로 나눈 것이다. 포스코 조강에는 전기로 몫도 섞여 있고
회계 경계도 다르다. 막대 길이를 1 대 1 로 견주면 안 된다.
"""
import argparse, datetime, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
SLIDE = "manual-steel-co2-route"
SLIDE2 = "manual-h2steel-grid"
SFOC_URL = "https://forourclimate.org/ko/research/693"

POSRI_URL = ("https://newsroom.posco.com/kr/특별기고-탄소저감-강재-표준화-"
             "지속가능한-철강산/")
ESG_URL = "https://sustainability.posco.co.kr/assets/file/%s_POSCO_ESG_Factbook.pdf"

# POSRI 기고의 '조강 생산제법별 탄소배출량 비교' 그래프. 단위 CO2 ton/Steel ton.
ROUTES = [
    ("고로/전로", 2.2, "#c0322f"),
    ("고로+수소 혼합", 1.85, "#d4663f"),
    ("고로+부생가스 연료와 화학 활용", 1.79, "#d4663f"),
    ("천연가스(NG) 기반 DRI 전기로", 1.4, "#e8a33c"),
    ("고로+탄소포집(CCUS)", 1.28, "#e8a33c"),
    ("스크랩 기반 전기로", 0.6, "#6a9b4a"),
    ("수소 환원", 0.11, "#3f8f3c"),
]
POSCO_COLOR = "#2f5e8e"


def posco():
    """포스코 ESG 팩트북에서 (연도, 집약도, Scope1+2, 조강생산량)."""
    now = datetime.datetime.now(KST).year
    txt = None
    for y in range(now, now - 4, -1):
        p = f"/tmp/posco_esg_{y}.pdf"
        r = subprocess.run(["curl", "-sSL", "--max-time", "120", "-o", p, ESG_URL % y,
                            "-w", "%{http_code}"], capture_output=True)
        if r.stdout.decode().strip() != "200" or os.path.getsize(p) < 200000:
            continue
        t = f"/tmp/posco_esg_{y}.txt"
        if subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", p, t]).returncode:
            continue
        txt = open(t, encoding="utf-8").read()
        print(f"  포스코 {y} ESG 팩트북을 읽었습니다.")
        break
    if txt is None:
        raise SystemExit("포스코 ESG 팩트북을 받지 못했습니다.")

    def row(pat):
        m = re.search(pat + r"[^\n]*", txt, re.M)
        if not m:
            raise SystemExit(f"'{pat}' 줄을 찾지 못했습니다.")
        tail = m.group(0).split(")")[-1]
        return [float(x.replace(",", "")) for x in
                re.findall(r"(?<![A-Za-z0-9.,])\d[\d,]*(?:\.\d+)?(?![A-Za-z0-9.])", tail)]

    hdr = re.search(r"온실가스\s+단위\s+((?:20\d\d\s+)+20\d\d)", txt)
    if not hdr:
        hdr = re.search(r"단위\s+((?:20\d\d\s+)+20\d\d)", txt)
    if not hdr:
        raise SystemExit("연도 머리글을 찾지 못했습니다.")
    yrs = hdr.group(1).split()

    inten = row(r"직/간접 배출량 집약도\(조강생산량 기준, Scope 1&2\)")
    s1 = row(r"직접 배출\(Scope 1\)")
    s2 = row(r"간접 배출\(Scope 2\)")
    crude = row(r"^ 조강 생산량\s")
    n = min(len(yrs), len(inten), len(s1), len(s2), len(crude))
    if n < 2:
        raise SystemExit(f"읽은 해가 {n}개뿐입니다.")
    # 집약도가 (Scope1+2) / 조강생산량 과 맞는지 모든 해에서 확인한다.
    bad = []
    for i in range(n):
        calc = (s1[i] + s2[i]) / (crude[i] * 1000)
        if abs(calc - inten[i]) > 0.012:
            bad.append((yrs[i], inten[i], round(calc, 3)))
    if bad:
        raise SystemExit(f"집약도가 배출량/생산량과 어긋납니다: {bad}")
    print(f"  집약도 검산: {yrs[0]}~{yrs[n-1]} 모두 (Scope1+2)/조강생산량 과 일치")
    return yrs[:n], inten[:n], s1[:n], s2[:n], crude[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    yrs, inten, s1, s2, crude = posco()
    y, v = yrs[-1], inten[-1]
    print(f"  포스코 조강 1톤당 {', '.join(f'{yy} {vv}' for yy, vv in zip(yrs, inten))}")

    rows = [(f"포스코 실적({y}년, 조강 전체)", v, POSCO_COLOR)] + \
           [(n, x, c) for n, x, c in ROUTES]
    rows.sort(key=lambda r: -r[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = {r[0]: r[2] for r in rows}

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    item = {
        "slide": SLIDE, "category": "기후와 에너지",
        "title": "철강 1톤을 만들 때 나오는 이산화탄소",
        "vizType": "bar", "unit": "톤",
        "labels": labels, "series": [vals],
        "seriesNames": ["조강 1톤당 이산화탄소"],
        "labelColors": colors,
        "source": ("제법별 값은 포스코경영연구원(POSRI) 특별기고의 '조강 생산제법별 "
                   "탄소배출량 비교'(원출처 표기: OECD, BNP Paribas 및 POSRI 자료 "
                   f"종합). 포스코 실적은 포스코 ESG 팩트북의 조강생산량 기준 "
                   f"Scope 1&2 집약도, {y}년. 단위: 톤."),
        "sourceUrl": POSRI_URL,
        "notes": [
            f"고로와 전로를 쓰는 지금의 주력 공정이 조강 1톤당 {ROUTES[0][1]}톤입니다. "
            f"스크랩을 전기로에 녹이면 {ROUTES[5][1]}톤, 수소로 환원하면 "
            f"{ROUTES[6][1]}톤입니다. 고로에서 수소환원으로 가면 배출이 "
            f"{ROUTES[0][1] / ROUTES[6][1]:.0f}분의 1로 줄어듭니다.",
            "일곱 개 제법은 한 자료에서 나온 값이라 막대 길이를 그대로 견줄 수 "
            "있습니다. 포스코경영연구원 특별기고에 실린 그래프이고, 그래프에 적힌 "
            "원출처는 'OECD, BNP Paribas 및 POSRI 자료 종합' 입니다. 기준 연도는 "
            "적혀 있지 않습니다.",
            f"파란 막대만 성격이 다릅니다. 포스코가 {y}년에 실제로 낸 배출량"
            f"({(s1[-1] + s2[-1]) / 1e6:,.1f}백만 톤)을 그 해 조강생산량"
            f"({crude[-1] / 1000:,.1f}백만 톤)으로 나눈 값입니다. 나머지는 기술 "
            "하나의 표준적인 수준이고 이것은 한 회사의 한 해 실적이라, 1 대 1 로 "
            "견주면 안 됩니다.",
            "특히 포스코 조강에는 전기로 몫이 섞여 있습니다. 그래서 고로만 쓰는 "
            "경우보다 낮게 나옵니다. 회계 경계도 다릅니다. 포스코 값은 Scope 1과 "
            "Scope 2를 더한 것이고, 원료를 사 오면서 생기는 배출(Scope 3)은 "
            "빠져 있습니다.",
            "포스코 값은 " + ", ".join(f"{yy}년 {vv}" for yy, vv in zip(yrs, inten))
            + "톤으로 거의 움직이지 않았습니다. 탄소중립 선언 이후에도 조강 1톤당 "
            "배출은 제자리라는 뜻입니다. 전체 배출량이 줄어든 해가 있어도 생산량이 "
            "같이 줄어든 몫이 큽니다.",
            "수소 환원의 0.11톤은 수소를 만드는 데 쓰는 전기가 깨끗하다는 전제가 "
            "깔린 값입니다. 전기를 석탄으로 만들면 이 숫자는 성립하지 않습니다. "
            "그래프에는 그 전제가 적혀 있지 않습니다.",
            "스크랩 기반 전기로는 값이 낮지만 생산량을 무한정 늘릴 수 없습니다. "
            "고품질 철스크랩의 공급이 세계 수요에 못 미칩니다. 기고문도 같은 이유로 "
            "전기로가 고로를 완전히 대체하기는 어렵다고 적습니다.",
            "기후솔루션은 전기로를 1톤당 0.8톤으로 적어 이 그래프의 0.6과 "
            "다릅니다. 공정 경계와 전력 배출계수를 어떻게 잡느냐에 따라 달라지는 "
            "값이라, 여러 자료의 숫자를 섞어 쓰면 비교가 성립하지 않습니다. 이 "
            "차트가 제법별로는 한 자료만 쓴 이유입니다.",
            f"포스코 실적은 ESG 팩트북이 새로 나오면 자동으로 갱신됩니다. 집약도가 "
            f"(Scope 1 + Scope 2) / 조강생산량 과 맞는지 {len(yrs)}개 해 모두에서 "
            "확인하고 씁니다. 제법별 값은 그림 속 숫자라 자동 갱신이 안 됩니다.",
        ],
        "updated": now,
    }

    # ── 두 번째 차트. 기후솔루션 「녹색 철강 생산 경로의 선택」(2026년 9월)
    #    표 2 를 그대로 옮긴다. 넷 다 수소환원제철 한 공정의 값이고, 전기를
    #    어디서 끌어오느냐와 몇 년이냐에 따라 갈린다. 그림 속 숫자가 아니라
    #    PDF 본문 표라 값이 분명하지만, 보고서가 개정되면 손으로 고쳐야 한다.
    GRID = ["한국 2025", "일본 2025", "한국 2035", "일본 2035"]
    g_grid = [2.38, 1.64, 0.81, 0.59]
    g_re = [0.40, 0.40, 0.28, 0.28]
    STD = 0.4
    item2 = {
        "slide": SLIDE2, "category": "기후와 에너지",
        "title": "수소환원제철의 이산화탄소, 전기를 어디서 끌어오느냐",
        "vizType": "combo", "unit": "톤",
        "labels": GRID, "series": [g_grid, g_re, [STD] * len(GRID)],
        "seriesNames": ["국가 전력망", "독립형 재생에너지", "녹색철강 기준 0.4톤"],
        "seriesKinds": ["bar", "bar", "line"], "seriesAxes": [0, 0, 0],
        "seriesColors": ["#c0322f", "#3f8f3c", "#999999"],
        "source": ("기후솔루션 「녹색 철강 생산 경로의 선택: 한국, 일본, 호주에의 "
                   "시사점」(2026년 9월) 표 2. 조강 1톤당 배출집약도. 단위: 톤."),
        "sourceUrl": SFOC_URL,
        "notes": [
            "네 묶음 모두 수소환원제철 한 공정의 값입니다. 서로 다른 제법이 "
            "아닙니다. 같은 공정인데 수소를 만드는 전기를 어디서 끌어오느냐에 "
            f"따라 {max(g_grid)}톤에서 {min(g_re)}톤까지 여덟 배 넘게 "
            "벌어집니다.",
            f"한국 국가 전력망으로 2025년에 돌리면 조강 1톤당 {g_grid[0]}톤입니다. "
            f"고로보다 많습니다. ResponsibleSteel 이 제시한 녹색철강 기준 "
            f"{STD}톤의 약 {g_grid[0] / STD:.0f}배입니다.",
            f"전력망이 탈탄소화되는 2035년에도 국가 전력망으로는 {g_grid[2]}톤으로 "
            "기준을 넘습니다. 수소환원제철 설비를 깔아도 전력 부문이 같이 바뀌지 "
            "않으면 녹색철강으로 인정받지 못한다는 뜻입니다.",
            f"일본이 한국보다 낮습니다. 2025년 {g_grid[1]}톤, 2035년 {g_grid[3]}톤"
            "입니다. 전력 배출계수가 낮아서입니다. 제철 기술의 차이가 아닙니다.",
            f"독립형(off-grid) 재생에너지를 쓰면 2025년부터 {g_re[0]}톤으로 기준을 "
            f"맞추고 2035년에는 {g_re[2]}톤까지 내려갑니다. 두 나라가 같은 값인 "
            "것은 전력을 계통에서 받지 않아 국가별 배출계수가 끼어들지 않기 "
            "때문입니다.",
            "보고서는 재생에너지 조달 방식 가운데 독립형만 분석에 넣었습니다. "
            "그것이 유일한 방안이라는 뜻은 아니라고 각주에 적어 두었습니다. "
            "전력구매계약 같은 다른 방식은 값이 달라질 수 있습니다.",
            "이 결과 때문에 보고서는 뒤이은 생산비용 비교에서 계통전력 경로를 "
            "아예 제외했습니다. 비용이 싸도 녹색철강으로 인정받지 못하면 비교할 "
            "이유가 없다는 판단입니다.",
            "제법끼리의 비교는 '철강 1톤을 만들 때 나오는 이산화탄소' 차트를 "
            "보십시오. 그 차트의 수소 환원 0.11톤은 다른 자료에서 온 값이라 이 "
            "차트의 숫자와 직접 견주면 안 됩니다.",
        ],
        "updated": now,
    }

    for n, v2 in zip(labels, vals):
        print(f"    {n:34s} {v2}")
    print(f"\n  {SLIDE} — 막대 {len(labels)}개, 비고 {len(item['notes'])}개")
    print(f"  {SLIDE2} — {len(GRID)}묶음, 비고 {len(item2['notes'])}개: "
          + ", ".join(f"{a} 계통 {b} 재생 {c}" for a, b, c in zip(GRID, g_grid, g_re)))
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    for it in (item, item2):
        cur = next((i for i in doc["items"] if i.get("slide") == it["slide"]), None)
        if cur and cur.get("id"):
            it["id"] = cur["id"]
        else:
            k = "S\x1f%s\x1f%s" % (it["slide"], it["title"])
            if ids.get(k):
                it["id"] = ids[k]
        if cur:
            doc["items"][doc["items"].index(cur)] = it
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
