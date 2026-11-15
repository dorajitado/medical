// AnalysisReview.tsx — CT·3D·오른쪽 상세가 함께 참조하는 실행/후보 상태.
// 원본·AI 후보·사용자 판단의 경계를 유지하며, 이 상태는 AI 출력 선택만 담당한다.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

/** 모델 ID는 백엔드의 명시적 어댑터 목록과 대응하며 임의 task를 받지 않는다. */
export type ModelId = 'total' | 'lung_nodules' | 'pleural_pericard_effusion' | 'monai_nodule';
export const modelTitles: Record<ModelId, string> = {
  total: '해부학 분할', lung_nodules: '폐결절 후보', pleural_pericard_effusion: '흉수·심낭삼출',
  monai_nodule:'MONAI 결절 탐지',
};
export type Structure = {
  label: number; title: string; color: string; voxel_count: number;
  volume_ml: number; touches_boundary: boolean;
};
/** 점수 없음은 null로 보존한다. 후보 ID는 실행 내부에서만 유일하다. */
export type Finding = {
  id: string; selection_label: number; kind: string; title: string; label: number; color: string;
  voxel_count: number | null; volume_mm3: number | null; volume_ml: number | null; diameter_mm: number | null;
  diameter_slice_z: number | null; diameter_method: string; representative_index_xyz: number[];
  representative_lps_mm: number[]; centroid_lps_mm: number[]; touches_boundary: boolean;
  source_instance_id: string; score: number | null; model_id: ModelId;
  bounds_index_xyz?:number[][]; representation?:string;
};
export type AnalysisResult = {
  run_id: string; model_id: ModelId; series_id: string; shape_xyz: number[];
  structures: Structure[]; findings?: Finding[]; finding_count?: number; finding_status?: string;
  limitations: string[]; measurement_method: string;
  metrics: { elapsed_seconds: number | null; cuda_peak_allocated_bytes: number | null; cuda_peak_reserved_bytes: number | null };
};
type ReviewState = { result: AnalysisResult | null; candidateId: string | null };
type ReviewContext = ReviewState & {
  selectedFinding: Finding | null;
  publishResult: (result: AnalysisResult | null) => void;
  selectCandidate: (id: string | null) => void;
};
const Context = createContext<ReviewContext | null>(null);

/** 검사 변경 순간 이전 결과를 반환하지 않고, 비동기 하위 작업도 별도 취소한다. */
export function AnalysisReviewProvider({ seriesId, children }: { seriesId: string; children: ReactNode }) {
  const [state, setState] = useState<ReviewState>({ result: null, candidateId: null });
  useEffect(() => { setState({ result: null, candidateId: null }); }, [seriesId]);
  const publishResult = useCallback((result: AnalysisResult | null) => {
    setState({ result, candidateId: null });
  }, []);
  const selectCandidate = useCallback((id: string | null) => {
    setState(previous => ({ ...previous, candidateId: previous.result?.findings?.some(f => f.id === id) ? id : null }));
  }, []);
  const result = state.result?.series_id === seriesId ? state.result : null;
  const selectedFinding = result?.findings?.find(f => f.id === state.candidateId) || null;
  return <Context.Provider value={{ result, candidateId: selectedFinding?.id || null, selectedFinding, publishResult, selectCandidate }}>
    {children}
  </Context.Provider>;
}

export function useAnalysisReview() {
  const context = useContext(Context);
  if (!context) throw new Error('AnalysisReviewProvider is required');
  return context;
}
