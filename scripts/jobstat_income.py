#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""일자리행정통계 임금근로일자리 소득 차트.

  python3 scripts/jobstat_income.py            # 미리보기
  python3 scripts/jobstat_income.py --apply

국가데이터처 일자리행정통계(KOSIS 101). 쓰는 표는 넷이다.

  DT_1EP_2005  성별 소득
  DT_1EP_2012  기업규모별 성별 소득
  DT_1EP_2001  기업규모별 소득
  DT_1EP_2014  기업규모별 연령대별 소득

네 표 모두 '가장 최근 한 해'만 담는다. 그래서 통째로 다시 까는 대신 표에
담긴 해를 차트에 이어 붙인다. 이미 들어 있으면 값이 맞는지만 보고 넘어가고,
어긋나면 그 차트는 건드리지 않는다.

연도별 추이 차트(c0184, c0185, c0186, c0191)는 해마다 한 점씩 늘고,
연령대별 스냅샷(c0188)은 해가 바뀌면 통째로 갈린다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

NOTES = [
    "국가데이터처 일자리행정통계입니다. 건강보험과 국민연금, 국세 자료를 모은 "
    "행정자료 기반이라 표본조사가 아닙니다. 임금근로일자리를 가진 사람의 "
    "세전 월평균 소득입니다.",
    "평균소득은 상위 소득자에게 끌려 올라갑니다. 체감에 가까운 값은 중위소득인데 "
    "이 차트는 평균입니다.",
    "대기업과 중소기업은 공정거래법과 중소기업기본법의 기업집단 구분을 따릅니다. "
    "사업체 규모(몇 인 이상)와는 다른 기준입니다.",
]
AGE = [("19세 이하", "10"), ("20대", "2"), ("30대", "3"), ("40대", "4"),
       ("50대", "5"), ("60대", "6"), ("70세 이상", "7")]

# 차트별 설계. kind=year 는 해마다 한 점씩, kind=snap 은 해마다 통째로.
REGISTRY = {
    "c0184": dict(kind="year", tbl="DT_1EP_2005", itm="T001", o1="110+", o2="1+2+",
                  keys=[("C2_NM", "남자"), ("C2_NM", "여자")],
                  title="성별 연도별 임금 격차",
                  source="국가데이터처 일자리행정통계. 임금근로일자리 월평균 소득. 단위: 만 원."),
    "c0185": dict(kind="year", tbl="DT_1EP_2012", itm="T001", o1="1+2+", o2="11+",
                  keys=[("C1_NM", "남자"), ("C1_NM", "여자")],
                  title="대기업 성별 연도별 임금 격차",
                  source="국가데이터처 일자리행정통계. 대기업 임금근로일자리 월평균 소득. 단위: 만 원."),
    "c0186": dict(kind="year", tbl="DT_1EP_2012", itm="T001", o1="1+2+", o2="12+",
                  keys=[("C1_NM", "남자"), ("C1_NM", "여자")],
                  title="중소기업 성별 연도별 임금 격차",
                  source="국가데이터처 일자리행정통계. 중소기업 임금근로일자리 월평균 소득. 단위: 만 원."),
    "c0191": dict(kind="year", tbl="DT_1EP_2001", itm="T001", o1="110+", o2="11+12+",
                  keys=[("C2_NM", "대기업"), ("C2_NM", "중소기업")],
                  title="기업규모별 연도별 임금 격차",
                  source="국가데이터처 일자리행정통계. 임금근로일자리 월평균 소득. 단위: 만 원."),
    "c0188": dict(kind="snap", tbl="DT_1EP_2014", itm="T001",
                  o1="".join(c + "+" for _, c in AGE), o2="11+12+",
                  title="대기업과 중소기업 연령대별 임금 격차",
                  source="국가데이터처 일자리행정통계. 임금근로일자리 월평균 소득. 단위: 만 원."),
}


def pull(tbl, itm, o1, o2, key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=101&tblId=%s&prdSe=Y&itmId=%s+"
           "&objL1=%s&objL2=%s&newEstPrdCnt=1" % (key, tbl, itm, o1, o2))
    with urllib.request.urlopen(url, timeout=120) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        return [], None
    rows = [x for x in doc if x.get("DT")]
    return rows, (rows[0]["PRD_DE"] if rows else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    base = {}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and "items" in doc:
            for it in doc["items"]:
                if it.get("id"):
                    base[it["id"]] = it

    touched = 0
    for cid, sp in REGISTRY.items():
        rows, year = pull(sp["tbl"], sp["itm"], sp["o1"], sp["o2"], key)
        if not rows:
            print("  %s 자료를 받지 못했습니다." % cid)
            continue
        cur = {**base.get(cid, {}), **(ov.get(cid) or {})}
        meta = dict(id=cid, title=sp["title"], source=sp["source"], unit="만 원",
                    sourceUrl="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=" + sp["tbl"],
                    notes=NOTES,
                    updated=datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M"))

        if sp["kind"] == "year":
            vals = []
            for col, nm in sp["keys"]:
                v = [float(x["DT"]) for x in rows if x.get(col) == nm]
                vals.append(round(v[0], 1) if v else None)
            if None in vals:
                print("  %s 계열을 못 찾았습니다." % cid)
                continue
            lab = [str(x) for x in (cur.get("labels") or [])]
            ser = [list(s) for s in (cur.get("series") or [])]
            if len(ser) != len(vals):
                print("  %s 계열 수가 다릅니다." % cid)
                continue
            if year in lab:
                i = lab.index(year)
                bad = [j for j, v in enumerate(vals)
                       if ser[j][i] is not None and abs(ser[j][i] - v) > max(1.0, abs(v) * 0.01)]
                if bad:
                    for j in bad:
                        print("  어긋남 %s %s: 차트 %s / KOSIS %s" % (cid, year, ser[j][i], vals[j]))
                    print("  %s 는 건드리지 않습니다." % cid)
                    continue
                ov[cid] = {**(ov.get(cid) or {}), **meta}
                print("  %s 이미 %s년 반영됨 (출처와 비고만 갱신)" % (cid, year))
                touched += 1
                continue
            lab.append(year)
            for j, v in enumerate(vals):
                ser[j].append(v)
            order = sorted(range(len(lab)), key=lambda i: lab[i])
            ov[cid] = {**(ov.get(cid) or {}), **meta,
                       "labels": [lab[i] for i in order],
                       "series": [[s[i] for i in order] for s in ser]}
            print("  %s 에 %s년 추가 (%s)" % (cid, year, vals))
            touched += 1
        else:
            big, sml = [], []
            for nm, _ in AGE:
                b = [float(x["DT"]) for x in rows if x.get("C1_NM") == nm.replace("20대", "20~29세")
                     .replace("30대", "30~39세").replace("40대", "40~49세").replace("50대", "50~59세")
                     .replace("60대", "60~69세") and x.get("C2_NM") == "대기업"]
                s = [float(x["DT"]) for x in rows if x.get("C1_NM") == nm.replace("20대", "20~29세")
                     .replace("30대", "30~39세").replace("40대", "40~49세").replace("50대", "50~59세")
                     .replace("60대", "60~69세") and x.get("C2_NM") == "중소기업"]
                big.append(round(b[0], 1) if b else None)
                sml.append(round(s[0], 1) if s else None)
            if None in big or None in sml:
                print("  %s 연령대를 다 못 받았습니다." % cid)
                continue
            ov[cid] = {**(ov.get(cid) or {}), **meta,
                       "title": "%s년 대기업과 중소기업 연령대별 임금 격차" % year,
                       "labels": [nm for nm, _ in AGE],
                       "series": [big, sml],
                       "seriesNames": ["대기업", "중소기업"],
                       "seriesColors": ["#2a5ca8", "#9aa7bd"]}
            print("  %s %s년 스냅샷 갱신 (대기업 %s)" % (cid, year, big))
            touched += 1

    if a.apply and touched:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("-> data/overrides.json 에 반영했습니다(%d장)." % touched)
    elif not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
