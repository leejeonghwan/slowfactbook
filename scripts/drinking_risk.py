#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연령대별 고위험음주율과 월간폭음률.

  python3 scripts/drinking_risk.py            # 미리보기
  python3 scripts/drinking_risk.py --apply

질병관리청 국민건강영양조사. 본체는 국가데이터처 포털에서 받고(177/DT_11702_N018
고위험음주율, 177/DT_11702_N234 월간폭음률), 아직 포털에 올라오지 않은 2025년은
질병관리청이 2026년 9월 30일 낸 「2025년 국민건강영양조사」 보도자료 별첨에서
가져온다.

두 곳을 섞는 것이 아니다. 같은 기관의 같은 조사이고, 별첨이 먼저 나오고 포털이
나중에 따라오는 관계다. 그래도 믿고 쓰려면 겹치는 구간이 맞아야 하므로,
별첨에 실린 2016~2024년 아홉 해를 포털 값과 연령대마다 대조한다. 한 칸이라도
어긋나면 쓰지 않고 멈춘다. 포털에 2025년이 올라오면 이 대조가 열 해로 늘고
박아 둔 값은 쓰이지 않는다.

주의. 이 조사의 '전체' 는 연령표준화 값이다. 포털에서 뽑을 때 '19세이상' 이
아니라 '19세이상(표준화)' 를 집어야 보도자료와 맞는다. 2024년 월간폭음률이
'19세이상' 은 34.0%, '19세이상(표준화)' 는 37.8%다. 이 차트는 연령대별 값만
쓰므로 그 문제와 무관하다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
PR = "https://www.kdca.go.kr/bbs/kdca/42/312791/artclView.do"
AGES = [("201", "19-29세", "19~29세", "#1f3f6e"),
        ("202", "30-39세", "30~39세", "#2a5ca8"),
        ("203", "40-49세", "40~49세", "#5b8bc4"),
        ("204", "50-59세", "50~59세", "#d4a15c"),
        ("205", "60-69세", "60~69세", "#d4823c"),
        ("206", "70세이상", "70세 이상", "#c0322f")]
PY0 = 2016  # 별첨에 실린 첫 해

SPEC = {
    "manual-high-risk-drinking": {
        "tbl": "DT_11702_N018", "itm": "MEAN",
        "title": "연령대별 고위험음주율",
        "defn": ("최근 1년 동안 한 번에 마시는 양이 남자는 7잔, 여자는 5잔 이상이면서 "
                 "주 2회 이상 마시는 사람의 비율입니다."),
        "pdf": {
            "19-29세": [13.8, 14.2, 15.9, 11.2, 11.4, 12.9, 12.5, 12.9, 9.9, 9.3],
            "30-39세": [16.4, 16.9, 15.2, 13.8, 16.6, 15.6, 14.9, 12.6, 14.5, 14.2],
            "40-49세": [15.8, 16.9, 18.1, 15.3, 19.0, 16.3, 18.1, 19.6, 20.4, 16.3],
            "50-59세": [15.4, 14.5, 14.6, 13.9, 13.9, 13.8, 17.2, 15.9, 14.0, 15.4],
            "60-69세": [9.0, 9.1, 11.2, 10.4, 10.9, 9.1, 10.6, 10.5, 10.9, 10.1],
            "70세이상": [2.7, 3.2, 3.0, 4.7, 3.5, 3.7, 4.4, 3.4, 3.9, 4.1],
        },
    },
    "manual-binge-drinking": {
        "tbl": "DT_11702_N234", "itm": "RATIO",
        "title": "연령대별 월간폭음률",
        "defn": ("최근 1년 동안 한 달에 한 번 이상, 한 번의 술자리에서 남자는 7잔"
                 "(또는 맥주 5캔), 여자는 5잔(또는 맥주 3캔) 이상 마신 사람의 "
                 "비율입니다."),
        "pdf": {
            "19-29세": [49.8, 50.6, 48.2, 48.0, 44.8, 43.7, 45.2, 44.2, 42.7, 35.4],
            "30-39세": [45.6, 42.6, 42.1, 45.0, 46.3, 41.1, 40.9, 41.6, 43.2, 39.6],
            "40-49세": [41.0, 41.2, 43.0, 38.6, 40.5, 38.0, 40.3, 41.3, 42.6, 41.9],
            "50-59세": [34.7, 34.3, 34.7, 34.3, 34.4, 31.9, 37.7, 33.4, 34.5, 36.2],
            "60-69세": [24.4, 26.0, 27.3, 28.3, 25.6, 23.4, 24.5, 26.2, 27.9, 24.4],
            "70세이상": [9.9, 10.5, 10.3, 12.3, 11.3, 9.5, 9.9, 10.4, 10.1, 10.7],
        },
    },
}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    out = []
    for slide, sp in SPEC.items():
        obj = "+".join(c for c, _, _, _ in AGES)
        u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
             f"&apiKey={key}&format=json&jsonVD=Y&orgId=177&tblId={sp['tbl']}&prdSe=Y"
             f"&startPrdDe=2005&endPrdDe={now.year}&itmId={sp['itm']}"
             f"&objL1=1&objL2={obj}")
        r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
        if r.returncode:
            raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
        d = json.loads(r.stdout.decode("utf-8", "replace"))
        if not isinstance(d, list):
            raise SystemExit(f"{sp['tbl']} 응답이 표가 아닙니다: {str(d)[:160]}")
        m, unit = {}, None
        for x in d:
            if x.get("DT") in (None, "", "-"):
                continue
            m.setdefault(x["C2_NM"], {})[int(x["PRD_DE"])] = float(x["DT"])
            unit = x.get("UNIT_NM")
        miss = [k for _, k, _, _ in AGES if k not in m]
        if miss:
            raise SystemExit(f"{sp['tbl']} 에 없는 연령대: {miss}")

        # 검산. 보도자료 별첨과 포털이 겹치는 해에 맞는가
        bad, seen = [], 0
        for _, k, _, _ in AGES:
            for i, v in enumerate(sp["pdf"][k]):
                y = PY0 + i
                if y in m[k]:
                    seen += 1
                    if abs(m[k][y] - v) > 0.051:
                        bad.append((k, y, v, m[k][y]))
        if seen < 40:
            raise SystemExit(f"{sp['title']}: 대조할 칸이 {seen}개뿐입니다.")
        if bad:
            raise SystemExit(f"{sp['title']}: 보도자료 별첨과 포털이 어긋납니다"
                             f"({len(bad)}곳): {bad[:5]}")
        print(f"    검산 {sp['title']}: 별첨과 포털이 겹치는 {seen}칸 모두 일치")

        # 포털에 없는 해만 별첨에서 채운다
        added = []
        for _, k, _, _ in AGES:
            for i, v in enumerate(sp["pdf"][k]):
                y = PY0 + i
                if y not in m[k]:
                    m[k][y] = v
                    if y not in added:
                        added.append(y)
        if added:
            print(f"      별첨에서 채운 해: {sorted(added)}")

        ys = sorted(set().union(*[set(m[k]) for _, k, _, _ in AGES]))
        ys = list(range(ys[0], ys[-1] + 1))
        for y in ys:
            have = [k for _, k, _, _ in AGES if y in m[k]]
            if have and len(have) != len(AGES):
                raise SystemExit(f"{y}년에 일부 연령대만 있습니다: {have}")
        last = max(y for y in ys if y in m["19-29세"])
        yng, old = m["19-29세"], m["50-59세"]
        y0 = min(yng)
        src = (f"질병관리청 국민건강영양조사 {sp['title'].replace('연령대별 ', '')}. "
               f"19세 이상. {ys[0]}~{last}년. 단위: %.")
        out.append({
            "slide": slide,
            "category": "건강과 보건",
            "title": sp["title"],
            "vizType": "line", "unit": unit or "%",
            "labels": [str(y) for y in ys],
            "series": [[m[k].get(y) for y in ys] for _, k, _, _ in AGES],
            "seriesNames": [nm for _, _, nm, _ in AGES],
            "seriesColors": [c for _, _, _, c in AGES],
            "source": src,
            "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=177&tblId=" + sp["tbl"],
            "notes": [
                sp["defn"],
                f"{last}년 19~29세가 {yng[last]}%, 50~59세가 {old[last]}% 입니다. "
                f"{y0}년에는 {yng[y0]}%와 {old[y0]}% 였습니다."
                + (" 젊은 층이 내려오고 중년층이 올라 두 선의 순서가 뒤집혔습니다."
                   if yng[y0] > old[y0] and yng[last] < old[last] else
                   f" 19~29세는 {yng[last] - yng[y0]:+.1f}%포인트, 50~59세는 "
                   f"{old[last] - old[y0]:+.1f}%포인트 움직였습니다."),
                f"{last}년 값은 질병관리청이 2026년 9월 30일 낸 보도자료 별첨에서 "
                "가져왔습니다. 국가데이터처 포털에는 아직 올라오지 않았습니다. "
                "별첨에 함께 실린 2016년부터 2024년까지 아홉 해를 포털 값과 "
                "연령대마다 대조해 한 칸도 어긋나지 않는 것을 확인했습니다.",
                "2006년은 값이 없습니다. 국민건강영양조사가 그해에는 없었습니다.",
                "자가보고 조사입니다. 마신 양을 줄여 말하는 경향이 있어 실제보다 "
                "낮게 나올 수 있고, 그 정도가 연령대마다 다를 수 있습니다.",
                "이 조사의 '전체' 값은 연령표준화 값입니다. 포털에서 뽑을 때 "
                "'19세이상' 이 아니라 '19세이상(표준화)' 를 집어야 보도자료와 "
                "맞습니다. 2024년 월간폭음률이 각각 34.0%와 37.8%로 다릅니다. "
                "이 차트는 연령대별 값이라 그 문제와 무관합니다.",
            ],
            "updated": ymd,
        })

    for it in out:
        print(f"\n  {it['title']} {len(it['labels'])}점 "
              f"{it['labels'][0]}~{it['labels'][-1]}")
        for nm, s in zip(it["seriesNames"], it["series"]):
            v = [x for x in s if x is not None]
            print(f"    {nm:10s} {v[0]} ... {v[-1]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/manual.json 에 씁니다)")
        return 0
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    by = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for it in out:
        o = by.get(it["slide"])
        if o:
            keep = {k: o[k] for k in ("id",) if k in o}
            o.clear(); o.update(it); o.update(keep)
        else:
            doc["items"].append(it)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"-> data/manual.json 에 반영했습니다({len(doc['items'])}장).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
