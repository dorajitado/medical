# CT 중심 종합 검토 검증

2026-11-16. REQUIREMENTS v0.8, API 0.7.0, WBS 1·2·5·7~10. 사용자 승인: 병원 소견 대조 선택, 소견서 없이 CT에서 확인할 후보/결과 이해. Docker 미사용. 전문 정답/검토자 없는 VAL-05는 미완료다.

## 인수 범위와 증거

| 요구사항/목표 | 구현 | 확인한 내용 |
|---|---|---|
| AI-11, CTG-02 | backend/ct_review.py, ct_review_api.py, analysis.py, analysis_volume.py, storage.py | 고정 원본 digest/shape/affine·선택 모델·실행 연결, 단일 GPU 큐·모델별 대기/실행/완료/실패·준비 실패 격리·취소·재시작 중단·재실행 버전. 지원 불가 사유, 소견서 의존 없음 |
| OUT-05, CTG-03 | ct_review.py, src/IntegratedReview.tsx | 종류별 쉬운 한국어·실제 측정/단위·대표 단면/원본·추정 폐엽 위치. 독립 점수/중복 가능한 제안과 사용자 기록 구별. 미분석/실패/손상/미지원은 정상 아님 |
| UI-06, CTG-04 | src/App.tsx, IntegratedReview.tsx, AnalysisPanel.tsx, AnalysisReview.tsx | 기본 종합 검토·한 번 실행, 소견 대조 기본 꺼짐·선택 메뉴, 후보에서 정확한 실행/CT절편·3D·LPS/상세 이동, 4개씩 후보 페이지·접이식 근거·설정·반응형·오류 재시도 |
| OUT-02/03, NFR-03, CTG-05 | ct_review.py, exports.py, maintenance.py | CT만의 고정 버전 JSON/한글 PDF, 사용자 기록/출처/모델/좌표/한계. opt-out 원문/문서 제외, opt-in 무자료 허용·전사 출처/선택 대조 버전 확인. 백업/복원·검사 삭제 FK 정합 |
| CTG-01/06, VAL-02/03/04 | 요구사항/추적표·WBS·README·아키텍처·일일 기록·본 문서 | 새 ID/분모와 기존 보류 유지, 합성/공개/운영 자료 분리, 기능/출처 검증과 임상 성능 구별·운영 보존 |

## 자동 검증

Python 전체 **80개 고유 검사 통과(47.292초)**: 기존 65개와 backend/test_ct_review.py 신규 15개. 전체 로그 `data/qa-ct-review-python-all.txt`. 마지막 원본 격자 shape/PDF 사용자 기록 표시 변경 후 관련 15개를 재실행해 **26.334초 OK** (`data/qa-ct-review-tests-final.txt`). 제한 실행 환경에서 지연된 첫 재검증은 중지하고 임시 DB 테스트를 네이티브 실행해 완료했다. 중지된 실행은 통과 증거로 집계하지 않았다.

신규 테스트는 소견서 없는 요약/추정 위치, opt-in 무자료/유자료/다시 끄기, 최신 실패 시 과거 성공 대체 금지, NaN·원본 순서·파일 변경·잘못된 위치 지도 격자 차단, 고정 원본 batch/실행 원자 연결·준비 실패·실행기 실패·취소·중단·다른 시리즈 차단, 실행 전 변경 차단, 대조 버전 경계, CT JSON/PDF와 백업/복원/삭제, 엄격한 API/요청 헤더, 미지원 모델, OCR 첨부 전사 출처를 확인한다. 양성 마스크는 알려진 합성 정답이며 실제 모델 성능 자료가 아니다.

Edge 전체 **19개 고유 검사 통과**:

| 구성 | 검사 수 | 기록 |
|---|---|---|
| 기본 등록/영상 | 4 | data/qa-ct-review-browser-base.txt, 18.6초 |
| 기존 메뉴/구조화·대조·문서·관리 | 6 | data/qa-ct-review-browser-workflow.txt, 30.5초 |
| 기존 실제 모델 결과 | 3 | data/qa-ct-review-browser-models.txt, 17.9초 |
| 기존 합성 후보 이동/복구 | 2 | data/qa-ct-review-browser-findings.txt, 11.4초 |
| 신규 CT 종합 검토 | 4 | data/ct-review-browser-log.txt, 최종 27.4초 |

신규 4개: 보고서가 전혀 없는 기본 화면→단일 batch POST→네 항목 완료→정확한 CT/3D/대표 LPS→사용자 기록→CT JSON/PDF; 대조 켰을 때 소견서 없음/있음/끄면 원문 마커 제외; 실제 실패 상태 주입·재시도/취소 시 정상 오표시 금지; 390/1280/1920 화면 overflow와 통신 오류 후 낡은 결과 제거/재시도. 외부 요청 없음도 검사했다. backend/qa_ct_review_server.py는 별도 TempDir와 8005 포트·합성 worker를 사용한다. 기존 개별 영상 메뉴 테스트 URL은 새 기본 화면과 구분해 /#viewer로 명시했다.

`npm run build` 타입 검사/프로덕션 빌드 통과 (`data/qa-ct-review-build.txt`). Vite의 500kB 초과 chunk 안내는 남아 있으나 빌드 오류는 없다. 실행 시 Three.js는 지연 로딩한다.

## 실제 GPU 일괄 실행

`python -m backend.qa_ct_review`는 보존된 공식 공개 작은 CT `example_ct_sm.nii.gz`의 SHA-256 `e50c00b2914e2cac0aaee8e7f3b5f57d44d9f21bfd5c0577271c54c0cb49e9fb` 및 data/qa-week3/workspace-* 경계를 확인한다. 사용자 CT/운영 DB는 사용하지 않는다.

122×101×30, 3mm 공개 예제에서 total→lung_nodules→pleural_pericard_effusion→monai_nodule 실제 순차 실행, 네 항목 완료·종합 검토 available·소견 대조 꺼짐·CT 전용 스냅샷 저장 통과. 요청~결과/저장까지 **119.343초**, 후보 **5개 제안**. 실행별 metrics/출처는 `data/qa-ct-review/actual-batch.json`, 단계 로그는 `data/qa-ct-review-actual-log.txt`. 합성 UI의 6개와 구별한다. 이 숫자는 진단 정확도·확정 병변 수·일반 조영 CT의 처리시간 보장이 아니다.

## 시각 확인과 운영 보존

최종 합성 결과 화면 `data/ct-review-browser-results/ct-positive-1920.png`, `ct-positive-1280.png`와 좁은/실패 상태 `ct-first-{390,1280,1920}.png` 확인. 기본 블루그레이 MUI 테마를 유지하고 PC 결과 두 열/모바일 한 열, 소견 메뉴 선택 표시, 후보/설정 접기·페이지 나누기로 분리했다. UI-01 최종 사용자 디자인 검토는 별도 대기다.

최종 `ct-only-review.pdf` 69,305바이트, **3쪽**을 Poppler로 `data/qa-ct-review/pdf/final-1.png`~`final-3.png` 렌더링해 모두 확인했다. 한글·단위·출처·3자리 표시 LPS·독립 점수·현재 사용자 기록/역사·소견 미사용 문구·페이지 번호·한계가 읽히고 잘림/겹침이 없다. JSON은 원본 좌표 정밀도를 유지한다. 원문 문자열은 이스케이프하고 외부 글꼴/이미지를 불러오지 않는다.

유휴 상태에서 프로젝트 API만 재시작해 **0.7.0/schema v5** 반영. HTML/JS HTTP 200, 네 모델 준비·네이티브 영상 ready. 재시작 직전/직후 **검사 2개·원본 288개·소견 버전 4개·기존 분석 실행 3개**, 진행 작업 0, 원본 실제 바이트/목록·소견 전체 버전 SHA 지문 동일. 두 운영 시리즈의 CT 전용 GET은 모두 200·report_enabled=false·원문 0·clinical_validation=not_evaluated. 운영 CT는 새 분석을 시작하지 않았다. 증거 `data/qa-ct-review/production-before.json`, `production-after.json`(preserved=true). 이전 작업 때의 소견 3개 기록과 이번 직전 4개 기준을 혼동하지 않는다. 운영 복원/삭제·OS 종료를 수행하지 않았다.

## 완료율과 남은 기준

CT_REVIEW_PLAN의 최초 CTG-01~06 **6/6=100%**. AI-11/OUT-05/UI-06의 구현·기능 검증을 인수해 전체 P0 **48/51=94.1%**(전체 루트 58개). UI-01 최종 사용자 디자인, NFR-05 새 PC AI/영상 전체 재설치, NFR-07 대표 실제 전체 조영 CT 성능은 미완료다. P1 이전 CT 전체 영상 정합/자유로운 문장 재작성, 조건부 추가 소견·VAL-05 전문 정답/평가도 유지한다. 이번 문장 요약은 규칙 기반이며 새로운 자유 LLM 판독을 추가하지 않았다. 폐색전·기흉·폐실질 이상·림프절 등을 평가했다고 표시하지 않는다.

원시 검증 자료·모델 출력·PDF/이미지·운영 지문은 data/ 아래 Git 제외다. 문서에는 환자명·본문·DICOM UID를 복사하지 않는다. 재현 명령/소스와 검증 수치만 기록한다.

## 퍼센트 진행 막대 후속 검증 — 2026-11-16

사용자 요청, UI-04/UI-06·AI-11, WBS 7·9. src/IntegratedReview.tsx에서 `completed_count / selected_count × 100`(소수 한 자리 반올림)을 결정형 MUI LinearProgress·숫자·완료/전체 항목 수와 접근성 aria-valuenow/aria-valuetext로 표시한다. 전부 완료한 선택 batch의 100%는 숨기지 않는다. 실패/취소는 성공 완료로 세지 않으며 각 개수와 모델 상태를 별도 표시한다. 4개 중 하나 실패/3개 완료이면 75%이며 시간 경과로 올리지 않는다. 각 모델 내부 추론의 세부 퍼센트/시간 예측은 제공하지 않는다.

`npm run build` 타입/프로덕션 빌드 통과: data/qa-ct-progress-build.txt. `npx playwright test -c playwright.ct-review.config.ts` **4개 통과(29.1초)**: data/ct-progress-browser-log.txt. 기존 소견 선택·영상 연결·저장·반응형/복구 회귀에 더해 실행 중 0<값<100, 모두 완료 후 100 및 정확한 접근성 문구, 실패 1개 후 75%·실패/취소 별도 개수, 취소 후 DB 완료 수와 비율 일치를 확인했다. 기존 19개 브라우저 사례 중 관련 4개 재검증이며 고유 테스트 수를 중복 합산하지 않는다. 백엔드/모델 로직은 변경하지 않아 실제 GPU/전체 Python 검사를 반복하지 않았다.

합성 전용 ct-progress-running.png(25%)와 ct-positive-1280.png(완료 100%)에서 숫자/막대·완료 상태 가독성을 확인했다. 원시 자료는 data/ct-review-browser-results/로 분리한다. API를 재시작하지 않고 최신 정적 화면 제공(HTML/JS 200·새 퍼센트/기준 문자열 포함)을 data/qa-ct-progress-production.json에 기록했다. 운영 CT 분석/소견/원본 데이터는 수정하지 않았다. CT-P1~3 **3/3=100%**, 전체 요구사항 58개·P0 검증 **48/51=94.1%** 유지.
