#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GDP 대비 공공사회복지지출(c0231)을 KOSIS 표에서 다시 받는다.

  KOSIS_API_KEY=... python3 scripts/socx.py            # 미리보기
  KOSIS_API_KEY=... python3 scripts/socx.py --apply

보건복지부 '총사회복지지출 비율(GDP 대비)' 표(DT_11777_N220)는 네 갈래로
나뉜다. 총계와 공공지출, 법정민간지출, 자발적민간지출이다. 이 차트는 그 가운데
공공지출만 그린다. 국제 비교에서 쓰는 OECD SOCX 의 public 에 해당한다.

총계는 2022년까지만 있고 공공지출은 2024년까지 있다. 둘을 한 그림에 올리면
뒤쪽 두 해가 비어 오해를 부르므로 공공지출만 둔다.

대조해서 어긋나면 소급 수정으로 보고 KOSIS 값으로 덮는다. 이 통계는 국민계정
개편과 지출 재분류로 지난 해 숫자가 뒤에 바뀐다.
"""
import argparse, datetime, json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CID = "c0231"
ORG, TBL = "117", "DT_11777_N220"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=117&tblId=DT_11777_N220"


def pull(key):
    q = {"method": "getList", "apiKey": key, "format": "json", "jsonVD": "Y",
         "orgId": ORG, "tblId": TBL, "itmId": "ALL", "objL1": "ALL",
         "prdSe": "Y", "startPrdDe": "1990",
         "endPrdDe": str(datetime.datetime.now(KST).year)}
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{a}={urllib.parse.quote(str(b), safe='+')}" for a, b in q.items()))
    d = json.loads(urllib.request.urlopen(u, timeout=90).read().decode("utf-8"))
    if isinstance(d, dict):
        raise SystemExit("KOSIS: " + str(d)[:120])
    out = {}
    for r in d:
        out.setdefault(r["C1_NM"], {})[r["PRD_DE"]] = float(r["DT"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    raw = pull(key)
    pub = raw.get("공공지출") or {}
    tot = raw.get("총계") or {}
    if len(pub) < 20:
        raise SystemExit(f"공공지출 값이 {len(pub)}개뿐입니다 — 쓰지 않습니다.")
    years = sorted(pub)

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    full = {i["id"]: i for i in
            json.load(open(os.path.join(DATA, "full.json"), encoding="utf-8"))["items"]
            if i.get("id")}
    cur = {**full.get(CID, {}), **(ov.get(CID) or {})}
    old = dict(zip([str(x) for x in (cur.get("labels") or [])],
                   (cur.get("series") or [[]])[0]))
    moved = [(y, old.get(y), pub[y]) for y in years
             if old.get(y) is not None and round(old[y], 1) != round(pub[y], 1)]
    added = [y for y in years if y not in old]

    print(f"KOSIS {TBL} 공공지출 {years[0]} ~ {years[-1]} ({len(years)}개 해)")
    print(f"  총계는 {min(tot) if tot else '-'} ~ {max(tot) if tot else '-'} 까지만 있습니다.")
    for y, o, n in moved:
        print(f"  소급 수정 {y}: {o} -> {n}")
    if added:
        print(f"  새로 붙는 해: {added}")
    if not moved and not added:
        print("  바뀐 값 없음")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0

    last = years[-1]
    o = ov.setdefault(CID, {})
    o["id"] = CID
    o["title"] = "GDP 대비 공공사회복지지출"
    o["labels"] = years
    o["series"] = [[pub[y] for y in years]]
    o["seriesNames"] = ["공공사회복지지출"]
    o["unit"] = "%"
    o["source"] = ("보건복지부 총사회복지지출 비율(KOSIS 표 DT_11777_N220) 가운데 "
                   f"공공지출. {years[0]}~{last}년. 단위: %.")
    o["sourceUrl"] = URL
    o["notes"] = [
        "공공지출만 그렸습니다. 원래 표는 총계와 공공지출, 법정민간지출, "
        "자발적민간지출 네 갈래입니다. 국제 비교에서 쓰는 OECD 의 공공사회복지지출"
        "(SOCX public)에 해당하는 것이 이 공공지출입니다.",
        ("총계를 같이 그리지 않은 이유는 수록 기간이 달라서입니다. 총계는 "
         f"{max(tot)}년까지인데 공공지출은 {last}년까지 있습니다. 한 그림에 "
         f"올리면 뒤쪽 두 해가 비어 총계가 줄어든 것처럼 보입니다. 참고로 "
         f"{max(tot)}년 총계는 {tot[max(tot)]}%이고 공공지출은 {pub[max(tot)]}%입니다. "
         "나머지가 법정민간과 자발적민간 몫입니다.") if tot else
        "총계 계열은 이번에 받지 못했습니다.",
        "2020년에 크게 뛴 것은 분자와 분모가 같이 움직였기 때문입니다. 코로나로 "
        "지출이 늘었고 명목 GDP 증가가 멈췄습니다. 비율 지표를 볼 때 분모 쪽 "
        "변화를 같이 봐야 하는 전형적인 해입니다.",
        "지난 해 숫자가 뒤에 바뀝니다. 국민계정 기준년 개편과 지출 재분류 "
        "때문입니다. 이 차트도 KOSIS 를 다시 받을 때마다 과거 값을 덮습니다.",
        "국제 비교에는 그대로 쓰기 어렵습니다. OECD 가 따로 집계한 SOCX 와 "
        "발표 시점과 분류가 달라 같은 해라도 소수점이 어긋날 수 있습니다.",
    ]
    o["updated"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
