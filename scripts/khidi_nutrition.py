#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""국민영양통계(한국보건산업진흥원)의 영양소별 섭취량으로 차트 여섯 장.

  python3 scripts/khidi_nutrition.py            # 미리보기
  python3 scripts/khidi_nutrition.py --apply

원천은 국민건강영양조사 영양부문이고, 진흥원이 질병관리청 원시데이터를 해마다
다시 돌려 '국민영양통계' 로 공표한다. 사이트에 '연도별 섭취량' 그래프 메뉴가
있지만 현재 열리지 않는다(graph1 이 오류 페이지를 돌려준다). 그래서 연도별
페이지를 2008년부터 한 해씩 모아 시계열을 직접 세운다.

표 한 줄은
  영양소명 | 전체 평균 | 전체 표준오차 | 1-2세 평균 | 1-2세 표준오차 | ...
로 연령 구간 여덟 개까지 열아홉 칸이다. 평균만 쓴다.

못 쓰는 지표가 있다. 철은 2012년 14.5mg -> 2013년 17.8mg -> 2017년 12.8mg,
비타민C 는 2016년 96.7mg -> 2017년 62.7mg 으로 튄다. 섭취가 변한 게 아니라
식품성분 데이터베이스가 개정된 것이라 한 선으로 이으면 거짓말이 된다. 이
어댑터는 그 둘을 쓰지 않는다.

사이트 쪽 오류도 하나 있다. 2020년 지방급원에너지비 공표값이 61.22% 인데
앞뒤 해가 22.46%, 23.52% 다. g 값으로 계산하면 24.7% 이므로 자리수 오류로
보인다. 그래서 열량 구성비는 공표 비율 열을 쓰지 않고 g 에서 계산한다.

영양소 이름 표기가 해마다 다르다. '에너지(Kcal)', '에너지(kcal)',
'에너지 섭취량(kcal)' 이 다 같은 항목이다. 괄호와 '섭취량' 을 떼고 맞춘다.
"""
import argparse, datetime, json, os, re, subprocess, time
import html as H

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

BASE = ("https://www.khidi.or.kr/kps/dhraStat/result5"
        "?menuId=MENU01657&gubun=age1&year=%s")
PAGE = "https://www.khidi.or.kr/kps/dhraStat/result5?menuId=MENU01657"
FIRST = 2008
CAT = "식량"

# 조사 기수. 기수가 바뀌는 해에 단층이 생긴다.
WAVES = [("제4기", 2007, 2009), ("제5기", 2010, 2012), ("제6기", 2013, 2015),
         ("제7기", 2016, 2018), ("제8기", 2019, 2021), ("제9기", 2022, 2024)]

AGE_SRC = ["1-2", "3-5", "6-11", "12-18", "19-29", "30-49", "50-64"]
AGE_OUT = ["1~2세", "3~5세", "6~11세", "12~18세", "19~29세", "30~49세", "50~64세",
           "65세 이상"]

SLIDES = {
    "macro": "manual-khidi-macro-ratio",
    "sodium": "manual-khidi-sodium",
    "animal": "manual-khidi-animal-protein",
    "energy": "manual-khidi-energy",
    "energy_age": "manual-khidi-energy-by-age",
    "sodium_age": "manual-khidi-sodium-by-age",
}


def norm(name):
    """'에너지 섭취량(kcal)' -> '에너지'."""
    return re.sub(r"\(.*?\)", "", name.replace(" ", "").replace("섭취량", ""))


def fetch(year):
    """{영양소: [전체, 1-2, 3-5, ...]} — 평균만. 자료가 없으면 {}."""
    last = ""
    for attempt in range(3):
        r = subprocess.run(["curl", "-sS", "--max-time", "60", BASE % year],
                           capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 50000:
            break
        last = r.stderr.decode()[:120] or f"{len(r.stdout)}바이트"
        time.sleep(1.5)
    else:
        raise SystemExit(f"{year}년 내려받기 실패: {last}")
    s = r.stdout.decode("utf-8", "replace")

    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S | re.I):
        c = [H.unescape(re.sub(r"<[^>]+>", "", x)).replace("\xa0", " ").strip()
             for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if c:
            rows.append(c)
    if not rows:
        raise SystemExit(f"{year}년 표를 찾지 못했습니다.")

    head = next((c for c in rows if c and c[0].startswith("영양소")), None)
    if head is None:
        return {}
    # 머리글이 전체 + 연령 구간 여덟 개인지 확인한다. 구간이 바뀌면 멈춘다.
    got = [x.replace(" ", "") for x in head[1:]]
    want = ["전체"] + AGE_SRC + ["≥65"]
    if got != want:
        raise SystemExit(f"{year}년 연령 구간이 달라졌습니다: {got}")

    out = {}
    for c in rows:
        if len(c) != 19 or not c[0] or c[0].startswith("영양소"):
            continue
        try:
            v = [float(x.replace(",", "")) for x in c[1::2]]
        except ValueError:
            continue
        out[norm(c[0])] = v
    return out


def wave(year):
    for name, a, b in WAVES:
        if a <= year <= b:
            return name
    return "?"


def check(raw):
    """받은 값이 서로 맞는지 본다. 어긋나면 쓰지 않고 멈춘다."""
    years = sorted(raw)
    need = ["에너지", "탄수화물", "단백질", "동물성단백질", "지방", "나트륨",
            "동물성단백질비", "지방급원에너지비"]
    for y in years:
        miss = [n for n in need if n not in raw[y]]
        if miss:
            raise SystemExit(f"{y}년에 없는 항목: {miss}")

    bad = [(y, raw[y]["동물성단백질"][0], raw[y]["단백질"][0]) for y in years
           if raw[y]["동물성단백질"][0] > raw[y]["단백질"][0]]
    if bad:
        raise SystemExit(f"동물성단백질이 단백질보다 큽니다: {bad}")

    # 3대 영양소 열량 합은 에너지의 93~100% 사이여야 한다. 알코올 등이
    # 에너지에는 들어가고 3대 영양소에는 안 들어가서 100%가 못 된다.
    for y in years:
        r = raw[y]
        kc = (r["탄수화물"][0] + r["단백질"][0]) * 4 + r["지방"][0] * 9
        sh = kc / r["에너지"][0] * 100
        if not 93.0 <= sh <= 100.0:
            raise SystemExit(f"{y}년 3대 영양소 열량이 에너지의 {sh:.1f}% 입니다.")

    # 계산한 지방 열량비와 공표 지방급원에너지비의 차이가 해마다 일정해야
    # 한다. 일정하면 표를 제대로 읽은 것이고, 어긋나면 열이 밀린 것이다.
    gaps, broken = {}, []
    for y in years:
        r = raw[y]
        kc = (r["탄수화물"][0] + r["단백질"][0]) * 4 + r["지방"][0] * 9
        mine = r["지방"][0] * 9 / kc * 100
        pub = r["지방급원에너지비"][0]
        if abs(mine - pub) > 5:
            broken.append((y, pub, round(mine, 1)))
        else:
            gaps[y] = mine - pub
    if len(broken) > 1:
        raise SystemExit(f"지방 열량비가 공표값과 크게 어긋나는 해가 여럿입니다: {broken}")
    if not gaps:
        raise SystemExit("지방 열량비를 대조할 해가 없습니다.")
    lo, hi = min(gaps.values()), max(gaps.values())
    if not (0.3 <= lo and hi <= 2.0 and hi - lo <= 0.9):
        raise SystemExit(f"지방 열량비 차이가 들쭉날쭉합니다: {lo:.2f}~{hi:.2f}")

    # 전체 평균은 연령 구간 값의 최솟값과 최댓값 사이에 있어야 한다.
    for y in years:
        for n in ("에너지", "나트륨"):
            v = raw[y][n]
            if not (min(v[1:]) - 1e-6 <= v[0] <= max(v[1:]) + 1e-6):
                raise SystemExit(f"{y}년 {n} 전체값이 연령 구간 밖입니다: {v}")

    return broken, (lo, hi)


def upsert(items):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    for item in items:
        cur = next((i for i in doc["items"] if i.get("slide") == item["slide"]), None)
        # id 를 항목 안에 적어 둬야 cNNNN 키로 쓴 overrides 가 먹는다.
        if cur and cur.get("id"):
            item["id"] = cur["id"]
        else:
            k = "S\x1f%s\x1f%s" % (item["slide"], item["title"])
            if ids.get(k):
                item["id"] = ids[k]
        if cur:
            doc["items"][doc["items"].index(cur)] = item
        else:
            doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    this_year = datetime.datetime.now(KST).year
    raw, empty = {}, []
    for y in range(FIRST, this_year):
        d = fetch(y)
        if d:
            raw[y] = d
        else:
            empty.append(y)
    if len(raw) < 10:
        raise SystemExit(f"받은 해가 {len(raw)}개뿐입니다 — 쓰지 않습니다.")
    years = sorted(raw)
    gap = [y for y in range(years[0], years[-1] + 1) if y not in raw]
    if gap:
        raise SystemExit(f"중간에 빠진 해가 있습니다: {gap}")
    broken, (lo, hi) = check(raw)
    last = years[-1]

    print(f"국민영양통계 {years[0]}~{last}년 ({len(years)}개 해)")
    print(f"  자료 없는 해: {empty or '없음'}")
    print(f"  지방 열량비 대조: 계산값이 공표값보다 {lo:.2f}~{hi:.2f}%p 높음 (일정)")
    for y, pub, mine in broken:
        print(f"  ※ {y}년 공표 지방급원에너지비 {pub} 는 사이트 오류로 봅니다"
              f" (계산값 {mine}). 비율은 g 에서 계산하므로 차트에는 영향 없음")

    lab = [str(y) for y in years]
    E = [raw[y]["에너지"][0] for y in years]
    NA = [raw[y]["나트륨"][0] for y in years]
    AP = [raw[y]["동물성단백질비"][0] for y in years]
    carb, prot, fat = [], [], []
    for y in years:
        r = raw[y]
        kc = (r["탄수화물"][0] + r["단백질"][0]) * 4 + r["지방"][0] * 9
        carb.append(round(r["탄수화물"][0] * 4 / kc * 100, 1))
        prot.append(round(r["단백질"][0] * 4 / kc * 100, 1))
        fat.append(round(r["지방"][0] * 9 / kc * 100, 1))

    print(f"  에너지 {E[0]:.0f} -> {E[-1]:.0f} kcal, 나트륨 {NA[0]:.0f} -> {NA[-1]:.0f} mg")
    print(f"  탄수화물 {carb[0]} -> {carb[-1]}%, 지방 {fat[0]} -> {fat[-1]}%,"
          f" 동물성단백질비 {AP[0]} -> {AP[-1]}%")

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    recall = ("하루치 회상이라 개인의 평상시 섭취와는 다릅니다. 전국 평균으로 "
              "보면 쓸 수 있지만, 한 사람이 날마다 이만큼 먹는다는 뜻은 "
              "아닙니다. 회상법은 먹은 양을 실제보다 적게 답하는 경향도 "
              "알려져 있습니다.")
    wavenote = ("조사 기수가 바뀌는 해에 단층이 있습니다. 제4기(2007~2009), "
                "제5기(2010~2012), 제6기(2013~2015), 제7기(2016~2018), "
                "제8기(2019~2021), 제9기(2022~2024)로 끊기는데, 기수마다 "
                "표본 설계와 가중치가 다시 잡힙니다. 2009년 에너지 "
                f"{raw[2009]['에너지'][0]:.0f}kcal 에서 2010년 "
                f"{raw[2010]['에너지'][0]:.0f}kcal 로 한 해에 160kcal 넘게 뛴 "
                "것은 식생활이 그만큼 변했다기보다 제4기에서 제5기로 넘어간 "
                "탓으로 보는 쪽이 안전합니다.")
    method22 = ("2022년부터 조사 방식이 또 바뀌었습니다. 조사 장소가 집에서 "
                "이동검진차량으로 옮겨졌고, 먹은 음식을 묻는 기준일이 '조사 "
                "1일 전' 에서 '2일 전' 으로 변경됐습니다. 2022년 앞뒤를 "
                "비교할 때 감안해야 합니다.")
    dbnote = ("식품성분 데이터베이스가 개정되면 같은 음식의 영양소 값이 바뀝니다. "
              "철은 2012년 14.5mg 에서 2013년 17.8mg 으로 올랐다가 2017년 "
              "12.8mg 으로 떨어지고, 비타민C 는 2016년 96.7mg 에서 2017년 "
              "62.7mg 으로 내려앉습니다. 먹는 양이 변한 게 아니라 계산에 쓰는 "
              "성분표가 바뀐 것이라, 이 두 영양소는 시계열로 그리지 않았습니다.")
    srcnote = ("진흥원 사이트에 '연도별 섭취량' 그래프 메뉴가 있지만 현재 열리지 "
               "않습니다. 그래서 연도별 페이지를 한 해씩 따로 모아 이었습니다. "
               "영양소 이름 표기가 해마다 달라('에너지(Kcal)', "
               "'에너지 섭취량(kcal)') 괄호와 '섭취량' 을 떼고 맞췄습니다.")
    nextyear = (f"{last + 1}년치는 아직 공표되지 않았습니다. 국민건강영양조사 "
                "결과는 이듬해 말에 나오고, 이 차트는 그때 자동으로 늘어납니다.")
    SRC = (f"한국보건산업진흥원 국민영양통계(국민건강영양조사 영양부문). "
           f"{years[0]}~{last}년, 1인 1일 평균.")

    items = []

    # ── 1. 열량 구성비
    items.append({
        "slide": SLIDES["macro"], "category": CAT,
        "title": "탄수화물과 지방의 열량 구성비",
        "source": SRC + " 3대 영양소 열량을 100으로 본 구성비. 단위: %.",
        "sourceUrl": PAGE, "vizType": "line", "unit": "%",
        "labels": lab, "series": [carb, prot, fat],
        "seriesNames": ["탄수화물", "단백질", "지방"],
        "seriesColors": ["#2f5e8e", "#7a9e3f", "#c0322f"],
        "notes": [
            f"탄수화물 {carb[0]}% 에서 {carb[-1]}% 로 내려가고 지방이 "
            f"{fat[0]}% 에서 {fat[-1]}% 로 올라갔습니다. 16년 동안 한 방향으로 "
            f"움직였고 단백질은 {prot[0]}% 에서 {prot[-1]}% 로 거의 그대로입니다. "
            "쌀이 빠진 자리를 기름이 채웠다는 뜻입니다.",
            "탄수화물과 단백질은 1g 당 4kcal, 지방은 9kcal 로 환산해 셋의 합을 "
            "100으로 본 구성비입니다. 그래서 세 값을 더하면 100이 됩니다.",
            "진흥원이 따로 공표하는 '지방급원에너지비' 와는 조금 다릅니다. "
            f"공표값은 사람마다 비율을 구해 평균한 값이고 분모가 전체 에너지라 "
            f"이 차트보다 {lo:.1f}~{hi:.1f}%p 낮습니다. 이 차트는 평균 섭취량에서 "
            "비율을 구했고 분모에 알코올 등 3대 영양소 밖의 열량이 들어가지 "
            "않습니다. 방향과 폭은 두 방식이 같습니다.",
            "공표 지방급원에너지비 열은 쓰지 않았습니다. 2020년 값이 61.22% 로 "
            "적혀 있는데 앞 해가 22.46%, 뒤 해가 23.52% 입니다. 사이트 쪽 "
            "오류로 보여 g 값에서 직접 계산했습니다.",
            wavenote, method22, recall, srcnote, nextyear,
        ],
        "updated": now,
    })

    # ── 2. 나트륨
    items.append({
        "slide": SLIDES["sodium"], "category": CAT,
        "title": "나트륨 섭취량",
        "source": SRC + " WHO 권고 상한은 성인 1일 2,000mg. 단위: mg.",
        "sourceUrl": PAGE, "vizType": "line", "unit": "mg",
        "labels": lab, "series": [NA, [2000] * len(lab)],
        "seriesNames": ["1인 1일 나트륨 섭취량", "WHO 권고 상한 2,000mg"],
        "seriesColors": ["#2f5e8e", "#c0322f"],
        "notes": [
            f"{years[0]}년 {NA[0]:,.0f}mg 에서 {last}년 {NA[-1]:,.0f}mg 으로 "
            f"{(1 - NA[-1] / NA[0]) * 100:.0f}% 줄었습니다. 2010년 "
            f"{raw[2010]['나트륨'][0]:,.0f}mg 이 가장 높았고 거기서 보면 "
            f"{(1 - NA[-1] / raw[2010]['나트륨'][0]) * 100:.0f}% 감소입니다. "
            f"그래도 WHO 권고 상한의 {NA[-1] / 2000:.1f}배입니다.",
            "WHO 는 성인 1일 나트륨 2,000mg(소금 5g) 미만을 권고합니다. "
            "한국 기준은 더 느슨합니다. 2025 한국인 영양소 섭취기준은 성인 "
            "19~64세의 만성질환위험감소섭취량을 2,300mg, 충분섭취량을 "
            "1,500mg 으로 둡니다. 65세 이상은 더 낮습니다.",
            "줄어든 폭을 전부 식습관 변화로 보기는 어렵습니다. 2012년 "
            f"{raw[2012]['나트륨'][0]:,.0f}mg 에서 2013년 "
            f"{raw[2013]['나트륨'][0]:,.0f}mg 으로 한 해에 "
            f"{raw[2012]['나트륨'][0] - raw[2013]['나트륨'][0]:,.0f}mg 떨어진 "
            "것은 제5기에서 제6기로 넘어가며 식품성분 데이터베이스와 표본 "
            "설계가 같이 바뀐 해입니다. 그 단층을 빼고 보면 감소는 더 "
            "완만합니다.",
            "2013년 이후로는 대체로 내려오다가 최근 2년은 다시 조금 올랐습니다. "
            f"2022년 {raw[2022]['나트륨'][0]:,.0f}mg, {last}년 "
            f"{NA[-1]:,.0f}mg 입니다. 두 해뿐이라 추세가 꺾였다고 말하기는 "
            "이릅니다.",
            "국이나 찌개 국물, 김치, 장류에서 많이 들어옵니다. 식약처가 2012년 "
            "나트륨 저감 종합계획을 내놓은 뒤 가공식품 표시와 급식 기준이 "
            "바뀐 것이 감소에 영향을 준 것으로 평가되지만, 이 차트만으로 "
            "정책 효과를 가려낼 수는 없습니다.",
            recall, wavenote, method22, srcnote, nextyear,
        ],
        "updated": now,
    })

    # ── 3. 동물성단백질 비율
    items.append({
        "slide": SLIDES["animal"], "category": CAT,
        "title": "단백질 가운데 동물성 비율",
        "source": SRC + " 공표 동물성단백질비. 단위: %.",
        "sourceUrl": PAGE, "vizType": "line", "unit": "%",
        "labels": lab, "series": [AP], "seriesNames": ["동물성단백질 비율"],
        "seriesColors": ["#c0322f"], "yMin": 30, "yMax": 60,
        "notes": [
            f"{years[0]}년 {AP[0]}% 에서 {last}년 {AP[-1]}% 로 올랐습니다. "
            "2019년에 처음 절반을 넘었습니다. 먹는 단백질의 출처가 콩과 곡류에서 "
            "고기와 생선, 달걀, 유제품으로 옮겨 간 것입니다.",
            "전체 단백질 섭취량 자체는 거의 늘지 않았습니다. "
            f"{years[0]}년 {raw[years[0]]['단백질'][0]:.1f}g 에서 {last}년 "
            f"{raw[last]['단백질'][0]:.1f}g 입니다. 양이 아니라 구성이 "
            "바뀌었습니다.",
            "진흥원이 공표하는 동물성단백질비를 그대로 썼습니다. 사람마다 비율을 "
            "구해 평균한 값이어서, 평균 동물성단백질을 평균 단백질로 나눈 값"
            f"({raw[last]['동물성단백질'][0] / raw[last]['단백질'][0] * 100:.1f}%)"
            " 보다 낮게 나옵니다. 둘은 계산 순서가 다른 서로 다른 통계입니다.",
            "비율이라 식품성분 데이터베이스 개정에 상대적으로 둔감합니다. 분자와 "
            "분모가 같이 움직이기 때문입니다. 그래도 기수가 바뀌는 해의 단층은 "
            "남아 있습니다.",
            "세로축은 0 이 아니라 30에서 끊었습니다. 0 부터 그리면 변화가 눌려 "
            "보이지 않습니다. 축을 끊은 만큼 등락이 실제보다 커 보이는 점은 "
            "감안해 주십시오.",
            wavenote, method22, recall, srcnote, nextyear,
        ],
        "updated": now,
    })

    # ── 4. 에너지 섭취량
    top = max(years, key=lambda y: raw[y]["에너지"][0])
    items.append({
        "slide": SLIDES["energy"], "category": CAT,
        "title": "1인 1일 에너지 섭취량",
        "source": SRC + " 단위: kcal.",
        "sourceUrl": PAGE, "vizType": "line", "unit": "kcal",
        "labels": lab, "series": [E], "seriesNames": ["에너지 섭취량"],
        "seriesColors": ["#2f5e8e"], "yMin": 1500,
        "notes": [
            f"{top}년 {raw[top]['에너지'][0]:,.0f}kcal 이 가장 높았고 거기서 "
            f"{last}년 {E[-1]:,.0f}kcal 까지 내려왔습니다. "
            f"{raw[top]['에너지'][0] - E[-1]:,.0f}kcal, "
            f"{(1 - E[-1] / raw[top]['에너지'][0]) * 100:.0f}% 줄었습니다.",
            "먹는 양이 줄었다기보다 하루 중 끼니 수와 조사 방식이 함께 작용한 "
            "결과로 보입니다. 열량은 줄었는데 지방 섭취량은 같은 기간 늘었습니다"
            f"({raw[years[0]]['지방'][0]:.1f}g -> {raw[last]['지방'][0]:.1f}g). "
            "줄어든 쪽은 탄수화물입니다"
            f"({raw[years[0]]['탄수화물'][0]:.0f}g -> "
            f"{raw[last]['탄수화물'][0]:.0f}g).",
            wavenote,
            "2020년과 2021년은 코로나 기간입니다. 외식과 급식이 줄고 조사 수행도 "
            "영향을 받은 해여서 다른 해와 같은 조건으로 보기 어렵습니다.",
            method22, recall,
            "세로축은 0 이 아니라 1,500에서 끊었습니다. 0 부터 그리면 변화가 "
            "눌려 보이지 않습니다.",
            srcnote, nextyear,
        ],
        "updated": now,
    })

    # ── 5·6. 연령대별 스냅샷
    for key, nut, unit, color in (("energy_age", "에너지", "kcal", "#2f5e8e"),
                                  ("sodium_age", "나트륨", "mg", "#c0322f")):
        v = raw[last][nut]
        vals = [round(x, 1) for x in v[1:]]
        hi_i = max(range(len(vals)), key=lambda i: vals[i])
        lo_i = min(range(len(vals)), key=lambda i: vals[i])
        n = [
            f"{last}년 한 해 조사입니다. 전체 평균은 {v[0]:,.0f}{unit} 이고 "
            f"{AGE_OUT[hi_i]}가 {vals[hi_i]:,.0f}{unit} 로 가장 많고 "
            f"{AGE_OUT[lo_i]}가 {vals[lo_i]:,.0f}{unit} 로 가장 적습니다.",
            "연령 구간의 폭이 고르지 않습니다. 1~2세와 3~5세는 두세 살씩인데 "
            "30~49세는 스무 살입니다. 질병관리청 국민건강통계의 생애주기 구분을 "
            "그대로 따른 것이어서, 막대 높이를 인구 규모로 읽으면 안 됩니다.",
            "구간별 표본 수가 크게 다릅니다. 어린 나이 구간은 백 명이 안 되는 "
            "해도 있어 값이 흔들립니다. 진흥원은 구간마다 표준오차를 함께 "
            "공표하는데 이 차트에는 평균만 올렸습니다.",
            recall, srcnote,
        ]
        if nut == "에너지":
            n.insert(1, "노년층이 낮은 것을 절식으로만 읽기는 어렵습니다. 몸집과 "
                        "활동량이 적으면 필요 열량도 낮습니다. 다만 "
                        f"{AGE_OUT[-1]}의 {vals[-1]:,.0f}kcal 은 같은 해 "
                        "성인 구간 가운데 가장 낮고, 노년층 영양 부족을 다루는 "
                        "논의에서 자주 인용되는 수치입니다.")
            n.insert(2, "어린 나이 구간이 낮은 것은 당연합니다. 이 차트는 "
                        "연령대별로 얼마나 먹는지를 보는 것이고, 필요량 대비 "
                        "충족률이 아닙니다.")
        else:
            n.insert(1, "중장년이 가장 높고 어린 나이와 노년에서 낮습니다. 먹는 "
                        "총량과 같이 움직이는 부분이 있어, 나트륨만 떼어 "
                        "'짜게 먹는다' 로 읽으려면 열량당 나트륨으로 다시 "
                        "봐야 합니다.")
            n.insert(2, "WHO 권고 상한은 성인 1일 2,000mg 입니다. 1~2세를 뺀 "
                        "모든 구간이 그보다 높습니다.")
        items.append({
            "slide": SLIDES[key], "category": CAT,
            "title": f"연령대별 {nut} 섭취량 ({last}년)",
            "source": (f"한국보건산업진흥원 국민영양통계(국민건강영양조사 "
                       f"영양부문) {last}년. 1인 1일 평균. 단위: {unit}."),
            "sourceUrl": PAGE, "vizType": "column", "unit": unit,
            "labels": AGE_OUT, "series": [vals], "seriesNames": [f"{nut} 섭취량"],
            "seriesColors": [color], "notes": n, "updated": now,
        })

    print()
    for it in items:
        print(f"  {it['slide']:34s} {it['title']}")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    upsert(items)
    print("-> data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
