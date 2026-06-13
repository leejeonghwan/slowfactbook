#!/usr/bin/env bash
# 한 방 업데이트: 키노트를 PowerPoint로 내보내 source/ 에 덮어쓴 뒤 이 스크립트 실행.
#   ./update.sh
# 추출 → 사이트/임베드 재생성 → 변경분 커밋 → push (GitHub Actions가 자동 배포)
set -e
cd "$(dirname "$0")"

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
git push
echo "✅ push 완료. 1~2분 뒤 사이트와 모든 임베드가 자동 갱신됩니다."
