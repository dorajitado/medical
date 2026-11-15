# 1주차 검증 기록

날짜: 2026-11-15 / 기준: REQUIREMENTS.md v0.3 / 목표: W1-01~06

## 구현 증거

| 작업 | 구현 파일 |
|---|---|
| 설계 | docs/ARCHITECTURE.md, REQUIREMENTS.md |
| 사용자 폴더/파일 입력 및 원본 보호 | src/IntakePanel.tsx, backend/intake.py |
| 저장·검사/시리즈·작업·소견 버전 관계 | backend/storage.py, backend/app.py |
| 모델 후보 레지스트리 | backend/models.py, /api/models |
| 설정·오류 복구 화면 | src/App.tsx, src/api.ts |
| 설치 및 실행 | setup.ps1, start.ps1, start.cmd, package-lock.json, backend/requirements-lock.txt |

## 실행 검증

- Python API 테스트: `data/install-check-venv/Scripts/python.exe -m unittest backend.test_app backend.test_intake -v` — **17개 통과**.
- 브라우저: `npx playwright test` — 실제 Microsoft Edge headless에서 **3개 통과**.
- 타입/화면 빌드: `npm run build` — TypeScript 및 Vite 통과.
- 새 Python 격리 환경: `data/install-check-venv`에 requirements-lock.txt 설치 성공, 동일 17개 테스트 통과. 새 OS/다른 PC 검증은 아님.
- 실제 화면 해상도: 1280×720, 1920×1080, 390×844에서 가로 넘침 없음 및 폴더 선택 버튼 노출/활성 확인. 1280px·390px 전체 페이지 캡처를 직접 확인.
- 캡처: data/browser-results/workspace-1280.png, workspace-1920.png, workspace-390.png. 합성 QA 자료만 포함하며 Git 제외.
- 통합 테스트 서버는 8001 포트 임시 DB를 사용. 운영 data/workspace.sqlite3에 합성 환자 자료를 삽입하지 않음.
- `start.ps1`로 운영 서버를 재시작하고 API v0.2.0 확인. `/`, `/api/health`, `/api/studies`, `/api/models`, `/api/imports` 모두 HTTP 200. 운영 검사 수 0 확인.

## 확인한 시나리오

하위 폴더 포함 DICOM 선택, 2개 파일의 한 검사/시리즈 그룹화, 바이트 해시 원본 보존, 같은 UID/같은 파일의 중복, 같은 UID/다른 바이트 충돌, 다른 검사에 연결된 시리즈 충돌의 롤백, 비DICOM·비CT·필수 태그 누락·다중프레임·로컬라이저·잘못된 간격/방향 거부, 파일 크기 한도, 처리 총수 초과 차단, 작업 취소·조기 완료 차단·동시 작업 차단, 서버 재시작 후 interrupted 상태와 임시 파일 정리.

판독소견서 출처 스키마, 없는 검사 입력 차단, 빈 내용 거부, 검사 간 소견 분리, 원문과 수정 버전 보존, 재접속/앱 인스턴스 재생성 후 복원, HTML 문자열을 텍스트로 표시, 설정 비동기 저장 및 재접속 복원, 연결 실패 시 등록 비활성 및 재시도 복구.

## 검증 중 발견 및 조치

- 기존 SQLite 연결이 with 블록 뒤에도 열린 채 남을 수 있어 Store.connect에서 명시적으로 닫도록 수정.
- 파일 전송을 앱 내에서 순차 처리하고 DB 트랜잭션으로 중복 충돌 처리. 입력 파일명을 서버 경로로 사용하지 않음.
- MUI Switch의 실제 접근성 역할은 switch이며, 저장 API 후 체크 상태가 바뀜. 브라우저 테스트를 실제 역할과 비동기 완료 대기에 맞춰 수정 후 통과.
- Starlette TestClient의 httpx 지원 중단 예정 경고는 남아 있음. 테스트 통과와 별개로 의존성 갱신 시 추적.

## 요구사항 인수 범위

- DCM-01/02: 사용자 선택·분류·원본 보존·중복 식별 검증 완료. 픽셀 판독/시리즈 적합성 인수와는 구분.
- AI-01: 후보·버전/가중치 미등록·입력 조건·라이선스/출처·평가 상태 조회, 미설치 모델 실행 불가 표시 검증 완료. 실제 추론은 AI-02~04에 남음.
- REP-01~03: 직접 입력·검사 연결·출처·조회·버전 수정 및 보존 검증 완료. 구조화/자동 대조는 REP-04~05, CMP 항목에 남음.
- UI/NFR의 나머지 일부는 기반만 구현. 사용자 화면 검토, 전체 영상·분석 상태, 백업/복원·최종 설치 인수 등을 남기고 완료 체크하지 않음.

## 후속 검증

실제 환자 CT·병원 문서와 임상 모델 성능은 이 단계에서 평가하지 않았다. 메타데이터 등록 성공은 픽셀 무결성·연속성·측정 정확도 또는 특정 모델 입력 적합성의 확정이 아니다. 압축 CT/Enhanced CT 지원, 취소된 파일 재전송, 백업/복원/삭제 도구는 후속 범위다.
