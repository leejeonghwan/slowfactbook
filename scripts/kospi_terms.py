#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""역대 정부 코스피 지수(c0687)를 취임 달 기준으로 다시 그린다.

  python3 scripts/kospi_terms.py            # 미리보기
  python3 scripts/kospi_terms.py --apply

가로축이 날짜가 아니라 '취임 뒤 몇 번째 달'이라서 market_update.py 의 라벨
맞추기로는 안 되고, 그래서 따로 둔다. admin_cpi.py 와 같은 구조다.

한 달은 한 정부에만 넣는다. 정권이 바뀐 달은 들어오는 쪽이 가져간다
(2008년 2월은 이명박). 탄핵과 파면 뒤 권한대행 기간은 어느 쪽에도 넣지
않는다(2017년 4월, 2025년 5월이 비어 있다).

월말 종가는 한국은행 ECOS 의 KOSPI 일별 자료(802Y001 0001000)에서 그 달의
마지막 거래일을 뽑아 쓴다. 야후 파이낸스 월간 캔들(c2206)을 쓰지 않는 이유는
1990년대가 틀리기 때문이다. 당시 증시는 토요일 오전에도 열렸는데 야후는 그
장을 빠뜨린다(1997년 5월 31일, 1998년 5월 30일과 10월 31일이 모두 토요일이고
세 달 모두 값이 다르게 나온다).

ECOS 일별 자료는 1995년 1월부터다. 그 앞은 원천이 없어서 기존 값을 그대로
둔다. 노태우 정부 전체와 김영삼 정부 앞부분이 여기에 해당한다.

대조해서 어긋나면 아무것도 쓰지 않고 멈춘다. 원천이 바뀐 것을 모르고 조용히
덮는 것이 가장 나쁘기 때문이다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CID = "c0687"
KEY = os.environ.get("ECOS_API_KEY", "")
TITLE = "역대 정부 코스피 지수"

# (이름, 첫 달, 마지막 달). 마지막 달이 None 이면 임기 중이라 최근 달까지 그린다.
#   노태우 1988-02-25 ~ 1993-02-24
#   김영삼 1993-02-25 ~ 1998-02-24
#   김대중 1998-02-25 ~ 2003-02-24
#   노무현 2003-02-25 ~ 2008-02-24
#   이명박 2008-02-25 ~ 2013-02-24
#   박근혜 2013-02-25 ~ 2017-03-10 (탄핵)
#   문재인 2017-05-10 ~ 2022-05-09
#   윤석열 2022-05-10 ~ 2025-04-04 (파면)
#   이재명 2025-06-04 ~
TERMS = [("노태우", "1988-02", "1993-01"),
         ("김영삼", "1993-02", "1998-01"),
         ("김대중", "1998-02", "2003-01"),
         ("노무현", "2003-02", "2008-01"),
         ("이명박", "2008-02", "2013-01"),
         ("박근혜", "2013-02", "2017-03"),
         ("문재인", "2017-05", "2022-04"),
         ("윤석열", "2022-05", "2025-04"),
         ("이재명", "2025-06", None)]

SPAN = 61          # 가로축 칸 수. 5년 임기가 60달이고 한 칸을 여유로 둔다.


def step(m, k):
    y, mo = int(m[:4]), int(m[5:7])
    t = (y * 12 + mo - 1) + k
    return "%04d-%02d" % (t // 12, t % 12 + 1)


def months(a, b):
    out, m = [], a
    while m <= b:
        out.append(m); m = step(m, 1)
    return out


def month_end():
    """{'YYYY-MM': 그 달 마지막 거래일 종가}. ECOS 일별을 5년씩 끊어 받는다."""
    out, now = {}, datetime.datetime.now(KST)
    for y0 in range(1995, now.year + 1, 5):
        y1 = min(y0 + 4, now.year)
        u = ("https://ecos.bok.or.kr/api/StatisticSearch/" + KEY +
             "/json/kr/1/100000/802Y001/D/%d0101/%d1231/0001000" % (y0, y1))
        d = json.loads(urllib.request.urlopen(u, timeout=120).read().decode("utf-8"))
        if "RESULT" in d:
            raise SystemExit("ECOS: " + d["RESULT"].get("MESSAGE", "")[:100])
        for r in d.get("StatisticSearch", {}).get("row", []):
            v = r.get("DATA_VALUE")
            if v in (None, "", "."):
                continue
            t = str(r["TIME"])
            m = t[:4] + "-" + t[4:6]
            if m not in out or t >= out[m][0]:
                out[m] = (t, float(v))
    # 진행 중인 달은 뺀다. 아직 월말 종가가 아니다.
    now = now.strftime("%Y-%m")
    return {m: v for m, (_, v) in out.items() if m < now}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not KEY:
        raise SystemExit("ECOS_API_KEY 가 필요합니다(.env).")
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    kospi = month_end()
    have = sorted(kospi)
    print(f"코스피 월말 종가 {have[0]} ~ {have[-1]} ({len(kospi)}개월)")

    cur = ov.get(CID) or {}
    old = [list(s) for s in (cur.get("series") or [])]
    names = [nm for nm, _, _ in TERMS]
    if len(old) != len(names):
        raise SystemExit(f"계열 수가 {len(old)}개로 기대({len(names)})와 다릅니다.")

    bad, cols, note = [], [], []
    for j, (nm, s, e) in enumerate(TERMS):
        last = e or have[-1]
        ms = [m for m in months(s, last) if m in kospi][:SPAN]
        if not ms:
            cols.append(old[j][:SPAN] + [None] * (SPAN - len(old[j][:SPAN])))
            note.append(f"    {nm}: 원천 없음 — 기존 {len([x for x in old[j] if x is not None])}점 유지")
            continue
        # 덮기 전에 겹치는 구간을 통째로 대조한다.
        base = months(s, last)
        for i, m in enumerate(base[:SPAN]):
            o = old[j][i] if i < len(old[j]) else None
            n = kospi.get(m)
            if o is not None and n is not None and round(o, 2) != round(n, 2):
                bad.append((nm, m, o, n))
        col = [kospi.get(m) for m in base[:SPAN]]
        # 원천이 없는 앞 구간은 기존 값을 살린다(노태우·김영삼 경계).
        for i, v in enumerate(col):
            if v is None and i < len(old[j]) and old[j][i] is not None:
                col[i] = old[j][i]
        col += [None] * (SPAN - len(col))
        cols.append(col)
        n = len([x for x in col if x is not None])
        note.append(f"    {nm}: {base[0]} ~ {base[min(n, SPAN) - 1] if n else '-'} {n}점")

    print("\n".join(note))
    if bad:
        print(f"\n  어긋남 {len(bad)}곳 — 아무것도 쓰지 않습니다.")
        for nm, m, o, n in bad[:20]:
            print(f"    {nm} {m}: 차트 {o} / ECOS {n}")
        return 1
    print(f"  겹치는 구간 대조 — 일치")

    moved = cols != [list(s) + [None] * (SPAN - len(s)) for s in old]
    print(f"  바뀐 값 {'있음' if moved else '없음'}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0

    o = ov.setdefault(CID, {})
    o["id"] = CID
    o["title"] = TITLE
    o["labels"] = (["1년차"] + [""] * 11 + ["2년차"] + [""] * 11 + ["3년차"] + [""] * 11
                   + ["4년차"] + [""] * 11 + ["5년차"] + [""] * 11 + ["임기 말"])
    o["series"] = cols
    o["seriesNames"] = names
    o["unit"] = "p"
    o["source"] = ("한국은행 ECOS KOSPI 일별 자료에서 뽑은 월말 종가. 각 정부 취임한 "
                   "달을 1년차 첫 칸에 두고 임기 끝까지. 1995년 이전은 기존 팩트북 "
                   "계열. 단위: p.")
    o["sourceUrl"] = "https://ecos.bok.or.kr/#/Short/7a6d1c"
    o["notes"] = [
        "가로축은 날짜가 아니라 취임 뒤 몇 번째 달입니다. 임기가 겹치지 않는 "
        "정부들을 같은 출발선에 세워 견주려는 것입니다. 같은 칸이라도 정부마다 "
        "실제 연도가 다릅니다.",
        "한 달은 한 정부에만 넣었습니다. 정권이 바뀐 달은 들어오는 쪽이 가져갑니다. "
        "2008년 2월은 이명박 정부의 첫 달로 셌습니다.",
        "탄핵과 파면 뒤 권한대행 기간은 어느 쪽에도 넣지 않았습니다. 2017년 4월과 "
        "2025년 5월이 비어 있습니다. 그래서 박근혜 정부는 50점, 윤석열 정부는 "
        "36점에서 끊깁니다.",
        "지수의 절대 수준이 정부마다 크게 다릅니다. 노태우 정부의 600선과 이재명 "
        "정부의 5000선을 같은 축에 놓으면 앞쪽 정부들의 등락은 거의 평평하게 "
        "보입니다. 상승률로 견주려면 역대 정부 코스피 상승률 쪽을 보십시오.",
        "월말 종가입니다. 임기 중 꼭지와 바닥은 이 선에 드러나지 않습니다.",
        "1995년 이전 값은 기존 팩트북 계열을 그대로 두었습니다. 한국은행 ECOS 의 "
        "KOSPI 일별 자료가 1995년 1월부터여서 그 앞은 대조할 원천이 없습니다. "
        "노태우 정부 전체와 김영삼 정부 앞부분이 여기에 해당합니다.",
        "야후 파이낸스의 월간 자료는 쓰지 않았습니다. 1990년대 증시는 토요일 "
        "오전에도 열렸는데 야후 월간 캔들이 그 장을 빠뜨립니다. 1997년 5월과 "
        "1998년 5월, 10월의 월말이 모두 토요일이고 세 달 모두 값이 달라집니다.",
    ]
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
