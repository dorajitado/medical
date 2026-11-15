
// api.ts — API 통신 함수와 공유 타입 정의
// 로컬 서버와의 JSON 통신 함수, 모든 컴포넌트가 공유하는 응답 타입을 한 곳에 관리한다.

/** 서버 상태 — 저장소·영상 엔진·분석 연결 상태 포함 */
export type Health = {
  status: 'ready';
  storage: 'ready';
  version: string;
  imaging: 'not_connected' | 'configured';
  analysis: 'not_connected' | 'configured';
};

/** 검사(Study) 요약 정보 — 목록 조회용 */
export type Study = {
  id: string;
  study_date: string | null;
  description: string | null;
};

/** 사용자 환경 설정 — 입체 구조 영역 표시 여부 등 */
export type Preferences = { show_structure: boolean };

/** DICOM 가져오기 작업(Job) 상태 — 진행률·오류 포함 */
export type Job = {
  id: string;
  status: string;
  total: number;
  imported: number;
  duplicates: number;
  excluded: number;
  failed: number;
  last_issue: string | null;
};

/** 시리즈 정보 — 절편 두께·조영 태그·재구성 조건 포함 */
export type Series = {
  id: string;
  description: string | null;
  instance_count: number;
  slice_thickness: string | null;
  contrast_agent: string | null;
  validation: string;
  ctpa: string;
  convolution_kernel: string | null;
  image_type: string[];
  reconstruction_diameter: string | null;
};

/** 판독소견서 또는 메모 — 출처(source)로 유형 구분 */
export type Report = {
  id: string;
  text: string;
  source: string;
  created_at: string;
};

/** AI 분석 모델 등록 정보 — 설치·검증 상태 포함 */
export type Model = {
  id: string;
  name: string;
  target: string;
  status: string;
  limitation: string;
  package_version: string | null;
  weights_sha256: string | null;
  validation_status: string;
};

/**
 * 범용 API 요청 함수 — JSON 기반 통신
 * body가 있으면 해당 method(기본 PUT)로 전송, 없으면 GET
 * 서버 오류 시 detail 메시지를 추출하여 Error로 던진다.
 */
export async function request<T>(
  path: string,
  signal?: AbortSignal,
  body?: unknown,
  method = 'PUT',
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    signal,
    cache: 'no-store',
    ...(body !== undefined
      ? {
        method,
        headers: { 'Content-Type': 'application/json', 'X-Workspace-Request': '1' },
        body: JSON.stringify(body),
      }
      : {}),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(
      typeof detail?.detail === 'string' ? detail.detail : `요청 실패 (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}
