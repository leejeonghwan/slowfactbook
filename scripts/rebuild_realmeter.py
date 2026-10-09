#!/usr/bin/env python3
"""
리얼미터 주간통계표 아카이브를 통째로 받아 대통령 국정수행 평가 주간 시계열을 복원한다.

차트마다 긍정률 시계열이 조금씩 달라(68주·70주·64주) 어느 것이 맞는지 가릴 수 없었다.
원자료가 주 단위로 다 남아 있으므로 거기서 다시 쌓는다.

  python3 scripts/rebuild_realmeter.py --scan            아카이브 목록만 모은다
  python3 scripts/rebuild_realmeter.py --fetch 12        아직 안 받은 것 12개를 받아 파싱
  python3 scripts/rebuild_realmeter.py --report          모인 것으로 시계열을 만들어 차트와 대조

받은 결과는 .cache/poll/realmeter_weeks.json 에 쌓인다(이어받기 가능).
"""
import os, re, sys, json, argparse, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
CACHE = os.path.join(ROOT, ".cache", "poll")
STORE = os.path.join(CACHE, "realmeter_weeks.json")
LIST = os.path.join(CACHE, "realmeter_list.json")
BASE = "http://www.realmeter.net/category/pdf/"
UA = {"User-Agent": "Mozilla/5.0 slowfactbook"}


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def save(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def scan(maxpage=12):
    import requests
    urls = []
    for pg in range(1, maxpage + 1):
        u = BASE if pg == 1 else BASE + f"page/{pg}/"
        t = requests.get(u, timeout=40, headers=UA).text
        got = [g for g in dict.fromkeys(re.findall(r'href="([^"]+?\.pdf)(?:#[^"]*)?"', t))
               if "주간통계표" in g]
        if not got:
            break
        urls += got
        print(f"  page {pg}: {len(got)}건")
    urls = list(dict.fromkeys(urls))
    save(LIST, urls)
    print(f"총 {len(urls)}개 → {os.path.relpath(LIST, ROOT)}")
    return urls


def fetch(n):
    import requests
    from poll_charts import parse_realmeter
    urls = load(LIST, [])
    if not urls:
        urls = scan()
    got = load(STORE, {})
    todo = [u for u in urls if u not in got][:n]
    print(f"받을 것 {len(todo)}개 (누적 {len(got)}/{len(urls)})")
    os.makedirs(CACHE, exist_ok=True)
    for u in todo:
        name = os.path.basename(u.split("?")[0])
        path = os.path.join(CACHE, name)
        try:
            if not os.path.exists(path):
                r = requests.get(u, timeout=90, headers=UA)
                r.raise_for_status()
                open(path, "wb").write(r.content)
            d = parse_realmeter(path, allow_no_party=True)
            got[u] = {"week": d["week"], "approve": d["approve"], "disapprove": d["disapprove"],
                      "party": d["party"][-1] if d["party"] else None, "file": name}
            y, mo, wk = d["week"]
            print(f"  {y}-{mo:02d} {wk}주  {d['approve']} / {d['disapprove']}")
        except SystemExit as e:
            got[u] = {"error": str(e), "file": name}
            print(f"  [실패] {name}: {str(e)[:70]}")
        except Exception as e:
            got[u] = {"error": f"{type(e).__name__}: {e}", "file": name}
            print(f"  [실패] {name}: {type(e).__name__} {str(e)[:60]}")
        save(STORE, got)
    left = len([u for u in urls if u not in got])
    print(f"남은 것 {left}개")
    return left


def weeks():
    got = load(STORE, {})
    rows = [v for v in got.values() if v.get("week") and v.get("approve") is not None]
    rows.sort(key=lambda r: tuple(r["week"]))
    return rows


def report():
    rows = weeks()
    bad = [v for v in load(STORE, {}).values() if v.get("error")]
    print(f"파싱 성공 {len(rows)}주 / 실패 {len(bad)}건")
    if rows:
        a, b = rows[0]["week"], rows[-1]["week"]
        print(f"  구간 {a[0]}년 {a[1]}월 {a[2]}주 ~ {b[0]}년 {b[1]}월 {b[2]}주")
    seen = {}
    for r in rows:
        k = tuple(r["week"])
        if k in seen and seen[k] != (r["approve"], r["disapprove"]):
            print(f"  [주의] {k} 가 두 번 나오는데 값이 다릅니다: {seen[k]} vs {(r['approve'], r['disapprove'])}")
        seen[k] = (r["approve"], r["disapprove"])
    for e in bad:
        print("  실패:", e["file"], "|", str(e["error"])[:80])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--fetch", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--maxpage", type=int, default=12)
    a = ap.parse_args()
    if a.scan:
        scan(a.maxpage)
    if a.fetch:
        fetch(a.fetch)
    if a.report or not (a.scan or a.fetch):
        report()


if __name__ == "__main__":
    main()
