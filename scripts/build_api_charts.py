#!/usr/bin/env python3
"""
등록된 API 차트를 매 빌드마다 최신값으로 받아 data/api.json 을 만든다.

  data/api_charts.json  (등록부 — newchart.py 가 채운다)
        │  빌드할 때마다 KOSIS·ECOS에서 새로 받는다
        ▼
  data/api.json         (generate_site.load_items 가 자동으로 읽는 형식)
        ▼
  site/

이 트랙의 차트는 사람이 갱신할 일이 없다. 빌드하면 그 시점의 최신이 된다.
키노트에서 만든 기존 차트(origin=keynote)와는 파일이 분리돼 있어 섞이지 않는다.

  KOSIS_API_KEY=... ECOS_API_KEY=... python3 scripts/build_api_charts.py
"""
import os, sys, json, time, datetime, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REG = os.path.join(DATA, "api_charts.json")
OUTP = os.path.join(DATA, "api.json")
KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "")


def kosis_series(spec):
    q = {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
         "orgId": spec["orgId"], "tblId": spec["tblId"], "itmId": spec["itmId"],
         "prdSe": spec["prdSe"], "startPrdDe": spec.get("startPrdDe", "1960"),
         "endPrdDe": spec.get("endPrdDe", "2030")}
    for i in range(1, 5):
        if spec.get(f"objL{i}"):
            q[f"objL{i}"] = spec[f"objL{i}"]
    u = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?"
         + "&".join(f"{k}={urllib.parse.quote(str(v), safe='+')}" for k, v in q.items()))
    last = None
    for t in range(4):
        try:
            with urllib.request.urlopen(u, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if not isinstance(d, list):
                raise RuntimeError(str(d)[:100])
            out = {}
            for row in d:
                try:
                    out[row["PRD_DE"]] = float(row["DT"])
                except (TypeError, ValueError, KeyError):
                    continue
            return sorted(out.items())
        except Exception as e:
            last = e
            time.sleep(1 + t)
    raise RuntimeError(str(last)[:100])


def ecos_series(spec):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import ecos
    return ecos.search(spec["statCode"], spec["cycle"], spec["start"], spec["end"],
                       spec.get("itemCode"))


def pp(t, cyc):
    t = str(t)
    if cyc == "M" and len(t) == 6:
        return f"{t[:4]}-{t[4:]}"
    if cyc == "Q" and len(t) > 4:
        return f"{t[:4]} {t[4:].lstrip('0Q') or '1'}Q"
    if cyc == "D" and len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    return t[:4]


def main():
    if not os.path.exists(REG):
        print("등록된 API 차트가 없습니다. scripts/newchart.py 로 추가하세요.")
        json.dump({"category": "새 데이터", "items": []},
                  open(OUTP, "w", encoding="utf-8"), ensure_ascii=False)
        return 0
    reg = json.load(open(REG, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    items, errs = [], 0
    for key, c in reg.items():
        if c.get("disabled"):
            continue
        try:
            ser = ecos_series(c) if c.get("provider") == "ecos" else kosis_series(c)
        except Exception as e:
            print(f"  ✗ {key} {c['title']}: {str(e)[:60]}")
            errs += 1
            continue
        if len(ser) < 2:
            continue
        sc = c.get("scale", 1) or 1
        cyc = c.get("cycle", "Y")
        items.append({
            "slide": key,
            "title": c["title"],
            "category": c.get("category", "새 데이터"),
            "source": f"{c.get('source','')} 「{c.get('table','')}」"
                      + (f", 단위: {c['unit']}" if c.get("unit") else ""),
            "sourceUrl": c.get("sourceUrl", ""),
            "vizType": c.get("vizType", "line"),
            "labels": [pp(p, cyc) for p, _ in ser],
            "seriesNames": [c["title"]],
            "updated": today,
            "series": [[round(v * sc, 6) for _, v in ser]],
        })
        print(f"  · {key} {c['title'][:26]:28s} {pp(ser[0][0],cyc)}~{pp(ser[-1][0],cyc)} ({len(ser)}개)")
    json.dump({"category": "새 데이터", "_origin": "api", "items": items},
              open(OUTP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nAPI 차트 {len(items)}건 → data/api.json  (실패 {errs})")
    print("다음: python3 scripts/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
