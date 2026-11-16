#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""연령대별 월간 음주율(c0259).

  python3 scripts/drinking_rate.py            # 미리보기
  python3 scripts/drinking_rate.py --apply

질병관리청 국민건강영양조사 「월간 음주율 추이」(177/DT_11702_N012) 에서 받는다.

'월간' 은 조사 주기가 아니라 지표 이름이다. 최근 1년 동안 한 달에 한 번
이상 술을 마신 사람의 비율이다. 조사는 해마다 한 번이고 차트도 연간이다.

2006년은 값이 없다. 국민건강영양조사가 그해에는 없었다. 제3기가 2005년,
제4기 1차년도가 2007년이다. 빈칸으로 둔다.

검산은 차트에 이미 들어 있는 해의 값이 표와 맞는지 본다. 어긋나면 쓰지
않는다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
TBL = "DT_11702_N012"
URL = "https://kosis.kr/statHtml/statHtml.do?orgId=177&tblId=" + TBL
AGES = [("201", "19-29세", "19~29세", "#1f3f6e"),
        ("202", "30-39세", "30~39세", "#2a5ca8"),
        ("203", "40-49세", "40~49세", "#5b8bc4"),
        ("204", "50-59세", "50~59세", "#d4a15c"),
        ("205", "60-69세", "60~69세", "#d4823c"),
        ("206", "70세이상", "70세 이상", "#c0322f")]


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

    obj = "+".join(c for c, _, _, _ in AGES)
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId=177&tblId={TBL}&prdSe=Y"
         f"&startPrdDe=2005&endPrdDe={now.year}&itmId=RATIO&objL1=1&objL2={obj}")
    r = subprocess.run(["curl", "-sS", "--max-time", "170", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit(f"응답이 표가 아닙니다: {str(d)[:160]}")
    m, unit = {}, None
    for x in d:
        if x.get("DT") in (None, "", "-"):
            continue
        m.setdefault(x["C2_NM"], {})[int(x["PRD_DE"])] = float(x["DT"])
        unit = x.get("UNIT_NM")
    miss = [k for _, k, _, _ in AGES if k not in m]
    if miss:
        raise SystemExit(f"응답에 없는 연령대: {miss}")

    ys = sorted(set().union(*[set(v) for v in m.values()]))
    ys = list(range(ys[0], ys[-1] + 1))          # 빠진 해를 빈칸으로 남긴다
    for y in ys:
        have = [k for _, k, _, _ in AGES if y in m[k]]
        if have and len(have) != len(AGES):
            raise SystemExit(f"{y}년에 일부 연령대만 있습니다: {have}")
    empty = [y for y in ys if y not in m["19-29세"]]
    print(f"  {len(ys)}년 {ys[0]}~{ys[-1]}, 값 없는 해 {empty or '없음'}")

    # 검산. 차트에 들어 있는 해가 표와 맞는가
    base = {}
    for f in ("full.json", "manual.json", "api.json"):
        p = os.path.join(DATA, f)
        if not os.path.exists(p):
            continue
        for i in json.load(open(p, encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    cur = {**base.get("c0259", {}), **(ov.get("c0259") or {})}
    old = {}
    for nm, ser in zip(cur.get("seriesNames") or [], cur.get("series") or []):
        key2 = nm.strip().replace("+", "세이상")
        key2 = key2 if key2.endswith("세이상") else key2 + "세"
        old[key2] = dict(zip([int(x) for x in cur["labels"]], ser))
    bad, seen = [], 0
    for _, k, _, _ in AGES:
        for y, v in (old.get(k) or {}).items():
            if y in m[k]:
                seen += 1
                if abs(m[k][y] - v) > 0.051:
                    bad.append((k, y, v, m[k][y]))
    if not seen:
        raise SystemExit("기존 차트와 대조할 값을 찾지 못했습니다.")
    if bad:
        raise SystemExit(f"기존 값이 표와 어긋납니다({len(bad)}곳): {bad[:5]}")
    print(f"    검산: 기존 차트의 {seen}칸이 모두 표와 일치")

    ser = [[m[k].get(y) for y in ys] for _, k, _, _ in AGES]
    last = max(y for y in ys if y in m["19-29세"])
    i = ys.index(last)
    young, old70 = m["19-29세"], m["70세이상"]
    y0 = min(young)
    out = {
        "c0259": {
            "id": "c0259",
            "title": "연령대별 월간 음주율.",
            "vizType": "line", "unit": unit or "%",
            "labels": [str(y) for y in ys],
            "series": ser,
            "seriesNames": [nm for _, _, nm, _ in AGES],
            "seriesColors": [c for _, _, _, c in AGES],
            "source": (f"질병관리청 국민건강영양조사 월간 음주율. 19세 이상. "
                       f"{ys[0]}~{ys[-1]}년. 단위: %."),
            "sourceUrl": URL,
            "notes": [
                "'월간' 은 조사 주기가 아니라 지표 이름입니다. 최근 1년 동안 한 달에 "
                "한 번 이상 술을 마신 사람의 비율입니다. 조사는 해마다 한 번이고 "
                "이 차트도 연간입니다.",
                f"{last}년 19~29세가 {young[last]}%, 70세 이상이 {old70[last]}% "
                f"입니다. {y0}년에는 각각 {young[y0]}%, {old70[y0]}% 였습니다. "
                f"젊은 층은 내려가고 나이 든 층은 올라가 두 선이 가까워지고 "
                f"있습니다.",
                f"40~49세는 {y0}년 {m['40-49세'][y0]}%에서 {last}년 "
                f"{m['40-49세'][last]}%로 올랐습니다. {last}년에는 19~29세보다 "
                f"높습니다. 가장 많이 마시는 연령대가 20대에서 40대로 넘어갔습니다.",
                "2006년은 값이 없습니다. 국민건강영양조사가 그해에는 없었습니다. "
                "제3기가 2005년, 제4기 1차년도가 2007년입니다.",
                "한 달에 한 번만 마셔도 들어가는 지표라 음주량이나 폭음은 보이지 "
                "않습니다. 많이 마시는지를 보려면 고위험음주율이나 월간폭음률을 "
                "따로 봐야 합니다.",
                "자가보고 조사입니다. 술을 마신 사실을 덜 말하는 경향이 있어 실제보다 "
                "낮게 나올 수 있고, 그 정도가 연령대마다 다를 수 있습니다.",
            ],
            "updated": ymd,
        }
    }
    o = out["c0259"]
    print(f"\n  c0259 {len(ys)}점 {ys[0]}~{ys[-1]}")
    for nm, s in zip(o["seriesNames"], o["series"]):
        print(f"    {nm:10s} {s[0]} ... {s[i]}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, v in out.items():
        ov.setdefault(cid, {}).update(v)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
