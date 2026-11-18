#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재는 방법에 따라 달라지는 건강수명.

  python3 scripts/hale_methods.py            # 미리보기
  python3 scripts/hale_methods.py --apply

'아프지 않고 사는 기간' 을 재는 방법이 셋이고 값이 크게 다르다. 같은 해 같은
나라를 두고 65년대와 73년대가 함께 나온다. 그 차이 자체를 보여 주는 차트다.

  유병기간 제외 기대수명   국가데이터처 생명표. 101/DT_1B46 항목 T1.
                      조사에서 "최근 2주간 아팠다" 고 답한 기간을 뺀다.
  주관적 건강평가 기대수명  같은 표 항목 T2. 스스로 건강하다고 답한 기간을 센다.
  건강수명(질병관리청)    「한 눈에 보는 건강수명」 통계집. 질병별 발생과 유병
                      자료에 장애가중치를 매겨 계산한다(설리반 방식).

앞의 둘은 2년 간격으로 2012년부터, 뒤의 하나는 해마다 2008년부터 있다. 이
차트는 셋이 겹치는 2년 간격 구간에 맞춘다.

국가데이터처 표의 주기 코드는 'F' 다. 'Y' 를 넣으면 자료가 없다고 나온다.

검산은 셋이다. 세 계열이 모두 50~90세 사이인지, 유병기간 제외 쪽이 주관적
평가 쪽보다 처음에는 높고 나중에는 낮아지는 역전이 실제로 있는지, 그리고
질병관리청 값이 hale_kdca.py 가 쓰는 값과 같은지 본다.
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
sys.path.insert(0, HERE)
import hale_kdca as K                                   # noqa: E402

TBL = "DT_1B46"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=" + TBL
ITM = [("T1", "유병기간 제외 기대수명", "#c0322f"),
       ("T2", "주관적 건강평가 기대수명", "#2a5ca8")]
KDCA = ("건강수명(질병관리청)", "#6a8f3c")


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


def pull(key, itm, y1):
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId=101&tblId={TBL}&prdSe=F"
         f"&startPrdDe=2010&endPrdDe={y1}&itmId={itm}&objL1=S0&objL2=01")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"{itm} 응답이 표가 아닙니다: {str(d)[:160]}")
    out = {int(x["PRD_DE"]): float(x["DT"])
           for x in d if x.get("DT") not in (None, "", "-")}
    if len(out) < 5:
        raise SystemExit(f"{itm} 받은 해가 {len(out)}개뿐입니다.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    got = {itm: pull(key, itm, now.year) for itm, _, _ in ITM}
    kd = dict(zip(K.TREND_Y, K.HALE))
    ys = sorted(set(got["T1"]) & set(got["T2"]))
    print(f"  국가데이터처 {len(ys)}년 {ys[0]}~{ys[-1]}, 질병관리청 "
          f"{len(kd)}년 {min(kd)}~{max(kd)}")

    # 검산 1. 값의 범위
    for itm, nm, _ in ITM:
        bad = [(y, v) for y, v in got[itm].items() if not 50 <= v <= 90]
        if bad:
            raise SystemExit(f"{nm} 에 범위를 벗어난 값: {bad[:3]}")
    print("    검산 범위: 세 계열 모두 50~90세 안")

    # 검산 2. 두 지표의 격차가 실제로 벌어졌는가
    first, last = ys[0], ys[-1]
    g0 = round(got["T2"][first] - got["T1"][first], 1)
    g1 = round(got["T2"][last] - got["T1"][last], 1)
    if not (abs(g0) < 1.5 and g1 > g0 + 3):
        raise SystemExit(f"두 지표의 격차 설명이 안 맞습니다. {first}년 {g0}년, "
                         f"{last}년 {g1}년. 설명을 손봐야 합니다.")
    print(f"    검산 격차: {first}년 {g0}년에서 {last}년 {g1}년으로 벌어짐")

    # 검산 3. 질병관리청 값이 통계집 스크립트와 같은가
    for y, e, h, g in zip(K.TREND_Y, K.EXPECT, K.HALE, K.TREND_GAP):
        if abs(round(e - h, 2) - g) > 0.011:
            raise SystemExit(f"{y}년 통계집 값이 어긋납니다.")
    print(f"    검산 통계집: {len(K.TREND_Y)}년 격차가 모두 맞습니다")

    ser = [[got[itm].get(y) for y in ys] for itm, _, _ in ITM]
    ser.append([kd.get(y) for y in ys])
    names = [nm for _, nm, _ in ITM] + [KDCA[0]]
    cols = [c for _, _, c in ITM] + [KDCA[1]]
    kl = [y for y in ys if y in kd]
    gap = got["T2"][last] - got["T1"][last]

    out = {
        "slide": "manual-hale-methods",
        "category": "건강과 보건",
        "title": "재는 방법에 따라 달라지는 건강수명",
        "vizType": "line", "unit": "세",
        "labels": [str(y) for y in ys],
        "series": ser, "seriesNames": names, "seriesColors": cols,
        "source": (f"유병기간 제외와 주관적 건강평가는 국가데이터처 생명표 "
                   f"건강수준별 기대여명, 건강수명은 질병관리청 「한 눈에 보는 "
                   f"건강수명, 2023」. 출생 시 기준, 남녀전체. {ys[0]}~{ys[-1]}년. "
                   f"단위: 세."),
        "sourceUrl": URL,
        "notes": [
            f"{last}년에 유병기간 제외 기대수명은 {got['T1'][last]}세, 주관적 "
            f"건강평가 기대수명은 {got['T2'][last]}세입니다. 같은 해 같은 나라인데 "
            f"{gap:.1f}년 차이가 납니다. {first}년에는 {got['T1'][first]}세와 "
            f"{got['T2'][first]}세로 {g0}년 차이에 그쳤습니다.",
            "세 계열은 재는 방법이 다릅니다. 유병기간 제외는 조사에서 최근 2주간 "
            "아팠다고 답한 기간을 빼고, 주관적 건강평가는 스스로 건강하다고 답한 "
            "기간을 세고, 질병관리청 건강수명은 질병별 발생과 유병 자료에 "
            "장애가중치를 매겨 계산합니다.",
            "방향도 서로 반대입니다. 주관적 건강평가는 계속 올라가고 유병기간 "
            f"제외는 {first}년 {got['T1'][first]}세에서 {last}년 "
            f"{got['T1'][last]}세로 제자리이거나 내려갔습니다. 사람들이 스스로 더 "
            "건강하다고 여기게 된 것과 아픈 기간이 줄어든 것은 같은 말이 "
            "아닙니다.",
            f"질병관리청 계열은 {kl[-1]}년까지입니다. 통계집이 해마다 나오는데 "
            "가장 최근 판이 2023년까지 담고 있습니다. 해마다의 값은 c0237 에 "
            "따로 있습니다.",
            "앞의 두 계열은 2년 간격으로만 공표됩니다. 그래서 이 차트도 2년 "
            "간격입니다.",
            "어느 하나가 맞고 나머지가 틀린 것이 아닙니다. 건강수명을 인용할 때 "
            "어느 기준인지 밝히지 않으면 8년 가까이 다른 숫자가 같은 이름으로 "
            "돌아다니게 됩니다.",
        ],
        "updated": ymd,
    }
    print(f"\n  {out['title']} {len(ys)}점 {ys[0]}~{ys[-1]}")
    for nm, s in zip(names, ser):
        v = [x for x in s if x is not None]
        print(f"    {nm:22s} {v[0]} ... {v[-1]}  ({len(v)}점)")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    o = by.get(out["slide"])
    if o:
        keep = {k: o[k] for k in ("id",) if k in o}
        o.clear(); o.update(out); o.update(keep)
    else:
        doc["items"].append(out)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
