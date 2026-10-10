#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제목이 출처 칸에 들어가 버린 차트를 찾아낸다.

키노트에서 뽑을 때 제목 텍스트 상자와 캡션 텍스트 상자의 순서가 뒤바뀐 슬라이드가
있어서, 제목이 비고 출처 자리에 제목 문구가 들어간 차트가 꽤 된다.
(예: c1883 '100대 광고주 광고비 집행 현황', c1839 '4대 은행 이자이익')

판정은 '출처처럼 보이는 표시'가 있는지로 한다 — 기관 이름, '단위/기준/자료/조사',
연도만 적힌 문자열, URL. 하나도 없으면 제목일 가능성이 높다고 본다.

  python3 scripts/title_in_source.py                 # 화면에 요약
  python3 scripts/title_in_source.py --tsv 파일.tsv   # 표로 저장
"""
import argparse, csv, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import generate_site as g

AGENCY = ("통계청|한국은행|금융감독원|행정안전부|국토교통부|기획재정부|보건복지부|교육부|"
          "고용노동부|여성가족부|환경부|산업통상자원부|과학기술정보통신부|국세청|관세청|"
          "경찰청|대검찰청|법원행정처|선거관리위원회|국회예산정책처|감사원|한국갤럽|갤럽|"
          "리얼미터|한국언론진흥재단|언론재단|닐슨|KOSIS|코시스|ECOS|OECD|IMF|World Bank|세계은행|"
          "퓨리서치|Pew|스타티스타|Statista|블룸버그|Bloomberg|로이터|Reuters|"
          "제일기획|KB|국민은행|신한|우리은행|하나은행|부동산원|감정원|거래소|예탁원|"
          "보험연구원|금융연구원|조세재정연구원|노동연구원|개발연구원|KDI|산업연구원|"
          "리서치|Research|연구원|연구소|협회|재단|학회|위원회|공사|공단|진흥원|"
          "전자공시|다트|DART|야후|Flurry|451")
MARK = r"단위|기준|자료|조사|집계|추산|추정|출처|설문|분석|응답|표본|발췌|재구성|가공"


def looks_like_source(s):
    s = (s or "").strip()
    if not s:
        return None                       # 출처 자체가 없다
    if re.search(r"https?://", s):
        return "URL"
    if re.search(AGENCY, s, re.I):
        return "기관명"
    if re.search(MARK, s):
        return "표시어"
    if re.fullmatch(r"[\d\s년월분기~\-–.,()QqＱ]+", s):
        return "연도·기간만"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv")
    ap.add_argument("--all", action="store_true", help="제목이 있는 차트까지 모두")
    a = ap.parse_args()

    rows = []
    for it in g.load_items(os.path.join(ROOT, "data")):
        title = (it.get("title") or "").strip()
        src = (it.get("source") or "").strip()
        if title and not a.all:
            continue
        why = looks_like_source(src)
        if why and not a.all:
            continue                       # 출처는 출처다 — 제목만 따로 비어 있는 경우
        rows.append({
            "id": it.get("id") or "", "현재제목": title, "출처칸": src,
            "판정": "제목으로 보임" if (src and not why) else ("출처 맞음(" + why + ")" if why else "둘 다 비었음"),
            "종류": it["vizType"], "계열수": len(it["series"]), "라벨수": len(it["labels"]),
            "계열이름": " / ".join(str(n or "") for n in it["seriesNames"])[:60],
            "첫라벨": str(it["labels"][0]), "끝라벨": str(it["labels"][-1]),
            "분류": it.get("category", ""), "새제목": "",
        })

    cand = [r for r in rows if r["판정"] == "제목으로 보임"]
    empty = [r for r in rows if r["판정"] == "둘 다 비었음"]
    print(f"제목 비어 있는 차트 {len(rows)}개")
    print(f"  출처 칸에 제목이 들어간 것으로 보임 : {len(cand)}")
    print(f"  제목도 출처도 비었음               : {len(empty)}\n")
    for r in cand[:40]:
        print(f"  {r['id']}  {r['출처칸'][:48]:50s} {r['종류']:12s} 계열{r['계열수']} 라벨{r['라벨수']}")
    if len(cand) > 40:
        print(f"  … 외 {len(cand)-40}건")

    if a.tsv:
        os.makedirs(os.path.dirname(a.tsv) or ".", exist_ok=True)
        with open(a.tsv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["판정"] != "제목으로 보임", r["id"])))
        print(f"\n→ {a.tsv} ({len(rows)}행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
