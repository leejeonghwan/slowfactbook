#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초등학교 입학 연령 인구. 주민등록 만 6세 인구와, 이미 태어난 아이들로 본
앞으로 6년.

  python3 scripts/school_entry_age.py            # 미리보기
  python3 scripts/school_entry_age.py --apply

교육부가 내는 '입학자 수' 를 쓰고 싶었지만 국가통계포털에서 받을 수가 없다.
교육통계연보의 '초등학교 개황'(334/DT_1963003_002)에 입학자수 항목이 정의돼
있는데 어떤 조합으로 불러도 값이 돌아오지 않고, 같은 표의 최신판에는 항목
자체가 빠졌다. 교육통계서비스(KESS)는 자동 접근을 막는다.

그래서 주민등록 1세별 인구(101/DT_1B04006)의 만 6세를 쓴다. 초중등교육법은
만 6세가 된 해의 다음 해 3월에 입학시키게 하므로, 어느 해 말의 만 6세 인구가
이듬해 입학 대상과 거의 겹친다. 취학률이 98% 안팎이어서 수준도 비슷하다.

이 자료의 쓸모는 앞을 볼 수 있다는 데 있다. 2031년에 만 6세가 될 아이들은
이미 태어나 주민등록에 올라 있다. 추계가 아니라 이미 있는 숫자를 한 살씩
밀어 놓는 것이다. 믿을 만한지 과거로 확인했다. 어느 해 만 n세와 이듬해 만
n+1세를 견주면 만 1세부터 6세까지는 평균 0.1~0.4% 밖에 어긋나지 않는다.
만 0세만 평균 4.2% 늘어나는데 출생신고가 늦게 들어오기 때문이다. 그래서
마지막 해는 하한으로 읽어야 한다.
"""
import argparse, datetime, json, os, re, statistics, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

ORG, TBL = "101", "DT_1B04006"
SLIDE = "manual-school-entry-age"
URL = ("https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B04006")
ENTRY = 6          # 입학 직전 연령
BACK = 6           # 앞으로 몇 해를 밀어 볼 것인가


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
         f"&prdSe=Y&startPrdDe=2008&endPrdDe={now}&itmId=T2&objL1=00&objL2=ALL")
    r = subprocess.run(["curl", "-sS", "--max-time", "120", u], capture_output=True)
    if r.returncode != 0:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit("KOSIS 응답이 표가 아닙니다: " + str(d)[:160])
    age = {}
    for x in d:
        m = re.fullmatch(r"(\d+)세", str(x.get("C2_NM") or ""))
        if m and x.get("DT") not in (None, "", "-"):
            age.setdefault(int(m.group(1)), {})[x["PRD_DE"]] = int(x["DT"])
    if ENTRY not in age:
        raise SystemExit("만 6세 인구를 찾지 못했습니다.")
    return age


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    age = fetch()
    yrs = sorted(age[ENTRY])
    last = yrs[-1]
    if len(yrs) < 12:
        raise SystemExit(f"받은 해가 {len(yrs)}개뿐입니다 — 쓰지 않습니다.")

    # 코호트 이동이 믿을 만한지 과거로 확인한다. 어느 해 만 n세와 이듬해
    # 만 n+1세가 같은 아이들이어야 한다. 어긋나면 밀어 보는 일을 하지 않는다.
    err = {}
    for n in range(0, ENTRY + 1):
        g = [(age[n + 1][str(int(y) + 1)] - age[n][y]) / age[n][y] * 100
             for y in yrs[:-1]
             if n + 1 in age and str(int(y) + 1) in age[n + 1] and y in age[n]]
        if len(g) < 10:
            raise SystemExit(f"만 {n}세 코호트 대조 표본이 {len(g)}개뿐입니다.")
        err[n] = (statistics.fmean(g), min(g), max(g))
    print(f"주민등록 1세별 인구 {yrs[0]}~{last} ({len(yrs)}개 해)")
    print("  코호트 이동 오차(%) — 어느 해 만 n세 대비 이듬해 만 n+1세")
    for n, (m, lo, hi) in err.items():
        print(f"    만 {n}세 -> {n + 1}세: 평균 {m:+.2f}  범위 {lo:+.2f}~{hi:+.2f}")
    bad = [n for n in range(1, ENTRY + 1) if abs(err[n][0]) > 1.5 or abs(err[n][2]) > 2.5]
    if bad:
        raise SystemExit(f"만 {bad} 세의 코호트 이동이 어긋납니다 — 쓰지 않습니다.")
    if not 1.5 <= err[0][0] <= 8.0:
        raise SystemExit(f"만 0세 신고 지연 폭이 평균 {err[0][0]:+.2f}% 입니다 — "
                         "예상 범위를 벗어나 쓰지 않습니다.")
    print(f"  만 1~{ENTRY}세는 모두 오차 범위 안입니다. 만 0세만 신고 지연으로 "
          f"평균 {err[0][0]:+.2f}%")

    # 앞으로 BACK 해. 마지막 해의 만 (ENTRY-k)세가 last+k 년의 만 6세가 된다.
    fore = {}
    for k in range(1, BACK + 1):
        n = ENTRY - k
        if n in age and last in age[n]:
            fore[str(int(last) + k)] = age[n][last]
    lab = [str(y) for y in range(int(yrs[0]), int(last) + BACK + 1)]
    real = [round(age[ENTRY][y] / 10000, 2) if y in age[ENTRY] else None for y in lab]
    # 두 선이 이어지게 마지막 실적 해를 추정 쪽에도 넣는다.
    proj = [round(fore[y] / 10000, 2) if y in fore
            else (round(age[ENTRY][last] / 10000, 2) if y == last else None) for y in lab]

    top = max((y for y in yrs), key=lambda y: age[ENTRY][y])
    trough = min(fore, key=lambda y: fore[y]) if fore else None
    print(f"  만 6세 인구: {top}년 {age[ENTRY][top] / 10000:.2f}만 명이 가장 많고 "
          f"{last}년 {age[ENTRY][last] / 10000:.2f}만 명")
    for y in sorted(fore):
        print(f"    {y}년 예상 {fore[y] / 10000:.2f}만 명 (지금 만 {ENTRY - (int(y) - int(last))}세)")

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    item = {
        "slide": SLIDE, "category": "인구 구조",
        "title": "초등학교 입학 연령 인구",
        "vizType": "line", "unit": "만 명", "yMin": 0,
        "labels": lab, "series": [real, proj],
        "seriesNames": ["만 6세 인구", "이미 태어난 아이들"],
        "seriesColors": ["#2f5e8e", "#c0322f"],
        "source": ("국가데이터처 주민등록 1세별 인구. 각 해 12월 기준 만 6세 인구와, "
                   f"{last}년 현재 만 0~5세를 한 살씩 밀어 본 값. 단위: 만 명."),
        "sourceUrl": URL,
        "notes": [
            f"{top}년 {age[ENTRY][top] / 10000:.2f}만 명에서 {last}년 "
            f"{age[ENTRY][last] / 10000:.2f}만 명으로 줄었습니다. "
            f"{(1 - age[ENTRY][last] / age[ENTRY][top]) * 100:.0f}% 감소입니다.",
            "교육부가 내는 '입학자 수' 가 아니라 주민등록 인구입니다. 초중등교육법은 "
            "만 6세가 된 해의 다음 해 3월에 입학시키게 하므로, 어느 해 말의 만 6세 "
            "인구가 이듬해 입학 대상과 거의 겹칩니다. 취학률이 98% 안팎이어서 수준도 "
            "비슷하지만 같은 숫자는 아닙니다. 조기 입학과 입학 유예, 취학 의무 "
            "면제가 빠져 있습니다.",
            "교육부 입학자 수를 쓰지 않은 것은 받을 수가 없어서입니다. 국가통계포털의 "
            "교육통계연보 표에 입학자수 항목이 정의돼 있는데 어떤 조합으로 불러도 "
            "값이 돌아오지 않고, 같은 표의 최신판에는 항목 자체가 빠졌습니다. "
            "교육통계서비스는 자동 접근을 막습니다.",
            "빨간 선은 추계가 아닙니다. " + (
                f"{sorted(fore)[0]}년부터 {sorted(fore)[-1]}년까지 만 6세가 될 아이들은 "
                "이미 태어나 주민등록에 올라 있습니다. 지금의 만 0~5세를 한 살씩 "
                "밀어 놓은 것입니다." if fore else ""),
            f"밀어 보는 방식이 믿을 만한지 과거로 확인했습니다. 어느 해 만 n세와 "
            f"이듬해 만 n+1세를 {len(yrs) - 1}개 해에 걸쳐 견주면 만 1세부터 "
            f"{ENTRY}세까지는 평균 "
            f"{min(err[n][0] for n in range(1, ENTRY + 1)):.2f}~"
            f"{max(err[n][0] for n in range(1, ENTRY + 1)):.2f}% 밖에 어긋나지 "
            "않습니다. 사망과 국제 이동이 그만큼 적습니다.",
            f"다만 마지막 해({sorted(fore)[-1] if fore else '-'})는 하한으로 "
            f"읽어야 합니다. 만 0세는 출생신고가 늦게 들어와 이듬해 만 1세가 될 때 "
            f"평균 {err[0][0]:+.2f}% 늘어납니다. 그만큼 올려 보면 "
            + (f"{fore[sorted(fore)[-1]] * (1 + err[0][0] / 100) / 10000:.2f}만 명쯤 "
               "됩니다." if fore else "") ,
            (f"가장 적은 해는 {trough}년의 {fore[trough] / 10000:.2f}만 명입니다. "
             "그 뒤에 조금 늘어나는 것은 2024년에 출생아 수가 반등한 몫입니다. "
             "다만 반등한 수준이 2010년대 중반의 절반에 못 미칩니다.") if trough else "",
            "연말 기준이라 한 연령에 두 해 출생아가 섞입니다. 예를 들어 어느 해 말의 "
            "만 6세는 그 전 해 말부터 그 해 말 사이에 여섯 번째 생일을 맞은 "
            "아이들입니다. 그래서 출생아 수 차트와 한 해씩 정확히 맞아떨어지지는 "
            "않습니다.",
            "2008년에서 시작하는 것은 주민등록 1세별 인구가 그때부터 공표되기 "
            "때문입니다. 더 거슬러 올라간 흐름은 초등학생 수 차트에서 보십시오. "
            "1960년대에는 지금의 두 배가 넘었습니다.",
            "주민등록 기준이어서 외국인은 빠지고, 해외에 살면서 주민등록을 둔 아이는 "
            "들어 있습니다. 학교 현장의 입학생 수와는 이 두 방향으로 어긋납니다.",
        ],
        "updated": now,
    }
    item["notes"] = [n for n in item["notes"] if n]

    print(f"\n  {SLIDE} — {len(lab)}개 해 ({lab[0]}~{lab[-1]}), 비고 {len(item['notes'])}개")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0

    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    ids = json.load(open(os.path.join(DATA, "ids.json"), encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == SLIDE), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    else:
        k = "S\x1f%s\x1f%s" % (SLIDE, item["title"])
        if ids.get(k):
            item["id"] = ids[k]
    if cur:
        doc["items"][doc["items"].index(cur)] = item
    else:
        doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/manual.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
