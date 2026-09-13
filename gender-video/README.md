# 격차의 구조 — 데이터 설명 영상

기초 기사: https://slownews.kr/156679

- 1920 × 1080, 16:9, 30 fps, H.264 / AAC
- 약 2분 42초, 한국어 합성 내레이션(macOS Yuna), 화면 자막
- 플랫 도형과 실제 수치 기반 차트. 음원·자료화면을 사용하지 않음.
- `gender-gap-explained.mp4`: 완성 영상
- `captions.srt`: 별도 자막 파일 (장면 내 문장 길이 비례 타이밍, 단어 단위 강제 정렬은 아님)
- `narration.md`: 내레이션 대본
- `scenes.json`: 장면별 제목, 설명, 출처와 대본
- `render.py`: 영상 수정·재생성용 소스
- `storyboard.jpg`: 9개 장면 미리보기
- `narration.wav`: 전체 내레이션 트랙

## 수치와 해석

- 2024 시급: 남성 28,734원, 여성 20,363원. 비율 70.9%, 격차 29.1%.
- 2025 시급: 남성 29,411원, 여성 21,164원. 격차 28.0%.
- 출처: https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?freq=Y&idx_cd=4215&period=N&stts_cd=421501
- 2024 월평균소득: 남성 442만원, 여성 289만원. 격차 34.6%.
- 출처: https://eiec.kdi.re.kr/policy/materialView.do?num=277139
- OECD 2023 전일제 중위임금 격차: 29.3%. 국내 평균 지표와 구분.
- 정의: https://www.oecd.org/en/data/indicators/gender-wage-gap.html
- 시간·고용형태·연령·출산 전후 자료: 상위 data/full.json의 49, 105, 225, 202번 차트. 원조사표 추가 대조가 필요한 항목은 화면에 표시.
- 분해 결과: 한국노동연구원 「성별 임금격차와 기업의 역할」 표 1-2, 본문 11쪽. 2023년 시간당 로그임금 격차 중 설명 53.1%, 미설명 46.9%. 미설명=차별로 해석하지 않음.
- 원문: https://www.kli.re.kr/pdfPreviewDownload?fileName=59133CADA438DF5F49258C3D00096155_3.pdf&fileNameOrg=성별+임금격차와+기업의+역할_web.pdf&filePath1=jsphome/DATA/pblctList/issue/59133CADA438DF5F49258C3D00096155

확인일 2026-09-11. 영상은 자료 스냅샷이며 자동 갱신되지 않습니다. 동영상은 로컬 산출물이며 외부에 업로드하지 않았습니다.

## 두 번째 버전.

`gender-gap-explained-v2.mp4`: 검정 배경(#000000), 텍스트 #fdad00. 일·돌봄·경력 일러스트를 추가했습니다. 자막은 문장 단위로 표시하고 마침표로 끝나도록 정리했습니다.

일러스트는 built-in ImageGen으로 생성했습니다. 원본: `assets/work-care-career.png`. 사용한 프롬프트: `assets/illustration-prompt.md`.

수정된 대본: `narration-v2.md`. 자막: `captions-v2.srt`. 장면 구성: `storyboard-v2.jpg`. 기존 첫 버전은 보존합니다.

## 무음 버전.

`gender-gap-silent.mp4`: 음성 트랙과 하단 내레이션 자막을 제거했습니다. 차트 제목·수치·주석·출처 및 일러스트는 유지했습니다. 1920×1080, 30fps, 161.8초. 재생성 소스는 `render-silent.py`입니다.
