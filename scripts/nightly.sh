#!/usr/bin/env bash
# 자동 갱신. launchd 가 하루 한 번 부른다.
#
#   수집 어댑터 → 빌드 → data/ 만 커밋 → push → slownews 배포
#
# 손으로 돌리는 ./update.sh 와 다른 점이 둘이다.
#   1) git add 를 data/ 로 좁힌다. 손대는 중인 스크립트나 다른 작업 폴더가
#      한밤중에 통째로 딸려 올라가지 않게 한다.
#   2) 모든 출력을 logs/ 에 남긴다. 아침에 무엇이 바뀌었는지 볼 수 있다.
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

# launchd 는 로그인 셸이 아니라 PATH 가 거의 비어 있다.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p logs
LOG="logs/nightly-$(date '+%Y%m%d').log"
exec >>"$LOG" 2>&1
echo "════════ $(date '+%Y-%m-%d %H:%M:%S %Z') 자동 갱신 시작"

[ -f .env ] && set -a && . ./.env && set +a

run() {                     # 하나가 엎어져도 나머지는 돈다
  echo "──── $1"
  shift
  "$@" || echo "   (실패 — 기존 값 유지)"
}

run "한국갤럽"            python3 scripts/gallup_update.py --apply
run "한국갤럽 주간"       python3 scripts/gallup_weekly.py --apply
run "리얼미터 주간"       python3 scripts/realmeter_weekly.py --apply
run "전력거래소"          python3 scripts/epsis_update.py --apply
run "오피넷 기름값"       python3 scripts/opinet_update.py --apply
run "공항 여객"           python3 scripts/airport_update.py --apply
run "미국 고용(BLS)"      python3 scripts/bls_update.py --apply
run "KOSIS API 트랙"      python3 scripts/build_api_charts.py
run "KOSIS 차트 갱신"     python3 scripts/refresh_api.py
run "KB부동산"            python3 scripts/kbapi_update.py --apply
run "한국거래소"          python3 scripts/krx_update.py --apply
run "한국은행 ECOS"       python3 scripts/ecos_update.py --apply
run "반도체 수출 비중"    python3 scripts/semi_share.py --apply
run "IMF WEO"             python3 scripts/imf_update.py --apply
run "BIS 총신용"          python3 scripts/bis_update.py --apply
run "한국공항공사"        python3 scripts/kac_update.py --apply
run "인터넷트렌드"        python3 scripts/ittrend_update.py --apply
run "역대 정부 누적 물가" python3 scripts/admin_cpi.py --apply
run "FRED"                python3 scripts/fred_update.py --apply
run "지수·시세"           python3 scripts/market_update.py --apply

echo "──── 빌드"
python3 scripts/build.py || { echo "빌드 실패 — 여기서 멈춘다"; exit 1; }

echo "──── 커밋"
git add data/
if git diff --cached --quiet; then
  echo "바뀐 데이터 없음 — 커밋도 배포도 건너뛴다."
  echo "════════ $(date '+%H:%M:%S') 끝"
  exit 0
fi
git commit -q -m "자동 데이터 갱신 $(date '+%Y-%m-%d')"
git pull --rebase --quiet && git push --quiet && echo "push 완료"

echo "──── 배포"
./update.sh --deploy-only

# 로그는 30일치만 둔다
find logs -name 'nightly-*.log' -mtime +30 -delete 2>/dev/null

echo "════════ $(date '+%H:%M:%S') 끝"
