#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OECD 나라별 일반정부 총금융부채(GDP 대비)를 한 장에 세운다.

  python3 scripts/oecd_debt.py            # 미리보기
  python3 scripts/oecd_debt.py --apply

OECD 경제전망(Economic Outlook) 의 GGFLQ 한 계정만 쓴다. 나라마다 다른 표에서
숫자를 긁어 모으면 기준이 섞인다. 한국의 '국가채무(D1)' 와 일본의 '국·지방
장기채무' 를 한 막대 그림에 나란히 세우는 것이 그런 경우인데, 둘은 포괄 범위가
달라 견줄 수 없다. 그래서 한 계정에서 한꺼번에 받는다.

GGFLQ 는 국민계정 기준 일반정부 총금융부채다. 중앙정부와 지방정부, 사회보장
기금을 모두 더한 값이고, 한국에서 흔히 쓰는 국가채무(D1)보다 넓다. 2025년
한국이 59.4% 로 나오는 것은 자료가 틀려서가 아니라 포괄 범위가 넓어서다.

멕시코와 노르웨이, 칠레, 튀르키예, 콜롬비아, 코스타리카는 이 계정에 값이 없다.
기준을 맞추려고 뺀 것이지 부채가 없어서가 아니다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-oecd-gov-debt"
URL = ("https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,1.2/.GGFLQ.A"
       "?startPeriod=%s&endPeriod=%s&dimensionAtObservation=AllDimensions")
PAGE = "https://data-explorer.oecd.org/"

KO = {
    "Japan": "일본", "Greece": "그리스", "Italy": "이탈리아", "United States": "미국",
    "France": "프랑스", "OECD": "OECD 전체", "Belgium": "벨기에", "Spain": "스페인",
    "Canada": "캐나다", "United Kingdom": "영국", "Portugal": "포르투갈",
    "Euro area (17 countries)": "유로존", "Finland": "핀란드", "Austria": "오스트리아",
    "Hungary": "헝가리", "Iceland": "아이슬란드", "Croatia": "크로아티아",
    "Slovenia": "슬로베니아", "Slovak Republic": "슬로바키아", "Poland": "폴란드",
    "Israel": "이스라엘", "Romania": "루마니아", "Germany": "독일",
    "New Zealand": "뉴질랜드", "Australia": "호주", "Latvia": "라트비아",
    "Korea": "한국", "Czechia": "체코", "Netherlands": "네덜란드", "Sweden": "스웨덴",
    "Lithuania": "리투아니아", "Switzerland": "스위스", "Ireland": "아일랜드",
    "Denmark": "덴마크", "Bulgaria": "불가리아", "Estonia": "에스토니아",
    "Luxembourg": "룩셈부르크", "Norway": "노르웨이", "Mexico": "멕시코",
    "Chile": "칠레", "Türkiye": "튀르키예", "Colombia": "콜롬비아",
    "Costa Rica": "코스타리카", "Turkey": "튀르키예",
}
# 묶음은 나라가 아니다. 따로 표시한다.
GROUPS = {"OECD 전체", "유로존"}


def pull(year):
    u = URL % (year, year)
    r = urllib.request.Request(u, headers={
        "User-Agent": "Mozilla/5.0 slowfactbook",
        "Accept": "application/vnd.sdmx.data+json;version=1.0"})
    d = json.loads(urllib.request.urlopen(r, timeout=120).read())
    st = d["data"].get("structure") or d["data"]["structures"][0]
    vals = st["dimensions"]["observation"][0]["values"]
    out = {}
    for k, v in d["data"]["dataSets"][0]["observations"].items():
        i = int(k.split(":")[0])
        if v[0] is None:
            continue
        out[vals[i]["name"]] = round(v[0], 1)
    return out


def upsert(item):
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    else:
        ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
        key = "S\x1f%s\x1f%s" % (SLIDE, item["title"])
        if ids.get(key):
            item["id"] = ids[key]
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
    ap.add_argument("--year", default="")
    a = ap.parse_args()

    # 올해 값은 전망치다. 끝난 해부터 찾아 내려온다. 해가 바뀌면 저절로 한 칸
    # 움직여서 손댈 일이 없다.
    year = a.year or str(datetime.datetime.now(KST).year - 1)
    raw = {}
    for y in range(int(year), int(year) - 4, -1):
        raw = pull(str(y))
        if len(raw) >= 20:
            year = str(y)
            break
    if not raw:
        raise SystemExit("OECD 에서 값을 받지 못했습니다.")

    miss = sorted(n for n in raw if n not in KO)
    if miss:
        raise SystemExit("한국어 이름이 없는 항목: %s" % miss)
    rows = sorted(((KO[n], v) for n, v in raw.items()), key=lambda x: -x[1])
    labels = [n for n, _ in rows]
    vals = [v for _, v in rows]
    kor = dict(rows).get("한국")

    print(f"OECD 경제전망 GGFLQ {year}년 — {len(rows)}개 항목")
    for n, v in rows:
        mark = "  ←" if n == "한국" else ("  (묶음)" if n in GROUPS else "")
        print(f"    {n:12s} {v:6.1f}{mark}")

    item = {
        "slide": SLIDE,
        "title": "GDP 대비 국가부채 비교",
        "category": "조세와 재정",
        "source": ("OECD 경제전망(Economic Outlook) 일반정부 총금융부채, GDP 대비. "
                   f"{year}년 기준. 국민계정 기준이라 한국에서 흔히 쓰는 "
                   "국가채무(D1)보다 포괄 범위가 넓다. 단위: %."),
        "sourceUrl": PAGE,
        "vizType": "bar", "unit": "%",
        "labels": labels,
        "series": [vals],
        "seriesNames": ["GDP 대비 부채"],
        "labelColors": {"한국": "#c0322f", "OECD 전체": "#6e6e6e", "유로존": "#6e6e6e"},
        "notes": [
            "OECD 경제전망의 한 계정(GGFLQ)에서 한꺼번에 받은 값입니다. 나라마다 "
            "다른 표에서 숫자를 긁어 모으면 기준이 섞입니다. 한국의 국가채무(D1)와 "
            "일본의 국가와 지방 장기채무를 한 그림에 나란히 세우는 것이 그런 "
            "경우인데, 포괄 범위가 달라 견줄 수 없습니다.",
            f"한국은 {kor}%입니다. 뉴스에서 자주 보는 '국가채무 비율 50% 안팎'과 "
            "다른 이유는 자료가 틀려서가 아니라 기준이 달라서입니다. 여기 쓴 "
            "일반정부 총금융부채는 중앙정부와 지방정부, 사회보장기금을 모두 "
            "더하고 미지급금 같은 항목까지 넣습니다. 국가채무(D1)는 중앙정부와 "
            "지방정부의 확정 채무만 셉니다.",
            "총부채입니다. 정부가 가진 금융자산을 빼지 않았습니다. 국민연금 "
            "적립금이 큰 한국이나 국부펀드가 큰 나라는 순부채로 보면 순위가 "
            "크게 달라집니다.",
            "일본이 유독 높은 것은 국채의 상당 부분을 일본은행과 국내 기관이 "
            "들고 있어 오래 버틸 수 있었기 때문입니다. 숫자만으로 위험도를 "
            "줄 세우기는 어렵습니다.",
            "멕시코와 노르웨이, 칠레, 튀르키예, 콜롬비아, 코스타리카는 이 계정에 "
            "값이 없어 빠졌습니다. 부채가 없어서가 아니라 기준을 맞추려고 뺀 "
            "것입니다. 반대로 크로아티아와 루마니아, 불가리아는 OECD 회원국이 "
            "아니지만 이 계정에 들어 있어 함께 실었습니다.",
            "'OECD 전체'와 '유로존'은 나라가 아니라 묶음이어서 회색으로 "
            "구분했습니다.",
            f"{year}년 값입니다. OECD 경제전망은 해마다 두 차례 나오고 지난 해 "
            "수치도 뒤에 고쳐집니다. 올해 값은 전망치여서 쓰지 않았습니다.",
        ],
        "updated": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    upsert(item)
    print("-> data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
