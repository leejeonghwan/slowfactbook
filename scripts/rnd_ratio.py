#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연구개발비 비율 두 장을 KOSIS 에서 다시 받는다.

  KOSIS_API_KEY=... python3 scripts/rnd_ratio.py            # 미리보기
  KOSIS_API_KEY=... python3 scripts/rnd_ratio.py --apply

  c1119  GDP 대비 연구개발비, 나라 비교   OECD MSTI (KOSIS 표 DT_2OEST001, T03)
  c1130  GDP 대비 연구개발비, 재원별 추이  과기정통부 (KOSIS 표 DT_KBA0001)

c1119 는 원래 Statista 를 출처로 적어 두고 값을 소수(0.0602)로 담고 있었다.
단위는 % 였으니 화면에는 6.02% 가 아니라 0.06% 로 떴다. 100 배 틀린 숫자가
떠 있던 셈이라 계정째 바꿨다. OECD 표에는 대만과 중국, 싱가포르처럼 회원이
아닌 나라도 들어 있어 견줄 범위가 오히려 넓어진다.

c1130 은 재원을 둘로 나눈 값이다. 표에 비율이 바로 있지는 않아서 재원별
금액(백만 원)을 국내총생산(십억 원)으로 나눠 직접 계산한다. 둘을 더하면
표의 '국내총생산대비(A/B)' 와 맞아야 한다. 어긋나면 멈춘다.
"""
import argparse, datetime, json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CROSS, TREND = "c1119", "c1130"
GROUPS = {"OECD", "유럽연합", "EU"}


def pull(key, org, tbl, start="1960"):
    q = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": org, "tblId": tbl, "itmId": "ALL", "objL1": "ALL", "prdSe": "Y",
         "startPrdDe": start, "endPrdDe": str(datetime.datetime.now(KST).year)}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{a}={urllib.parse.quote(str(b), safe='+')}" for a, b in q.items()))
    d = json.loads(urllib.request.urlopen(u, timeout=150).read().decode("utf-8"))
    if isinstance(d, dict):
        raise SystemExit(f"KOSIS {tbl}: " + str(d)[:120])
    return d


def save(ov, cid, patch):
    o = ov.setdefault(cid, {})
    o["id"] = cid
    o.update(patch)
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def build_cross(key):
    rows = [r for r in pull(key, "101", "DT_2OEST001", "2000")
            if r["ITM_ID"] == "T03"]
    by = {}
    for r in rows:
        by.setdefault(r["PRD_DE"], {})[r["C1_NM"]] = float(r["DT"])
    # 나라가 가장 많이 찬 최근 해를 쓴다. 맨 끝 해는 몇 나라만 올라와 있다.
    full = max(len(v) for v in by.values())
    year = max(y for y, v in by.items() if len(v) >= full * 0.8)
    vals = {n.replace("[비회원국]", ""): round(v, 2) for n, v in by[year].items()}
    rank = sorted(vals.items(), key=lambda x: -x[1])
    labels = [n for n, _ in rank]
    kor = vals.get("대한민국")
    place = labels.index("대한민국") + 1
    print(f"  c1119  OECD MSTI {year}년 — {len(labels)}개 항목")
    print(f"         상위 {[f'{n} {v}' for n, v in rank[:5]]}")
    print(f"         대한민국 {kor}% ({place}위)")
    return year, labels, [v for _, v in rank], kor, place


def build_trend(key):
    rows = pull(key, "127", "DT_KBA0001", "1976")
    by = {}
    for r in rows:
        by.setdefault(r["C1_NM"], {})[r["PRD_DE"]] = float(r["DT"])
    gov, pri = by["정부·공공재원"], by["민간·외국재원"]
    gdp, ratio = by["국내총생산(B)"], by["국내총생산대비(A/B)"]
    years = sorted(set(gov) & set(pri) & set(gdp) & set(ratio))
    g = [round(gov[y] / 1000 / gdp[y] * 100, 4) for y in years]
    p = [round(pri[y] / 1000 / gdp[y] * 100, 4) for y in years]
    # 두 재원을 더하면 표의 전체 비율과 맞아야 한다.
    bad = [(y, round(a + b, 2), ratio[y]) for y, a, b in zip(years, g, p)
           if abs(a + b - ratio[y]) > 0.05]
    if bad:
        raise SystemExit(f"c1130: 재원 합이 전체 비율과 어긋납니다 — {bad[:5]}")
    print(f"  c1130  과기정통부 {years[0]} ~ {years[-1]} ({len(years)}개 해) — 합계 대조 일치")
    print(f"         {years[-1]}년 정부·공공 {g[-1]:.2f}% + 민간·외국 {p[-1]:.2f}%"
          f" = {ratio[years[-1]]}%")
    return years, g, p, ratio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    year, labels, vals, kor, place = build_cross(key)
    years, g, p, ratio = build_trend(key)
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))

    save(ov, CROSS, {
        "title": "GDP 대비 연구개발비, 나라 비교",
        "labels": labels, "series": [vals],
        "seriesNames": ["GDP 대비 연구개발비"],
        "unit": "%", "vizType": "bar",
        "labelColors": {"대한민국": "#c0322f", "OECD": "#6e6e6e"},
        "source": (f"OECD 과학기술산업 주요지표(MSTI) 국내총연구개발비(GERD) 가운데 "
                   f"GDP 대비 비율, {year}년 기준(KOSIS 표 DT_2OEST001). 단위: %."),
        "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_2OEST001",
        "notes": [
            "국내총연구개발비(GERD)입니다. 정부와 기업, 대학, 비영리기관이 쓴 "
            "연구개발비를 모두 더한 값이라 정부 예산만 보는 것과 다릅니다. "
            "한국은 이 가운데 기업 몫이 4분의 3 가까이 됩니다.",
            f"{year}년 기준입니다. 나라마다 발표 시기가 달라 몇 나라는 더 최근 "
            "값이 나와 있지만, 기준을 맞추려고 대부분의 나라가 올라온 해를 "
            "골랐습니다.",
            f"대한민국은 {kor}%로 {len(labels)}개 항목 가운데 {place}위입니다. "
            "비율이 높다는 것이 성과가 좋다는 뜻은 아닙니다. 분모인 GDP 규모와 "
            "산업 구성에 따라 달라집니다.",
            "OECD 회원이 아닌 나라도 들어 있습니다. 대만과 중국, 싱가포르, "
            "러시아 등입니다. 원래 표의 '[비회원국]' 표시는 떼고 적었습니다.",
            "'OECD'는 나라가 아니라 회원국을 묶은 값이어서 회색으로 "
            "구분했습니다.",
            "같은 해 국내 집계와 소수점이 어긋날 수 있습니다. 과학기술정보통신부 "
            "연구개발활동조사와 OECD 가 쓰는 분모와 환산 시점이 다릅니다. "
            "나라끼리 견줄 때는 이 표를, 한국의 흐름을 볼 때는 국내 표를 "
            "쓰는 편이 낫습니다.",
            "전에는 이 차트가 Statista 를 출처로 적고 값을 소수로 담고 있었습니다. "
            "단위가 %여서 6.02%가 0.06%로 떴습니다. 계정을 OECD 원자료로 "
            "바꾸면서 바로잡았습니다.",
        ],
    })

    save(ov, TREND, {
        "title": "GDP 대비 연구개발비, 재원별",
        "labels": years,
        "series": [[round(x, 2) for x in g], [round(x, 2) for x in p]],
        "seriesNames": ["정부와 공공 재원", "민간과 외국 재원"],
        "unit": "%", "vizType": "line",
        "seriesColors": ["#2f5e8e", "#f5a623"],
        "source": ("과학기술정보통신부 연구개발활동조사(KOSIS 표 DT_KBA0001). "
                   "재원별 연구개발비를 국내총생산으로 나눈 값. 단위: %."),
        "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=127&tblId=DT_KBA0001",
        "notes": [
            "연구개발비를 '누가 댔는가'로 나눈 것입니다. 연구를 누가 수행했는지와 "
            "다릅니다. 정부가 댄 돈으로 기업이 연구하는 경우가 많습니다.",
            "표에 비율이 바로 있지는 않아 재원별 금액을 국내총생산으로 나눠 "
            "계산했습니다. 두 선을 더하면 표가 공표하는 전체 비율과 맞는 것을 "
            f"{len(years)}개 해 모두에서 확인했습니다. "
            f"{years[-1]}년은 {g[-1]:.2f} + {p[-1]:.2f} = {ratio[years[-1]]}%입니다.",
            "민간과 외국 재원이 8할 가까이입니다. 이 비중은 주요국 가운데 높은 "
            "편이고, 그만큼 기업 사정에 따라 나라 전체 연구개발비가 흔들립니다.",
            "분모가 국내총생산이라 경기와 물가가 섞여 있습니다. 비율이 올랐다고 "
            "연구개발비 자체가 그만큼 늘어난 것은 아닙니다.",
            "국민계정 기준년이 바뀌면 분모가 달라져 과거 비율도 함께 움직입니다. "
            "이 차트는 KOSIS 를 다시 받을 때마다 전체를 덮습니다.",
        ],
    })

    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
