#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국은행 이슈노트가 짚은 고용 지표를 경제활동인구조사에서 다시 세운다.

  python3 scripts/bok_employment.py            # 미리보기
  python3 scripts/bok_employment.py --apply

한국은행 이슈노트 2026-8호(남성 청년층 경제활동참가율), 2026-19호(청년고용
위축, AI 탓인가), 2026-25호(AI와 지역 노동시장), 2026-27호(청년고용 부진)가
제시한 그림 가운데 공개 통계로 되짚을 수 있는 넷을 만든다. 이슈노트의 그림에는
값이 박혀 있지 않아 베낄 수 없고, 한국은행이 원자료로 직접 계산한 지표(AI
노출도별 고용 증감, 신규채용 청년 비중, 유보임금, AI준비도)는 재현이 안 된다.
그래서 원천 통계를 직접 받아 같은 정의로 다시 계산한다.

  1 연령대별 남성 경제활동참가율   101/DT_1DA7012S  (2026-8호 그림 2)
  2 학력별 청년 실업률            101/DT_1DA7105S  (2026-19호 그림 11)
  3 수도권 취업자 비중            101/DT_1DA7004S  (2026-25호 그림 1)
  4 청년층 시간제 근로자 비중      101/DT_1DE7006S  (2026-27호 그림 8)

연령별 종사상지위(청년층 임시근로자와 일용근로자 비중, 2026-27호 그림 7)는
공개 표에 연령과 종사상지위의 교차가 없어 만들지 않았다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
Y0, Y1 = 2000, datetime.datetime.now(KST).year
U = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId="
BOK = "https://www.bok.or.kr/portal/bbs/P0002353/list.do?menuNo=200066"


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


KEY = None


def pull(tbl, itm, obj, s=None, e=None, mon=None):
    """연간 자료를 {연도: 값} 으로 돌려준다.

    mon 을 주면 PRD_DE 가 'YYYYMM' 인 표에서 그 달만 골라 연도로 바꾼다.
    근로형태별 부가조사는 해에 따라 3월과 8월이 섞여 있다.
    """
    q = "&".join(f"objL{i + 1}={v}" for i, v in enumerate(obj))
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={KEY}&format=json&jsonVD=Y&orgId=101&tblId={tbl}&prdSe=Y"
         f"&startPrdDe={s or Y0}&endPrdDe={e or Y1}&itmId={itm}&{q}")
    r = subprocess.run(["curl", "-sS", "--max-time", "150", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"{tbl} {itm} {obj} 응답이 표가 아닙니다: {str(d)[:140]}")
    out = {}
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        p = str(x["PRD_DE"])
        if mon:
            if len(p) != 6 or p[4:] != mon:
                continue
            p = p[:4]
        out[int(p)] = float(x["DT"])
    if not out:
        raise SystemExit(f"{tbl} {itm} {obj} 가 비었습니다.")
    return out


def years(*maps):
    ys = set(maps[0])
    for m in maps[1:]:
        ys &= set(m)
    return sorted(ys)


def rate(pop, act, ys):
    return [round(act[y] / pop[y] * 100, 1) for y in ys]


# ── 1 연령대별 남성 경제활동참가율
def chart_lfpr():
    T = "DT_1DA7012S"
    A = {"25-29": "202", "30-34": "301", "35-39": "302",
         "40-44": "401", "45-49": "402", "50-54": "501", "20-24": "201"}
    raw = {}
    for sex in ("2", "3"):
        for nm, code in A.items():
            raw[(sex, nm, "pop")] = pull(T, "T10", [sex, code])
            raw[(sex, nm, "act")] = pull(T, "T20", [sex, code])

    def band(sex, parts):
        pop, act = {}, {}
        for y in years(*[raw[(sex, p, "pop")] for p in parts]):
            pop[y] = sum(raw[(sex, p, "pop")][y] for p in parts)
            act[y] = sum(raw[(sex, p, "act")][y] for p in parts)
        return pop, act

    # 검산. 공표된 참가율과 합산해 계산한 참가율이 맞아야 한다.
    for sex, parts, code in (("2", ["20-24", "25-29"], "20"),
                             ("2", ["30-34", "35-39"], "30"),
                             ("3", ["20-24", "25-29"], "20")):
        pub = pull(T, "T60", [sex, code])
        pop, act = band(sex, parts)
        ys = years(pub, pop)
        bad = [(y, pub[y], round(act[y] / pop[y] * 100, 1))
               for y in ys if abs(pub[y] - act[y] / pop[y] * 100) > 0.11]
        if bad:
            raise SystemExit(f"참가율 합산 검산 실패 성{sex} {code}: {bad[:4]}")
        print(f"    검산 성{sex} {code}세: {len(ys)}년 공표값과 일치")

    specs = [("25~34세 남성", "2", ["25-29", "30-34"], "#2a5ca8"),
             ("35~44세 남성", "2", ["35-39", "40-44"], "#7f9fc7"),
             ("45~54세 남성", "2", ["45-49", "50-54"], "#b8c7da"),
             ("25~34세 여성", "3", ["25-29", "30-34"], "#e8820c")]
    bands = [(nm, *band(sex, parts), col) for nm, sex, parts, col in specs]
    ys = years(*[b[1] for b in bands])
    ser = [rate(b[1], b[2], ys) for b in bands]
    m = dict(zip(ys, ser[0]))
    peak = max(ys, key=lambda y: m[y])
    return {
        "slide": "manual-bok-male-lfpr",
        "category": "노동",
        "title": "연령대별 남성 경제활동참가율",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in ys], "series": ser,
        "seriesNames": [b[0] for b in bands],
        "seriesColors": [b[3] for b in bands],
        "source": (f"국가데이터처 경제활동인구조사 성별 연령별 경제활동인구. "
                   f"{ys[0]}~{ys[-1]}년. 경제활동인구를 15세 이상 인구로 나눈 값. 단위: %."),
        "sourceUrl": U + "DT_1DA7012S",
        "notes": [
            f"25~34세 남성이 {m[peak]}%({peak}년)에서 {m[ys[-1]]}%"
            f"({ys[-1]}년)로 {round(m[peak] - m[ys[-1]], 1)}%포인트 내렸습니다. "
            f"같은 기간 35~44세와 45~54세 남성은 거의 움직이지 않았고, 25~34세 "
            f"여성은 {dict(zip(ys, ser[3]))[ys[0]]}%에서 "
            f"{dict(zip(ys, ser[3]))[ys[-1]]}%로 올랐습니다.",
            "경제활동참가율은 일하거나 일자리를 찾는 사람의 비율입니다. 고용률과 "
            "달리 실업자도 분자에 들어갑니다. 참가율이 내려간다는 것은 취업에 "
            "실패했다는 뜻이 아니라 구직 자체를 하지 않는 사람이 늘었다는 뜻입니다.",
            "한국은행 이슈노트 2026-8호 「남성 청년층 경제활동참가율의 하락 추세 "
            "평가」가 짚은 그림을 원천 통계에서 다시 세운 것입니다. 이슈노트는 "
            "이 하락이 청년기에 그치지 않고 이들이 나이를 먹으면서 중년층 참가율 "
            "하락으로 이어질 수 있다고 봤습니다.",
            "연령 구간을 다섯 살 단위로 더해 만들었습니다. 25~34세는 25~29세와 "
            "30~34세의 인구와 경제활동인구를 각각 더해 나눈 값입니다. 공표된 "
            "20~29세와 30~39세 참가율로 같은 방식의 계산이 맞는지 해마다 "
            "대조했습니다.",
        ],
    }


# ── 2 학력별 청년 실업률
def chart_edu_unemp():
    T = "DT_1DA7105S"
    E = [("전체", "00", "#4a4a4a"), ("대학교졸 이상", "42", "#c0322f"),
         ("전문대졸", "41", "#2a5ca8"), ("고졸", "30", "#7f9fc7")]
    got = {nm: pull(T, "T80", ["75", c]) for nm, c, _ in E}
    pub = pull("DT_1DA7012S", "T80", ["0", "75"])
    ys = years(*got.values(), pub)
    bad = [(y, pub[y], got["전체"][y]) for y in ys if abs(pub[y] - got["전체"][y]) > 0.051]
    if bad:
        raise SystemExit(f"청년 실업률 전체값이 다른 표와 어긋납니다: {bad[:4]}")
    print(f"    검산 전체 실업률: {len(ys)}년 두 표가 일치")
    u, c = got["대학교졸 이상"], got["전문대졸"]
    flip = [y for y in ys if u[y] > c[y]]
    return {
        "slide": "manual-bok-youth-unemp-edu",
        "category": "노동",
        "title": "학력별 청년 실업률(15~29세)",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in ys],
        "series": [[got[nm][y] for y in ys] for nm, _, _ in E],
        "seriesNames": [nm for nm, _, _ in E],
        "seriesColors": [col for _, _, col in E],
        "source": (f"국가데이터처 경제활동인구조사 연령별 교육정도별 실업률, 15~29세. "
                   f"{ys[0]}~{ys[-1]}년. 단위: %."),
        "sourceUrl": U + "DT_1DA7105S",
        "notes": [
            f"{ys[-1]}년 대학교졸 이상 {u[ys[-1]]}%, 전문대졸 {c[ys[-1]]}%, "
            f"고졸 {got['고졸'][ys[-1]]}%, 전체 {got['전체'][ys[-1]]}% 입니다. "
            + (f"대학교졸 이상이 전문대졸보다 높았던 해는 {len(flip)}번입니다."
               if flip else "대학교졸 이상이 전문대졸보다 높았던 해는 없습니다."),
            "학력이 높을수록 실업률이 낮다는 통념과 어긋나는 구간이 있습니다. "
            "대졸자는 눈높이에 맞는 일자리를 찾는 동안 구직 상태로 남기 때문에 "
            "실업자로 잡힙니다. 고졸자는 구직을 접고 비경제활동인구로 빠지면 "
            "실업률 계산에서 아예 빠집니다. 실업률이 낮은 쪽이 사정이 나은 것이 "
            "아닐 수 있습니다.",
            "한국은행 이슈노트 2026-19호 「청년고용 위축, AI 탓인가」가 같은 지표를 "
            "월별 12개월 이동평균으로 제시했습니다. 이슈노트는 챗GPT 출시 뒤 "
            "대졸 청년층의 실업률과 확장실업률이 전문대졸 이하보다 높아졌다고 "
            "봤습니다. 이 차트는 연간값이라 이슈노트의 월별 숫자와 그대로 맞지 "
            "않습니다.",
            "이슈노트는 '고졸이하' 로 묶었는데 공개 표는 초졸이하, 중졸, 고졸로 "
            "나뉘어 있습니다. 비율은 더할 수 없어 고졸만 넣었습니다. 중졸 이하를 "
            "합치면 실업률이 더 낮게 나옵니다. 구직을 하지 않는 사람이 많기 "
            "때문입니다.",
        ],
    }


# ── 3 수도권 취업자 비중
def chart_capital_share():
    T = "DT_1DA7004S"
    nat = pull(T, "T30", ["00"])
    cross = pull("DT_1DA7012S", "T30", ["0", "00"])
    bad = [(y, nat[y], cross[y]) for y in years(nat, cross) if abs(nat[y] - cross[y]) > 1.0]
    if bad:
        raise SystemExit(f"전국 취업자가 다른 표와 어긋납니다: {bad[:4]}")
    print(f"    검산 전국 취업자: {len(years(nat, cross))}년 두 표가 일치")
    SIDO = ["11", "21", "22", "23", "24", "25", "26", "29", "31", "32",
            "33", "34", "35", "36", "37", "38", "39"]
    part = {c: pull(T, "T30", [c]) for c in SIDO}
    ys = years(nat, part["11"], part["23"], part["31"])
    for y in ys:
        s = sum(part[c][y] for c in SIDO if y in part[c])
        if abs(s - nat[y]) / nat[y] > 0.005:
            raise SystemExit(f"{y}년 시도 합({s:,.1f})과 전국({nat[y]:,.1f})이 어긋납니다.")
    print(f"    검산 시도 합계: {len(ys)}년 전국과 0.5% 안에서 일치")
    cap = {y: part["11"][y] + part["23"][y] + part["31"][y] for y in ys}
    sh = [round(cap[y] / nat[y] * 100, 1) for y in ys]
    d = dict(zip(ys, sh))
    return {
        "slide": "manual-bok-capital-share",
        "category": "지역",
        "title": "수도권 취업자 비중",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in ys], "series": [sh],
        "seriesNames": ["수도권 취업자 비중"],
        "seriesColors": ["#2a5ca8"],
        "source": (f"국가데이터처 경제활동인구조사 행정구역별 경제활동인구. "
                   f"{ys[0]}~{ys[-1]}년. 서울과 인천과 경기 취업자를 전국 취업자로 "
                   f"나눈 값. 단위: %."),
        "sourceUrl": U + "DT_1DA7004S",
        "notes": [
            f"{ys[0]}년 {d[ys[0]]}%에서 {ys[-1]}년 {d[ys[-1]]}%로 "
            f"{round(d[ys[-1]] - d[ys[0]], 1)}%포인트 올랐습니다. "
            f"{ys[-1]}년 전국 취업자 {nat[ys[-1]] / 1e3:,.1f}백만 명 가운데 "
            f"{cap[ys[-1]] / 1e3:,.1f}백만 명이 수도권입니다.",
            "인구가 수도권으로 몰리면 취업자도 따라 몰립니다. 이 비중만으로는 "
            "일자리의 질이나 임금 격차를 알 수 없습니다. 같은 비중이라도 어떤 "
            "일자리가 어디에 생겼는지는 따로 봐야 합니다.",
            "한국은행 이슈노트 2026-25호 「AI와 지역 노동시장」의 출발 그림입니다. "
            "이슈노트는 생성형 AI와 에이전틱 AI에 많이 노출된 직업이 수도권에 "
            "몰려 있어, AI 확산이 지역 격차를 더 벌릴 수 있다고 봤습니다. 노출도 "
            "지표 자체는 한국은행이 원자료로 계산한 것이라 이 차트에는 들어 있지 "
            "않습니다.",
            "시도별 취업자를 모두 더한 값이 전국과 0.5% 안에서 맞는지 해마다 "
            "확인했습니다. 세종특별자치시는 2012년부터 따로 집계됩니다.",
        ],
    }


# ── 4 청년층 시간제 근로자 비중
def chart_parttime():
    T = "DT_1DE7006S"
    A = ("10", "20")
    g = {}
    for itm in ("T01", "T03", "T06"):
        for a in A:
            g[(itm, a)] = pull(T, itm, ["0", a], 2003, Y1, mon="08")
    ys = years(*g.values())
    for y in ys:
        for a in A:
            w, n, p = g[("T01", a)][y], g[("T03", a)][y], g[("T06", a)][y]
            if not p <= n <= w:
                raise SystemExit(f"{y}년 {a} 시간제({p}) 비정규직({n}) 임금근로자({w}) 순서가 어긋납니다.")
    print(f"    검산 시간제 <= 비정규직 <= 임금근로자: {len(ys)}년 모두 성립")
    wage = {y: sum(g[("T01", a)][y] for a in A) for y in ys}
    pt = {y: sum(g[("T06", a)][y] for a in A) for y in ys}
    irr = {y: sum(g[("T03", a)][y] for a in A) for y in ys}
    s1 = [round(pt[y] / wage[y] * 100, 1) for y in ys]
    s2 = [round(irr[y] / wage[y] * 100, 1) for y in ys]
    d1, d2 = dict(zip(ys, s1)), dict(zip(ys, s2))
    return {
        "slide": "manual-bok-youth-parttime",
        "category": "노동",
        "title": "청년층 시간제와 비정규직 비중(15~29세)",
        "vizType": "line", "unit": "%",
        "labels": [str(y) for y in ys], "series": [s1, s2],
        "seriesNames": ["시간제 근로자 비중", "비정규직 비중"],
        "seriesColors": ["#c0322f", "#2a5ca8"],
        "source": (f"국가데이터처 경제활동인구조사 근로형태별 부가조사, 성별 연령별 "
                   f"근로형태별 취업자. {ys[0]}~{ys[-1]}년 8월. 15~19세와 20~29세를 "
                   f"더한 임금근로자 대비 비중. 단위: %."),
        "sourceUrl": U + "DT_1DE7006S",
        "notes": [
            f"{ys[-1]}년 청년 임금근로자 가운데 시간제가 {d1[ys[-1]]}%, "
            f"비정규직이 {d2[ys[-1]]}% 입니다. {ys[0]}년에는 각각 "
            f"{d1[ys[0]]}%와 {d2[ys[0]]}% 였습니다.",
            "시간제는 같은 일을 하는 사람보다 정해진 근로시간이 짧은 근로자로, "
            "보통 주 36시간 미만입니다. 시간제는 비정규직에 포함되므로 두 선은 "
            "겹치는 부분이 있습니다.",
            "시간제가 늘어난 것을 모두 고용의 질 악화로 읽을 수는 없습니다. "
            "학업과 함께 일하는 청년이 늘어난 몫도 섞여 있습니다. 한국은행 "
            "이슈노트 2026-27호 「청년고용 부진 및 정책 과제」는 이 가운데 "
            "비자발적 시간제를 따로 떼어 봤는데, 그 구분은 원자료 계산이 필요해 "
            "이 차트에는 없습니다.",
            "해마다 8월에 한 번 조사하는 부가조사입니다. 월별이나 분기별로는 "
            "없습니다. 임금근로자만 분모이고 자영업자와 무급가족종사자는 "
            "빠져 있습니다.",
            "같은 이슈노트의 연령대별 임시근로자와 일용근로자 비중은 만들지 "
            "못했습니다. 공개 표에 연령과 종사상지위의 교차가 없어 청년층만 "
            "떼어낼 수 없습니다.",
        ],
    }


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    KEY = envkey("KOSIS_API_KEY")
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    out = []
    for fn in (chart_lfpr, chart_edu_unemp, chart_capital_share, chart_parttime):
        print(f"  {fn.__name__}")
        it = fn()
        it["updated"] = ymd
        out.append(it)
        print(f"    {it['title']:34s} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]} 계열 {len(it['series'])}")
        for nm, s in zip(it["seriesNames"], it["series"]):
            print(f"      {nm:16s} {s[0]} ... {s[-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        old = by.get(it["slide"])
        if old:
            keep = {k: old[k] for k in ("id",) if k in old}
            old.clear()
            old.update(it)
            old.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
