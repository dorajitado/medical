# 요구사항 구현·검증 추적표

기준: REQUIREMENTS.md v0.4 / 갱신일: 2026-11-15

현재 상태: 2주차 CT 열람·좌표·측정 완료. 요구사항별 전체 완료 여부는 아래 증거로 구분한다.

- 구현: 요구사항의 코드 및 동작 연결이 끝난 경우 체크.
- 검증: 요구사항의 완료 기준을 확인하고 증거를 기록한 경우 체크.
- 증거: 구현 파일, 테스트/실행 명령, 결과 또는 검토 기록의 경로를 기입. 개인 의료정보를 복사하지 않는다.
- 부분 구현: 체크를 비워 두고 상태를 `진행 중`으로 표시한다.
- P1/조건부: 후속 범위를 보존한 항목이며 첫 통합 버전의 필수 완료율과 별도로 집계한다.
- WBS 번호는 DEVELOPMENT_PLAN.md의 1~10 작업을 가리킨다. 체크가 요구사항 내용이나 인수 기준을 대체하지 않는다.

| ID | 우선순위 | 작업 | WBS | 구현 | 검증 | 상태 | 구현 파일·검증 증거·보류 사유 |
|---|---|---|---|---|---|---|---|
| DCM-01 | P0 | 로컬 DICOM 폴더와 복수 파일 가져오기 | 3 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/intake.py — UI 폴더/복수 파일, 하위 폴더 수집·실제 처리 수·원본 해시 보존; 증거: docs/verification/week1.md |
| DCM-02 | P0 | 검사·시리즈·인스턴스 식별 및 중복 처리 | 3 | [x] | [x] | 검증 완료 | backend/storage.py, backend/intake.py — 검사/시리즈/SOP UID 그룹화·중복·충돌·롤백 검증; 증거: docs/verification/week1.md |
| DCM-03 | P0 | 촬영 조건 및 시리즈 선택 | 3 | [x] | [x] | 검증 완료 | backend/intake.py, src/IntakePanel.tsx — 실제 시리즈 선택·절편/조영/재구성 태그 표시; CTPA 미확정 유지; 증거: docs/verification/week2.md |
| DCM-04 | P0 | 입력 무결성·지원 여부 확인 | 3 | [x] | [x] | 검증 완료 | backend/geometry.py, backend/test_geometry.py — 픽셀/원본 해시·혼합/불규칙/기울어진 geometry 제한 및 열람/측정 차단; 증거: docs/verification/week2.md |
| DCM-05 | P0 | 원본과 파생 데이터의 추적 관계 보존 | 3 | [ ] | [ ] | 진행 중 | backend/geometry.py — 정렬 원본 인스턴스 및 좌표 추적; 향후 AI 공간 변환·분석 결과 연결 남음; 증거: docs/verification/week2.md |
| VIEW-01 | P0 | 원본 CT 탐색 및 창 조절 | 3, 4 | [x] | [x] | 검증 완료 | src/Viewer.tsx, backend/native_imaging.py — OHIF 실제 CT·휠/슬라이더·확대·이동·창 드래그/프리셋 검증; 증거: docs/verification/week2.md |
| VIEW-02 | P0 | 다평면 보기 및 방향 표기 | 3, 4 | [x] | [x] | 검증 완료 | backend/geometry.py, tests/browser/z-viewer.spec.ts — LPS 사선/반전 좌표 기준 검증, MPR 3평면·Crosshairs 위치 동기화; 증거: docs/verification/week2.md |
| VIEW-03 | P0 | 거리·HU 측정 | 3, 4 | [x] | [x] | 검증 완료 | backend/geometry.py, tests/browser/z-viewer.spec.ts — 원본 HU·패딩 제외·LPS 거리 및 화면 Length 동작/단위 검증; 증거: docs/verification/week2.md |
| VIEW-04 | P0 | AI 윤곽·마스크 표시 | 3, 4 | [ ] | [ ] | 미착수 | — |
| VIEW-05 | P0 | 본인 영상 기반 3D | 4, 5 | [ ] | [ ] | 미착수 | — |
| VIEW-06 | P0 | 병변 선택의 화면 간 동기화 | 5, 7 | [ ] | [ ] | 미착수 | — |
| AI-01 | P0 | 모델 등록 정보·적용 범위 관리 | 1, 2 | [x] | [x] | 검증 완료 | backend/models.py, /api/models — 모델별 입력·출처·라이선스·버전/가중치 미등록·평가 상태 제공; 미설치 실행 불가; 증거: docs/verification/week1.md |
| AI-02 | P0 | 해부학 분할 | 4, 5 | [ ] | [ ] | 미착수 | — |
| AI-03 | P0 | 폐결절 후보 분석 | 4, 5 | [ ] | [ ] | 미착수 | — |
| AI-04 | P0 | 흉수·심낭삼출 후보 분석 | 4, 5 | [ ] | [ ] | 미착수 | — |
| AI-05 | P0 | 측정 정의와 단위 관리 | 5, 9 | [ ] | [ ] | 미착수 | — |
| AI-06 | P0 | 분석 작업의 상태·취소·재실행 | 2, 5, 9 | [ ] | [ ] | 미착수 | — |
| AI-07 | P0 | 시리즈별 분석 가능 여부 | 1, 5 | [ ] | [ ] | 미착수 | — |
| AI-08 | P1 | 두 번째 결절 모델 비교 | 후속 | [ ] | [ ] | 미착수 | — |
| AI-09 | 조건부 | 폐색전 후보 분석 | 후속 | [ ] | [ ] | 미착수 | — |
| AI-10 | 조건부 | 추가 흉부 분석 모듈 | 후속 | [ ] | [ ] | 미착수 | — |
| REP-01 | P0 | PDF·이미지·텍스트 등록 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/app.py — 직접 작성/병원전사/메모 출처·원문 저장·빈 입력/위조 출처 거부; 증거: docs/verification/week1.md |
| REP-02 | P0 | 문서와 검사 연결 확인 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/app.py — 검사 선택·명시적 저장·없는 검사 차단·다른 검사 격리; 증거: docs/verification/week1.md |
| REP-03 | P0 | 추출 원문 확인·수정 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/storage.py — 원문 조회·새 버전 수정·재접속/재시작 보존; 증거: docs/verification/week1.md |
| REP-04 | P0 | 소견 구조화 및 출처 연결 | 6 | [ ] | [ ] | 미착수 | — |
| REP-05 | P0 | 구조화 결과 정정 | 6 | [ ] | [ ] | 미착수 | — |
| REP-06 | P1 | 병원 문서 업로드·로컬 OCR | 후속 | [ ] | [ ] | 미착수 | 사용자 정정에 따라 직접 입력 우선, 기존 OCR 범위 보존 |
| CMP-01 | P0 | 병원 소견과 AI 후보 연결 | 7 | [ ] | [ ] | 미착수 | — |
| CMP-02 | P0 | 대조 상태 및 카운트 | 7 | [ ] | [ ] | 미착수 | — |
| CMP-03 | P0 | 측정 차이 설명 | 7 | [ ] | [ ] | 미착수 | — |
| CMP-04 | P0 | 검토·메모·진료 질문 | 7 | [ ] | [ ] | 미착수 | — |
| CMP-05 | P0 | 누락·정상·오류의 구분 | 7 | [ ] | [ ] | 미착수 | — |
| CMP-06 | P1 | 이전 CT 비교 | 후속 | [ ] | [ ] | 미착수 | — |
| OUT-01 | P0 | 근거 기반 정리본 | 8 | [ ] | [ ] | 미착수 | — |
| OUT-02 | P0 | PDF·JSON 내보내기 | 8 | [ ] | [ ] | 미착수 | — |
| OUT-03 | P0 | 수정·실행 이력 | 2, 8 | [ ] | [ ] | 진행 중 | backend/storage.py — 원본 소견/수정 버전·등록 이력; 분석/대조/정리본 변경 이력 남음; 증거: docs/verification/week1.md |
| OUT-04 | P1 | 로컬 언어모델 문장 다듬기 | 후속 | [ ] | [ ] | 미착수 | — |
| UI-01 | P0 | React + TypeScript + Material Design | 1, 2, 3 | [ ] | [ ] | 진행 중 | src/theme.ts, src/App.tsx, src/IntakePanel.tsx — React/MUI 초기 화면 및 실제 브라우저 검증; 사용자 화면 검토 남음; 증거: docs/verification/week1.md |
| UI-02 | P0 | 가변 화면 구성 | 1, 3, 7 | [ ] | [ ] | 진행 중 | src/App.tsx — 구조 영역 접기, 3종 해상도 넘침 검사; 전체 영상 패널 확대·조절 남음; 증거: docs/verification/week1.md |
| UI-03 | P0 | 데이터 기반 화면 | 1, 3, 7 | [ ] | [ ] | 진행 중 | src/IntakePanel.tsx — 실제 등록/소견/모델 데이터; 병변·측정·3D 연결 남음; 증거: docs/verification/week1.md |
| UI-04 | P0 | 입력·대기·오류·재시도 상태 | 1, 3, 7 | [ ] | [ ] | 진행 중 | src/App.tsx, src/IntakePanel.tsx — 등록·문서·연결 오류/재시도; 영상·분석 상태 남음; 증거: docs/verification/week1.md |
| UI-05 | P0 | 조작·가독성 | 1, 3, 7 | [ ] | [ ] | 진행 중 | tests/browser/workspace.spec.ts — 실제 역할/라벨, 3종 해상도 검사; 전체 영상 도구 키보드 검증 남음; 증거: docs/verification/week1.md |
| NFR-01 | P0 | 환자 데이터 로컬 처리 | 2, 9, 10 | [ ] | [ ] | 진행 중 | docs/ARCHITECTURE.md, backend/app.py — 로컬 입력·저장만 사용; 향후 OCR/추론 네트워크 동작 검증 남음; 증거: docs/verification/week1.md |
| NFR-02 | P0 | 로컬 접근 및 파일 보호 | 2, 9, 10 | [ ] | [ ] | 진행 중 | backend/app.py, backend/intake.py — Host/Origin·변경 헤더·UUID 저장 경로·크기 제한; 향후 파일 삭제/영상 엔진 검증 남음; 증거: docs/verification/week1.md |
| NFR-03 | P0 | 데이터 영속성·백업·삭제 | 2, 10 | [ ] | [ ] | 진행 중 | backend/storage.py — 검사/원본/소견 버전/설정 영속성; 백업·복원·삭제 및 전체 검토 상태 남음; 증거: docs/verification/week1.md |
| NFR-04 | P0 | RTX 3080 10GB 자원 관리 | 2, 9, 10 | [ ] | [ ] | 미착수 | — |
| NFR-05 | P0 | 설치·재현성 | 2, 10 | [ ] | [ ] | 진행 중 | setup.ps1, start.cmd, lock 파일 — 새 Python 격리 설치·실행 확인; 전체 가중치 고정/새 PC 및 최종 인수 남음; 증거: docs/verification/week1.md |
| NFR-06 | P0 | 오류 격리·일관성 | 2, 9, 10 | [ ] | [ ] | 진행 중 | backend/storage.py — 등록 중단 복구·트랜잭션·임시 파일 정리; 모델 오류 격리·추론 중단 복구 남음; 증거: docs/verification/week1.md |
| NFR-07 | P0 | 성능 기준 수립·측정 | 2, 9, 10 | [ ] | [ ] | 진행 중 | docs/verification/week2.md — 합성 32절편 조작 확인; 대표 임상 CT 처리시간·메모리/성능 기준 남음; 증거: docs/verification/week2.md |
| NFR-08 | P0 | Docker 없는 Windows 로컬 실행 | 2, 3, 10 | [x] | [x] | 검증 완료 | setup-imaging.ps1, backend/run_local.py — Windows 네이티브 Orthanc/OHIF 실행 및 실제 CT 연결; 증거: docs/verification/week2.md |
| VAL-01 | P0 | 영상·측정 검증 | 9 | [ ] | [ ] | 진행 중 | backend/test_geometry.py — 원본 좌표·거리/HU 기준 및 MPR 동작 검증; 분할 부피·리샘플링 오차 검증 남음; 증거: docs/verification/week2.md |
| VAL-02 | P0 | 문서·대조 검증 | 9 | [ ] | [ ] | 미착수 | — |
| VAL-03 | P0 | 데이터 누출 없는 분석·평가 | 9 | [ ] | [ ] | 미착수 | — |
| VAL-04 | P0 | 기능 인수 및 요구사항 추적 | 1~10 | [ ] | [ ] | 진행 중 | WEEK1_PROGRESS.md, docs/verification/week1.md — 주간 목표·증거·추적 갱신; 전체 P0 인수 남음; 증거: docs/verification/week1.md |
| VAL-05 | 조건부 | 진료 적용 평가 | 별도 평가 | [ ] | [ ] | 미착수 | — |

## 현재 집계

- 전체 요구사항: 55개
- P0: 48개 / 구현·검증 완료 12 (25.0%) / 부분 진행 15
- P1: 4개 / 구현 0 / 검증 0
- 조건부: 3개 / 구현 0 / 검증 0

## 작업 기록

열람 진입 후속 검증: UI-02/04/05, DCM-03, VIEW-01 — 왼쪽 검사 클릭, 단일 검사/시리즈 자동 선택, 항상 보이는 영상 열기 버튼. 구현 src/App.tsx·src/IntakePanel.tsx, 증거 docs/verification/week2.md. 기존 항목의 나머지 완료 기준 및 전체 완료율은 유지한다.

| 날짜 | 대상 ID | 변경·검증 결과 | 남은 작업 |
|---|---|---|---|
| 2026-11-15 | 전체 | 요구사항 ID, 완료 기준, WBS 연결 및 추적표 작성 | 미결정 사항 해소 |
| 2026-11-15 | UI-01~04, NFR-02/03/05, VAL-04 | 로컬 개발 기반, API 테스트 6개, 빌드, HTTP 확인. docs/verification/day1.md | 각 요구사항의 남은 전체 완료 기준 검증 |

| 2026-11-15 | DCM-01/02, AI-01, REP-01~03 및 부분 진행 항목 | 1주차 완료, API 17개·브라우저 3개·빌드·격리 설치 검증. 요구사항 v0.3 반영 | 영상/추론/자동 대조/백업 등 후속 작업 |

| 2026-11-15 | DCM-03/04, VIEW-01~03, NFR-08 | 2주차 완료: 네이티브 CT·MPR·거리/HU, API 26개·브라우저 4개·빌드. docs/verification/week2.md | 모델 추론·분할·자동 대조·전체 검증 등 |

## 릴리스 점검

- [ ] 첫 릴리스의 범위와 미결정 사항을 검토했다.
- [ ] 모든 P0의 구현 증거를 연결했다.
- [ ] 모든 P0의 완료 기준을 검증하고 결과를 연결했다.
- [ ] 실패·보류·미지원·후속 기능 목록을 정리했다.
- [ ] 원본 영상·문서와 결과의 연결 및 데이터 보존을 확인했다.
- [ ] 설치·종료·재시작·백업 복원을 확인했다.
- [ ] 기능 동작 확인과 진료 적용 평가 결과를 구분해 보고했다.
