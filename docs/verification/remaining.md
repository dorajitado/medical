# 현재 구현 통합·메뉴 UI 검증

2026-11-15~16. 기준 REQUIREMENTS v0.7, WBS 6~10. API 0.6.0. Docker 미사용. 사용자의 11월 16일 지시로 새 기능 확장을 멈추고 현재 구현 검증·좌측 메뉴 UI를 우선했다. 전문 정답/검토자는 아직 없으며 진료 성능 미검증 상태다.

## 구현과 검증 자료

| 대상 | 구현 | 확인한 내용 |
|---|---|---|
| REP-04/05, VAL-02 | report_parser.py, workflow.py, ReviewWorkspace.tsx | 한/영·Unicode 원문 범위, mm/cm/부피 단위·부정/의심/과거/추적 권고, 다중/모호 항목 확인 필요, 정정·추가·제외의 새 버전과 원문 보존 |
| CMP-01~05 | workflow.py, workflow_api.py, ReviewWorkspace.tsx | 같은 검사/시리즈·원본 해시의 모델별 완료 실행만 연결, 다대다 후보와 확인/거절, 입력/AI 집계 분리, 같은 검사 차이와 성장 구분, 사용자 판단/질문 재접속 보존, 실패/빈/미지원 구분 |
| OUT-01~03 | exports.py, workflow.py, ReviewWorkspace.tsx | 원문/AI/사용자 판단의 고정 스냅샷, 실행·추출·정정·연결·검토·출력 감사 기록, UTF-8 JSON, 로컬 맑은 고딕 한글 PDF·원본 위치/단위/버전·한계. 외부 이미지/마크업 삽입 차단 |
| NFR-02/03/06 | maintenance.py, maintenance_api.py, owned_process.py | loopback/Host/Origin/변경 헤더, 경로 이탈·해시 변경 거부, SQLite 일관 백업·무결성/FK·복원/롤백, 외부 원본·백업 보존, 삭제 전 확인, 잠긴 파일·삭제 중단 복구/확정 후 정리 재시도, 중단 문서 실패와 자식 프로세스 소유 |
| REP-06 | documents.py, ocr_worker.mjs, UtilityWorkspace.tsx | 원본/SHA·페이지 이미지·추출/전사 출처 분리, 실제 한글·영문 이미지 OCR와 PDF 내장 텍스트, 실패 원본 보존, 사용자 대조/수정·확인 전 저장 차단, 메뉴 이동/문서 저장 시 직접 입력 초안 보존 |
| AI-08 | monai_worker.py, extended_workflow.py, ExtendedWorkspace.tsx | 고정 MONAI RetinaNet 독립 GPU 실행, 원본 좌표로 탐지상자 복원, 점수 독립·악성 확률 아님, 박스 크기를 병변 장경/분할 부피로 사용하지 않음, 같은 원본 연결 후보/수동 확인·거절·버전 |
| CMP-06 부분 | extended_workflow.py, ExtendedWorkspace.tsx | 이전 촬영일·동일 환자/병변 사용자 확인, 수동 비공선 LPS 기준점의 강체 행렬/RMS, 정합 없거나 모델/측정법/수치가 불일치하면 계산 불가. 알려진 이동/장경 차이 시험 통과. 실제 이전 CT 영상에 정합을 적용·검토하는 전체 인수는 남음 |
| OUT-04 제한 구현 | editorial.py, ReviewWorkspace.tsx | 실제 Qwen CPU 실행, 사용자 확인 원문 인용만 입력, ID 순열만 허용하고 원문 문구를 서버에서 재구성, 누락/중복/추가/임의 문장 차단. 자유로운 문장 재작성·문체 품질 인수는 남음 |
| VAL-03/05 도구 | extended_workflow.py, extended_api.py | 판독소견을 영상 모델에 전달하지 않음; 원본 해시/제공된 환자 그룹의 분할 중복 방지, 평가 사례 준비/대장 내보내기, 전문가 입력 계수와 빈 분모 null, 임상 인수 미확정 유지. 실제 정답·검토자·표본/성능 목표 미확보 |
| AI-09/10 조건 조사 | extended_api.py, CLINICAL_EVALUATION.md | 폐색전·폐혈관/기도·심장방·추가 소견별 선행 조건/미연결 사유·출처. 일반 조영 CT를 CTPA나 미지원 소견 음성으로 취급하지 않음 |

`backend/test_workflow.py`, `backend/test_remaining.py`의 양성/부정 자료는 명시적 합성 fixture다. 운영 시작에서 import하지 않는다. 실제 모델 smoke는 공식 공개 예제로 분리하고 모델 정확도 지표로 집계하지 않았다. 실제 환자 자료를 테스트나 Git에 복사하지 않았다.

## 메뉴 UI — UI-02~05 / UI-N1~4

src/App.tsx에 좌측 11개 메뉴를 두고 선택한 작업만 노출한다. CT 열람과 AI 분석/3D도 별도 화면이다. 판독소견 입력·구조화, 후보 대조, 검토/출력, OCR, 독립 모델, 이전 CT, 평가, 백업을 한 페이지 아래로 이어 붙이지 않는다. PC 탐색은 고정, 모바일은 왼쪽 Drawer다. 문서 전체 높이는 뷰포트 안에서 유지하고 해당 작업 내용/보조 패널을 독립 스크롤한다.

메뉴 URL에는 허용된 UI 경로만 담는다. 검사 식별자나 문서를 브라우저 주소에 넣지 않는다. 검사/열린 시리즈·입력 초안·선택 후보/분석 버전은 메뉴 전환 시 보존하고 실제 검사/시리즈 전환 때에는 이전 결과를 해제한다. 키보드 Enter 메뉴·확대/복원, 선택 메뉴 aria-current, 390/1280/1920px 가로 넘침과 모바일 탐색을 검증했다. 초기 로딩 중 완료 실행이 없는 선택기는 비활성화한다.

실제 확인 파일: tests/remaining/navigation.spec.ts, workflow.spec.ts; tests/browser/workspace.spec.ts, z-viewer.spec.ts; tests/analysis 및 tests/findings. 화면 캡처는 Git 제외 `data/remaining-browser-results/menu-*.png`, `workflow-*.png`와 `data/qa-remaining/menu-viewer-1280.png`에 보존한다. UI-01의 최종 사용자 디자인 검토는 아직 완료로 표시하지 않는다.

## 실행 결과와 재현

- `python -m unittest discover -s backend -t . -v`: **65개 통과**. 로그 `data/qa-remaining/python-tests.txt`. 새 고정 의존성 가상환경에서도 65개 통과: `cold-python-tests.txt`, 설치/의존성 로그 `install-log.txt`.
- `npm run build`: 타입/프로덕션 빌드 통과. 로컬 3D와 본문 번들이 500 kB 경고를 내지만 빌드 실패가 아니다.
- Edge: 기본 4개, 메뉴/통합 6개, 실제 모델 3개, 합성 후보 2개 = **15개**. 실행 명령은 각 playwright.*.config.ts에 정의. 로그 `data/qa-remaining/browser-base.txt`, `browser-menu.txt`, `browser-real-models.txt`, `browser-findings.txt`.
- API/AI `pip check`: 통과. `setup_optional ocr/monai/llm`: 고정 파일·크기·SHA 검증 통과. API 새 가상환경 설치와 선택 런타임 재검증은 완료했으나 완전한 새 PC의 AI/영상 전체 재설치 인수는 남음.
- 한글 PDF: 2쪽 모두 Poppler PNG로 렌더링해 글자·줄바꿈·페이지 번호·마지막 내용 잘림을 시각 확인. `data/qa-remaining/summary-ko.pdf`, `summary-ko.png`, `summary-ko-page2.png`. 실제 이미지 OCR의 알려진 문구는 인식했으나 일부 불필요 문자도 발생했으며 정정 단계가 필요하다. OCR 정확도를 보장하지 않는다.

브라우저가 연결을 끊는 과정에서 Windows asyncio의 WinError 10054 로그가 관찰됐으나 요청 상태/데이터 회귀는 통과했다. 재시작/오류 상태를 정상으로 바꾸지 않는다.

## 자원 실측 — NFR-04 / NFR-07 부분

`python -m backend.qa_performance`: 별도 512×512×128, 1×1×2 mm **해석적 합성 CT 팬텀**. 실행 전에 한도(모델당 600초, 프로세스 트리 표본 RSS 32 GiB, torch CUDA reserved 9 GiB)를 `performance-criteria.json`에 기록했다. 네 모델 순차 실행, 자식 종료 후 CUDA 메모리 해제. OOM 실패 격리/재시도는 별도 단위 주입 시험으로 검증한다.

| 모델 | 전체 대기/처리 초 | worker 초 | CUDA peak allocated GiB | reserved GiB | 표본 트리 RSS GiB |
|---|---:|---:|---:|---:|---:|
| 해부학 | 32.78 | 26.27 | 2.68 | 3.75 | 4.07 |
| 결절 분할 | 61.70 | 53.99 | 4.10 | 4.26 | 4.70 |
| 흉수·심낭삼출 | 45.63 | 38.78 | 1.72 | 1.74 | 3.63 |
| MONAI 결절 탐지 | 33.72 | 26.75 | 1.51 | 1.70 | 6.87 |

모두 이 팬텀 한도 내 완료. RSS는 0.5초 표본이므로 순간 최대치 보장이 아니다. 근거 `data/qa-remaining/performance-results.json`. 소형 공개 예제 MONAI 결과는 4상자, worker 10.25초/allocated 약 0.89 GiB. Qwen 2개 합성 문장 순서 정리는 CPU worker 약 2.78초(모델 파일 검증 시간 별도). 근거 monai-smoke.json, llm-smoke.json.

팬텀/소형 예제는 대표 얇은 절편 전체 조영 흉부 CT나 임상 성능 평가를 대체하지 않는다. NFR-07의 대표 CT·뷰어 반응·허용 대기 기준의 최종 인수는 미완료다. 사용자 CT를 자동으로 분석하지 않았다.

## 보류와 릴리스 범위

현재는 기능 검토 버전이다. 미완료 P0: UI-01 최종 사용자 화면 검토, NFR-05 완전한 새 PC AI/영상 재설치, NFR-07 대표 실제 CT 성능 인수. P1의 이전 CT 전체 영상 정합/인수와 자유 문장 다듬기, 조건부 폐색전·추가 흉부 모듈·진료 적용 평가는 완료하지 않았다. 최초 R-01~12 목표를 축소해 100%로 만들지 않는다. 새 개발 확장은 사용자 지시에 따라 멈추고 메뉴 UI를 우선했다.

운영 반영 결과는 DAILY_PROGRESS.md의 마지막 확인과 `data/qa-remaining/production-before.json`, `production-after.json`으로 기록한다. 원본 목록/검사·인스턴스·소견 수를 비교하며 환자 원문/UID를 검증 문서에 복사하지 않는다.


최종 메뉴 재확인: `browser-navigation-final.txt` 2개 통과(기존 15개에 포함된 동일 고유 검사). 활성 키보드 메뉴 배경 RGB(27,63,99)와 흰 글자를 확인하고 Drawer 종료 후 PNG를 검사했다. `browser-viewer-menu-final.txt`로 실제 OHIF 문서·CT canvas·HU/거리 값의 메뉴 왕복 보존 1개가 통과했다(기존 15개에 포함된 검사). 스크린샷은 합성 검증 자료이며 운영 화면에 기본 자료로 주입하지 않는다.
