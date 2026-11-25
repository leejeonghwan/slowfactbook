#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전지구 일평균 기온 — 코페르니쿠스 C3S 의 ERA5 일별 계열.

출처는 C3S 클라이밋 펄스가 내놓는 한 파일이다.
  https://sites.ecmwf.int/data/climatepulse/data/series/
      era5_daily_series_2t_global.csv
1940년 1월 1일부터 어제까지 하루에 한 줄이고, 칸은 절대기온(2t),
1991~2020년 평년값(clim_91-20), 그 평년 대비 편차(ano_91-20), 확정 여부다.

기준을 옮겨야 한다 — 여기가 틀리기 쉬운 자리다.
  파일의 편차는 1991~2020년 기준인데, 기사에 쓰는 '산업화 이전 대비'는
  1850~1900년 기준이다. 두 기준의 차이는 0.88도다. 짐작이 아니라
  검산으로 확인한다. 0.88 을 더해 연평균을 내면 2023년 1.48도,
  2024년 1.60도가 나오는데 C3S 가 공표한 값과 같다. 틀리면 쓰지 않는다.

섞으면 안 되는 것.
  c0894(산업화 이전과 비교한 평균 온도 상승)는 아워월드인데이터의
  HadCRUT 계열이다. 2024년이 1.53도로 여기 1.60도와 다르다. 관측을
  모으는 방식이 달라 생기는 차이이고, 어느 쪽이 틀린 것이 아니다.
  두 계열을 한 선에 이어 붙이면 안 된다.

  마지막 며칠은 PRELIMINARY 다. 확정되면 값이 조금 바뀐다.
  ERA5 는 5일쯤 늦게 들어오므로 오늘과 어제 값은 없다.
"""
import argparse
import csv
import datetime
import io as _io
import json
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

CSV = ("https://sites.ecmwf.int/data/climatepulse/data/series/"
       "era5_daily_series_2t_global.csv")
SITE = "https://pulse.climate.copernicus.eu/"
SRC = "코페르니쿠스 기후변화서비스(C3S) ERA5"
OFF = 0.88            # 1991~2020년 평균이 1850~1900년보다 높은 정도
GATE = {"2023": 1.48, "2024": 1.60}      # C3S 공표 연평균
GREY, GREY2 = "#9b9b9b", "#cfcfcf"
RED = "#c0322f"
WARM = ["#f2c08a", "#e8a05a", "#e8820c"]   # 2023, 2024, 2025
RECENT = ["2023", "2024", "2025"]


def fetch(tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(CSV, headers={"User-Agent":
                                                       "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=150).read()
            if len(raw) < 500000:
                raise RuntimeError(f"받은 파일이 {len(raw)}바이트뿐이다")
            txt = raw.decode("utf-8")
            body = [l for l in txt.splitlines() if not l.startswith("#")]
            rows = list(csv.DictReader(body))
            if len(rows) < 30000:
                raise RuntimeError(f"줄이 {len(rows)}개뿐이다")
            return rows
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(3 + 3 * i)
    raise RuntimeError(f"C3S 파일을 받지 못했다: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    rows = fetch()
    day = {}
    prelim = []
    for r in rows:
        d = r["date"]
        v = r.get("ano_91-20")
        if v in (None, ""):
            continue
        day[d] = round(float(v) + OFF, 3)
        if (r.get("status") or "").upper().startswith("PRE"):
            prelim.append(d)
    ds = sorted(day)
    print(f"    받음: {len(ds)}일 {ds[0]}~{ds[-1]} "
          f"(잠정 {len(prelim)}일)")

    # 검산 1. 날짜가 하루도 빠지지 않았는가
    first = datetime.date.fromisoformat(ds[0])
    last = datetime.date.fromisoformat(ds[-1])
    want = (last - first).days + 1
    if want != len(ds):
        print(f"  검산 실패: {first}~{last} 는 {want}일인데 {len(ds)}일뿐이다")
        return 1
    print(f"    검산 연속: {first}부터 {last}까지 하루도 빠지지 않음")

    # 검산 2. 기준을 옮긴 값이 C3S 공표 연평균과 같은가
    yr = {}
    for d, v in day.items():
        yr.setdefault(d[:4], []).append(v)
    bad = [(y, round(sum(yr[y]) / len(yr[y]), 2), w)
           for y, w in GATE.items()
           if abs(sum(yr[y]) / len(yr[y]) - w) > 0.005]
    if bad:
        print(f"  검산 실패: 0.88 을 더한 연평균이 공표값과 다르다 {bad}")
        return 1
    print(f"    검산 기준: 1991~2020년 기준에 {OFF} 를 더하니 "
          + ", ".join(f"{y}년 {sum(yr[y])/len(yr[y]):.2f}도" for y in GATE)
          + " 로 C3S 공표값과 일치")

    out = []

    # 1. 연중 일별 비교 (가디언이 그린 모양)
    mmdd = [f"{m:02d}-{d:02d}" for m in range(1, 13)
            for d in range(1, [31, 29, 31, 30, 31, 30, 31, 31, 30, 31,
                               30, 31][m - 1] + 1)]
    past = {k: [] for k in mmdd}
    for d, v in day.items():
        if d[:4] <= "2022" and d[5:] in past:
            past[d[5:]].append(v)
    hi = [round(max(past[k]), 2) if past[k] else None for k in mmdd]
    avg = [round(sum(past[k]) / len(past[k]), 2) if past[k] else None
           for k in mmdd]
    cur = {}
    for y in RECENT + ["2026"]:
        cur[y] = [day.get(f"{y}-{k}") for k in mmdd]
    over = sum(1 for i, k in enumerate(mmdd)
               if cur["2026"][i] is not None and hi[i] is not None
               and cur["2026"][i] > hi[i])
    done = sum(1 for v in cur["2026"] if v is not None)
    print(f"    2026년: {done}일 가운데 {over}일이 1940~2022년 "
          "같은 날 최고치보다 높음")
    out.append({
        "slide": "manual-c3s-doy", "category": "기후와 에너지",
        "title": "연중 날짜별 지구 평균 기온.",
        "vizType": "line", "unit": "도",
        "labels": mmdd,
        "series": [hi, avg] + [cur[y] for y in RECENT + ["2026"]],
        "seriesNames": ["1940~2022년 최고", "1940~2022년 평균",
                        "2023년", "2024년", "2025년", "2026년"],
        "seriesColors": [GREY, GREY2] + WARM + [RED],
        "source": (f"{SRC} 일별 전지구 평균 기온. 1850~1900년 평균 대비 "
                   f"편차, {ds[-1]}까지. 단위: 섭씨 도."),
        "sourceUrl": SITE,
        "notes": [
            f"2026년은 {ds[-1]}까지 {done}일 가운데 {over}일이 "
            "1940년부터 2022년까지 같은 날 최고치보다 높았습니다.",
            f"기록상 가장 더웠던 날은 "
            + ", ".join(f"{d} {day[d]:.2f}도" for d in
                        sorted(day, key=lambda x: -day[x])[:3])
            + "입니다.",
            "가로축은 연중 날짜입니다. 같은 날짜끼리 해를 견주려고 이렇게 "
            "그립니다. 2월 29일은 뺐습니다.",
            "파일의 편차는 1991~2020년 기준입니다. 산업화 이전"
            "(1850~1900년) 기준으로 옮기려고 0.88도를 더했습니다. "
            "이렇게 내면 2023년 1.48도, 2024년 1.60도로 코페르니쿠스가 "
            "공표한 연평균과 같습니다.",
            "c0894 산업화 이전과 비교한 평균 온도 상승은 아워월드인데이터의 "
            "다른 계열입니다. 2024년이 1.53도로 여기 1.60도와 다릅니다. "
            "관측을 모으는 방식이 달라 생기는 차이이고 섞어 쓰면 안 됩니다.",
            "마지막 며칠은 잠정값이라 확정되면 조금 바뀝니다.",
        ],
        "updated": ymd,
    })

    # 2. 12개월 이동평균 (월말 기준)
    win, run = [], []
    labs, vals = [], []
    for d in ds:
        win.append(day[d])
        if len(win) > 365:
            win.pop(0)
        run.append((d, sum(win) / len(win)) if len(win) == 365 else None)
    bymon = {}
    for i, d in enumerate(ds):
        if run[i]:
            bymon[d[:7]] = round(run[i][1], 3)
    ms = sorted(bymon)
    cross = next((m for m in ms if bymon[m] >= 1.5), None)
    print(f"    12개월 이동평균: {len(ms)}개월 {ms[0]}~{ms[-1]} "
          f"(끝 {bymon[ms[-1]]:.2f}도, 1.5도 처음 넘은 달 {cross})")
    out.append({
        "slide": "manual-c3s-run12", "category": "기후와 에너지",
        "title": "지구 평균 기온 12개월 이동평균.",
        "vizType": "line", "unit": "도",
        "labels": ms, "series": [[bymon[m] for m in ms]],
        "seriesNames": ["12개월 이동평균"], "hideLegend": True,
        "seriesColors": [RED],
        "source": (f"{SRC} 일별 전지구 평균 기온의 365일 이동평균. "
                   f"1850~1900년 평균 대비 편차, 월말 기준, "
                   f"{ms[0]}~{ms[-1]}. 단위: 섭씨 도."),
        "sourceUrl": SITE,
        "notes": [
            f"{ms[-1]} 기준 {bymon[ms[-1]]:.2f}도입니다."
            + (f" 12개월 평균이 1.5도를 처음 넘은 것은 {cross}입니다."
               if cross else ""),
            "하루치 값은 날씨 때문에 크게 흔들립니다. 365일 평균을 내면 "
            "계절과 날씨가 지워지고 흐름만 남습니다.",
            "1.5도는 파리협정이 말하는 기준선입니다. 다만 협정이 말하는 "
            "1.5도는 여러 해에 걸친 평균이라, 12개월 평균이 한 번 넘었다고 "
            "곧바로 넘어선 것은 아닙니다.",
            "월말 기준으로 뽑았습니다. 산업화 이전 기준으로 옮기려고 "
            "0.88도를 더했습니다.",
        ],
        "updated": ymd,
    })

    # 3. 연평균
    ys = sorted(yr)
    ya = [round(sum(yr[y]) / len(yr[y]), 3) for y in ys]
    partial = len(yr[ys[-1]]) < 365
    top = sorted(zip(ys, ya), key=lambda x: -x[1])[:3]
    print(f"    연평균: {len(ys)}해 {ys[0]}~{ys[-1]} "
          f"(끝 {ya[-1]:.2f}도{', 아직 안 끝난 해' if partial else ''})")
    out.append({
        "slide": "manual-c3s-year", "category": "기후와 에너지",
        "title": "지구 평균 기온 연평균.",
        "vizType": "line", "unit": "도",
        "labels": [y if not (partial and y == ys[-1])
                   else f"{y}({len(yr[y])}일)" for y in ys],
        "series": [ya], "seriesNames": ["연평균"], "hideLegend": True,
        "seriesColors": [RED],
        "source": (f"{SRC} 일별 전지구 평균 기온의 연평균. 1850~1900년 "
                   f"평균 대비 편차, {ys[0]}~{ys[-1]}년. 단위: 섭씨 도."),
        "sourceUrl": SITE,
        "notes": [
            "가장 더웠던 해는 "
            + ", ".join(f"{y}년 {v:.2f}도" for y, v in top) + "입니다."
            + (f" {ys[-1]}년은 아직 끝나지 않았고 {ds[-1]}까지 "
               f"{ya[-1]:.2f}도입니다." if partial else ""),
            f"{ys[0]}년에는 {ya[0]:.2f}도였습니다.",
            "1850~1900년 평균을 0으로 둔 값입니다. 파일의 1991~2020년 "
            "기준 편차에 0.88도를 더했습니다.",
            "c0894 는 1850년부터 그리지만 아워월드인데이터의 다른 "
            "계열입니다. 두 숫자를 섞지 마십시오.",
        ],
        "updated": ymd,
    })

    print()
    for x in out:
        print(f"  {x['slide']} {len(x['labels'])}점 | 계열 "
              f"{len(x['series'])} | {x['title']}")
    if not a.apply:
        print("\n  (--apply 를 붙이면 씁니다)")
        return 0

    mp = os.path.join(DATA, "manual.json")
    doc = json.load(open(mp, encoding="utf-8"))
    idx = {i.get("slide"): i for i in doc["items"] if i.get("slide")}
    for x in out:
        prev = idx.get(x["slide"])
        if prev:
            keep = {k: prev[k] for k in ("id",) if k in prev}
            prev.clear()
            prev.update(x)
            prev.update(keep)
        else:
            doc["items"].append(x)
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    json.load(open(mp, encoding="utf-8"))
    print(f"-> data/manual.json 에 {len(out)}장을 반영했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
