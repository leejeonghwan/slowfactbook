#!/usr/bin/env bash
# 한 방 업데이트: 키노트를 PowerPoint로 내보내 source/ 에 덮어쓴 뒤 이 스크립트 실행.
#   ./update.sh
# 추출 → 사이트/임베드 재생성 → 변경분 커밋 → push (GitHub Actions가 자동 배포)
set -e
cd "$(dirname "$0")"

# ─────────────────────────────────────────────────────────────
# slownews.net/factbook/ 미러 배포
#   GitHub Pages 는 푸시하면 자동 배포되지만 slownews 쪽은 EC2 에 직접 올려야
#   한다. 둘이 따로 가면 "고쳤는데 안 바뀐다"가 반복되므로 여기서 같이 처리한다.
#   .env 에 아래를 넣어두면 자동으로 돈다 (없으면 조용히 건너뛴다).
#     SLOWNEWS_HOST=ubuntu@ec2-15-165-13-179.ap-northeast-2.compute.amazonaws.com
#     SLOWNEWS_KEY=$HOME/.ssh/slowkey
#     SLOWNEWS_PATH=/var/www/.../factbook       # 서버의 factbook 디렉터리
#   쓰기:  ./update.sh                (수집 → 빌드 → 커밋 → 배포)
#          ./update.sh --deploy-only  (이미 빌드된 site/ 만 다시 올린다)
#          ./update.sh --no-deploy    (배포 건너뛰기)
# ─────────────────────────────────────────────────────────────
deploy_slownews() {
  if [ "$NO_DEPLOY" = "1" ]; then
    echo "▶ slownews 배포 건너뜀 (--no-deploy)"
    return 0
  fi
  if [ -z "$SLOWNEWS_HOST" ] || [ -z "$SLOWNEWS_PATH" ]; then
    echo "▶ slownews 배포 설정 없음 — .env 에 SLOWNEWS_HOST / SLOWNEWS_PATH / SLOWNEWS_KEY 를 넣으면 자동으로 올립니다."
    return 0
  fi
  key_opt=""
  [ -n "$SLOWNEWS_KEY" ] && key_opt="-i $SLOWNEWS_KEY"
  echo "▶ slownews 배포: site/ → $SLOWNEWS_HOST:$SLOWNEWS_PATH"
  # --delete 는 기본으로 쓰지 않는다. 경로를 잘못 넣었을 때 웹 루트를 비우는 사고를 막는다.
  # 서버에서 사라진 차트까지 정리하려면 SLOWNEWS_DELETE=1 로 한 번만 돌린다.
  del=""
  [ "$SLOWNEWS_DELETE" = "1" ] && del="--delete"
  # macOS 기본 rsync 는 2.6.9 라 --info 계열 옵션이 없다. --stats 로 간다.
  rsync -az --stats $del \
        -e "ssh $key_opt -o StrictHostKeyChecking=accept-new" \
        site/ "$SLOWNEWS_HOST:$SLOWNEWS_PATH/"
  echo "✅ slownews 배포 완료 — https://slownews.net/factbook/"
}

NO_DEPLOY=0
case "$1" in
  --deploy-only)
    [ -f .env ] && set -a && . ./.env && set +a
    if [ ! -f site/index.html ]; then
      echo "site/ 가 없습니다. 먼저 python3 scripts/build.py 를 돌리세요."
      exit 1
    fi
    deploy_slownews
    exit 0 ;;
  --no-deploy) NO_DEPLOY=1 ;;
esac


# KOSIS 수집을 여기(국내)서 한다. GitHub 빌드 서버(해외)는 KOSIS OpenAPI 가 자주 응답하지 않는다.
# 키는 .env 파일(KOSIS_API_KEY=…) 또는 환경변수. 없으면 이 단계는 건너뛴다.
[ -f .env ] && set -a && . ./.env && set +a
if [ -n "$KOSIS_API_KEY" ]; then
  echo "▶ KOSIS 수집 (API 트랙 + 확정 매칭 갱신)…"
  python3 scripts/build_api_charts.py || echo "  API 트랙 수집 실패 — 직전 성공본 유지"
  python3 scripts/refresh_charts.py --apply || echo "  확정 매칭 갱신 실패"
  python3 scripts/term_charts.py --apply || echo "  정권별 비교 차트 갱신 실패"
else
  echo "▶ KOSIS_API_KEY 없음 — 수집은 GitHub 빌드에 맡김 (.env 에 넣으면 여기서 받는다)"
fi

echo "▶ 여론조사 지지율 (리얼미터 주간집계)…"
python3 scripts/poll_charts.py realmeter --apply || echo "  리얼미터 갱신 실패/보류 — 기존 값 유지"

echo "▶ 석유류 가격 (오피넷)…"
python3 scripts/opinet_update.py --apply || echo "  오피넷 갱신 실패/보류 — 기존 값 유지"

echo "▶ 지수·시세 (야후 파이낸스)…"
python3 scripts/market_update.py --apply || echo "  시세 갱신 실패/보류 — 기존 값 유지"

echo "▶ 빌드 (추출 + 사이트 생성)…"
python3 scripts/build.py

echo "▶ 변경된 데이터:"
git --no-pager diff --stat data/ || true

git add -A
if git diff --cached --quiet; then
  echo "커밋할 변경 없음 — 깃은 건너뛴다."
else
  git commit -m "데이터 업데이트 $(date '+%Y-%m-%d %H:%M')"
  git pull --rebase --quiet   # 매일 새벽 자동 갱신 커밋(봇)이 먼저 올라가 있을 수 있다
  git push
  echo "✅ push 완료. 1~2분 뒤 GitHub Pages 와 모든 임베드가 자동 갱신됩니다."
fi

deploy_slownews
