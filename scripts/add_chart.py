#!/usr/bin/env python3
"""
데이터(CSV·TSV·엑셀·붙여넣은 표)로 새 차트를 만든다. 키노트를 거치지 않는다.

  python3 scripts/add_chart.py 표.csv --title "합계출산율" --category "출산" --source "국가데이터처 인구동향조사" --unit "명" --url https://...
  pbpaste | python3 scripts/add_chart.py - --title "..." --category "..."

기본은 미리보기, 반영은 --apply. 새 차트는 data/manual.json 에 들어가고(origin=manual), 빌드 때 새 id 를 받는다.
키노트에서 뽑은 것(full.json)·API 트랙(api.json)과 파일이 다르니 섞이지 않는다.

차트 종류(--type)를 안 주면 라벨이 시점이면 line, 아니면 계열 하나일 때 bar, 여럿이면 column.
  line · column · bar · stacked_bar · stacked_bar_h · area · pie · combo
"""
import os, sys, json, re, datetime, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import generate_site as g       # noqa: E402
import tabledata as td          # noqa: E402

MANUAL = os.path.join(DATA, "manual.json")
TYPES = ["line", "column", "bar", "stacked_bar", "stacked_bar_h", "area", "pie", "combo"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", help="CSV/TSV/XLSX/텍스트 파일. '-' 는 표준입력")
    ap.add_argument("--title", required=True)
    ap.add_argument("--category", required=True, help="기존 분류명을 그대로 쓰면 그 묶음에 들어간다 (예: 노동, 부동산)")
    ap.add_argument("--type", choices=TYPES)
    ap.add_argument("--source", help="출처 표기")
    ap.add_argument("--unit")
    ap.add_argument("--url", help="출처 URL")
    ap.add_argument("--sheet")
    ap.add_argument("--transpose", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0, help="값에 곱할 배수 (만원→억 원 0.0001)")
    ap.add_argument("--note")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    text = sys.stdin.read() if a.data == "-" else None
    try:
        new = td.load(path=None if text is not None else a.data, text=text,
                      sheet=a.sheet, transpose=True if a.transpose else None)
    except Exception as e:
        print(f"표를 읽지 못했습니다: {e}")
        return 1
    if a.scale != 1.0:
        new["series"] = [[None if v is None else v * a.scale for v in s] for s in new["series"]]

    labels, names, series = new["labels"], new["seriesNames"], new["series"]
    timeish = all(td.period_key(l) for l in labels)
    viz = a.type or ("line" if timeish else ("bar" if len(series) == 1 else "column"))

    # 같은 제목이 이미 있으면 알려준다 (중복 차트 방지)
    items = g.load_items(DATA)
    dup = [it for it in items if re.sub(r"\s", "", it["title"]) == re.sub(r"\s", "", a.title)]
    if dup:
        print(f"! 같은 제목의 차트가 이미 있습니다: " + ", ".join(f"{d['slide']}[{d['category']}]" for d in dup))
        print("  기존 차트를 갱신하려면 set_data.py 를 쓰세요. 그래도 새로 만들려면 제목을 조금 바꾸세요.")
        return 1

    src = a.source or ""
    if a.unit and "단위" not in src:
        src = f"{src}, 단위: {a.unit}" if src else f"단위: {a.unit}"
    doc = json.load(open(MANUAL, encoding="utf-8")) if os.path.exists(MANUAL) else \
        {"category": "새 데이터", "_origin": "manual", "items": []}
    n = 1 + max([int(it["slide"].split("-")[1]) for it in doc["items"]] or [0])
    slide = f"m-{n:04d}"
    today = datetime.date.today().isoformat()
    item = {"slide": slide, "title": a.title, "category": a.category, "source": src,
            "sourceUrl": a.url or "", "vizType": viz, "labels": labels,
            "seriesNames": names, "series": [[None if v is None else round(v, 6) for v in s] for s in series],
            "updated": today}
    if viz == "combo":
        item["seriesKinds"] = ["column"] * (len(series) - 1) + ["line"]
        item["seriesAxes"] = ["y"] * (len(series) - 1) + ["y2"]

    print(f"새 차트: {slide} [{a.category}] {a.title}  ({viz})")
    print(f"  {labels[0]} ~ {labels[-1]}  {len(labels)}점 × {len(series)}계열  {names}" +
          ("  (뒤집어 읽음)" if new["transposed"] else ""))
    for nm, s in zip(names, series):
        print(f"    {nm}: {s[:4]} … {s[-3:]}")
    print(f"  출처: {src or '(없음)'}  {a.url or ''}")
    if a.url and "kosis.kr" in a.url and "tblId=" in a.url:
        tbl = re.search(r"tblId=([A-Z0-9_]+)", a.url).group(1)
        print(f"  · KOSIS 표 {tbl} — 자동 갱신 후보. 반영 뒤: python3 scripts/register_auto.py {slide} --tbl {tbl}")
    if not a.apply:
        print("\n(미리보기입니다. 반영하려면 --apply)")
        return 0

    doc["items"].append(item)
    json.dump(doc, open(MANUAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # id 를 지금 받아 둔다 (빌드 때 받는 것과 같은 규칙)
    items = g.load_items(DATA)
    g.assign_ids(items, os.path.join(DATA, "ids.json"))
    cid = next((it["id"] for it in items if it["slide"] == slide), "?")
    clp = os.path.join(DATA, "changelog.json")
    cl = json.load(open(clp, encoding="utf-8")) if os.path.exists(clp) else []
    cl.append({"date": today, "slide": slide, "id": cid, "title": a.title, "category": a.category,
               "mode": "new", "from": labels[0], "to": labels[-1], "n": len(labels),
               "sourceUrl": a.url or "", "note": a.note or "", "keynoteSynced": False})
    json.dump(cl, open(clp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {slide} = {cid} 로 data/manual.json 에 추가. 다음: python3 scripts/build.py  (임베드: embed.html?id={cid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
