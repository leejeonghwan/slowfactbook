#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""종사자 규모별 남녀 일자리(c0192).

  python3 scripts/jobstat_size.py            # 미리보기
  python3 scripts/jobstat_size.py --apply

국가데이터처 일자리행정통계, KOSIS 표 DT_1EP_3021(종사자규모별 성별 일자리).
2016년부터 담겨 있고 해마다 한 해씩 는다. 가장 최근 해로 다시 깐다.

비율 차트(c0197, c0199)는 내렸다. 남녀 분포가 소수점 차이밖에 나지 않아
보여 줄 것이 없었다. 규모별 분포가 아니라 같은 규모 안의 임금과 직급 차이를
봐야 한다.

원표는 규모를 아홉 칸으로 나눈다. 차트는 여섯 칸이라 아래 BANDS 대로 합친다.
합치는 규칙을 여기 적어 두는 것은, 나중에 '왜 300명 이상이 한 칸인가'를 다시
묻지 않기 위해서다.

여기서 말하는 규모는 종사자 수다. 같은 통계 안에 있는 대기업·중소기업 구분
(공정거래법·중소기업기본법 기준, DT_1EP_3017)과는 다른 축이다. 섞지 말 것.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_1EP_3021"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=" + TBL
BANDS = [("1∼4명", ["1~4명"]), ("5∼9명", ["5~9명"]), ("10∼29명", ["10~29명"]),
         ("30∼99명", ["30~49명", "50~99명"]),
         ("100∼299명", ["100~199명", "200~299명"]),
         ("300명 이상", ["300~999명", "1000명 이상"])]
CODES = ["00", "10", "20", "30", "40", "50", "60", "70", "80", "90"]


def fetch(key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=101&tblId=%s&prdSe=Y&itmId=T00+"
           "&objL1=%s&objL2=1+2+&objL3=00+&startPrdDe=2010&endPrdDe=2035"
           % (key, TBL, "".join(c + "+" for c in CODES)))
    with urllib.request.urlopen(url, timeout=150) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        raise SystemExit("KOSIS 응답이 이상합니다: %s" % doc)
    m = {}
    for x in doc:
        if x.get("DT"):
            m.setdefault(x["PRD_DE"], {}).setdefault(x["C2_NM"], {})[x["C1_NM"]] = float(x["DT"])
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")

    m = fetch(key)
    year = max(m)
    cur = m[year]
    need = [n for b in BANDS for n in b[1]] + ["총 계"]
    for sx in ("남자", "여자"):
        missing = [n for n in need if n not in cur.get(sx, {})]
        if missing:
            raise SystemExit("%s 에서 못 찾은 칸: %s" % (sx, missing))

    cnt = {sx: [round(sum(cur[sx][n] for n in parts), 1) for _, parts in BANDS]
           for sx in ("남자", "여자")}
    tot = {sx: cur[sx]["총 계"] for sx in ("남자", "여자")}
    pct = {sx: [round(v / tot[sx] * 100, 1) for v in cnt[sx]] for sx in cnt}
    print("  %s년 남자 총 %s만 개, 여자 총 %s만 개" % (year, tot["남자"], tot["여자"]))
    for i, (nm, _) in enumerate(BANDS):
        print("    %-10s 남 %7s (%4s%%)  여 %7s (%4s%%)"
              % (nm, cnt["남자"][i], pct["남자"][i], cnt["여자"][i], pct["여자"][i]))

    src = ("국가데이터처 일자리행정통계 종사자규모별 성별 일자리(KOSIS 표 %s). %s년. "
           "30∼99명은 30∼49명과 50∼99명을, 100∼299명은 100∼199명과 200∼299명을, "
           "300명 이상은 300∼999명과 1000명 이상을 합쳤다." % (TBL, year))
    notes = [
        "국가데이터처 일자리행정통계입니다. 건강보험과 국민연금, 국세 자료를 모은 "
        "행정자료 기반이라 표본조사가 아닙니다. 사람 수가 아니라 '일자리 수'입니다. "
        "한 사람이 둘 이상을 가지면 각각 셉니다.",
        "여기서 규모는 종사자 수입니다. 대기업과 중소기업을 가르는 기업집단 기준"
        "(공정거래법, 중소기업기본법)과는 다릅니다. 같은 통계 안에 두 기준이 따로 "
        "있습니다.",
        "원표는 규모를 아홉 칸으로 나눕니다. 이 차트는 여섯 칸으로 합쳤고, 합친 "
        "규칙은 출처에 적었습니다.",
        "남녀 분포가 생각보다 비슷합니다. 규모별 분포보다 같은 규모 안에서의 임금과 "
        "직급 차이를 봐야 합니다.",
    ]
    stamp = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    ov["c0192"] = {**(ov.get("c0192") or {}), "id": "c0192",
                   "title": "%s년 종사자 규모별 남녀 일자리 수" % year,
                   "source": src + " 단위: 만 개.", "sourceUrl": URL, "unit": "만 개",
                   "vizType": "column", "labels": [n for n, _ in BANDS],
                   "series": [cnt["남자"], cnt["여자"]],
                   "seriesNames": ["남성", "여성"],
                   "seriesColors": ["#2a5ca8", "#c0322f"],
                   "notes": notes, "updated": stamp}
    if a.apply:
        with open(ovp, "w", encoding="utf-8") as fh:
            json.dump(ov, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        print("-> data/overrides.json 에 반영했습니다(1장).")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
