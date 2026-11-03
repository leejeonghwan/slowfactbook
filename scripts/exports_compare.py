#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주요 7개국의 연도별 상품 수출액을 한 장에 겹친다.

  python3 scripts/exports_compare.py            # 미리보기
  python3 scripts/exports_compare.py --apply

세계은행 World Development Indicators 의 BX.GSR.MRCH.CD 한 계정만 쓴다.
국제수지 기준 상품 수출이고 현재 미국 달러 표시다. 나라마다 다른 통계청에서
숫자를 가져오면 평가 시점과 환율, 통관과 국제수지 기준 차이로 견줄 수 없다.

서비스를 포함한 수출(NE.EXP.GNFS.CD)도 있지만 쓰지 않았다. 한국에서 '수출'은
대개 상품 수출을 뜻하고, 그 계정이 7개국 모두 가장 최근 해까지 차 있다.
다만 영국처럼 서비스 비중이 큰 나라는 상품만 보면 작게 보인다.

일본은 이 계정에 1996년부터 값이 있다. 그래서 가로축을 1996년부터 잡았다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

SLIDE = "manual-exports-7"
IND = "BX.GSR.MRCH.CD"
# 보여 줄 차례. 2025년 수출액이 큰 쪽부터다.
CTY = [("CHN", "중국"), ("USA", "미국"), ("DEU", "독일"), ("JPN", "일본"),
       ("KOR", "한국"), ("FRA", "프랑스"), ("GBR", "영국")]
START = 1996
API = ("https://api.worldbank.org/v2/country/%s/indicator/" + IND +
       "?format=json&per_page=4000&date=%d:%d")


def pull(end):
    u = API % (";".join(c for c, _ in CTY), START, end)
    r = subprocess.run(["curl", "-sS", "--compressed", "--max-time", "90", u],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:120])
    d = json.loads(r.stdout)
    if not isinstance(d, list) or len(d) < 2 or not d[1]:
        raise RuntimeError("세계은행에서 값을 받지 못했습니다.")
    out = {}
    for x in d[1]:
        if x.get("value") is None:
            continue
        out.setdefault(x["countryiso3code"], {})[x["date"]] = x["value"]
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
    a = ap.parse_args()

    raw = pull(datetime.datetime.now(KST).year)
    miss = [n for c, n in CTY if c not in raw]
    if miss:
        raise SystemExit("값이 없는 나라: %s" % miss)

    # 마지막 해는 아직 다 차지 않은 나라가 있다. 7개국이 모두 있는 해까지만 그린다.
    years = sorted(set.intersection(*[set(raw[c]) for c, _ in CTY]))
    labels = [y for y in years if int(y) >= START]
    cols = [[round(raw[c][y] / 1e9, 1) for y in labels] for c, _ in CTY]
    last = labels[-1]

    print(f"세계은행 {IND} — {labels[0]} ~ {last} ({len(labels)}개 해)")
    for (c, n), col in zip(CTY, cols):
        print(f"    {n:5s} {col[0]:8.1f} -> {col[-1]:8.1f} 십억 달러"
              f"  (받은 범위 {min(raw[c])}~{max(raw[c])})")
    kor = dict(zip([n for _, n in CTY], cols))["한국"][-1]
    chn = dict(zip([n for _, n in CTY], cols))["중국"][-1]
    print(f"  {last}년 중국이 한국의 {chn / kor:.1f}배")

    item = {
        "slide": SLIDE,
        "title": "주요국 수출",
        "category": "수출과 무역",
        "source": ("세계은행 World Development Indicators 상품 수출(BX.GSR.MRCH.CD). "
                   "국제수지 기준, 현재 미국 달러. 단위: 십억 달러."),
        "sourceUrl": "https://data.worldbank.org/indicator/BX.GSR.MRCH.CD",
        "vizType": "line", "unit": "십억 달러",
        "labels": labels,
        "series": cols,
        "seriesNames": [n for _, n in CTY],
        "notes": [
            "세계은행의 한 계정에서 한꺼번에 받은 값입니다. 나라마다 자기 통계청 "
            "숫자를 가져오면 통관 기준과 국제수지 기준, 평가 시점, 환율이 달라 "
            "막대 길이를 견줄 수 없습니다.",
            "상품 수출입니다. 서비스는 들어 있지 않습니다. 영국처럼 금융과 "
            "사업서비스 수출이 큰 나라는 이 그림에서 실제보다 작게 보입니다. "
            "서비스를 포함하면 영국은 2024년 500십억 달러가 아니라 1,148십억 "
            "달러로 독일 다음입니다.",
            "현재 달러 표시라 물가와 환율이 섞여 있습니다. 실질 수출 물량의 "
            "변화만 보려면 다른 자료가 필요합니다. 특히 달러가 강했던 해는 "
            "비달러권 나라의 수출이 줄어 보입니다.",
            f"중국이 {last}년 기준 한국의 {chn / kor:.1f}배입니다. 2001년 세계무역"
            "기구 가입 뒤 중국이 올라선 궤적이 이 그림의 가장 큰 변화입니다.",
            "일본은 이 계정에 1996년부터 값이 있어 가로축을 그 해부터 잡았습니다. "
            "다른 나라는 1970년대 값도 있지만 기준을 맞추려고 잘랐습니다.",
            "유럽 나라들의 수출에는 유럽연합 안에서 오간 몫이 들어 있습니다. "
            "독일과 프랑스의 숫자를 미국이나 중국과 견줄 때는 이 점을 "
            "감안해야 합니다.",
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
