#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""고용센터 구인 구직 현황(c0051). 연간 총계로 검산하고 빠진 달을 되돌린다.

  python3 scripts/jobcenter_vacancy.py            # 미리보기
  python3 scripts/jobcenter_vacancy.py --apply

월별 고용센터 신규구인인원과 신규구직건수는 공개 API 가 없다. 국가데이터처
포털에 표가 없고, 고용노동부 통계포털은 막혀 있다. e-나라지표는 연간만 준다.

고용노동부가 매달 내는 「고용행정통계로 본 노동시장 동향」 의 '신규구인' 과
'신규구직' 은 쓰면 안 된다. 기준이 더 넓다. 2025년 10월을 보면 보도자료는
구인 14만 2천명인데 고용센터 기준은 9만 4,236명이다. 1.5배 차이다. 이어
붙이면 한 차트 안에서 기준이 갈린다. c0016 이 바로 그렇게 망가졌다.

그래서 이 어댑터는 자료를 새로 받아오지 않는다. 대신

  1 e-나라지표의 연간 총계와 차트의 월별 합계를 해마다 대조한다. 사람 수까지
    맞아야 하고, 어긋나면 쓰지 않고 멈춘다. 기준이 섞이면 여기서 걸린다.
  2 마지막 해에 열한 달만 있으면 연간 총계에서 그 열한 달을 빼 남은 한 달을
    되돌린다. 두 수가 모두 검산을 통과한 값이므로 뺄셈 결과도 정확하다.

e-나라지표는 최근 다섯 해만 보여주므로 검산도 그 다섯 해에 걸린다.
"""
import argparse, datetime, json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
KST = datetime.timezone(datetime.timedelta(hours=9))
IDX = ("https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do"
       "?stts_cd=150501&idx_cd=1505&freq=Y&period=N")
IDX_PAGE = ("https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=1505")


def fetch_annual():
    r = subprocess.run(["curl", "-sS", "--max-time", "90", "-A", "Mozilla/5.0", IDX],
                       capture_output=True)
    if r.returncode:
        raise SystemExit("e-나라지표 내려받기 실패: " + r.stderr.decode()[:120])
    s = r.stdout.decode("utf-8", "replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    i = t.find("고용센터 구인/구직 및 취업현황")
    if i < 0:
        raise SystemExit("e-나라지표 표를 못 찾았습니다. 서식이 바뀐 것 같습니다.")
    seg = t[i:i + 1200]
    ys = [int(x) for x in re.findall(r"\b(20\d\d)\b", seg[:200])]

    def row(name):
        m = re.search(name + r"((?:\s+[\d,]+){%d})" % len(ys), seg)
        if not m:
            raise SystemExit(f"'{name}' 줄을 못 찾았습니다.")
        return [int(x.replace(",", "")) for x in m.group(1).split()]

    hire, seek = row("구인"), row("구직")
    if not (len(ys) == len(hire) == len(seek)) or len(ys) < 3:
        raise SystemExit(f"연도 {len(ys)}개와 값 개수가 안 맞습니다.")
    return dict(zip(ys, zip(hire, seek)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ann = fetch_annual()
    print("  e-나라지표 연간:", ", ".join(
        f"{y} 구인 {v[0]:,} 구직 {v[1]:,}" for y, v in sorted(ann.items())))

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
    c = {**base.get("c0051", {}), **(ov.get("c0051") or {})}
    L = [str(x) for x in c["labels"]]
    S = [list(x) for x in c["series"]]
    if c.get("seriesNames") != ["구인", "구직"]:
        raise SystemExit(f"계열 이름이 바뀌었습니다: {c.get('seriesNames')}")

    # 1 연간 총계 대조
    partial = None
    for y, (h, k) in sorted(ann.items()):
        idx = [i for i, lb in enumerate(L) if lb.startswith(f"{y}-")]
        got = [round(sum(S[j][i] for i in idx) * 1e4) for j in (0, 1)]
        if len(idx) == 12:
            if got != [h, k]:
                raise SystemExit(f"{y}년 월별 합계 {got} 가 연간 총계 [{h}, {k}] 와 "
                                 f"어긋납니다. 기준이 섞였을 수 있어 쓰지 않습니다.")
            print(f"    검산 {y}년: 12달 합계가 연간 총계와 일치")
        elif len(idx) == 11:
            partial = (y, idx, got, h, k)
            print(f"    {y}년: 11달뿐입니다. 연간 총계에서 되돌릴 수 있습니다.")
        else:
            print(f"    {y}년: {len(idx)}달뿐이라 넘어갑니다.")

    added = None
    if partial:
        y, idx, got, h, k = partial
        have = {L[i][5:7] for i in idx}
        miss = sorted({f"{m:02d}" for m in range(1, 13)} - have)
        if len(miss) != 1:
            raise SystemExit(f"{y}년에 빠진 달이 {miss} 입니다. 하나일 때만 되돌립니다.")
        vh, vk = (h - got[0]) / 1e4, (k - got[1]) / 1e4
        lo, hi = min(S[0][i] for i in idx), max(S[0][i] for i in idx)
        lo2, hi2 = min(S[1][i] for i in idx), max(S[1][i] for i in idx)
        if not (lo * 0.6 <= vh <= hi * 1.4 and lo2 * 0.6 <= vk <= hi2 * 1.4):
            raise SystemExit(f"되돌린 값 구인 {vh:.4f} 구직 {vk:.4f} 가 그 해 "
                             f"범위(구인 {lo:.2f}~{hi:.2f}, 구직 {lo2:.2f}~{hi2:.2f})를 "
                             f"벗어납니다. 쓰지 않습니다.")
        lab = f"{y}-{miss[0]}"
        if lab in L:
            raise SystemExit(f"{lab} 이 이미 있습니다.")
        if lab < L[-1]:
            raise SystemExit(f"{lab} 이 마지막 라벨 {L[-1]} 보다 앞입니다. 손으로 봐야 합니다.")
        L.append(lab)
        S[0].append(round(vh, 4))
        S[1].append(round(vk, 4))
        added = (lab, round(vh, 4), round(vk, 4))
        print(f"    되돌림 {lab}: 구인 {vh:.4f}만 명, 구직 {vk:.4f}만 명")

    if not added:
        print("  새로 더할 달이 없습니다.")

    ymd = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    out = {
        "c0051": {
            "id": "c0051", "labels": L, "series": S,
            "seriesNames": ["구인", "구직"],
            "seriesColors": ["#2a5ca8", "#c0322f"],
            "unit": "만 명",
            "source": (f"고용노동부 고용센터 구인/구직 및 취업현황(워크넷, 고용정보통합"
                       f"분석시스템). {L[0]}~{L[-1]}. 월별 신규구인인원과 신규구직건수. "
                       f"단위: 만 명."),
            "sourceUrl": IDX_PAGE,
            "notes": [
                f"{L[-1].replace('-', '년 ')}월 구인 {S[0][-1]:.2f}만 명, 구직 "
                f"{S[1][-1]:.2f}만 명입니다. 구직자 한 명당 일자리 수는 "
                f"{S[0][-1] / S[1][-1]:.2f}개입니다.",
                "고용센터에 들어온 신규 구인인원과 신규 구직건수입니다. 나라 전체의 "
                "일자리와 구직자가 아닙니다. 공공 고용서비스를 거친 몫만 잡힙니다. "
                "민간 구인 플랫폼으로 옮겨 가면 구인이 줄어든 것처럼 보일 수 "
                "있습니다.",
                "구인은 사람 수이고 구직은 건수입니다. 한 사람이 여러 번 신청하면 "
                "여러 건으로 잡힙니다. 둘을 그대로 나눈 값이 구인배수인데, 이 때문에 "
                "'구직자 한 명당 일자리' 라는 말과는 정확히 같지 않습니다.",
                "고용노동부가 매달 내는 「고용행정통계로 본 노동시장 동향」 의 "
                "'신규구인' 과 '신규구직' 은 이 차트와 기준이 다릅니다. 보도자료는 "
                "고용센터보다 넓은 범위를 셉니다. 2025년 10월을 보면 보도자료는 구인 "
                "14만 2천명인데 고용센터 기준은 9만 4,236명입니다. 섞어 읽으면 "
                "안 됩니다.",
                "월별 자료는 공개 API 가 없습니다. 국가데이터처 포털에 표가 없고 "
                "e-나라지표는 연간만 줍니다. 그래서 자동 갱신이 되지 않습니다. 대신 "
                "해마다 e-나라지표의 연간 총계와 월별 합계가 사람 수까지 맞는지 "
                "대조하고, 한 해에 한 달만 빠져 있으면 총계에서 빼서 되돌립니다.",
            ],
            "updated": ymd,
        },
        "c0016": {
            "id": "c0016", "drop": True,
            "dropNote": ("c0051 과 같은 차트입니다. 2025년 10월에 고용노동부 월간 "
                         "보도자료의 값(구인 14만 2천명)을 끼워 넣어 기준이 갈렸습니다. "
                         "고용센터 기준은 같은 달 9만 4,236명입니다. c0051 을 보세요."),
            "updated": ymd,
        },
    }
    print(f"\n  c0051 {len(L)}달 {L[0]}~{L[-1]}")
    print(f"  c0016 중복이라 내립니다.")
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
