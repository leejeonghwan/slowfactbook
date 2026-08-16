#!/usr/bin/env python3
"""
매칭 결과를 사람이 읽는 형태로 정리한다.

  latest/매칭결과.html      매칭된 차트 · 복원된 시점 · 단위 배수 · 통계표 링크
  latest/미매칭.csv         매칭 안 된 차트 목록 (후보 통계표 포함) — 수동 매핑용
  latest/보강추천.md        같은 통계표에서 더 뽑아볼 만한 지표 추천

  python3 scripts/report_match.py
"""
import os, sys, json, csv, html, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "latest")
os.makedirs(OUT, exist_ok=True)

conf = {}
for _f in ("api_map_auto.json", "ecos_map.json"):
    _p = os.path.join(DATA, _f)
    if os.path.exists(_p):
        conf.update(json.load(open(_p, encoding="utf-8")))
rev = []
for _f in ("_match_review.json", "_ecos_review.json"):
    _p = os.path.join(DATA, _f)
    if os.path.exists(_p):
        rev += json.load(open(_p, encoding="utf-8"))

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g
items = g.load_items(DATA)
g.assign_ids(items, os.path.join(DATA, "ids.json"))
by = {it["slide"]: it for it in items}

FREQ = {"Y": "연간", "Q": "분기", "M": "월간", "H": "반기"}

# ── 1. 매칭 결과 HTML ────────────────────────────────────────
rows = ""
for slide, s in sorted(conf.items(), key=lambda kv: kv[1].get("category", "")):
    it = by.get(slide)
    if not it:
        continue
    per = s.get("_periodRange") or []
    sc = s.get("scale", 1) or 1
    scs = "" if sc == 1 else f"×{sc:g}"
    restored = s.get("_chartFreq") in ("M", "Q", "H")
    rows += (f"<tr><td>{it['id']}</td><td>{html.escape(it['category'])}</td>"
             f"<td>{html.escape(it['title'])}</td>"
             f"<td>{FREQ.get(s.get('_chartFreq'), '')}"
             f"{'<b> 복원</b>' if restored else ''}</td>"
             f"<td class=n>{per[0] if per else ''}~{per[-1] if per else ''}</td>"
             f"<td class=n>{scs}</td>"
             f"<td><a href='{s['sourceUrl']}' target=_blank>{s.get('tblId') or s.get('statCode')}</a><br>"
             f"<span class=m>{html.escape(str(s.get('_statNm') or s.get('_tblNm') or ''))}</span></td>"
             f"<td class=n>{s.get('_matchScore','')}</td></tr>")

restored_n = sum(1 for s in conf.values() if s.get("_chartFreq") in ("M", "Q", "H"))
scaled_n = sum(1 for s in conf.values() if s.get("scale", 1) != 1)
open(os.path.join(OUT, "매칭결과.html"), "w", encoding="utf-8").write(f"""<!DOCTYPE html>
<html lang=ko><meta charset=utf-8><title>슬로우팩트북 · 통계표 매칭 결과</title><style>
body{{font:14px/1.55 system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;background:#fafafa;color:#1a1a1a;margin:0}}
.w{{max-width:1150px;margin:0 auto;padding:26px 20px 60px}}
h1{{font-size:21px;margin:0 0 4px}} p.s{{color:#666;font-size:13px;margin:0 0 18px}}
.k{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}
.k div{{background:#fff;border:1px solid #e6e6e6;border-radius:10px;padding:11px 15px}}
.k b{{display:block;font-size:21px}} .k span{{font-size:12px;color:#666}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e6e6;border-radius:10px;overflow:hidden}}
th{{text-align:left;font-size:12px;color:#555;background:#f4f4f2;padding:8px 9px;border-bottom:1px solid #e6e6e6}}
td{{padding:7px 9px;border-bottom:1px solid #f1f1ef;font-size:13px;vertical-align:top}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}} .m{{color:#999;font-size:11px}} a{{color:#2f5e8e}}
b{{color:#c0322f}}
</style><div class=w>
<h1>통계표 매칭 결과</h1>
<p class=s>차트의 과거 수치를 KOSIS 원본과 대조해 자동 검증한 결과입니다. 일치도 1.00은 겹치는 구간의 값이 모두 맞았다는 뜻입니다.
‘복원’ 표시는 x축이 연도만 찍혀 있었지만 실제로는 월간·분기 데이터여서 시점을 되살린 차트입니다.</p>
<div class=k>
 <div><b>{len(conf)}</b><span>매칭 확정</span></div>
 <div><b>{restored_n}</b><span>시점 복원(월·분기)</span></div>
 <div><b>{scaled_n}</b><span>단위 배수 탐지</span></div>
 <div><b>{len(rev)}</b><span>수동 검수 필요</span></div>
</div>
<table><thead><tr><th>ID</th><th>카테고리</th><th>제목</th><th>주기</th><th>실제 구간</th><th>단위배수</th><th>통계표</th><th>일치도</th></tr></thead>
<tbody>{rows}</tbody></table></div></html>""")

# ── 2. 미매칭 CSV ───────────────────────────────────────────
with open(os.path.join(OUT, "미매칭.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ID", "카테고리", "제목", "주기추정", "점개수", "현재출처",
                "최고일치도", "후보통계표1", "후보명1", "후보통계표2", "후보명2", "사유"])
    for r in sorted(rev, key=lambda x: (x.get("category", ""), x.get("title", ""))):
        it = by.get(r["slide"])
        c = r.get("cands") or []
        w.writerow([it["id"] if it else "", r.get("category", ""), r.get("title", ""),
                    FREQ.get(r.get("freq"), ""), r.get("n", ""), r.get("source", ""),
                    r.get("best_score", ""),
                    (c[0].get("tblId") or c[0].get("statCode")) if len(c) > 0 else "",
                    (c[0].get("statNm") or c[0].get("statName") or c[0].get("tblNm")) if len(c) > 0 else "",
                    (c[1].get("tblId") or c[1].get("statCode")) if len(c) > 1 else "",
                    (c[1].get("statNm") or c[1].get("statName") or c[1].get("tblNm")) if len(c) > 1 else "",
                    r.get("why", "")])

# ── 3. 보강 추천 ────────────────────────────────────────────
tbl_use = collections.Counter(s.get("tblId") or s.get("statCode") for s in conf.values())
stat_use = collections.Counter(str(s.get("_statNm") or s.get("_tblNm")) for s in conf.values())
cat_of = collections.defaultdict(set)
for slide, s in conf.items():
    cat_of[str(s.get("_statNm") or s.get("_tblNm"))].add(s.get("category", ""))

lines = ["# 보강 추천 — 이미 연결된 통계에서 더 뽑을 수 있는 것\n",
         "매칭이 확정된 통계표는 같은 조사 안에 쓰지 않은 지표가 더 있습니다.",
         "아래는 슬로우팩트북이 이미 쓰고 있는 조사별로, 같은 조사에서 추가로 만들 만한 차트입니다.\n"]
IDEA = {
    "경제활동인구조사": ["연령대별 고용률(15~29 / 30대 / 40대 / 50대 / 60세 이상) 한 장 비교",
                 "성별 경제활동참가율 격차 추이", "비경제활동인구 사유별(육아·가사·쉬었음) 구성 변화",
                 "확장실업률(고용보조지표 U6) vs 공식 실업률", "주당 취업시간대별 취업자(초단시간 근로 증가)"],
    "인구동향조사": ["모(母) 연령별 출산율 — 30대 후반·40대 비중 상승", "출생 순위별(첫째·둘째·셋째) 출생아 수",
                "평균 초혼연령 남녀 추이", "시도별 조출생률 지도용 데이터", "사망 원인 상위 10개 추이"],
    "고용형태별노동실태조사": ["정규직·비정규직 사회보험 가입률 격차", "근속연수별 임금 격차",
                     "비정규직 유형별(기간제·파견·용역·특수형태) 규모 변화"],
    "지역별고용조사": ["시군구별 고용률·실업률 지도", "경력단절 사유별 구성", "청년층 첫 일자리 근속기간"],
    "육아휴직통계": ["부(父) 육아휴직 비율 추이", "기업 규모별 육아휴직 사용률", "육아휴직 후 복직률·고용유지율"],
    "e-지방지표": ["시도별 인구소멸위험지수", "시도별 재정자립도", "시도별 1인당 지역내총생산"],
    "IMF": ["주요국 소비자물가 상승률 비교", "주요국 정부부채 비율(GDP 대비)", "주요국 경상수지"],
}
for stat, n in stat_use.most_common():
    cats = ", ".join(sorted(c for c in cat_of[stat] if c))
    lines.append(f"\n## {stat} — 현재 {n}개 차트 ({cats})")
    for i in IDEA.get(stat, []):
        lines.append(f"- {i}")
    if stat not in IDEA:
        lines.append("- (추천 목록 미작성 — KOSIS 통계표 목록에서 미사용 항목 확인 필요)")

lines.append("\n\n## 아직 연결 안 된 영역 — 새로 붙이면 좋을 정부 데이터\n")
lines += [
    "- **국립수산과학원 해양 수온** — 기후·식량 카테고리에 환경 변수가 하나도 없다. 어종·농산물 차트와 짝지을 축이 없다.",
    "- **한국은행 ECOS** — 환율(15건)·금융(39건)·주식(29건) 카테고리는 KOSIS보다 ECOS가 정본이다. 별도 어댑터 필요.",
    "- **국토교통부 실거래가 API(data.go.kr)** — 부동산 51건 중 KOSIS로 못 잡는 실거래 기반 지표.",
    "- **전력거래소·한국전력(data.go.kr)** — 기후와 에너지 153건, 발전원별 실적은 KOSIS 반영이 늦다.",
    "- **고용노동부 산업재해현황분석** — 산업재해 11건, KOSIS 수록이 제한적이라 원자료 파일 파싱이 필요.",
    "- **중앙선거관리위원회 선거통계시스템** — 정치 137건, 개표·투표율은 API보다 공표 파일이 정확하다.",
    "- **관세청 무역통계(TRASS/UNIPASS API)** — 수출과 무역 23건, 품목별 월간 갱신이 가능하다.",
]
open(os.path.join(OUT, "보강추천.md"), "w", encoding="utf-8").write("\n".join(lines))

print(f"매칭 확정 {len(conf)} · 시점 복원 {restored_n} · 단위배수 탐지 {scaled_n} · 미매칭 {len(rev)}")
print(f"→ {OUT}/매칭결과.html")
print(f"→ {OUT}/미매칭.csv")
print(f"→ {OUT}/보강추천.md")
