#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OECD 회원국의 GDP 대비 일반정부 총부채를 한 장에 세운다.

  python3 scripts/debt_compare.py            # 미리보기
  python3 scripts/debt_compare.py --apply

IMF World Economic Outlook 의 GGXWDG_NGDP 한 계정만 쓴다. 나라마다 다른 표에서
숫자를 긁어 모으면 기준이 섞인다. 한국의 '국가채무(D1)' 와 일본의 다른 기준
수치를 한 막대 그림에 나란히 세우는 것이 그런 경우인데, 포괄 범위가 달라
견줄 수 없다. 그래서 한 계정에서 한꺼번에 받는다.

OECD 경제전망(GGFLQ)도 같은 것을 재지만 값이 다르다. 2025년 기준으로 겹치는
35개 나라 가운데 일치하는 것이 하나도 없고 평균 8.8%p, 일본은 31.7%p 벌어진다
(OECD 236.5 / IMF 204.8). IMF 를 고른 이유는 둘이다. 멕시코와 노르웨이, 칠레,
튀르키예가 OECD 경제전망 계정에는 없고, 팩트북의 다른 부채 차트(c0669, c0670)가
이미 같은 IMF 계정을 써서 한국 값이 서로 맞는다.

IMF 에는 OECD 전체 같은 묶음 값이 없다. 회원국 단순 평균을 내서 '평균'인 척
세우면 GDP 가중인 공표 수치와 다른 숫자가 되므로 넣지 않고, 대신 한국의
순위를 비고에 적는다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-oecd-gov-debt"
IND = "GGXWDG_NGDP"
API = "https://www.imf.org/external/datamapper/api/v1/%s/%s"
PAGE = "https://www.imf.org/external/datamapper/GGXWDG_NGDP"

# OECD 회원국 38 개.
OECD = [
    ("JPN", "일본"), ("GRC", "그리스"), ("ITA", "이탈리아"), ("USA", "미국"),
    ("FRA", "프랑스"), ("BEL", "벨기에"), ("ESP", "스페인"), ("CAN", "캐나다"),
    ("GBR", "영국"), ("PRT", "포르투갈"), ("FIN", "핀란드"), ("AUT", "오스트리아"),
    ("HUN", "헝가리"), ("ISL", "아이슬란드"), ("SVN", "슬로베니아"),
    ("SVK", "슬로바키아"), ("POL", "폴란드"), ("ISR", "이스라엘"), ("DEU", "독일"),
    ("NZL", "뉴질랜드"), ("AUS", "호주"), ("LVA", "라트비아"), ("KOR", "한국"),
    ("CZE", "체코"), ("NLD", "네덜란드"), ("SWE", "스웨덴"), ("LTU", "리투아니아"),
    ("CHE", "스위스"), ("IRL", "아일랜드"), ("DNK", "덴마크"), ("EST", "에스토니아"),
    ("LUX", "룩셈부르크"), ("MEX", "멕시코"), ("NOR", "노르웨이"), ("CHL", "칠레"),
    ("TUR", "튀르키예"), ("COL", "콜롬비아"), ("CRI", "코스타리카"),
]


def fetch(cty):
    """{"YYYY": 값}. urllib 이 자주 막혀 curl 로 받는다(imf_update.py 와 같다)."""
    out = subprocess.run(["curl", "-sS", "--compressed", "--max-time", "20",
                          API % (IND, cty)], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:120])
    v = (json.loads(out.stdout).get("values") or {}).get(IND, {}).get(cty) or {}
    return {str(k): float(x) for k, x in v.items() if x is not None}


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

    # 올해 값은 전망치다. 끝난 해를 쓴다. 해가 바뀌면 저절로 한 칸 움직인다.
    year = a.year or str(datetime.datetime.now(KST).year - 1)
    got, fail = {}, []
    for code, name in OECD:
        try:
            s = fetch(code)
        except Exception as e:
            fail.append((name, str(e)[:60])); continue
        if year in s:
            got[name] = round(s[year], 1)
        else:
            fail.append((name, f"{year}년 값 없음"))
    if len(got) < 30:
        raise SystemExit(f"받은 나라가 {len(got)}개뿐입니다 — 쓰지 않습니다.")

    rows = sorted(got.items(), key=lambda x: -x[1])
    labels = [n for n, _ in rows]
    vals = [v for _, v in rows]
    rank = labels.index("한국") + 1
    kor = got["한국"]

    print(f"IMF World Economic Outlook {IND} {year}년 — {len(rows)}개국")
    for n, v in rows:
        print(f"    {n:10s} {v:6.1f}" + ("  ←" if n == "한국" else ""))
    if fail:
        print("  받지 못한 나라:", fail)
    print(f"  한국 {kor}% — {len(rows)}개국 가운데 {rank}위")

    item = {
        "slide": SLIDE,
        "title": "GDP 대비 국가부채 비교",
        "category": "조세와 재정",
        "source": (f"IMF World Economic Outlook 일반정부 총부채(GDP 대비), {year}년 "
                   "기준. OECD 회원국만 추렸다. 국제 비교 기준이라 한국에서 흔히 "
                   "쓰는 국가채무(D1)보다 포괄 범위가 넓다. 단위: %."),
        "sourceUrl": PAGE,
        "vizType": "bar", "unit": "%",
        "labels": labels,
        "series": [vals],
        "seriesNames": ["GDP 대비 부채"],
        "labelColors": {"한국": "#c0322f"},
        "notes": [
            "IMF 의 한 계정에서 한꺼번에 받은 값입니다. 나라마다 다른 표에서 "
            "숫자를 모으면 기준이 섞여 막대 길이를 견줄 수 없습니다. 한국의 "
            "국가채무(D1)와 일본의 다른 기준 수치를 나란히 세우는 것이 그런 "
            "경우입니다.",
            f"한국은 {kor}%로 {len(rows)}개국 가운데 {rank}위입니다. 뉴스에서 "
            "자주 보는 수치와 다를 수 있습니다. 여기 쓴 일반정부 총부채는 "
            "중앙정부와 지방정부, 비영리공공기관을 아우르는 국제 비교 기준이고, "
            "국가채무(D1)는 중앙정부와 지방정부의 확정 채무만 셉니다.",
            "같은 것을 재는 OECD 경제전망 수치와도 값이 다릅니다. 2025년 기준으로 "
            "겹치는 35개국 가운데 일치하는 것이 하나도 없고 평균 8.8%p 벌어집니다. "
            "일본은 OECD 236.5%, IMF 204.8%로 31.7%p 차이입니다. 어느 쪽이 "
            "틀린 것이 아니라 포괄 범위와 평가 방법이 다릅니다. 팩트북의 다른 "
            "부채 차트와 기준을 맞추려고 IMF 쪽을 썼습니다.",
            "총부채입니다. 정부가 가진 금융자산을 빼지 않았습니다. 국민연금 "
            "적립금이 큰 한국이나 국부펀드가 큰 노르웨이는 순부채로 보면 순위가 "
            "크게 달라집니다.",
            "일본이 유독 높은 것은 국채의 상당 부분을 일본은행과 국내 기관이 "
            "들고 있어 오래 버틸 수 있었기 때문입니다. 숫자만으로 위험도를 "
            "줄 세우기는 어렵습니다.",
            "IMF 에는 OECD 전체 같은 묶음 값이 없어 평균 막대를 넣지 않았습니다. "
            "회원국 단순 평균을 내면 GDP 가중으로 내는 공표 수치와 다른 숫자가 "
            "되기 때문입니다.",
            f"{year}년 값입니다. IMF 는 해마다 두 차례 자료를 고쳐 내고 지난 해 "
            "수치도 뒤에 바뀝니다. 올해 값은 전망치여서 쓰지 않았습니다.",
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
