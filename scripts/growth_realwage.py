#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경제 성장률과 실질임금 상승률(c0156).

  python3 scripts/growth_realwage.py            # 미리보기
  python3 scripts/growth_realwage.py --apply

이 차트는 어댑터가 없어 2024년에 멈춰 있었고, 성장률 계열이 한국은행의 옛
기준년 국민계정이었다. 2020년 기준년으로 개편된 지금 공표값과 다르다. 그래서
2025년만 덧붙이면 한 차트 안에 두 기준년이 섞인다. 성장률은 통째로 다시
세운다.

  성장률     한국은행 ECOS 200Y101 주요지표(연간), 항목 20101 국내총생산 실질성장률
  검산       같은 한국은행의 지출 쪽 실질 GDP(200Y110, 항목 10601)로 전년대비
            증감률을 따로 계산해 해마다 맞는지 본다

실질임금 상승률은 고용노동부 사업체노동력조사의 명목임금을 소비자물가지수로
나눈 값이다. 차트에 적혀 있던 값의 정체를 다음과 같이 확인했다. 명목 전체
임금총액(KOSIS 118/DT_118N_MON051)과 소비자물가지수(ECOS 901Y009)로 직접
계산한 2021~2024년이 차트 값과 0.04%p 안에서 재현된다.

문제는 명목임금 연간값을 받을 수 있는 구간이 2020년부터라는 것이다. 산업분류
차수가 바뀌면서 그 전 표가 내려갔다. 그래서 2012~2020년은 차트에 있던 값을
그대로 두고, 2021년부터는 계산해서 쓴다. 같은 조사의 같은 계산법이므로 기준이
갈리지 않는다. 재현 검산이 그걸 확인한다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
Y0 = 2012
ECOS = "https://ecos.bok.or.kr/api/StatisticSearch"
U_G = "https://ecos.bok.or.kr/"
U_W = "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_MON051"

# 2020년까지의 실질임금 상승률. 명목임금 연간 표가 2020년부터만 공개돼
# 되짚을 수 없는 구간이라 차트에 있던 값을 그대로 둔다.
PRE = {2012: 3.0, 2013: 2.1, 2014: 1.1, 2015: 2.3, 2016: 2.8,
       2017: 1.3, 2018: 3.7, 2019: 3.0, 2020: 0.5}


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


def get(url, what):
    r = subprocess.run(["curl", "-sS", "--max-time", "170", url], capture_output=True)
    if r.returncode:
        raise SystemExit(f"{what} 내려받기 실패: " + r.stderr.decode()[:120])
    return json.loads(r.stdout.decode("utf-8", "replace"))


def ecos(key, tbl, item, y1):
    d = get(f"{ECOS}/{key}/json/kr/1/200/{tbl}/A/{Y0 - 1}/{y1}/{item}", f"ECOS {tbl}")
    rows = (d.get("StatisticSearch") or {}).get("row")
    if not rows:
        raise SystemExit(f"ECOS {tbl} {item} 응답이 비었습니다: {str(d)[:160]}")
    return {int(x["TIME"]): float(x["DATA_VALUE"])
            for x in rows if x.get("DATA_VALUE") not in (None, "")}


def kosis(key, y1):
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId=118&tblId=DT_118N_MON051"
         f"&prdSe=Y&startPrdDe=2020&endPrdDe={y1}&itmId=13103110311MD_12"
         "&objL1=190326INDUSTRY_10S0&objL2=size01")
    d = get(u, "KOSIS 명목임금")
    if not isinstance(d, list):
        raise SystemExit(f"KOSIS 명목임금 응답이 표가 아닙니다: {str(d)[:160]}")
    return {int(x["PRD_DE"]): float(x["DT"])
            for x in d if x.get("DT") not in (None, "", "-")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ek, kk = envkey("ECOS_API_KEY"), envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    y1 = now.year
    ymd = now.strftime("%Y-%m-%d %H:%M")

    # ── 성장률
    g = ecos(ek, "200Y101", "20101", y1)
    gdp = ecos(ek, "200Y110", "10601", y1)
    ys = sorted(y for y in g if y >= Y0)
    if len(ys) < 12:
        raise SystemExit(f"성장률 받은 해가 {len(ys)}년뿐입니다.")
    bad = []
    for y in ys:
        if y - 1 in gdp and y in gdp:
            calc = (gdp[y] / gdp[y - 1] - 1) * 100
            if abs(calc - g[y]) > 0.061:
                bad.append((y, g[y], round(calc, 2)))
    if bad:
        raise SystemExit(f"성장률이 지출 쪽 실질 GDP 계산과 어긋납니다: {bad[:5]}")
    print(f"    검산 성장률: {len(ys)}년 모두 지출 쪽 실질 GDP 로 다시 계산한 값과 일치")

    # ── 실질임금 상승률
    w = kosis(kk, y1)
    cpi = ecos(ek, "901Y009", "0", y1)
    rw = {}
    for y in sorted(w):
        if y - 1 in w and y in cpi and y - 1 in cpi:
            rw[y] = round(((w[y] / cpi[y]) / (w[y - 1] / cpi[y - 1]) - 1) * 100, 1)
    if not rw:
        raise SystemExit("실질임금 상승률을 계산할 수 없습니다.")
    # 차트에 있던 값이 재현되는가
    old = {**PRE, 2021: 2.0, 2022: -0.2, 2023: -1.1, 2024: 0.5}
    chk = [(y, old[y], rw[y]) for y in rw if y in old and abs(old[y] - rw[y]) > 0.061]
    if chk:
        raise SystemExit(f"계산한 실질임금 상승률이 기존 값과 어긋납니다: {chk}. "
                         f"조사 기준이 바뀌었을 수 있어 쓰지 않습니다.")
    seen = sorted(y for y in rw if y in old)
    print(f"    검산 실질임금: {len(seen)}년({seen[0]}~{seen[-1]}) 기존 값과 재현")

    wage = dict(PRE)
    wage.update(rw)
    # 연도가 이어지는지
    miss = [y for y in ys if y not in wage]
    if miss and miss != [ys[-1]]:
        raise SystemExit(f"실질임금이 빠진 해: {miss}")
    if miss:
        print(f"    실질임금 {miss[0]}년은 아직 없어 비워 둡니다.")

    gs = [g[y] for y in ys]
    ws = [wage.get(y) for y in ys]
    last = ys[-1]
    lw = max((y for y in ys if wage.get(y) is not None), default=None)
    neg = [y for y in ys if wage.get(y) is not None and wage[y] < 0]
    out = {
        "c0156": {
            "id": "c0156",
            "title": "경제 성장률과 실질임금 상승률.",
            "vizType": "column", "unit": "%",
            "labels": [str(y) for y in ys],
            "series": [gs, ws],
            "seriesNames": ["경제 성장률.", "실질임금 상승률."],
            "seriesColors": ["#2a5ca8", "#c0322f"],
            "source": (f"경제 성장률은 한국은행 국민계정 국내총생산 실질성장률. "
                       f"실질임금 상승률은 고용노동부 사업체노동력조사 전체 근로자 "
                       f"1인당 월평균 임금총액을 국가데이터처 소비자물가지수로 나눈 "
                       f"값. {ys[0]}~{last}년. 단위: %."),
            "sourceUrl": U_W,
            "notes": [
                f"{last}년 성장률은 {g[last]}% 입니다. 실질임금 상승률은 "
                + (f"{lw}년 {wage[lw]}% 가 가장 최근입니다."
                   if lw != last else f"{wage[last]}% 입니다."),
                (f"실질임금이 줄어든 해는 {', '.join(str(y) for y in neg)}년입니다. "
                 "물가가 임금보다 빨리 올랐다는 뜻입니다." if neg else
                 "실질임금이 줄어든 해는 없습니다."),
                "성장률 계열을 통째로 다시 세웠습니다. 전에 실려 있던 값은 한국은행의 "
                "옛 기준년 국민계정이었습니다. 기준년이 2020년으로 개편되면서 공표값이 "
                "바뀌었습니다. 2021년이 4.3%에서 4.7%로, 2024년이 2.0%에서 2.2%로 "
                "올라갔습니다. 옛 값과 새 값을 한 차트에 섞을 수 없어 전부 새 "
                "기준으로 갈았습니다. 다른 자료에서 본 숫자와 다를 수 있습니다.",
                "실질임금 상승률은 명목임금을 소비자물가지수로 나눈 값입니다. "
                "명목임금 연간값을 받을 수 있는 구간이 2020년부터여서, 2021년부터는 "
                "직접 계산하고 그 전은 기존 값을 그대로 뒀습니다. 같은 조사의 같은 "
                "계산법이고, 겹치는 해에 계산값이 기존 값과 0.1%포인트 안에서 "
                "재현되는 것을 확인했습니다.",
                "두 막대는 대상이 다릅니다. 성장률은 나라 경제 전체이고, 실질임금은 "
                "상용근로자 1인 이상 사업체에 다니는 임금근로자입니다. 자영업자와 "
                "무급가족종사자는 임금 쪽에 들어 있지 않습니다. 성장이 임금으로 "
                "얼마나 돌아갔는지를 이 두 막대의 차이로 바로 계산할 수는 없습니다.",
                "임금총액에는 상여금과 성과급이 들어 있습니다. 특별급여가 몰린 해에 "
                "명목임금이 튀고, 그 반작용으로 이듬해가 낮게 나오기도 합니다.",
            ],
            "updated": ymd,
        }
    }
    print(f"\n  c0156 {len(ys)}점 {ys[0]}~{last}")
    for n, s in zip(out["c0156"]["seriesNames"], out["c0156"]["series"]):
        print(f"    {n:14s} {s[0]} ... {s[-1]}")
    print("    성장률:", ", ".join(f"{y}:{g[y]}" for y in ys))
    print("    실질임금:", ", ".join(f"{y}:{wage.get(y)}" for y in ys))
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "overrides.json")
    ov = json.load(open(p, encoding="utf-8"))
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
