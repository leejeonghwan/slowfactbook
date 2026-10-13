#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB부동산 데이터허브 월간 평균가격을 API 로 받아 차트를 이어붙인다.

kb_update.py 는 사람이 엑셀을 받아 넣어야 했다. 데이터허브 화면이 실제로 부르는
창구를 찾아 그 자리를 메운다. 키는 필요 없고 Referer 만 있으면 된다.

  https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/avgPrc
    매물종별구분  01 아파트
    매매전세코드  01 매매 · 02 전세
    기간          거슬러 올라갈 햇수. 20 이상이면 전 구간을 준다.
  응답 dataBody.data = {"날짜리스트": ["200812", …], "데이터리스트": [{"지역명","dataList"}]}
  값은 만원. 억 원으로 보려면 scale 0.0001.

매매와 전세는 시작 달이 다르다(매매 2008-12, 전세 2011-06). 날짜리스트를 각각
들고 와 달을 열쇠로 맞춘다 — 순서로 맞추면 다섯 달이 어긋난다.

등록부는 data/kbapi_charts.json. 열쇠는 차트 id.
  {"c0725": {"series": [{"name": "매매가격", "지역": "서울", "코드": "01"},
                        {"name": "전세가격", "지역": "서울", "코드": "02"}],
             "scale": 0.0001}}

겹치는 달이 하나라도 어긋나면 그 차트는 건드리지 않는다.
"""
import argparse, datetime, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
import generate_site as g

KST = datetime.timezone(datetime.timedelta(hours=9))
API = "https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/avgPrc"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
REF = "https://data.kbland.kr/"
# 한글 파라미터 이름을 그대로 써야 받아 준다.
Q = ("title=x&%EB%A7%A4%EB%AC%BC%EC%A2%85%EB%B3%84%EA%B5%AC%EB%B6%84={jong}"
     "&%EB%A7%A4%EB%A7%A4%EC%A0%84%EC%84%B8%EC%BD%94%EB%93%9C={code}"
     "&%EA%B8%B0%EA%B0%84=99&%EB%8B%A8%EC%9C%84=(%EB%8B%A8%EC%9C%84:%EB%A7%8C%EC%9B%90)")


def fetch(code, jong="01"):
    """{지역명: {"YYYY-MM": 값}} 으로 돌려준다."""
    url = f"{API}?{Q.format(jong=jong, code=code)}"
    body = subprocess.run(["curl", "-sS", "--max-time", "60", "-A", UA,
                           "-H", f"Referer: {REF}", url],
                          capture_output=True, text=True, timeout=90).stdout
    d = json.loads(body)["dataBody"]["data"]
    dates = [f"{str(x)[:4]}-{str(x)[4:6]}" for x in d["날짜리스트"]]
    out = {}
    for r in d["데이터리스트"]:
        out[r["지역명"]] = {k: v for k, v in zip(dates, r["dataList"]) if v is not None}
    return out


MAP_API = "https://data-api.kbland.kr/bfmstat/wthrchat/avgPrc"


def fetch_district(code, dong="1100000000", level=2):
    """시군구 단위 평균가격. {"구 이름": {"YYYY-MM": 값(만원)}}.

    지도 화면이 쓰는 창구라 응답에 경계 폴리곤이 딸려 와 16MB쯤 된다(한 달에 한 번
    부르는 것이라 그냥 둔다). 시도 단위와 달리 2022년 11월부터만 준다 — KB 가 구
    단위로는 그만큼만 공개한다.
    """
    import urllib.parse
    q = {"월간주간구분코드": "01", "조회시작일자": "201106", "조회종료일자": "209912",
         "단위구분코드": "01", "면적크기코드": "00", "매매전세코드": code,
         "레벨": str(level), "법정동코드": dong}
    url = MAP_API + "?" + "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}"
                                   for k, v in q.items())
    body = subprocess.run(["curl", "-sS", "--max-time", "120", "-A", UA,
                           "-H", f"Referer: {REF}", url],
                          capture_output=True, text=True, timeout=180).stdout
    rows = json.loads(body)["dataBody"]["data"]["depth1"]
    out = {}
    for r in rows:
        ym = str(r["통계기준년월일시"])[:6]
        v = r.get("현재데이터")
        if v is None:
            continue
        out.setdefault(r["지역명"], {})[f"{ym[:4]}-{ym[4:]}"] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()

    mp = os.path.join(DATA, "kbapi_charts.json")
    mapping = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    if a.only:
        mapping = {k: v for k, v in mapping.items() if k == a.only}
    if not mapping:
        print("data/kbapi_charts.json 이 비어 있습니다."); return 0

    now = datetime.datetime.now(KST)
    cut = now.strftime("%Y-%m")
    _items = g.load_items(DATA)
    g.assign_ids(_items, os.path.join(DATA, "ids.json"))
    items = {it["id"]: it for it in _items if it.get("id")}
    ovp = os.path.join(DATA, "overrides.json")
    ov = json.load(open(ovp, encoding="utf-8")) if os.path.exists(ovp) else {}
    stamp = now.strftime("%Y-%m-%d %H:%M")

    cache, plans, skips = {}, [], []
    for cid, spec in mapping.items():
        it = items.get(cid)
        if not it:
            skips.append((cid, "차트를 찾지 못했습니다")); continue
        labels = [str(x) for x in it["labels"]]
        # 구별 최신값 차트는 라벨이 구 이름이다. 달 꼴 검사는 시계열에만 건다.
        if not (spec.get("kind") == "district" and spec.get("mode") == "latest") \
           and not re.fullmatch(r"\d{4}-\d{2}", labels[-1]):
            skips.append((cid, f"라벨이 월 꼴이 아닙니다: {labels[-1]}")); continue
        sers = spec.get("series") or []
        sc = float(spec.get("scale", 1))
        if spec.get("kind") != "district" and len(sers) != len(it["series"]):
            skips.append((cid, f"등록 계열 {len(sers)}개 != 차트 계열 {len(it['series'])}개")); continue
        tol = float(spec.get("tol", 0.01))
        nd = int(spec.get("round", 4))

        if spec.get("kind") == "district":
            dong, lv = spec.get("법정동코드", "1100000000"), spec.get("레벨", 2)
            def grab(code):
                k = ("D", code, dong)
                if k not in cache:
                    cache[k] = fetch_district(code, dong, lv)
                return cache[k]
            try:
                if spec.get("ratio"):
                    # 전세가율처럼 두 값의 비(%). ["02","01"] 이면 전세÷매매.
                    nu, de = (grab(c) for c in spec["ratio"])
                    reg = {}
                    for n in set(nu) & set(de):
                        reg[n] = {m: nu[n][m] / de[n][m] * 100
                                  for m in set(nu[n]) & set(de[n]) if de[n][m]}
                    sc = 1.0
                else:
                    reg = grab(spec.get("코드", "02"))
            except Exception as e:
                skips.append((cid, f"조회 실패: {e}")); continue
            months = sorted({m for v in reg.values() for m in v})
            months = [m for m in months if m != cut]
            if not months:
                skips.append((cid, "받아온 달이 없습니다")); continue
            if spec.get("mode") == "latest":
                # 최신 달 한 장. 값이 큰 구부터 세워 가로 막대로 읽는다.
                last = months[-1]
                rank = sorted(((n, v[last] * sc) for n, v in reg.items() if last in v),
                              key=lambda x: -x[1])
                nl = [n for n, _ in rank]
                ns = [[round(v, nd) for _, v in rank]]
            else:
                names = sorted(reg, key=lambda n: -reg[n].get(months[-1], 0))
                nl = months
                ns = [[(round(reg[n][m] * sc, nd) if m in reg[n] else None) for m in months]
                      for n in names]
                spec["_names"] = names
            if nl == labels and all(ns[i] == it["series"][i] for i in range(len(ns))):
                skips.append((cid, "이미 최신")); continue
            plans.append({"id": cid, "title": it["title"], "labels": nl, "series": ns,
                          "n": len(nl), "from": labels[-1], "to": nl[-1],
                          "seriesNames": spec.get("_names")})
            continue

        got, err = [], None
        for s in sers:
            jong, code = s.get("종별", "01"), s["코드"]
            if (jong, code) not in cache:
                try:
                    cache[(jong, code)] = fetch(code, jong)
                except Exception as e:
                    err = f"조회 실패: {e}"; break
            reg = cache[(jong, code)]
            if s["지역"] not in reg:
                err = f"지역 '{s['지역']}' 이 응답에 없습니다"; break
            got.append(reg[s["지역"]])
        if err:
            skips.append((cid, err)); continue

        bad, seen = [], 0
        for si, d in enumerate(got):
            for i, lab in enumerate(labels):
                a0, b0 = it["series"][si][i], d.get(lab)
                if a0 is None or b0 is None:
                    continue
                seen += 1
                if abs(a0 - b0 * sc) > tol:
                    bad.append((lab, sers[si]["name"], a0, round(b0 * sc, 4)))
        if seen < 6:
            skips.append((cid, f"대조할 달이 부족합니다({seen}곳)")); continue
        if bad:
            skips.append((cid, f"겹치는 구간 {len(bad)}곳 불일치 (예 {bad[0]})")); continue

        addk = [k for k in sorted(set.intersection(*[set(d) for d in got]))
                if k > labels[-1] and k != cut]
        if not addk:
            skips.append((cid, "이미 최신")); continue
        plans.append({"id": cid, "title": it["title"], "labels": labels + addk,
                      "series": [list(s) + [round(d[k] * sc, 4) for k in addk]
                                 for s, d in zip(it["series"], got)],
                      "n": len(addk), "from": labels[-1], "to": addk[-1]})

    print(f"등록 {len(mapping)}건 · 이어붙일 것 {len(plans)}건 · 건너뜀 {len(skips)}건\n")
    for p in plans:
        print(f"  + {p['title'][:30]:32s} {p['from']} -> {p['to']}  ({p['n']}개월 추가)")
    for cid, why in skips:
        print(f"  - {cid}: {why}")

    if a.apply and plans:
        for p in plans:
            o = ov.setdefault(p["id"], {})
            o["id"] = p["id"]
            o["labels"] = p["labels"]; o["series"] = p["series"]; o["updated"] = stamp
            if p.get("seriesNames"):
                o["seriesNames"] = p["seriesNames"]
            u = (mapping.get(p["id"]) or {}).get("sourceUrl")
            if u:
                o["sourceUrl"] = u
        json.dump(ov, open(ovp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n-> data/overrides.json 에 {len(plans)}건 반영.")
    elif plans:
        print("\n(미리보기입니다. 반영하려면 --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
