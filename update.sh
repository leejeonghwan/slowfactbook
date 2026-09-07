#!/usr/bin/env bash
# 한 방 업데이트: 키노트를 PowerPoint로 내보내 source/ 에 덮어쓴 뒤 이 스크립트 실행.
#   ./update.sh
# 추출 → 사이트/임베드 재생성 → 변경분 커밋 → push (GitHub Actions가 자동 배포)
set -e
cd "$(dirname "$0")"

# KOSIS 수집을 여기(국내)서 한다. GitHub 빌드 서버(해외)는 KOSIS OpenAPI 가 자주 응답하지 않는다.
# 키는 .env 파일(KOSIS_API_KEY=…) 또는 환경변수. 없으면 이 단계는 건너뛴다.
[ -f .env ] && set -a && . ./.env && set +a
if [ -n "$KOSIS_API_KEY" ]; then
  echo "▶ KOSIS 수집 (API 트랙 + 확정 매칭 갱신)…"
  python3 scripts/build_api_charts.py || echo "  API 트랙 수집 실패 — 직전 성공본 유지"
  python3 scripts/refresh_charts.py --apply || echo "  확정 매칭 갱신 실패"
else
  echo "▶ KOSIS_API_KEY 없음 — 수집은 GitHub 빌드에 맡김 (.env 에 넣으면 여기서 받는다)"
fi

echo "▶ 빌드 (추출 + 사이트 생성)…"
python3 scripts/build.py

echo "▶ 변경된 데이터:"
git --no-pager diff --stat data/ || true

git add -A
if git diff --cached --quiet; then
  echo "변경 사항 없음. 종료."
  exit 0
fi
git commit -m "데이터 업데이트 $(date '+%Y-%m-%d %H:%M')"
git pull --rebase --quiet   # 매일 새벽 자동 갱신 커밋(봇)이 먼저 올라가 있을 수 있다
git push
echo "✅ push 완료. 1~2분 뒤 사이트와 모든 임베드가 자동 갱신됩니다."
