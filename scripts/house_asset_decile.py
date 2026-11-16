#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주택자산 상위 10%와 하위 10%(주택소유통계).

  python3 scripts/house_asset_decile.py            # 미리보기
  python3 scripts/house_asset_decile.py --apply

국가데이터처 주택소유통계 「주택자산가액기준 10분위별 주택소유가구 기본현황」
(101/DT_1OH0411) 에서 받는다. 2015년부터 있다.

검산은 두 가지다. 열 분위가 해마다 상위에서 하위로 순서가 지켜지는지 보고,
분위별 평균을 단순평균한 값이 표의 총계와 어긋나지 않는지 본다. 열 분위는
가구 수가 같게 나눈 것이므로 단순평균이 총계와 맞아야 한다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_1OH0411"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=" + TBL
ORDER = ["10분위(상위10%)", "9분위", "8분위", "7분위", "6분위",
         "5분위", "4분위", "3분위", "2분위", "1분위(하위10%)"]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId=101&tblId={TBL}&prdSe=Y"
         f"&startPrdDe=2015&endPrdDe={now.year}&itmId=T001&objL1=ALL")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"응답이 표가 아닙니다: {str(d)[:160]}")
    m, unit = {}, None
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        m.setdefault(x["C1_NM"], {})[int(x["PRD_DE"])] = float(x["DT"])
        unit = x.get("UNIT_NM")
    if unit != "억원":
        raise SystemExit(f"단위가 '억원' 이 아닙니다: {unit!r}")
    miss = [q for q in ORDER + ["총계"] if q not in m]
    if miss:
        raise SystemExit(f"응답에 없는 분위: {miss}")

    ys = sorted(set.intersection(*[set(m[q]) for q in ORDER + ["총계"]]))
    if len(ys) < 8:
        raise SystemExit(f"받은 해가 {len(ys)}년뿐입니다.")
    for y in ys:
        v = [m[q][y] for q in ORDER]
        if v != sorted(v, reverse=True):
            raise SystemExit(f"{y}년 분위 순서가 어긋납니다: {dict(zip(ORDER, v))}")
    print(f"    검산 분위 순서: {len(ys)}년 모두 상위에서 하위로 지켜짐")
    bad = []
    for y in ys:
        avg = sum(m[q][y] for q in ORDER) / 10
        if abs(avg - m["총계"][y]) > max(0.03, m["총계"][y] * 0.02):
            bad.append((y, round(avg, 3), m["총계"][y]))
    if bad:
        raise SystemExit(f"분위 평균과 총계가 어긋납니다: {bad[:5]}")
    print(f"    검산 분위 평균 대 총계: {len(ys)}년 모두 2% 안")

    top = [round(m["10분위(상위10%)"][y], 2) for y in ys]
    bot = [round(m["1분위(하위10%)"][y], 2) for y in ys]
    rat = [round(m["10분위(상위10%)"][y] / m["1분위(하위10%)"][y], 1) for y in ys]
    tot = [round(m["총계"][y], 2) for y in ys]
    last = ys[-1]
    pk = ys[top.index(max(top))]
    lo = ys[rat.index(min(rat))]

    def won(x):
        o, man = int(x), round((x - int(x)) * 10000)
        if man == 10000:          # 반올림이 억으로 올라가는 경우
            o, man = o + 1, 0
        if not o:
            return f"{man:,}만 원"
        return f"{o}억 {man:,}만 원" if man else f"{o}억 원"

    out = {
        "slide": "manual-house-asset-decile",
        "category": "부동산",
        "title": "주택자산 상위 10%와 하위 10%",
        "vizType": "combo", "unit": "억 원, 배",
        "labels": [str(y) for y in ys],
        "series": [top, bot, rat],
        "seriesNames": ["상위 10%", "하위 10%", "배율(상위÷하위)"],
        "seriesKinds": ["bar", "bar", "line"],
        "seriesAxes": [0, 0, 1],
        "seriesColors": ["#2a5ca8", "#8aa6c8", "#c0322f"],
        "source": (f"국가데이터처 주택소유통계 주택자산가액기준 10분위별 주택소유가구 "
                   f"기본현황. {ys[0]}~{last}년. 각 해 1월 1일 공시가격 기준. "
                   f"단위: 억 원, 배."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년 상위 10%는 가구당 평균 {won(top[-1])}, 하위 10%는 "
            f"{won(bot[-1])} 입니다. {rat[-1]}배 차이로 {ys[0]}년 이후 가장 "
            f"큽니다. 가장 좁았던 해는 {lo}년 {min(rat)}배였습니다.",
            f"하위 10%는 {ys[0]}년 {won(bot[0])}에서 {last}년 {won(bot[-1])}으로 "
            f"거의 움직이지 않았습니다. 같은 기간 상위 10%는 {won(top[0])}에서 "
            f"{won(top[-1])}으로 {top[-1] / top[0]:.1f}배가 됐습니다. 배율이 벌어진 "
            "것은 아래가 내려가서가 아니라 위가 올라가서입니다.",
            "주택을 가진 가구만 대상입니다. 무주택 가구는 아예 빠져 있습니다. "
            "그래서 '하위 10%'는 전체 가구의 하위 10%가 아니라 집을 가진 가구 "
            "가운데 하위 10%입니다. 무주택까지 넣으면 격차는 이보다 큽니다. "
            "무주택 가구 비율은 c0580 에 있습니다.",
            "시세가 아니라 공시가격 기준입니다. 공시가격은 시세보다 낮게 매겨지고 "
            "그 비율도 해마다 달라집니다. "
            f"{pk}년 {won(max(top))}에서 이듬해 크게 내려앉은 것에는 집값 하락만이 "
            "아니라 공시가격 산정 방침이 바뀐 몫이 섞여 있습니다. 해마다의 등락을 "
            "집값 등락으로 그대로 읽으면 안 됩니다.",
            f"전체 평균은 {last}년 {won(tot[-1])} 입니다. 가구별 합계가 아니라 "
            "가구당 평균이고, 한 가구가 여러 채를 가졌으면 그 합이 그 가구의 "
            "자산가액입니다.",
            "분위는 주택자산가액으로 가른 것이라 소득 분위와 다릅니다. 소득이 적어도 "
            "집값이 오른 가구는 위쪽 분위에 들어갑니다.",
        ],
        "updated": ymd,
    }
    print(f"\n  {out['title']} {len(ys)}점 {ys[0]}~{last}")
    for n, s in zip(out["seriesNames"], out["series"]):
        print(f"    {n:16s} {s[0]} ... {s[-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    old = by.get(out["slide"])
    if old:
        keep = {k: old[k] for k in ("id",) if k in old}
        old.clear(); old.update(out); old.update(keep)
    else:
        doc["items"].append(out)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
