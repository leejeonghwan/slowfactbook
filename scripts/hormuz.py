#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""호르무즈 해협 통과 선박. IMF 포트워치의 일별 자료로 네 장을 세운다.

  python3 scripts/hormuz.py            # 미리보기
  python3 scripts/hormuz.py --apply

수동 갱신이다. nightly.sh 와 액션에 등록하지 않는다.

원천은 IMF PortWatch 의 Daily_Chokepoints_Data 다. ArcGIS 피처서버라
열쇠가 필요 없다. 호르무즈는 portid=chokepoint6 이고 2019년 1월 1일부터
있다. 선박 수(n_total, n_tanker, n_cargo)와 화물 적재능력(capacity)을 준다.

주의할 점. 포트워치는 지난 날짜의 값을 뒤에 고친다. AIS 신호를 모아
처리하는 데 시간이 걸리기 때문이다. 팩트북에 들어 있던 값들은 옛 스냅샷
이어서 지금 값과 조금씩 달랐다(2019년 1월 월합 1,687척 대 현재 1,725척).
그래서 이 어댑터는 받을 때마다 과거 값까지 통째로 덮는다.

겹쳐 있던 차트를 정리했다. c0499 와 c2085 는 같은 자료였고(모양도 붕괴
시점도 같고 값만 스냅샷 시점 차이), c0498 과 c2087 은 S&P글로벌 출처로
적혀 있었지만 갱신할 길이 없었다. 네 장으로 줄이고 모두 포트워치 하나로
맞춘다.

  c0499  2026년 일별 선박 수(유조선과 그 밖의 선박)
  c2085  2026년 일별 물동량(화물 적재능력)
  c2086  월별 선박 수(2019년~)
  c2234  일별 유조선 수(2019년~)
  c0498  내림 — c0499 에 유조선 구분이 들어가 겹친다
  c2087  내림 — c0499 와 같은 자료다
"""
import argparse, collections, datetime, json, os, subprocess, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))

API = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
       "Daily_Chokepoints_Data/FeatureServer/0/query")
PAGE = "https://portwatch.imf.org/"
CHOKE = "chokepoint6"
YEAR = 2026                      # 일별 차트가 다루는 해
BLUE, RED, GRAY = "#2f5e8e", "#c0322f", "#aaaaaa"
DROP = {"c0498": "c0499 가 유조선과 그 밖의 선박을 나눠 담아 겹친다.",
        "c2087": "c0499 와 같은 자료다. 출처가 S&P글로벌로 적혀 있었지만 "
                 "값을 갱신할 길이 없었다."}


def fetch():
    rows, off = {}, 0
    while True:
        q = urllib.parse.urlencode({
            "where": f"portid='{CHOKE}'",
            "outFields": "date,n_total,n_tanker,n_cargo,capacity",
            "orderByFields": "date", "resultOffset": off,
            "resultRecordCount": 1000, "returnGeometry": "false", "f": "json"})
        r = subprocess.run(["curl", "-sS", "--max-time", "90", API + "?" + q],
                           capture_output=True)
        if r.returncode:
            raise SystemExit("내려받기 실패: " + r.stderr.decode()[:120])
        d = json.loads(r.stdout.decode("utf-8", "replace"))
        if d.get("error"):
            raise SystemExit("포트워치 오류: " + str(d["error"])[:160])
        fs = d.get("features") or []
        for f in fs:
            a = f["attributes"]
            dt = a["date"]
            if isinstance(dt, (int, float)):
                dt = datetime.datetime.utcfromtimestamp(dt / 1000).strftime("%Y-%m-%d")
            rows[dt] = a
        if len(fs) < 1000:
            return rows
        off += 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    H = fetch()
    ks = sorted(H)
    if len(ks) < 2000:
        raise SystemExit(f"받은 날이 {len(ks)}일뿐입니다 — 쓰지 않습니다.")
    first, last = ks[0], ks[-1]
    print(f"IMF 포트워치 호르무즈 {first} ~ {last} ({len(ks)}일)")

    # ── 검산 1. 전체는 유조선과 그 밖의 선박의 합이어야 한다.
    bad = [(k, H[k]["n_total"], H[k]["n_tanker"], H[k]["n_cargo"]) for k in ks
           if H[k]["n_total"] != H[k]["n_tanker"] + H[k]["n_cargo"]]
    if bad:
        raise SystemExit(f"전체가 유조선+그 밖의 합과 어긋납니다: {bad[:5]}")
    # ── 검산 2. 날짜가 하루도 빠지지 않아야 한다.
    d0 = datetime.date.fromisoformat(first)
    d1 = datetime.date.fromisoformat(last)
    miss = [(d0 + datetime.timedelta(days=i)).isoformat()
            for i in range((d1 - d0).days + 1)
            if (d0 + datetime.timedelta(days=i)).isoformat() not in H]
    if miss:
        raise SystemExit(f"빠진 날이 {len(miss)}일 있습니다: {miss[:5]}")
    print(f"  검산: 전체=유조선+그 밖의 선박, 날짜 빠짐 없음 ({len(ks)}일 모두)")

    yk = [k for k in ks if k.startswith(str(YEAR))]
    if not yk:
        raise SystemExit(f"{YEAR}년 자료가 없습니다.")
    base_years = [y for y in range(2019, YEAR)]
    import statistics
    norm = statistics.fmean(H[k]["n_total"] for k in ks
                            if int(k[:4]) in base_years)
    cur = statistics.fmean(H[k]["n_total"] for k in yk)
    print(f"  {YEAR}년 하루 평균 {cur:.1f}척, {base_years[0]}~{base_years[-1]}년 평균 "
          f"{norm:.1f}척 ({cur / norm * 100:.0f}%)")

    # 붕괴가 시작된 날: 처음으로 사흘 내리 평년의 30% 밑으로 내려간 날
    cut = None
    for i in range(len(yk) - 2):
        if all(H[yk[i + j]]["n_total"] < norm * 0.3 for j in range(3)):
            cut = yk[i]
            break
    print(f"  통행이 끊긴 날: {cut}")

    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    SRC = f"IMF 포트워치(PortWatch) 일별 요충지 통행 자료. {first}~{last}."
    REV = ("포트워치는 선박 자동식별장치(AIS) 신호를 모아 집계하므로 지난 "
           "날짜의 값을 뒤에 고칩니다. 이 차트는 받을 때마다 과거 값까지 "
           "다시 덮습니다. 예전에 받아 둔 값과 몇 척씩 다를 수 있습니다.")
    CALL = ("통과한 선박이 아니라 '해협 반경 안에 들어온 선박' 을 센 값입니다. "
            "포트워치는 요충지마다 정해 둔 구역에 들어온 배를 하루 단위로 "
            "셉니다. 되돌아 나간 배도 들어갑니다.")

    # 전쟁 뒤 수치를 '실제 통항' 으로 읽으면 크게 틀린다. 적재능력을 배럴로
    # 바꿔 보면 평년에는 알려진 통과량과 맞는데 전쟁 뒤에는 20분의 1 로
    # 떨어진다. 배가 사라진 게 아니라 AIS 신호가 꺼진 것이다.
    BBL_T = 0.136                       # 원유 1배럴 ≈ 0.136톤
    cap_norm = statistics.fmean(H[k]["capacity"] for k in ks
                                if int(k[:4]) in base_years)
    sep = [k for k in ks if k.startswith("2026-09")]
    cap_sep = statistics.fmean(H[k]["capacity"] for k in sep) if sep else 0
    DARK = ("이 숫자를 '실제로 지난 배' 로 읽으면 안 됩니다. 포트워치는 선박 "
            "자동식별장치(AIS) 신호로 셉니다. 전쟁 구역에서는 배가 신호를 끄고 "
            "다니기 때문에 집계에서 빠집니다. 2026년 3월 이후 수치에는 통항이 "
            "줄어든 몫과 신호를 끈 몫이 섞여 있고, 둘을 이 자료만으로는 "
            "가를 수 없습니다.")
    GAP = (f"얼마나 어긋나는지 가늠할 수 있습니다. 평년에는 이 방식이 잘 "
           f"맞았습니다. {base_years[0]}~{base_years[-1]}년 하루 적재능력 "
           f"{cap_norm / 1e4:,.0f}만 톤을 배럴로 바꾸면 하루 "
           f"{cap_norm / BBL_T / 1e4:,.0f}만 배럴로, 호르무즈 통과량으로 알려진 "
           "하루 2,000만 배럴 안팎과 들어맞습니다. 적재능력은 실제 실은 화물보다 "
           "크니 조금 높게 나오는 것이 맞습니다. "
           + (f"그런데 전쟁 뒤에는 어긋납니다. 뉴욕타임스가 전한 선박 추적업체 "
              f"케이플러 집계로는 2026년 9월에도 하루 1,000만 배럴이 해협을 "
              f"지났는데, 같은 달 포트워치 적재능력을 배럴로 바꾸면 하루 "
              f"{cap_sep / BBL_T / 1e4:,.0f}만 배럴입니다. 기사 수치의 "
              f"{cap_sep / BBL_T / 1e4 / 1000 * 100:.0f}% 수준입니다. 차이의 "
              "상당 부분은 꺼진 AIS 로 보입니다." if sep else ""))

    ov = json.load(open(os.path.join(DATA, "overrides.json"), encoding="utf-8"))
    out = {}

    # ── c0499 2026년 일별, 유조선과 그 밖의 선박
    out["c0499"] = {
        "id": "c0499", "title": f"호르무즈 해협 통과 선박 수({YEAR}년 일별)",
        "vizType": "stacked_bar", "unit": "척", "labels": yk,
        "series": [[H[k]["n_tanker"] for k in yk], [H[k]["n_cargo"] for k in yk]],
        "seriesNames": ["유조선", "그 밖의 선박"],
        "seriesColors": [RED, GRAY],
        "source": SRC + " 단위: 척.", "sourceUrl": PAGE,
        "notes": [
            DARK, GAP,
            f"{YEAR}년 하루 평균 {cur:.0f}척입니다. 2019년부터 "
            f"{base_years[-1]}년까지 평균이 {norm:.0f}척이었으니 "
            f"{cur / norm * 100:.0f}% 수준입니다. 가장 최근인 {last}에는 "
            f"{H[last]['n_total']}척이 지났습니다.",
            (f"{cut.replace('-', '년 ', 1).replace('-', '월 ')}일부터 통행이 "
             "사실상 끊겼습니다. 그 전까지는 평년과 다르지 않았습니다. 하루 "
             "단위로 끊긴 것이지 서서히 줄어든 것이 아닙니다.") if cut else "",
            "유조선을 따로 갈라 두었습니다. 호르무즈는 원유와 액화천연가스가 "
            "지나는 길목이라 유조선이 멈췄는지가 핵심입니다.",
            CALL, REV,
            "세로축을 0부터 그립니다. 평년과 지금의 격차가 워낙 커서 축을 "
            "끊을 이유가 없습니다.",
        ],
        "updated": now,
    }

    # ── c2085 2026년 일별 물동량
    cap = [round(H[k]["capacity"] / 10000, 1) for k in yk]
    capn = statistics.fmean(H[k]["capacity"] for k in ks if int(k[:4]) in base_years)
    capc = statistics.fmean(H[k]["capacity"] for k in yk)
    out["c2085"] = {
        "id": "c2085", "title": f"호르무즈 해협 물동량({YEAR}년 일별)",
        "vizType": "column", "unit": "만 톤", "labels": yk,
        "series": [cap], "seriesNames": ["하루 통과 화물 적재능력"],
        "seriesColors": [BLUE],
        "source": SRC + " 통과 선박의 화물 적재능력 합계. 단위: 만 톤.",
        "sourceUrl": PAGE,
        "notes": [
            DARK, GAP,
            f"{YEAR}년 하루 평균 {capc / 10000:.0f}만 톤입니다. 2019년부터 "
            f"{base_years[-1]}년까지 평균 {capn / 10000:.0f}만 톤의 "
            f"{capc / capn * 100:.0f}% 입니다.",
            "실제로 실은 화물이 아니라 그날 지나간 배들의 적재능력을 더한 "
            "값입니다. 배가 비어서 지나가도 적재능력은 그대로 잡힙니다. 그래서 "
            "물동량의 상한에 가깝습니다.",
            "선박 수보다 이쪽이 경제적 충격에 가깝습니다. 큰 배 한 척이 작은 "
            "배 여러 척보다 많이 나릅니다.",
            CALL, REV,
        ],
        "updated": now,
    }

    # ── c2086 월별 (끝난 달까지)
    M = collections.OrderedDict()
    cnt = collections.Counter()
    for k in ks:
        M[k[:7]] = M.get(k[:7], 0) + H[k]["n_total"]
        cnt[k[:7]] += 1
    days = {m: (datetime.date(int(m[:4]), int(m[5:]), 28) + datetime.timedelta(days=4)).replace(day=1)
            for m in M}
    full = [m for m in M if cnt[m] == (days[m] - datetime.date(int(m[:4]), int(m[5:]), 1)).days]
    mlab = full
    out["c2086"] = {
        "id": "c2086", "title": "호르무즈 해협 통과 선박 수(월별)",
        "vizType": "column", "unit": "척", "labels": mlab,
        "series": [[M[m] for m in mlab]], "seriesNames": ["월 합계"],
        "seriesColors": [BLUE],
        "source": (f"IMF 포트워치 일별 자료를 달마다 더한 값. "
                   f"{mlab[0]}~{mlab[-1]}. 단위: 척."),
        "sourceUrl": PAGE,
        "notes": [
            DARK, GAP,
            f"{mlab[-1]}에 {M[mlab[-1]]:,}척입니다. 가장 많았던 달은 "
            + (lambda m: f"{m}의 {M[m]:,}척")(max(mlab, key=lambda m: M[m])) + "입니다.",
            "달이 끝나기 전에는 그달을 넣지 않습니다. 며칠치만 더한 값이 "
            "한 달로 보이면 추세가 꺾인 것처럼 읽힙니다.",
            "날수가 달마다 달라 2월이 늘 낮게 나옵니다. 달끼리 견줄 때 "
            "감안하십시오.",
            CALL, REV,
        ],
        "updated": now,
    }

    # ── c2234 일별 유조선(2019년~)
    out["c2234"] = {
        "id": "c2234", "title": "호르무즈 해협 통과 유조선 수(2019년~)",
        "vizType": "line", "unit": "척", "labels": ks,
        "series": [[H[k]["n_tanker"] for k in ks]], "seriesNames": ["유조선"],
        "seriesColors": [RED],
        "source": SRC + " 유조선만. 단위: 척.", "sourceUrl": PAGE,
        "notes": [
            DARK, GAP,
            f"2019년부터 {last}까지 {len(ks):,}일입니다. 하루 유조선은 "
            f"{base_years[0]}~{base_years[-1]}년 평균 "
            f"{statistics.fmean(H[k]['n_tanker'] for k in ks if int(k[:4]) in base_years):.0f}척"
            f"이었고 {YEAR}년은 "
            f"{statistics.fmean(H[k]['n_tanker'] for k in yk):.0f}척입니다.",
            "날마다 크게 오르내립니다. 주말과 공휴일에 적고, 기상에 따라서도 "
            "달라집니다. 하루 값보다 흐름을 보십시오.",
            CALL, REV,
        ],
        "updated": now,
    }

    for cid, o in out.items():
        o["notes"] = [n for n in o["notes"] if n]
        lab = o["labels"]
        print(f"  {cid} {o['title'][:30]:32s} {o['vizType']:12s} {len(lab):5d}점 "
              f"{lab[0]}~{lab[-1]}")
    for cid, why in DROP.items():
        print(f"  {cid} 내림 — {why[:50]}")

    if not a.apply:
        print("\n  (--apply 를 붙이면 data/overrides.json 에 씁니다)")
        return 0
    for cid, o in out.items():
        ov.setdefault(cid, {}).update(o)
        ov[cid].pop("drop", None)
        ov[cid].pop("dropNote", None)
    for cid, why in DROP.items():
        ov.setdefault(cid, {})["id"] = cid
        ov[cid]["drop"] = True
        ov[cid]["dropNote"] = why
    p = os.path.join(DATA, "overrides.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(ov, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("-> data/overrides.json 에 반영했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
