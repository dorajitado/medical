// CandidateDetail.tsx — 후보 목록·CT·3D에서 고른 동일 실행/후보의 출처·측정 상세.
// 사용자 채택/제외나 병원 원문과의 대조는 후속 기능이며 여기서 AI를 확정하지 않는다.
import { Alert, Button, Paper, Stack, Typography } from '@mui/material';
import { modelTitles, useAnalysisReview } from './AnalysisReview';

export default function CandidateDetail() {
  const { result, selectedFinding: finding, selectCandidate } = useAnalysisReview();
  return <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1}>
      <Typography variant="h6" component="h3">선택한 AI 후보 상세</Typography>
      {!result ? <Typography variant="body2" color="text.secondary">분석 완료 결과를 선택하면 후보를 검토할 수 있습니다.</Typography>
        : result.model_id === 'total' ? <Typography variant="body2">현재 선택은 해부학 분할입니다. 질환 후보 분석은 중앙 모델 선택에서 실행하세요.</Typography>
          : !finding ? <Typography variant="body2">{result.finding_count === 0 ? '이 실행에서 후보가 생성되지 않았습니다. 질환 배제를 뜻하지 않습니다.' : '후보 목록 또는 3D 표면에서 항목을 선택하세요.'}</Typography>
            : <>
              <Typography fontWeight={700} data-testid="selected-candidate-title">{finding.title}</Typography>
              <Button size="small" onClick={() => selectCandidate(null)}>후보 선택 해제</Button>
              <Typography variant="body2">종류: {modelTitles[result.model_id]} · 검토 전 AI 후보</Typography>
              <Typography variant="body2">부피: {finding.volume_mm3===null?'탐지상자만 제공 · 분할 부피 없음':`${finding.volume_mm3.toFixed(2)} mm³ (${finding.volume_ml?.toFixed(3)} mL)`}</Typography>
              <Typography variant="body2">장경: {finding.diameter_mm === null ? (finding.model_id==='monai_nodule'?'탐지 모델에서 제공하지 않음':'산출 대상 아님 (삼출 영역)') : `${finding.diameter_mm.toFixed(2)} mm`}</Typography>
              {finding.diameter_mm !== null && <Typography variant="caption">원본 절편별 복셀 외곽 최대 Feret 중 최댓값. RECIST 측정이 아닙니다. 측정 절편: {(finding.diameter_slice_z ?? 0) + 1}</Typography>}
              <Typography variant="body2">CT 이동 절편: {finding.representative_index_xyz[2] + 1}</Typography>
              <Typography variant="caption" data-testid="selected-candidate-lps">대표 위치 LPS(mm): {finding.representative_lps_mm.map(v => v.toFixed(2)).join(', ')}</Typography>
              <Typography variant="caption">{finding.score===null?'탐지 점수·악성 확률: 모델에서 제공하지 않음':`MONAI 탐지 점수: ${finding.score.toFixed(4)} · 악성 확률이 아님 · 다른 모델 점수와 평균하지 않음`}</Typography>
              {finding.touches_boundary && <Alert severity="warning">영상 경계에 닿아 부분 영역·부분 부피일 수 있습니다.</Alert>}
              <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>후보: {finding.id}<br />실행: {result.run_id}<br />시리즈: {result.series_id}<br />원본 인스턴스: {finding.source_instance_id}</Typography>
            </>}
    </Stack>
  </Paper>;
}
