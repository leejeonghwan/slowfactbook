#!/usr/bin/env python3
"""
출처 캡션 정규화 — 단위 분리 · 기관명 통일 · 조사명 정밀화

키노트 캡션 한 줄에 "출처 + 단위"가 섞여 들어온 걸 정리한다.

  "국가데이터처 경제활동인구 조사, 단위: 1000명."
        ↓
  source = "국가데이터처 「경제활동인구조사」"
  unit   = "1000명"

결과는 data/overrides.json 에 병합된다 (기존 파이프라인 훅).
--dry-run 으로 먼저 무엇이 바뀔지 확인하고 실행한다.

  python3 scripts/fix_sources.py --dry-run
  python3 scripts/fix_sources.py
"""
import os, sys, re, json, argparse, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

UNIT_RE = re.compile(r"(단위\s*[:：]\s*[^.]*\.?)")

# 기관명 표기 통일 (2025년 통계청 → 국가데이터처 개편 반영)
AGENCY = [
    (r"^통계청|(?<![가-힣])통계청", "국가데이터처"),
    (r"한국거래소", "KRX"),
    (r"(?<![가-힣])KOSIS(?![가-힣])", "국가데이터처 KOSIS"),
]

# 조사명 표기 흔들림 정리 (띄어쓰기·약칭)
SURVEY_CANON = {
    "경제활동인구 조사": "경제활동인구조사",
    "경제활동 인구조사": "경제활동인구조사",
    "경제활동인구조사": "경제활동인구조사",
    "인구동향 조사": "인구동향조사",
    "인구주택 총조사": "인구주택총조사",
    "인구총조사": "인구주택총조사",
    "장래인구 추계": "장래인구추계",
    "가계동향 조사": "가계동향조사",
    "일자리 행정통계": "일자리행정통계",
    "사회 조사": "사회조사",
}

# 지표 → 실제 출처 통계 (표기 정밀화 제안). 자동 적용하지 않고 검수 목록으로 뺀다.
REFINE = [
    (r"임금\s*격차|평균\s*(임금|소득)|월\s*평균\s*임금",
     ["일자리행정통계"], "임금근로일자리 소득(보수) 결과",
     "일자리행정통계는 일자리 수 통계이고, 임금(보수)은 「임금근로일자리 소득(보수) 결과」가 정본이다."),
    (r"실업률|고용률|취업자|경제활동참가율|쉬었음|구직단념",
     ["일자리행정통계", "고용행정통계"], "경제활동인구조사",
     "가구 표본조사인 경제활동인구조사가 정본이다. 행정자료 기반 통계와 수치가 다르다."),
    (r"일자리\s*(수|증감|비중|현황)",
     ["경제활동인구조사"], "일자리행정통계",
     "행정자료 기반 일자리 수는 일자리행정통계가 정본이다."),
    (r"산업재해|산재|사고사망",
     [], "고용노동부 「산업재해현황분석」", "산업재해 통계의 정본."),
    (r"최저임금",
     [], "최저임금위원회", "고시 최저임금은 최저임금위원회가 정본이다."),
]


def split_caption(s):
    s = (s or "").strip()
    units = UNIT_RE.findall(s)
    rest = UNIT_RE.sub("", s)
    rest = re.sub(r"\s*,\s*,", ",", rest).strip(" ,.·")
    unit = " ".join(u.strip() for u in units)
    unit = re.sub(r"^단위\s*[:：]\s*", "", unit).strip(" .")
    unit = re.sub(r"\s*단위\s*[:：]\s*", " / ", unit).strip(" /.")
    return rest, unit


def canon_source(s):
    if not s:
        return s
    out = s
    for pat, rep in AGENCY:
        out = re.sub(pat, rep, out)
    for k, v in sorted(SURVEY_CANON.items(), key=lambda kv: -len(kv[0])):
        if k in out:
            out = out.replace(k, v)
    # 조사명에 낫표를 씌워 기관/조사 구분을 눈에 보이게
    out = re.sub(r"([가-힣]{2,}(?:조사|추계|통계|총조사|계정|지수))(?![」』])",
                 lambda m: "「" + m.group(1) + "」", out)
    out = re.sub(r"「(「+)", "「", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,.·")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import generate_site as g
    items = g.load_items(DATA)
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    changed, refine = 0, []
    stat = collections.Counter()
    for it in items:
        src, unit = split_caption(it["source"])
        new = canon_source(src)
        if new != it["source"] or unit:
            o = ov.get(it["slide"], {})
            o["source"] = new
            if unit:
                o["unit"] = unit
            ov[it["slide"]] = o
            changed += 1
            if unit:
                stat["단위 분리"] += 1
            if new != src:
                stat["기관·조사명 정규화"] += 1
            if not new:
                stat["출처 없음(보강 필요)"] += 1
        for pat, wrong, right, why in REFINE:
            if right.split("」")[0].strip("고용노동부 「") in src or right in src:
                continue                      # 이미 맞게 적혀 있으면 넘어간다
            if re.search(r"(국가\s*비교|OECD|주요국|해외)", it["title"]):
                continue                      # 국제 비교는 국내 정본 규칙 대상이 아니다
            if re.search(pat, it["title"]) and (wrong and any(w in src for w in wrong)):
                refine.append({"slide": it["slide"], "category": it["category"],
                               "title": it["title"], "current": src,
                               "suggest": right, "why": why})
                break

    json.dump(refine, open(os.path.join(DATA, "_source_refine.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if not a.dry_run:
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"{'[dry-run] ' if a.dry_run else ''}정리 대상 {changed}건 / 전체 {len(items)}")
    for k, v in stat.most_common():
        print(f"   {v:5d}  {k}")
    print(f"\n조사명 정밀화 검수 목록: {len(refine)}건 → data/_source_refine.json")
    seen = set()
    for r in refine[:10]:
        k = (r["current"], r["suggest"])
        if k in seen:
            continue
        seen.add(k)
        print(f"   [{r['category'][:6]}] {r['title'][:26]:28s} {r['current'][:20] or '(없음)':22s} → {r['suggest']}")


if __name__ == "__main__":
    main()
