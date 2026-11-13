#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""노동 차트 둘. 청년실업률(c0014)과 취업시간별 취업자 수(c0040).

  python3 scripts/labor_fix.py            # 미리보기
  python3 scripts/labor_fix.py --apply

둘 다 등록부에 올라 있는데도 몇 달씩 밀려 있었다. 이유가 서로 달랐다.

c0014 청년실업률. 값은 멀쩡했다. 분기 라벨 사이에 '2026-03' 이 하나
섞여 있었고(2026-Q3 를 잘못 적은 것) 그 때문에 자동 갱신이 라벨 꼴을
알아보지 못했다. 국가데이터처 101/DT_1YL20531E 전국 분기로 다시 세운다.

c0040 취업시간별 취업자 수. 라벨은 527달인데 값은 46개뿐이고, 그 46개가
앞쪽(1982년 자리)에 붙어 있었다. 꼬리로 맞춰 봐도 안 맞고 값 자체가 지금
원천과 다르다. 옛 판본이 라벨과 어긋난 채 남아 있던 것으로 보여 통째로
다시 세운다. 101/DT_1DA7011S 의 '*36시간 미만'(45)과 '*36시간 이상'(60)
이고 1982년 7월부터 월별로 있다.
"""
import argparse, datetime, json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

YOUTH = ("101", "DT_1YL20531E", "T80", "00")
WORK = ("101", "DT_1DA7011S", "T30", {"36시간 미만": "45", "36시간 이상": "60"})
U_Y = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1YL20531E"
U_W = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1DA7011S"


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


def pull(key, org, tbl, itm, obj, prd, s, e):
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
         f"&apiKey={key}&format=json&jsonVD=Y&orgId={org}&tblId={tbl}&prdSe={prd}"
         f"&startPrdDe={s}&endPrdDe={e}&itmId={itm}&objL1={obj}")
    r = subprocess.run(["curl", "-sS", "--max-time", "150", u], capture_output=True)
    if r.returncode:
        raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    if not isinstance(d, list):
        raise SystemExit("KOSIS 응답이 표가 아닙니다: " + str(d)[:160])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = envkey("KOSIS_API_KEY")
    now = datetime.datetime.now(KST)
    ymd = now.strftime("%Y-%m-%d %H:%M")

    # ── c0014 청년실업률 (분기)
    org, tbl, itm, obj = YOUTH
    q = {}
    for x in pull(key, org, tbl, itm, obj, "Q", "200001", f"{now.year}04"):
        if x.get("DT") in (None, "", "-"):
            continue
        p = x["PRD_DE"]
        q[f"{p[:4]}-Q{int(p[4:])}"] = float(x["DT"])
    ykeys = sorted(q, key=lambda k: (int(k[:4]), int(k[-1])))
    if len(ykeys) < 80:
        raise SystemExit(f"청년실업률 받은 분기가 {len(ykeys)}개뿐입니다.")
    # 빠진 분기가 없어야 한다.
    yy, qq = int(ykeys[0][:4]), int(ykeys[0][-1])
    for k in ykeys:
        if k != f"{yy}-Q{qq}":
            raise SystemExit(f"청년실업률에 빠진 분기가 있습니다: {yy}-Q{qq}")
        qq += 1
        if qq == 5:
            yy, qq = yy + 1, 1
    print(f"  c0014 청년실업률: {len(ykeys)}분기 {ykeys[0]}~{ykeys[-1]}")

    # ── c0040 취업시간별 취업자 수 (월별, 만 명)
    org, tbl, itm, cols = WORK
    got = {}
    for nm, o in cols.items():
        m = {}
        for x in pull(key, org, tbl, itm, o, "M", "198207", f"{now.year}12"):
            if x.get("DT") in (None, "", "-"):
                continue
            p = x["PRD_DE"]
            m[f"{p[:4]}-{p[4:6]}"] = round(float(x["DT"]) / 10, 1)   # 천명 -> 만 명
        got[nm] = m
    mk = sorted(set.intersection(*[set(v) for v in got.values()]))
    if len(mk) < 400:
        raise SystemExit(f"취업시간별 받은 달이 {len(mk)}개뿐입니다.")
    yy, mm = int(mk[0][:4]), int(mk[0][5:])
    for k in mk:
        if k != f"{yy:04d}-{mm:02d}":
            raise SystemExit(f"취업시간별에 빠진 달이 있습니다: {yy:04d}-{mm:02d}")
        mm += 1
        if mm == 13:
            yy, mm = yy + 1, 1
    print(f"  c0040 취업시간별: {len(mk)}달 {mk[0]}~{mk[-1]}")

    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8"))
    base = {}
    for f in ("full.json", "manual.json", "api.json"):
        p = os.path.join(DATA, f)
        if not os.path.exists(p):
            continue
        for i in json.load(open(p, encoding="utf-8"))["items"]:
            if i.get("id"):
                base.setdefault(i["id"], {}).update(i)

    # 검산. c0014 는 값이 멀쩡했으니 겹치는 구간이 다 맞아야 한다.
    c = {**base.get("c0014", {}), **(ov.get("c0014") or {})}
    old = {str(L): v for L, v in zip(c["labels"], c["series"][0]) if v is not None}
    bad = [(k, old[k], q[k]) for k in old if k in q and abs(old[k] - q[k]) > 0.051]
    seen = sum(1 for k in old if k in q)
    if bad:
        raise SystemExit(f"c0014 기존 값이 표와 어긋납니다({len(bad)}곳): {bad[:5]}")
    print(f"    c0014 겹치는 {seen}분기 모두 일치 (라벨만 고칩니다)")
    oddl = [str(L) for L in c["labels"] if str(L) not in q]
    print(f"    고칠 라벨: {oddl}")

    out = {
        "c0014": {
            "id": "c0014", "title": "15~29세 실업률", "vizType": "line", "unit": "%",
            "labels": ykeys, "series": [[q[k] for k in ykeys]],
            "seriesNames": ["15~29세 실업률"],
            "source": (f"국가데이터처 경제활동인구조사 청년실업률(시도), 전국. "
                       f"{ykeys[0]}~{ykeys[-1]}. 단위: %."),
            "sourceUrl": U_Y,
            "notes": [
                f"{ykeys[-1].replace('-Q', '년 ')}분기 {q[ykeys[-1]]}% 입니다. "
                f"가장 높았던 분기는 "
                + (lambda k: f"{k.replace('-Q', '년 ')}분기의 {q[k]}%")(
                    max(ykeys, key=lambda k: q[k])) + "입니다.",
                "15세부터 29세까지입니다. 분기마다 크게 오르내리는데 졸업과 "
                "채용 시기가 몰리기 때문입니다. 1분기가 높고 3분기가 낮은 "
                "모양이 해마다 되풀이됩니다. 전년 같은 분기와 견주는 쪽이 "
                "낫습니다.",
                "실업률은 일자리를 찾아 나선 사람 가운데 못 구한 비율입니다. "
                "구직을 접은 사람은 분모에서 빠지므로, 실업률이 내려가도 "
                "취업자가 늘었다는 뜻은 아닙니다.",
                "라벨이 하나 어긋나 있던 차트입니다. 분기 라벨 사이에 "
                "'2026-03' 이 섞여 있었고 그 때문에 자동 갱신이 라벨 꼴을 "
                "알아보지 못해 밀려 있었습니다. 값은 멀쩡했습니다.",
            ],
            "updated": ymd,
        },
        "c0040": {
            "id": "c0040", "title": "취업시간별 취업자 수(월별)",
            "vizType": "area", "unit": "만 명", "labels": mk,
            "series": [[got[nm][k] for k in mk] for nm in cols],
            "seriesNames": list(cols),
            "seriesColors": ["#e8820c", "#2f5e8e"],
            "source": (f"국가데이터처 경제활동인구조사 취업시간별 취업자. "
                       f"{mk[0]}~{mk[-1]}. 단위: 만 명."),
            "sourceUrl": U_W,
            "notes": [
                f"{mk[-1].replace('-', '년 ')}월 36시간 미만 "
                f"{got['36시간 미만'][mk[-1]]:,.0f}만 명, 36시간 이상 "
                f"{got['36시간 이상'][mk[-1]]:,.0f}만 명입니다. 둘을 더한 것이 "
                "취업자 전체는 아닙니다. 일시휴직자가 빠져 있습니다.",
                "통째로 다시 세운 차트입니다. 전에는 라벨이 527달인데 값은 "
                "46개뿐이었고, 그 46개가 1982년 자리에 붙어 있었습니다. 꼬리로 "
                "맞춰 봐도 안 맞고 값 자체가 지금 원천과 달라, 옛 판본이 "
                "라벨과 어긋난 채 남아 있던 것으로 보입니다.",
                "달마다 크게 흔들립니다. 명절이 낀 달에는 36시간 미만이 치솟고 "
                "36시간 이상이 내려앉습니다. 쉬는 날이 많아 그 주에 짧게 일한 "
                "사람으로 잡히기 때문입니다. 추세는 전년 같은 달과 견줘야 "
                "보입니다.",
                "36시간은 통계 구분선일 뿐 단시간 근로의 법적 기준이 아닙니다. "
                "주 15시간 미만이라야 초단시간 근로로 묶이고 주휴수당과 "
                "퇴직급여에서 빠집니다.",
            ],
            "updated": ymd,
        },
    }

    for cid, o in out.items():
        print(f"  {cid} {o['title']:24s} {len(o['labels'])}점 "
              f"{o['labels'][0]}~{o['labels'][-1]} 계열 {len(o['series'])}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
    with open(ovp, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
