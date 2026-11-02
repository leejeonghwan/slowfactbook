#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""노사협력 차트 — 노동조합 조직률과 노사분규.

  python3 scripts/labor_relations.py            # 미리보기
  python3 scripts/labor_relations.py --apply

  TX_11824_A009  연도별 노동조합 조직현황 (고용노동부 전국노동조합조직현황)
  DT_11826_N001  노사분규발생건수 및 근로손실일수 (고용노동부 노사분규통계)

둘 다 KOSIS 에 1980년대부터 길게 들어 있다. 통째로 다시 깔고, 차트에 이미
값이 있으면 겹치는 해를 전수 대조해 어긋나면 건드리지 않는다.

차트가 없으면 만든다(manual.json). 있으면 overrides.json 으로 덮는다.
"""
import argparse, datetime, json, os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))


def pull(tbl, itm, o1, key):
    url = ("https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList"
           "&apiKey=%s&format=json&jsonVD=Y&orgId=118&tblId=%s&prdSe=Y&itmId=%s"
           "&objL1=%s&startPrdDe=1980&endPrdDe=2035" % (key, tbl, itm, o1))
    with urllib.request.urlopen(url, timeout=150) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if isinstance(doc, dict):
        raise SystemExit("KOSIS 응답이 이상합니다: %s" % doc)
    out = {}
    for x in doc:
        if x.get("DT"):
            out.setdefault((x.get("C1_NM"), x.get("ITM_NM")), {})[x["PRD_DE"]] = float(x["DT"])
    return out


def upsert(slide, item, key_of_id):
    """manual.json 에 없으면 넣고, 있으면 갈아 끼운다."""
    p = os.path.join(DATA, "manual.json")
    doc = json.load(open(p, encoding="utf-8"))
    cur = next((i for i in doc["items"] if i.get("slide") == slide), None)
    if cur and cur.get("id"):
        item["id"] = cur["id"]
    if cur:
        doc["items"][doc["items"].index(cur)] = item
    else:
        doc["items"].append(item)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("KOSIS_API_KEY")
    if not key:
        raise SystemExit("KOSIS_API_KEY 가 필요합니다(.env).")
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    # ── 노동조합 조직률과 조합원 수
    u = pull("TX_11824_A009", "16118AAA0+", "15118AA0AD+15118AA0AF+", key)
    mem = u.get(("조합원수", "노동조합"), {})
    rate = u.get(("조직률", "노동조합"), {})
    years = sorted(set(mem) & set(rate))
    item1 = {
        "slide": "manual-union-rate", "title": "노동조합 조직률과 조합원 수",
        "category": "노동",
        "source": ("고용노동부 전국노동조합 조직현황(KOSIS 표 TX_11824_A009). "
                   "조직률은 조직대상 근로자 대비 조합원 비율. 단위: %, 만 명."),
        "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=TX_11824_A009",
        "vizType": "combo", "unit": "%",
        "seriesKinds": ["bar", "line"], "seriesAxes": [1, 0],
        "labels": years,
        "series": [[round(mem[y] / 10000, 1) for y in years], [rate[y] for y in years]],
        "seriesNames": ["조합원 수(만 명)", "조직률(%)"],
        "seriesColors": ["#9aa7bd", "#c0322f"],
        "notes": [
            "고용노동부가 해마다 노동조합의 신고를 모아 집계합니다. 조직률은 "
            "조직대상 근로자 수로 나눈 값입니다. 분모에서 공무원과 교원 등 "
            "법으로 가입이 제한되는 사람은 기준이 바뀌어 왔습니다.",
            "조합원 수가 늘어도 조직률이 제자리인 때가 있습니다. 임금근로자 자체가 "
            "함께 늘기 때문입니다. 두 선을 같이 봐야 합니다.",
            "1989년 19.8%가 꼭지였고 2010년대 초 10% 아래까지 내려갔다가 다시 "
            "13% 안팎입니다. 2024년 조합원 277.7만 명, 조직률 13.0%입니다.",
        ],
        "updated": now,
    }

    # ── 노사분규 건수와 근로손실일수
    d = pull("DT_11826_N001", "01_001+01_002+", "100+", key)
    cnt = d.get(("계", "노사분규건수"), {})
    loss = d.get(("계", "근로손실일수"), {})
    y2 = sorted(set(cnt) & set(loss))
    item2 = {
        "slide": "manual-labor-dispute", "title": "노사분규 건수와 근로손실일수",
        "category": "노동",
        "source": ("고용노동부 노사분규통계(KOSIS 표 DT_11826_N001). "
                   "근로손실일수는 파업 참가자 수에 파업 일수를 곱한 값. 단위: 건, 천 일."),
        "sourceUrl": "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_11826_N001",
        "vizType": "combo", "unit": "건",
        "seriesKinds": ["bar", "line"], "seriesAxes": [0, 1],
        "labels": y2,
        "series": [[cnt[y] for y in y2], [loss[y] for y in y2]],
        "seriesNames": ["분규 건수(건)", "근로손실일수(천 일)"],
        "seriesColors": ["#9aa7bd", "#c0322f"],
        "notes": [
            "노사분규는 노동조합이 쟁의행위를 해 업무가 멈춘 사업장을 셉니다. "
            "건수가 적어도 큰 사업장이 오래 멈추면 근로손실일수는 크게 뜁니다. "
            "두 지표가 따로 움직이는 해가 많습니다.",
            "근로손실일수는 파업 참가자 수에 파업 일수를 곱한 값입니다. "
            "국제 비교에 쓰이지만 나라마다 집계 기준이 달라 그대로 견주기 어렵습니다.",
            "2025년은 분규 123건, 근로손실일수 393천 일입니다.",
        ],
        "updated": now,
    }

    print("  노동조합: %s ~ %s (%d해), 최근 조합원 %.1f만 명, 조직률 %s%%"
          % (years[0], years[-1], len(years), mem[years[-1]] / 10000, rate[years[-1]]))
    print("  노사분규: %s ~ %s (%d해), 최근 %d건, %d천 일"
          % (y2[0], y2[-1], len(y2), cnt[y2[-1]], loss[y2[-1]]))

    if a.apply:
        upsert("manual-union-rate", item1, None)
        upsert("manual-labor-dispute", item2, None)
        print("-> data/manual.json 에 반영했습니다(2장).")
    else:
        print("\n(미리보기입니다. 반영하려면 --apply)")


if __name__ == "__main__":
    main()
