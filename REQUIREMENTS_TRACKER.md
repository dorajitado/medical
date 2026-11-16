# 요구사항 구현·검증 추적표

기준: REQUIREMENTS.md v0.9 / 갱신일: 2026-11-16

현재 상태: 승인된 CT 중심 종합 검토·일괄 분석·소견 선택 경로를 구현·검증했다. 요구사항별 전체 완료 여부는 아래 증거로 구분한다.

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
| DCM-05 | P0 | 원본과 파생 데이터의 추적 관계 보존 | 3, 4 | [x] | [x] | 검증 완료 | backend/analysis_volume.py, backend/analysis.py — 현재 해부학 실행의 Study/Series/SOP·원본 해시·XYZ/HU·LPS/RAS affine/역행렬·출력 복원 보존, 다른 시리즈 결과 차단; 증거: docs/verification/week3.md; backend/findings.py·surfaces.py — 후보/선택맵/표면도 실행·원본에 연결하고 해시/시리즈/모델 검증; docs/verification/week4.md |
| VIEW-01 | P0 | 원본 CT 탐색 및 창 조절 | 3, 4 | [x] | [x] | 검증 완료 | src/Viewer.tsx, backend/native_imaging.py — OHIF 실제 CT·휠/슬라이더·확대·이동·창 드래그/프리셋 검증; 증거: docs/verification/week2.md |
| VIEW-02 | P0 | 다평면 보기 및 방향 표기 | 3, 4 | [x] | [x] | 검증 완료 | backend/geometry.py, tests/browser/z-viewer.spec.ts — LPS 사선/반전 좌표 기준 검증, MPR 3평면·Crosshairs 위치 동기화; 증거: docs/verification/week2.md |
| VIEW-03 | P0 | 거리·HU 측정 | 3, 4 | [x] | [x] | 검증 완료 | backend/geometry.py, tests/browser/z-viewer.spec.ts — 원본 HU·패딩 제외·LPS 거리 및 화면 Length 동작/단위 검증; 증거: docs/verification/week2.md |
| VIEW-04 | P0 | AI 윤곽·마스크 표시 | 3, 4 | [x] | [x] | 검증 완료 | src/AnalysisPanel.tsx, backend/analysis_volume.py — 원본 격자 축상 마스크·표시·구조·불투명도·슬라이스 및 좌표 복원 검증. OHIF MPR와 별도 탐색; 증거: docs/verification/week3.md |
| VIEW-05 | P0 | 본인 영상 기반 3D | 4, 5 | [x] | [x] | 검증 완료 | backend/surfaces.py, src/SurfacePanel.tsx — 실제 마스크 LPS 표면·회전/확대·구조/윤곽/불투명도·시점 복원, 빈/오류/재시도. 현재 선택 실행 범위; 증거: docs/verification/week4.md |
| VIEW-06 | P0 | 병변 선택의 화면 간 동기화 | 5, 7 | [x] | [x] | 검증 완료 | src/AnalysisReview.tsx, src/AnalysisPanel.tsx, src/SurfacePanel.tsx, src/CandidateDetail.tsx — 후보 목록/표면 선택 시 CT 마스크 뷰·3D 표식·상세 동일 후보, 모델/실행/시리즈 변경 및 늦은 응답 차단. OHIF 탐색 독립; 증거: docs/verification/week4.md |
| AI-01 | P0 | 모델 등록 정보·적용 범위 관리 | 1, 2 | [x] | [x] | 검증 완료 | backend/models.py, backend/analysis_runtime.py — 후보와 실제 연결 task 구별, 패키지/가중치/설정·적용 구조·라이선스·기술/임상 상태, 파일·해시 검사; 증거: docs/verification/week1.md, docs/verification/week3.md; 3 task별 독립 가중치·crop 체크포인트·고정 SHA/설정과 실행 상태; docs/verification/week4.md |
| AI-02 | P0 | 해부학 분할 | 4, 5 | [x] | [x] | 검증 완료 | backend/inference_worker.py, backend/analysis_volume.py — 공개 total fast 3 mm 실제 GPU 실행, 지원 8구조 마스크·부피·출처, 실패/빈 분할 구별; 증거: docs/verification/week3.md. 추가 구조·3D·임상 성능은 별도 |
| AI-03 | P0 | 폐결절 후보 분석 | 4, 5 | [x] | [x] | 검증 완료 | backend/inference_worker.py, backend/findings.py — 실제 lung_nodules 실행·원본 복원·26연결 후보 위치/영역/크기/부피/출처, 점수 null. 빈 실제 출력과 합성 양성 검증 분리; 증거: docs/verification/week4.md |
| AI-04 | P0 | 흉수·심낭삼출 후보 분석 | 4, 5 | [x] | [x] | 검증 완료 | backend/inference_worker.py, backend/findings.py — 실제 pleural_pericard_effusion 실행, 흉수/심낭삼출 종류별 합산 영역/부피·미실행/실패/후보 없음 구별; 증거: docs/verification/week4.md |
| AI-05 | P0 | 측정 정의와 단위 관리 | 5, 9 | [x] | [x] | 검증 완료 | backend/findings.py, backend/test_findings.py — 원본 촬영 평면의 복셀 외곽 최대 Feret 장경·원본 복셀 부피, DICOM 기저/단위/삼출 해당 없음·점수 null, 기준 형상/방향 편차 검사. RECIST 아님; 증거: docs/verification/week4.md |
| AI-06 | P0 | 분석 작업의 상태·취소·재실행 | 2, 5, 9 | [x] | [x] | 검증 완료 | backend/analysis.py, backend/storage.py — 별도 GPU 프로세스 순차 대기/실행/완료/실패/취소, 중복·취소 우선·중단 복구·버전 보존, OOM 응답 주입 및 실제 실행 취소; 증거: docs/verification/week3.md; 모델별 큐/중복/버전·모든 모델 순차 실행·대기 중 가중치 변경 차단; docs/verification/week4.md |
| AI-07 | P0 | 시리즈별 분석 가능 여부 | 1, 5 | [x] | [x] | 검증 완료 | backend/analysis_volume.py, backend/analysis_runtime.py, src/AnalysisPanel.tsx — 초기 3 task별 geometry/간격/크기·설치·확인 검사, 미지원/알 수 없음/CTPA 미확정 표시. 초기 앱 범위이며 임상 적합성 미평가; 증거: docs/verification/week4.md |
| AI-08 | P1 | 두 번째 결절 모델 비교 | 후속 | [x] | [x] | 검증 완료 | backend/monai_worker.py, backend/extended_workflow.py, src/ExtendedWorkspace.tsx — 공식 고정 RetinaNet 독립 GPU 결과·탐지상자/점수·모델 간 후보/수동 연결·확인 버전. 점수 융합/박스 부피 없음; 실제 공개 예제 + 별도 합성 연결 검증; 증거: docs/verification/remaining.md |
| AI-09 | 조건부 | 폐색전 후보 분석 | 후속 | [ ] | [ ] | 선행 조건 대기 | backend/extended_api.py, docs/CLINICAL_EVALUATION.md — 소견별 지원 키/모델·입력·라이선스·정답 평가 선행 조건/출처 조사. 폐색전/추가 분석 어댑터 미연결; 미지원 정상 처리 없음 |
| AI-10 | 조건부 | 추가 흉부 분석 모듈 | 후속 | [ ] | [ ] | 선행 조건 대기 | backend/extended_api.py, docs/CLINICAL_EVALUATION.md — 소견별 지원 키/모델·입력·라이선스·정답 평가 선행 조건/출처 조사. 폐색전/추가 분석 어댑터 미연결; 미지원 정상 처리 없음 |
| REP-01 | P0 | 판독소견서 직접 입력·등록 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/app.py — 직접 작성/병원전사/메모 출처·원문 저장·빈 입력/위조 출처 거부; 증거: docs/verification/week1.md |
| REP-02 | P0 | 입력 소견과 검사 연결 확인 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/app.py — 검사 선택·명시적 저장·없는 검사 차단·다른 검사 격리; 증거: docs/verification/week1.md |
| REP-03 | P0 | 입력 원문 확인·수정 | 6 | [x] | [x] | 검증 완료 | src/IntakePanel.tsx, backend/storage.py — 원문 조회·새 버전 수정·재접속/재시작 보존; 증거: docs/verification/week1.md |
| REP-04 | P0 | 소견 구조화 및 출처 연결 | 6 | [x] | [x] | 검증 완료 | backend/report_parser.py, backend/workflow.py, src/ReviewWorkspace.tsx — 원문/Unicode 범위·부정/의심/과거/단위·모호함과 사용자 정정/추가/제외 버전; test_workflow 및 Edge; 증거: docs/verification/remaining.md |
| REP-05 | P0 | 구조화 결과 정정 | 6 | [x] | [x] | 검증 완료 | backend/report_parser.py, backend/workflow.py, src/ReviewWorkspace.tsx — 원문/Unicode 범위·부정/의심/과거/단위·모호함과 사용자 정정/추가/제외 버전; test_workflow 및 Edge; 증거: docs/verification/remaining.md |
| REP-06 | P1 | 병원 문서 업로드·로컬 OCR | 후속 | [x] | [x] | 검증 완료 | backend/documents.py, backend/ocr_worker.mjs, src/UtilityWorkspace.tsx — PDF/이미지 원본 SHA·페이지/로컬 OCR/내장 텍스트·정정 확인·문서 전사 출처·실패 보존. OCR 품질은 사용자 대조 필요; 증거: docs/verification/remaining.md |
| CMP-01 | P0 | 병원 소견과 AI 후보 연결 | 7 | [x] | [x] | 검증 완료 | backend/workflow.py, src/ReviewWorkspace.tsx — 같은 검사·원본 후보의 다대다 제안/확정과 분리 집계, 동일검사 차이·사용자 검토/질문 영속성·미분석/미지원/실패 구분; 증거: docs/verification/remaining.md |
| CMP-02 | P0 | 대조 상태 및 카운트 | 7 | [x] | [x] | 검증 완료 | backend/workflow.py, src/ReviewWorkspace.tsx — 같은 검사·원본 후보의 다대다 제안/확정과 분리 집계, 동일검사 차이·사용자 검토/질문 영속성·미분석/미지원/실패 구분; 증거: docs/verification/remaining.md |
| CMP-03 | P0 | 측정 차이 설명 | 7 | [x] | [x] | 검증 완료 | backend/workflow.py, src/ReviewWorkspace.tsx — 같은 검사·원본 후보의 다대다 제안/확정과 분리 집계, 동일검사 차이·사용자 검토/질문 영속성·미분석/미지원/실패 구분; 증거: docs/verification/remaining.md |
| CMP-04 | P0 | 검토·메모·진료 질문 | 7 | [x] | [x] | 검증 완료 | backend/workflow.py, src/ReviewWorkspace.tsx — 같은 검사·원본 후보의 다대다 제안/확정과 분리 집계, 동일검사 차이·사용자 검토/질문 영속성·미분석/미지원/실패 구분; 증거: docs/verification/remaining.md |
| CMP-05 | P0 | 누락·정상·오류의 구분 | 7 | [x] | [x] | 검증 완료 | backend/workflow.py, src/ReviewWorkspace.tsx — 같은 검사·원본 후보의 다대다 제안/확정과 분리 집계, 동일검사 차이·사용자 검토/질문 영속성·미분석/미지원/실패 구분; 증거: docs/verification/remaining.md |
| CMP-06 | P1 | 이전 CT 비교 | 후속 | [ ] | [ ] | 부분 구현 | backend/extended_workflow.py, src/ExtendedWorkspace.tsx — 이전일/동일 환자·병변 확인·수동 강체 기준점/RMS·측정법 검사·변화 버전. 실제 이전 CT 영상 정합 적용/검토와 전체 인수 남음; docs/verification/remaining.md |
| OUT-01 | P0 | 근거 기반 정리본 | 8 | [x] | [x] | 검증 완료 | backend/workflow.py, backend/exports.py, src/ReviewWorkspace.tsx — 불변 근거 스냅샷·출처/영상 위치·한글 PDF 시각/JSON 복원·감사 이력, 임의 정상 문장 없음; 증거: docs/verification/remaining.md |
| OUT-02 | P0 | PDF·JSON 내보내기 | 8 | [x] | [x] | 검증 완료 | backend/workflow.py, backend/exports.py, src/ReviewWorkspace.tsx — 불변 근거 스냅샷·출처/영상 위치·한글 PDF 시각/JSON 복원·감사 이력, 임의 정상 문장 없음; 증거: docs/verification/remaining.md |
| OUT-03 | P0 | 수정·실행 이력 | 2, 8 | [x] | [x] | 검증 완료 | backend/workflow.py, backend/exports.py, src/ReviewWorkspace.tsx — 불변 근거 스냅샷·출처/영상 위치·한글 PDF 시각/JSON 복원·감사 이력, 임의 정상 문장 없음; 증거: docs/verification/remaining.md |
| OUT-04 | P1 | 로컬 언어모델 문장 다듬기 | 후속 | [ ] | [ ] | 제한 구현 | backend/editorial.py, src/ReviewWorkspace.tsx — Qwen CPU 실제 실행·사용자 확인 인용의 순서 정리/수치·부정·불확실성·출처 보존·환각 출력 차단 검증. 자유 문장 재작성·문체 품질 인수 남음; docs/verification/remaining.md |
| UI-01 | P0 | React + TypeScript + Material Design | 1, 2, 3 | [x] | [ ] | 사용자 검토 대기 | src/theme.ts, src/App.tsx — React/TS/MUI·기존 블루그레이 테마·메뉴 화면 기술 검증 완료. 최종 사용자 디자인 검토 미완료; docs/verification/remaining.md |
| UI-02 | P0 | 가변 화면 구성 | 1, 3, 7 | [x] | [x] | 검증 완료 | src/App.tsx, src/ReviewWorkspace.tsx, src/UtilityWorkspace.tsx, src/ExtendedWorkspace.tsx, src/IntegratedReview.tsx — 좌측 12개 메뉴 (종합 검토 추가)·선택 화면·PC/모바일 Drawer·확대·API 동적 상태·초안/후보 유지·키보드/3종 해상도와 오류 회귀; 증거: docs/verification/remaining.md |
| UI-03 | P0 | 데이터 기반 화면 | 1, 3, 7 | [x] | [x] | 검증 완료 | src/App.tsx, src/ReviewWorkspace.tsx, src/UtilityWorkspace.tsx, src/ExtendedWorkspace.tsx, src/IntegratedReview.tsx — 좌측 12개 메뉴 (종합 검토 추가)·선택 화면·PC/모바일 Drawer·확대·API 동적 상태·초안/후보 유지·키보드/3종 해상도와 오류 회귀; 증거: docs/verification/remaining.md |
| UI-04 | P0 | 입력·대기·오류·재시도 상태 | 1, 3, 7 | [x] | [x] | 검증 완료 | src/App.tsx, src/ReviewWorkspace.tsx, src/UtilityWorkspace.tsx, src/ExtendedWorkspace.tsx, src/IntegratedReview.tsx — 좌측 12개 메뉴 (종합 검토 추가)·선택 화면·PC/모바일 Drawer·확대·API 동적 상태·초안/후보 유지·키보드/3종 해상도와 오류 회귀; 증거: docs/verification/remaining.md |
| UI-05 | P0 | 조작·가독성 | 1, 3, 7 | [x] | [x] | 검증 완료 | src/App.tsx, src/ReviewWorkspace.tsx, src/UtilityWorkspace.tsx, src/ExtendedWorkspace.tsx, src/IntegratedReview.tsx — 좌측 12개 메뉴 (종합 검토 추가)·선택 화면·PC/모바일 Drawer·확대·API 동적 상태·초안/후보 유지·키보드/3종 해상도와 오류 회귀; 증거: docs/verification/remaining.md |
| NFR-01 | P0 | 환자 데이터 로컬 처리 | 2, 9, 10 | [x] | [x] | 검증 완료 | backend/analysis_runtime.py, backend/offline/sitecustomize.py, backend/documents.py, backend/ocr_worker.mjs, backend/editorial.py — 영상 모델 외부 TCP/DNS 차단·원격 서비스 없는 로컬 OCR/CPU 모델, 고정 설치와 환자 처리 분리, 로컬 자산 처리·Edge 외부 요청 없음. 전면 보안 감사/임상 평가 아님; 증거: docs/verification/remaining.md |
| NFR-02 | P0 | 로컬 접근 및 파일 보호 | 2, 9, 10 | [x] | [x] | 검증 완료 | backend/app.py, backend/maintenance.py, backend/documents.py, backend/owned_process.py — 요청 출처/호스트/경로 보호·백업 해시/복원/롤백·범위/확인 삭제·중단 이동 복구/잠금 재시도·재시작 실패/소유 자식 관리; 운영 자료 자동 복원/삭제 없음; 증거: docs/verification/remaining.md |
| NFR-03 | P0 | 데이터 영속성·백업·삭제 | 2, 10 | [x] | [x] | 검증 완료 | backend/app.py, backend/maintenance.py, backend/documents.py, backend/owned_process.py — 요청 출처/호스트/경로 보호·백업 해시/복원/롤백·범위/확인 삭제·중단 이동 복구/잠금 재시도·재시작 실패/소유 자식 관리; 운영 자료 자동 복원/삭제 없음; 증거: docs/verification/remaining.md |
| NFR-04 | P0 | RTX 3080 10GB 자원 관리 | 2, 9, 10 | [x] | [x] | 검증 완료 | backend/analysis.py, backend/monai_worker.py, backend/qa_performance.py — 네 모델 순차/패치 처리·자식 종료 메모리 해제, OOM 주입 격리 및 512×512×128 합성 CT 자원 실측 모두 한도 내; 대표 실제 CT는 NFR-07 별도; 증거: docs/verification/remaining.md |
| NFR-05 | P0 | 설치·재현성 | 2, 10 | [x] | [ ] | 부분 검증 | setup*.ps1, backend/*requirements-lock.txt, *runtime-lock.json — API 새 가상환경 설치/65개 회귀, 선택 런타임 고정 SHA 재검증 통과. 완전한 새 PC AI/영상 전체 재설치 인수 남음; docs/verification/remaining.md |
| NFR-06 | P0 | 오류 격리·일관성 | 2, 9, 10 | [x] | [x] | 검증 완료 | backend/app.py, backend/maintenance.py, backend/documents.py, backend/owned_process.py — 요청 출처/호스트/경로 보호·백업 해시/복원/롤백·범위/확인 삭제·중단 이동 복구/잠금 재시도·재시작 실패/소유 자식 관리; 운영 자료 자동 복원/삭제 없음; 증거: docs/verification/remaining.md |
| NFR-07 | P0 | 성능 기준 수립·측정 | 2, 9, 10 | [x] | [ ] | 부분 검증 | backend/qa_performance.py — 사전 기록 한도·512×512×128 합성 CT 네 모델 자원 실측 통과. 대표 실제 얇은 절편 조영 CT·뷰어 반응/허용 대기 기준 최종 인수 남음; docs/verification/remaining.md |
| NFR-08 | P0 | Docker 없는 Windows 로컬 실행 | 2, 3, 10 | [x] | [x] | 검증 완료 | setup-imaging.ps1, backend/run_local.py — Windows 네이티브 Orthanc/OHIF 실행 및 실제 CT 연결; 증거: docs/verification/week2.md |
| VAL-01 | P0 | 영상·측정 검증 | 9 | [x] | [x] | 검증 완료 | backend/test_geometry.py, backend/test_analysis.py, backend/test_findings.py, Edge 3종 — 지원 입력의 좌표/좌우/거리/HU/부피/장경·리샘플 복원·3D 공간 회귀, 사전 오차와 결과 기록. 임상 성능/오차는 VAL-05로 별도; 증거: docs/verification/week2.md, week3.md, week4.md |
| VAL-02 | P0 | 문서·대조 검증 | 9 | [x] | [x] | 검증 완료 | backend/test_workflow.py, backend/test_remaining.py, backend/extended_workflow.py — 문서/모호한 연결/출처 회귀·소견 비입력 영상 추론, 원본/제공 환자 그룹 분할 방지와 평가 준비; 전문 정답 성능은 미평가; 증거: docs/verification/remaining.md |
| VAL-03 | P0 | 데이터 누출 없는 분석·평가 | 9 | [x] | [x] | 검증 완료 | backend/test_workflow.py, backend/test_remaining.py, backend/extended_workflow.py — 문서/모호한 연결/출처 회귀·소견 비입력 영상 추론, 원본/제공 환자 그룹 분할 방지와 평가 준비; 전문 정답 성능은 미평가; 증거: docs/verification/remaining.md |
| VAL-04 | P0 | 기능 인수 및 요구사항 추적 | 1~10 | [x] | [x] | 검증 완료 | REQUIREMENTS_TRACKER.md, REMAINING_PROGRESS.md, docs/verification/remaining.md — 각 P0 구현/증거/미완료·보류 목록, 기능 검토 릴리스 범위 명시. 모든 P0 인수나 임상 통과 선언 아님; 증거: docs/verification/remaining.md |
| VAL-05 | 조건부 | 진료 적용 평가 | 별도 평가 | [ ] | [ ] | 평가 준비 | 사용자 답변: 전문 정답·검토자 아직 없음. backend/extended_workflow.py, docs/CLINICAL_EVALUATION.md — 평가 사례/분할/계수/대장·절차 준비. 표본/목표·실제 전문가 평가·진료 적용 인수 미완료 |
| AI-11 | P0 | CT 종합 분석 실행 조율 | 2, 5, 7 | [x] | [x] | 검증 완료 | backend/ct_review.py, ct_review_api.py, analysis.py, storage.py — 고정 원본의 네 모델 순차 실행·상태/취소·준비 실패/재시작/실행 연결·새 버전. 공개 예제 실제 일괄 실행 119.343초, 보고서 입력 없음; backend/test_ct_review.py 및 docs/verification/ct-review.md |
| OUT-05 | P0 | CT 중심 종합 검토 | 7, 8 | [x] | [x] | 검증 완료 | backend/ct_review.py, exports.py, src/IntegratedReview.tsx — 한국어 후보/해부학 추정 위치·실측·원본 출처·범위·독립/중복 제안·사용자 기록. 소견 대조 기본 꺼짐·무자료 허용·구버전 차단, CT 전용 고정 PDF/JSON·백업/삭제 정합; docs/verification/ct-review.md |
| UI-06 | P0 | 종합 검토 기본 화면 | 7 | [x] | [x] | 검증 완료 | src/App.tsx, IntegratedReview.tsx, AnalysisPanel.tsx — 기본 진입·CT만으로 한 번 실행/이해/저장·정확한 실행/후보의 CT/3D/상세 연결·390/1280/1920·오류 재시도; tests/ct-review/integrated.spec.ts 4개, docs/verification/ct-review.md. 최종 디자인 사용자 인수는 UI-01 별도 |
| UI-07 | P0 | 사용자 매뉴얼·앱 도움말 | 1, 7, 9, 10 | [x] | [x] | 검증 완료 | public/user-manual.html, src/App.tsx, docs/USER_MANUAL.md — 실제 CT/선택 소견·결과/근거/저장/문제 해결·백업/종료 안내, 앱 새 창·오프라인·12장별 한 페이지/이전/다음·키보드/모바일/현재 장 인쇄. tests/ct-review/manual.spec.ts 신규 2개와 기존 종합 4개 통과, docs/verification/user-manual.md |

## 현재 집계

- 전체 요구사항: 59개
- P0: 52개 / 검증 완료 49 (94.2%) / 전체 검증 대기 3: UI-01·NFR-05·NFR-07
- P1: 4개 / 구현·검증 완료 2 / 부분·제한 구현 2
- 조건부: 3개 / 전체 구현·검증 완료 0 / 선행 조건·실제 평가 대기 3

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
- [x] 모든 P0의 구현 파일·증거 또는 미완료 사유를 연결했다.
- [ ] 모든 P0의 완료 기준을 검증하고 결과를 연결했다.
- [x] 실패·보류·미지원·후속 기능 목록을 정리했다.
- [x] 현재 지원 범위의 원본 영상·문서와 결과 연결 및 데이터 보존을 확인했다.
- [ ] 설치·종료·재시작·백업 복원을 확인했다.
- [x] 기능 동작 확인과 진료 적용 평가 결과를 구분해 보고했다.

2026-11-15 3주차: DCM-05, VIEW-04, AI-02/06 인수. AI-01 실제 설치 정보 보강. AI-05/07, NFR-04, VAL-03 등은 남은 기준을 명시해 부분 진행 유지. REQUIREMENTS.md v0.5와 연결. REP-01~03의 표 제목도 이미 확정된 직접 입력 기준으로 정합화했다. 증거: docs/verification/week3.md.

2026-11-15 4주차: AI-03/04/05/07, VIEW-05/06, VAL-01 초기 지원 범위 인수. 기존 출처/설치/큐·로컬/오류 검증 보강. 전체 55개/P0 48개 유지. 진료 적용은 VAL-05 미완료. 증거: docs/verification/week4.md.

2026-11-16: 현재 구현 통합과 좌측 메뉴 UI 인수. P0 45/48=93.8%, P1 2/4 검증 완료. 원래 R-01~12는 부분 기준을 보존하며 임상 평가/조건부를 완료 처리하지 않는다. 사용자 지시로 새 확장 중지, 메뉴 UI 우선. 증거: docs/verification/remaining.md.

2026-11-16 사용자 변경: CT만으로 종합 검토, 병원 대조 선택. 새 3개 P0를 추가해 58개/P0 51개. 이전 45/48 기록은 과거 분모로 유지. CTG-01~06으로 개발·검증.

2026-11-16 CTG 결과: 6/6, AI-11/OUT-05/UI-06 구현·검증 인수. Python 80개 고유 검사 및 마지막 변경의 CT 전용 15개 재검증, Edge 19개 고유 검사·빌드·공개 예제 실제 추론·한글 PDF 3쪽 확인. 운영 API 0.7.0, 기존 자료 보존·자동 추론 없음. 전체 P0 48/51=94.1%, P1/조건부 및 임상 평가 보류 유지. 증거: docs/verification/ct-review.md.

2026-11-16 UI-04/UI-06·AI-11 표시 개선 검증: src/IntegratedReview.tsx에 실제 완료/선택 항목 기준 퍼센트·결정형 막대·실패/취소 별도 개수·완료 후 100% 유지 추가. tests/ct-review/integrated.spec.ts에서 실행 중 0보다 크고 100보다 작은 값, 완료 100%, 1개 실패 시 75%, 취소 후 DB 실제 비율·접근성 값을 검증. Edge 4개(29.1초) 및 타입/빌드 통과, docs/verification/ct-review.md 후속 기록. 구현/검증 체크와 전체 P0 48/51은 유지.

2026-11-16 UI-07 인수: MAN-01~03 3/3. 실제 사용자 매뉴얼/앱 링크·로컬 오프라인·인쇄 표시·목차/키보드/해상도, 빌드·Edge 6개(신규 2개) 통과·운영 HTML 제공 확인. 전체 59개/P0 52개 중 49개(94.2%) 검증. 근거: docs/verification/user-manual.md. 기존 미완료 항목 유지.

2026-11-16 UI-07/UI-05 페이지 개선 추가 인수: public/user-manual.html, tests/ct-review/manual.spec.ts — 선택한 한 장만 표시·이전/다음·페이지 번호·브라우저 이력·오프라인·현재 장 인쇄·초점/스크롤/모바일 접기. 초기 Tab 순서 수정 뒤 Edge 2개 7.8초·빌드·운영 제공 통과. MPG-01~03 3/3, 전체 P0 49/52 유지. 증거 docs/verification/user-manual.md 후속 기록.
