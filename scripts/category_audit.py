#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""카테고리 점검. 제목·출처의 말머리로 제자리를 찾아 준다.

카테고리는 키노트 덱의 섹션 순서에서 왔다. 그래서 섹션 경계에 걸린 묶음이
통째로 엉뚱한 칸에 들어가 있는 경우가 있고(이를테면 '복지' 안의 옥천군 인구),
두세 장밖에 없는 칸도 생겼다. 여기서 두 가지를 본다.

  1) MERGE — 뜻이 겹치거나 너무 작은 칸을 큰 칸에 접는다.
  2) RULES — 제목에 또렷한 말머리가 있으면 그 칸으로 옮긴다.
     한 차트가 여러 규칙에 걸리면 점수가 가장 높은 칸으로 간다. 지금 칸도
     규칙에 걸리면 지금 칸을 우선한다(맞게 들어가 있는 걸 흔들지 않는다).

쓰기:
  python3 scripts/category_audit.py              # 점검표만
  python3 scripts/category_audit.py --apply      # overrides 에 반영
  python3 scripts/category_audit.py --min 3      # 점수 기준 조정

반영은 overrides.json 의 "category" 로 들어간다. data/_category_review.json 에
근거(걸린 말머리)를 남기니 되돌릴 때 그것을 본다.
"""
import argparse, datetime, json, os, re, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

# 뜻이 겹치거나 너무 작아 칸 구실을 못 하는 카테고리를 접는다.
MERGE = {
    "미디어": "미디어와 저널리즘",
    "에너지": "기후와 에너지",
    "물가와 생활": "소비와 물가",
    "복지": "복지와 사회 안전망",
    "최저임금": "노동",
    "비정규직": "노동",
    "산업재해": "노동",
    "쉬었음": "노동",
    "환율": "금융",
    "외국인": "인구 구조",
}
# 손대지 않는 칸. 여기 있는 것들은 '무엇을 다루나'가 아니라 '어떤 틀로 보나'로
# 묶인 칸이다. 부산·거제의 고용률 그래프는 고용률 그래프이기 전에 지역 사례이고,
# 성별 임금 격차는 임금 이야기이기 전에 젠더 이야기다. 제일모직·삼성물산 시가총액은
# 주가가 아니라 합병을 보는 그래프다. 말머리로 끌어내면 덱의 논지가 흩어진다.
# TMI 는 일부러 둔 잡동사니 칸이고, '한눈에 보는 한국'은 첫머리에 놓으려고
# 따로 뽑아 둔 묶음이다.
KEEP = {"TMI", "한눈에 보는 한국", "지역", "젠더와 격차", "재벌",
        "북한", "자살", "출산", "지속가능한 성장"}

# (카테고리, 가중치, 말머리). 가중치가 큰 쪽이 또렷한 신호다.
RULES = [
    ("자살", 5, r"자살|자해|극단적\s*선택"),
    ("출산", 4, r"출산율|합계출산|출생아|혼인\s*건수|난임|비혼\s*출산"),
    ("인구 구조", 4, r"인구\s*(피라미드|추계|전망|구조)|고령화|노인\s*인구|생산가능인구|부양비|소멸\s*지수|주민등록\s*인구"),
    ("인구 구조", 3, r"이주노동자|외국인\s*(주민|노동|근로)|이민자|체류\s*자격"),
    ("부동산", 4, r"아파트|집값|주택\s*가격|전세|월세|분양|매매\s*가격|주택\s*공급|재건축|청약|임대\s*주택|빈집"),
    ("노동", 4, r"최저임금|비정규직|정규직|산업재해|산재|노동시간|노동조합|파업|임금\s*격차|고용률|실업률|취업자|쉬었음|일자리|근로자|노동자"),
    ("조세와 재정", 4, r"세수|국세|법인세|소득세|부가가치세|종합부동산세|상속세|조세\s*부담|재정\s*적자|국가\s*채무|나라\s*살림|추경|예산안|감세|세금"),
    ("연금과 기금", 4, r"국민연금|기초연금|퇴직연금|연금\s*(기금|개혁|고갈|수령)|국민연금공단"),
    ("주식", 4, r"코스피|코스닥|나스닥|다우|S&P|주가\s*지수|공매도|배당\s*수익률|주주\s*환원"),
    # 시가총액은 '부동산 시가총액'처럼 부동산 이야기일 때가 있다. 그때는 안 걸리게 둔다.
    ("주식", 4, r"(?<!부동산\s)(?<!주택\s)시가총액"),
    ("금융", 4, r"환율|기준금리|금리|예금|대출|가계\s*부채|가계\s*빚|은행\s*(이익|예대)|예대\s*마진|통화량|M2|외환\s*보유|채권\s*수익률|신용\s*등급"),
    ("소비와 물가", 4, r"소비자\s*물가|물가\s*상승|생산자\s*물가|소비\s*지출|가계\s*동향|엥겔|외식\s*물가|장바구니|내수"),
    ("수출과 무역", 4, r"수출|수입액|무역\s*(수지|흑자|적자|액)|경상\s*수지|관세|교역"),
    ("기후와 에너지", 4, r"온실가스|탄소|기온|폭염|해수면|강수(량|일수)|재생\s*에너지|태양광|풍력|원전|원자력|전력\s*(수요|예비|거래|입찰)|발전(량|원|소)|석탄|LNG|전기\s*요금|휘발유|경유|에너지\s*(소비|수입|전환)"),
    ("식량", 4, r"쌀|농가|농업|축산|곡물|식량|어획|수산|농지|비료|밥상"),
    ("재벌", 4, r"재벌|총수|대기업\s*집단|지주\s*회사|내부\s*거래|일감\s*몰아주기|순환\s*출자"),
    ("기업과 산업", 3, r"영업\s*이익|매출|반도체|자동차\s*(생산|판매)|조선|철강|배터리|스타트업|상장\s*기업|점유율|생산\s*능력|설비\s*투자|가동률"),
    ("미디어와 저널리즘", 4, r"언론|신문|방송|기자\s*(회견|단|협회|실)|여성\s*기자|기자\s*수|뉴스|저널리즘|구독|시청률|열독률|포털|유튜브|광고\s*(비|매출|시장)|페이지뷰|KBS|MBC|SBS|YTN"),
    ("정치", 4, r"지지율|지지도|정당|대통령\s*(직무|평가)|총선|대선|지방\s*선거|투표율|국회|의원|개헌|탄핵|정치\s*성향|여론\s*조사"),
    ("젠더와 격차", 4, r"성별\s*격차|성별\s*임금|여성\s*(임원|관리자|의원|비율)|유리\s*천장|경력\s*단절|육아\s*휴직|돌봄|소득\s*불평등|지니\s*계수|자산\s*불평등|빈곤율"),
    ("복지와 사회 안전망", 4, r"기초\s*생활|복지\s*지출|사회\s*안전망|긴급\s*복지|노인\s*(빈곤|소득)|아동\s*수당|건강\s*보험|고용\s*보험|실업\s*급여|돌봄\s*공백|고독사|노숙인"),
    ("건강과 보건", 4, r"의사\s*수|의대|병상|의료\s*(비|이용|기관)|흡연율|음주율|비만|감염|백신|치매|기대\s*수명|사망률|질병"),
    ("지역", 4, r"지방\s*소멸|수도권\s*집중|시도별|지역\s*(격차|화폐|내)|읍면동|군\s*인구|도시\s*쇠퇴|균형\s*발전"),
    ("세계 경제", 3, r"OECD|IMF|세계\s*(경제|은행|GDP)|미국\s*(물가|고용|금리|실업)|중국\s*경제|유로존|일본\s*경제|신흥국|달러\s*패권|국제\s*투자"),
    ("북한", 5, r"북한|평양|개성|남북|대북"),
]
RULES = [(c, w, re.compile(p)) for c, w, p in RULES]


def score(text):
    s = Counter()
    hit = defaultdict(list)
    for cat, w, rx in RULES:
        m = rx.search(text)
        if m:
            s[cat] += w
            hit[cat].append(m.group(0))
    return s, hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min", type=int, default=4, help="옮길 최소 점수")
    ap.add_argument("--gap", type=int, default=2, help="지금 칸보다 이만큼 높아야 옮긴다")
    a = ap.parse_args()

    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}

    moves, merged, review = [], [], []
    for it in items:
        cid, cur = it.get("id"), (it.get("category") or "").strip()
        if not cid:
            continue
        # 출처는 보지 않는다. 출처에는 매체 이름(SBS·MBC·한국일보)과 기관 이름
        # (국세청·통계청)이 들어 있어서, 주제와 상관없이 '미디어'나 '조세'로
        # 끌려간다. 주제를 말해 주는 건 제목이다.
        text = str(it.get("title", ""))
        # 1) 칸 접기
        base = MERGE.get(cur, cur)
        if base != cur:
            merged.append((cid, cur, base))
        if cur in KEEP:
            continue
        # 2) 말머리로 제자리 찾기
        s, hit = score(text)
        if not s:
            continue
        top, tw = s.most_common(1)[0]
        if top == base:
            continue
        if tw < a.min or tw - s.get(base, 0) < a.gap:
            continue
        moves.append({"id": cid, "title": it.get("title", ""), "from": cur,
                      "base": base, "to": top, "score": tw,
                      "cur_score": s.get(base, 0), "why": hit[top]})

    # 접기만 하는 것(옮김 대상이 아닌 것)도 반영 목록에 넣는다.
    moved = {m["id"] for m in moves}
    folds = [{"id": c, "title": "", "from": f, "base": t, "to": t, "score": 0,
              "cur_score": 0, "why": ["칸 접기"]} for c, f, t in merged if c not in moved]

    print(f"총 {len(items)}장 · 칸 접기 {len(merged)}장 · 말머리로 옮길 것 {len(moves)}장\n")
    print("— 칸 접기")
    for src, dst in sorted(MERGE.items()):
        n = sum(1 for c, f, t in merged if f == src)
        if n:
            print(f"   {src} ({n}장) → {dst}")
    print("\n— 옮길 것")
    byto = defaultdict(list)
    for m in moves:
        byto[(m["base"], m["to"])].append(m)
    for (f, t), ms in sorted(byto.items(), key=lambda kv: -len(kv[1])):
        print(f"\n   {f or '(없음)'} → {t}  {len(ms)}장")
        for m in ms[:60]:
            print(f"      {m['id']} {m['title'][:40]:42s} {m['score']}:{m['cur_score']} {','.join(m['why'][:2])}")
        if len(ms) > 60:
            print(f"      … 그 밖 {len(ms)-60}장")

    allp = moves + folds
    json.dump(allp, open(os.path.join(DATA, "_category_review.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n→ data/_category_review.json ({len(allp)}건)")

    if a.apply:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        for m in allp:
            o = ov.setdefault(m["id"], {})
            o["id"] = m["id"]
            o["category"] = m["to"]
            o["revised"] = stamp
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"→ data/overrides.json 에 {len(allp)}건 반영.")
    else:
        print("(점검표입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
