#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KRX 오픈API 가 열렸는지 확인한다.

KRX 는 인증키를 받는 것과 개별 API 를 쓰는 것이 따로다. 키를 발급받아도
서비스마다 '활용신청'을 해서 승인이 나야 호출이 된다. 둘을 응답으로 가를 수 있다.

  "Unauthorized Key"       → 키 자체가 안 먹는다(오타·만료).
  "Unauthorized API Call"  → 키는 멀쩡한데 그 서비스를 신청하지 않았다.
  OUT_BLOCK 이 들어오면     → 쓸 수 있다.

키는 .env 의 KRX_API_KEY 에서 읽는다.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://data-dbg.krx.co.kr/svc/apis"

# 팩트북에 필요한 것들. 이름은 KRX 포털의 서비스 이름 그대로다.
APIS = [
    # 지수 — 코스피·코스닥 지수 차트(c2206~c2211)를 야후 대신 KRX 로 채울 수 있다.
    ("idx/kospi_dd_trd",      "KOSPI 시리즈 일별시세정보", "코스피 지수", True),
    ("idx/kosdaq_dd_trd",     "KOSDAQ 시리즈 일별시세정보", "코스닥 지수", True),
    ("idx/krx_dd_trd",        "KRX 시리즈 일별시세정보",   "KRX 통합 지수", False),
    # 주식 — 시가총액 차트(c1083·c1086)에 필요한 것.
    ("sto/stk_bydd_trd",      "유가증권 일별매매정보",     "시가총액·종가·상장주식수", True),
    ("sto/ksq_bydd_trd",      "코스닥 일별매매정보",       "코스닥 종목 시가총액", False),
    ("sto/stk_isu_base_info", "유가증권 종목기본정보",     "종목 코드 대조", False),
]


def key():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if ln.startswith("KRX_API_KEY="):
                return ln.split("=", 1)[1].strip()
    return os.environ.get("KRX_API_KEY", "")


def main():
    k = key()
    if not k:
        print(".env 에 KRX_API_KEY 가 없습니다."); return 1
    day = sys.argv[1] if len(sys.argv) > 1 else "20261008"
    print(f"기준일 {day} · 키 …{k[-4:]}\n")
    ok = 0
    for path, name, what, need in APIS:
        r = subprocess.run(["curl", "-sSL", "--max-time", "30",
                            "-H", f"AUTH_KEY: {k}", f"{BASE}/{path}?basDd={day}"],
                           capture_output=True, text=True, timeout=60).stdout
        try:
            d = json.loads(r)
        except Exception:
            print(f"  ? {name:26s} 응답을 읽지 못했습니다: {r[:60]}"); continue
        msg = d.get("respMsg")
        if msg is None:
            rows = next((v for v in d.values() if isinstance(v, list)), [])
            print(f"  ✓ {name:26s} {len(rows)}건 — {what}")
            if rows:
                print(f"      컬럼: {', '.join(list(rows[0])[:10])}")
            ok += 1
        elif "Key" in str(msg):
            print(f"  ✗ {name:26s} 키가 안 먹습니다 ({msg})")
        else:
            print(f"  {'!' if need else '·'} {name:26s} 활용신청이 필요합니다"
                  + ("  ← 꼭 필요" if need else "  (있으면 좋음)"))
    print(f"\n쓸 수 있는 서비스 {ok}/{len(APIS)}")
    if not ok:
        print("KRX 오픈API 포털(http://openapi.krx.co.kr)에서 위 서비스마다 '활용신청'을 누르세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
