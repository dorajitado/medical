/** CT-first review: optional reports, evidence-bound Korean facts and one batch
 * action. Source-keyed children own requests so stale replies cannot cross CTs. */
import { useEffect, useRef, useState } from 'react';
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Checkbox, Chip, FormControlLabel, LinearProgress, MenuItem, Pagination, Paper, Select, Stack, Switch, TextField, Typography } from '@mui/material';
import { ExpandMore, PlayArrow, VisibilityOutlined } from '@mui/icons-material';
import { request } from './api';
import { useIntake } from './IntakePanel';
import type { FindingFocus } from './AnalysisReview';

type Data = Record<string, any>;
type Destination = 'home' | 'analysis' | 'viewer' | 'reports' | 'compare';
type Props = { onNavigate: (id: Destination) => void; onFinding: (target: Omit<FindingFocus, 'nonce'>) => void };
const reviewLabels: Record<string, string> = { not_reviewed: '검토 전', accepted: '사용자 확인 표시', deferred: '확인 보류', excluded: '후보 제외 표시' };
const statuses: Record<string, string> = { available: '선택 범위 분석 완료', processing: '분석 중', partial: '일부 범위만 분석됨', needs_attention: '분석 상태 확인 필요', not_analysed: '분석 전' };
const jobStatuses: Record<string, string> = { completed: '실행 완료', queued: '순서 대기', running: '처리 중', preparing: '준비 중', failed: '실패', cancelled: '취소됨' };

/** SQLite timestamps are UTC; display explicit Korean local time in history. */
function displayTime(value: string) {
  const time = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z');
  return Number.isNaN(time.getTime()) ? '시각 확인 필요' : new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(time) + ' KST';
}

/** The report form is deliberately absent from this required input step. */
export default function IntegratedReview(props: Props) {
  const { connected, selectedStudy, selectedSeriesId, setSelectedSeriesId, series, detailLoading, openSeriesViewer } = useIntake();
  return <Stack spacing={2.5}>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 2.5 } }}><Stack spacing={1.5}>
      <Typography variant="h6" component="h2">CT를 선택하고 확인할 내용을 살펴보세요</Typography>
      <Typography variant="body2" color="text.secondary">병원 소견서 없이 사용할 수 있습니다. AI가 제안한 부위와 실제 분석 범위를 정리하고 원본 영상에 연결합니다.</Typography>
      {!connected ? <Alert severity="warning">로컬 서버 연결을 확인해 주세요.</Alert> : !selectedStudy ? <Alert severity="info" action={<Button onClick={() => props.onNavigate('home')}>CT 등록·선택</Button>}>왼쪽에서 검사를 선택하거나 CT 폴더를 등록해 주세요.</Alert> : <>
        {detailLoading && <LinearProgress aria-label="CT 시리즈 확인 중" />}
        <Select displayEmpty value={selectedSeriesId} onChange={e => setSelectedSeriesId(e.target.value)} inputProps={{ 'aria-label': '종합 분석할 CT 시리즈' }} disabled={detailLoading}>
          <MenuItem value="">CT 시리즈를 선택하세요</MenuItem>{series.map(s => <MenuItem key={s.id} value={s.id}>{s.description || '설명 미기재'} · {s.instance_count}장</MenuItem>)}
        </Select>
        {selectedSeriesId && <Stack direction="row" gap={1} flexWrap="wrap"><Chip size="small" variant="outlined" label={`선택 CT ${series.find(s => s.id === selectedSeriesId)?.instance_count ?? '확인 중'}장`} /><Button size="small" onClick={() => { openSeriesViewer(); props.onNavigate('viewer'); }}>원본 CT 먼저 보기</Button></Stack>}
      </>}
    </Stack></Paper>
    {connected && selectedStudy && selectedSeriesId && <CTContent key={`${selectedStudy}/${selectedSeriesId}`} seriesId={selectedSeriesId} {...props} onFinding={target => { openSeriesViewer(); props.onFinding(target); }} />}
  </Stack>;
}

function CTContent({ seriesId, onNavigate, onFinding }: Props & { seriesId: string }) {
  const { selectedStudy } = useIntake();
  const [plan, setPlan] = useState<Data | null>(null), [view, setView] = useState<Data | null>(null);
  const [batches, setBatches] = useState<Data[]>([]), [saved, setSaved] = useState<Data[]>([]), [comparisons, setComparisons] = useState<Data[]>([]);
  const [models, setModels] = useState<string[]>([]), [confirmed, setConfirmed] = useState(false), [batchId, setBatchId] = useState('');
  const [includeReport, setIncludeReport] = useState(false), [comparisonId, setComparisonId] = useState('');
  const [error, setError] = useState(''), [planError, setPlanError] = useState(''), [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0), [planRefresh, setPlanRefresh] = useState(0);
  const [kind, setKind] = useState('all'), [page, setPage] = useState(1), [saveId, setSaveId] = useState('');
  const [setupOpen, setSetupOpen] = useState(false);
  const alive = useRef(true), editedSelection = useRef(false), previousProcessing = useRef(false), initialReview = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  // Geometry/model eligibility is checked on entry and after processing, while
  // polling below reads progress/results. No image inference occurs on entry.
  useEffect(() => {
    const control = new AbortController(); setPlanError('');
    request<Data>(`series/${seriesId}/ct-plan`, control.signal).then(value => {
      if (control.signal.aborted) return; setPlan(value);
      if (!editedSelection.current) setModels(value.models.filter((m: Data) => m.eligible).map((m: Data) => m.id));
    }).catch(e => { if (!control.signal.aborted) { setPlan(null); setPlanError(e.message); } });
    return () => control.abort();
  }, [seriesId, planRefresh]);

  useEffect(() => {
    const control = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    setLoading(true); setError(''); setView(null);
    async function load() {
      try {
        const query = new URLSearchParams({ include_report: String(includeReport) });
        if (batchId) query.set('batch_id', batchId);
        if (includeReport && comparisonId) query.set('comparison_id', comparisonId);
        const [review, history, snapshots] = await Promise.all([
          request<Data>(`series/${seriesId}/ct-review?${query}`, control.signal),
          request<Data>(`series/${seriesId}/ct-batches`, control.signal),
          request<Data>(`series/${seriesId}/ct-reviews`, control.signal),
        ]);
        if (control.signal.aborted) return;
        setView(review); setBatches(history.items); setSaved(snapshots.items); setError(''); setLoading(false);
        if (initialReview.current) { setSetupOpen(review.completed_models === 0); initialReview.current = false; }
        const processing = review.status === 'processing';
        if (previousProcessing.current && !processing) setPlanRefresh(v => v + 1);
        previousProcessing.current = processing;
      } catch (e) {
        if (!control.signal.aborted) { setView(null); setError(e instanceof Error ? e.message : 'CT 검토 조회 실패'); setLoading(false); }
      } finally {
        if (!control.signal.aborted) timer = setTimeout(load, previousProcessing.current ? 1000 : 5000);
      }
    }
    void load(); return () => { control.abort(); clearTimeout(timer); };
  }, [seriesId, batchId, includeReport, comparisonId, refresh]);

  useEffect(() => {
    const control = new AbortController(); setComparisons([]);
    if (includeReport) request<Data>(`studies/${selectedStudy}/comparisons`, control.signal).then(r => {
      if (!control.signal.aborted) setComparisons(r.items.filter((c: Data) => c.payload.series_id === seriesId));
    }).catch(e => { if (!control.signal.aborted) setError(e.message); });
    return () => control.abort();
  }, [includeReport, selectedStudy, seriesId, refresh]);

  async function perform(work: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('');
    try { await work(); if (alive.current) setRefresh(v => v + 1); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '요청 실패'); }
    finally { if (alive.current) setBusy(false); }
  }
  const activeBatch = batches.find(b => b.status === 'running');
  const selectedBatch = batches.find(b => b.id === batchId);
  const progressBatch = activeBatch || selectedBatch;
  // Count only actual successful tasks. A running GPU task contributes no
  // invented fraction; failed/cancelled tasks remain separate from completion.
  const progressTotal = progressBatch?.selected_count || 0;
  const progressCompleted = progressBatch?.completed_count || 0;
  const progressPercent = progressTotal ? Math.round(progressCompleted / progressTotal * 1000) / 10 : 0;
  const progressFailed = progressBatch?.models.filter((m: Data) => m.status === 'failed').length || 0;
  const progressCancelled = progressBatch?.models.filter((m: Data) => m.status === 'cancelled').length || 0;
  const progressColor = progressBatch?.status === 'completed' ? 'success' : progressBatch?.status === 'running' ? 'primary' : 'warning';
  const selectedSaveId = saved.some(s => s.id === saveId) ? saveId : saved[0]?.id || '';
  const active = view?.status === 'processing' || !!activeBatch;
  const filtered = (view?.candidates || []).filter((c: Data) => kind === 'all' || c.kind === kind);
  const pages = Math.max(1, Math.ceil(filtered.length / 4));
  useEffect(() => { setPage(p => Math.min(p, pages)); }, [pages]);

  return <Stack spacing={2}>
    {loading && <LinearProgress aria-label="CT 종합 검토 불러오는 중" />}
    {error && <Alert severity="error" action={<Button onClick={() => { setRefresh(v => v + 1); setPlanRefresh(v => v + 1); }}>재시도</Button>}>{error}</Alert>}
    {message && <Alert severity="success">{message}</Alert>}
    <Accordion expanded={setupOpen} onChange={(_, value) => setSetupOpen(value)}><AccordionSummary expandIcon={<ExpandMore />}><Typography fontWeight={700}>이번 CT 분석 시작</Typography></AccordionSummary><AccordionDetails><Stack spacing={1.5}>
      {planError && <Alert severity="error" action={<Button onClick={() => setPlanRefresh(v => v + 1)}>준비 상태 재확인</Button>}>{planError}</Alert>}
      {!plan && !planError && <LinearProgress aria-label="CT 분석 범위 확인 중" />}
      {plan && <>
        <Typography variant="body2">선택한 항목을 순서대로 실행합니다. 구조 분석은 위치 표시용이고, 후보 분석은 확인할 부위를 제안합니다.</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 1 }}>
          {plan.models.map((m: Data) => <Box key={m.id}><FormControlLabel control={<Checkbox checked={models.includes(m.id)} disabled={busy || active || !m.eligible} onChange={(_, checked) => { editedSelection.current = true; setConfirmed(false); setModels(old => checked ? [...old, m.id] : old.filter(id => id !== m.id)); }} />} label={m.title} />
            <Typography variant="caption" display="block" color="text.secondary" sx={{ pl: 4 }}>{m.purpose}{!m.eligible && ` · ${m.reasons.join(' ')}`}</Typography></Box>)}
        </Box>
        <FormControlLabel control={<Checkbox checked={confirmed} disabled={busy || active} onChange={(_, value) => setConfirmed(value)} />} label="선택한 CT 시리즈와 분석 범위를 확인했습니다" />
        <Stack direction="row" gap={1} flexWrap="wrap"><Button variant="contained" startIcon={<PlayArrow />} disabled={busy || active || !confirmed || !models.length || models.some(id => !plan.models.find((m: Data) => m.id === id)?.eligible)} onClick={() => perform(async () => {
          const batch = await request<Data>(`series/${seriesId}/ct-batches`, undefined, { model_ids: models, confirmed }, 'POST');
          if (alive.current) { setBatchId(batch.id); setConfirmed(false); setSetupOpen(false); setMessage('선택한 CT의 종합 분석을 시작했습니다. 항목별 진행 상태를 확인하세요.'); }
        })}>종합 분석 실행</Button>
          {activeBatch && <Button color="warning" disabled={busy} onClick={() => perform(async () => { await request(`ct-batches/${activeBatch.id}/cancel`, undefined, {}, 'POST'); setMessage('종합 분석 취소를 요청했습니다. 완료된 이전 결과는 보존됩니다.'); })}>종합 분석 취소</Button>}
          <Button disabled={busy} onClick={() => setPlanRefresh(v => v + 1)}>실행 준비 다시 확인</Button>
        </Stack>
      </>}
      {busy && <LinearProgress aria-label="CT 종합 검토 요청 처리 중" />}
      {selectedBatch && <Typography variant="body2">선택한 분석 항목 {selectedBatch.selected_count}개 중 실행 완료 {selectedBatch.completed_count}개 · {selectedBatch.status === 'running' ? '순차 처리 중' : selectedBatch.status === 'completed' ? '모델 실행 완료' : '미완료 항목 확인 필요'}</Typography>}
      {!!batches.length && <Select size="small" displayEmpty value={batchId} onChange={e => setBatchId(e.target.value)} inputProps={{ 'aria-label': '종합 검토 기준 실행' }}><MenuItem value="">모델별 최신 실행 상태</MenuItem>{batches.map(b => <MenuItem key={b.id} value={b.id}>{displayTime(b.created_at)} · {b.completed_count}/{b.selected_count} 항목 완료 · {b.id.slice(0, 8)}</MenuItem>)}</Select>}
    </Stack></AccordionDetails></Accordion>

    {progressBatch && <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
        <Typography fontWeight={700}>종합 분석 진행 · {progressCompleted}/{progressTotal}개 항목 실행 완료</Typography>
        <Typography fontWeight={700} sx={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{progressPercent}%</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={progressPercent} color={progressColor} aria-label="종합 분석 완료율"
        aria-valuetext={`${progressPercent}% · ${progressTotal}개 중 ${progressCompleted}개 분석 완료`}
        sx={{ height: 10, borderRadius: 1 }} />
      <Typography variant="caption" color="text.secondary">선택한 분석 항목의 완료 비율입니다. 각 모델 내부 처리시간의 진행률과는 다릅니다.</Typography>
      {(progressFailed > 0 || progressCancelled > 0) && <Typography variant="body2" color="warning.main">실패 {progressFailed}개 · 취소 {progressCancelled}개 — 완료 비율에 포함하지 않았습니다.</Typography>}
      {progressBatch.status !== 'completed' && progressBatch.models.map((m: Data) => <Typography key={m.model_id} variant="body2">{plan?.models.find((p: Data) => p.id === m.model_id)?.title || '선택 분석'} · {jobStatuses[m.status] || '상태 확인 필요'}</Typography>)}
      {activeBatch && <Button disabled={busy} color="warning" onClick={() => perform(async () => { await request(`ct-batches/${activeBatch.id}/cancel`, undefined, {}, 'POST'); })}>진행 중인 종합 분석 취소</Button>}
    </Stack></Paper>}

    {view && <>
      <Paper variant="outlined" sx={{ p: 2.5 }}><Stack spacing={1.5}>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap"><Chip size="small" color={view.status === 'available' ? 'info' : 'warning'} label={statuses[view.status]} /><Chip size="small" variant="outlined" label="진료 성능 검증 전" /></Stack>
        <Typography variant="h5" component="h2" data-testid="ct-review-headline">{view.headline}</Typography>
        <Typography variant="body2">{view.completed_models}개 분석 항목의 완료 결과를 반영했습니다. 제안 수에는 모델 간 중복이 포함될 수 있습니다.</Typography>
        <Typography variant="caption" color="text.secondary">확인 범위는 결절·폐/심장 주위 액체 후보입니다. 폐색전·기흉·폐실질 이상·림프절 등은 이 화면에서 평가하지 않습니다.</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3,minmax(0,1fr))' }, gap: 1 }}>
          {view.modules.map((m: Data) => <Paper key={m.kind} variant="outlined" sx={{ p: 1.5 }}><Typography fontWeight={700}>{m.title}</Typography><Typography variant="body2">{m.text}</Typography><Typography variant="caption" color="text.secondary">관련 분석 {m.completed_models}/{m.available_models}개 완료</Typography></Paper>)}
        </Box>
        <Accordion disableGutters><AccordionSummary expandIcon={<ExpandMore />}><Typography>분석한 범위와 아직 확인하지 않은 항목</Typography></AccordionSummary><AccordionDetails><Stack spacing={1}>
          {view.coverage.map((c: Data) => <Box key={c.model_id}><Typography variant="body2">{c.title} · {c.status_text}</Typography>{c.issue && <Typography variant="caption" color="error">{c.issue}</Typography>}</Box>)}
          {view.limitations.map((text: string) => <Typography key={text} variant="caption">{text}</Typography>)}
        </Stack></AccordionDetails></Accordion>
      </Stack></Paper>

      {!!view.candidates.length && <Stack spacing={1.5}>
        <Stack direction="row" justifyContent="space-between" gap={1} flexWrap="wrap"><Typography variant="h6" component="h2">원본 CT에서 확인할 후보</Typography><Select size="small" value={kind} onChange={e => { setKind(e.target.value); setPage(1); }} inputProps={{ 'aria-label': '확인 후보 종류' }}><MenuItem value="all">모든 후보</MenuItem>{view.modules.map((m: Data) => <MenuItem key={m.kind} value={m.kind}>{m.title}</MenuItem>)}</Select></Stack>
        <Typography variant="caption" color="text.secondary">위치와 계산값은 AI의 제안입니다. 모델 점수와 자세한 근거는 각 후보에서 펼쳐볼 수 있습니다.</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 1.5 }}>
          {filtered.slice((page - 1) * 4, page * 4).map((candidate: Data) => <CandidateCard key={candidate.ref} candidate={candidate} studyId={view.study.id} disabled={busy} onSaved={() => setRefresh(v => v + 1)} onOpen={() => onFinding({ seriesId, runId: candidate.run_id, modelId: candidate.model_id, findingId: candidate.finding_id })} />)}
        </Box>
        {pages > 1 && <Pagination count={pages} page={page} onChange={(_, value) => setPage(value)} getItemAriaLabel={(type, number) => type === 'page' ? `후보 ${number}페이지` : type === 'next' ? '다음 후보 페이지' : '이전 후보 페이지'} />}
      </Stack>}

      <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
        <FormControlLabel control={<Switch checked={includeReport} onChange={(_, value) => { setIncludeReport(value); setComparisonId(''); }} />} label="병원 소견과도 대조하기 (선택)" />
        <Typography variant="body2" data-testid="ct-report-context">{view.report_context.text}</Typography>
        {includeReport && <>
          <Select size="small" value={comparisonId} displayEmpty onChange={e => setComparisonId(e.target.value)} inputProps={{ 'aria-label': '선택할 병원 소견 대조' }}><MenuItem value="">저장한 대조를 연결하지 않음</MenuItem>{comparisons.map(c => <MenuItem key={c.id} value={c.id}>{c.created_at} · {c.id.slice(0, 8)}</MenuItem>)}</Select>
          {view.comparison && <Typography variant="body2">사용자 확인 연결 {view.comparison.payload.report_counts.confirmed}개 · 연결 후보 {view.comparison.payload.report_counts.candidate}개 · 비교 불가 {view.comparison.payload.report_counts.not_comparable}개</Typography>}
          <Stack direction="row" gap={1}><Button onClick={() => onNavigate('reports')}>소견서 입력·확인</Button><Button onClick={() => onNavigate('compare')}>선택 대조 화면</Button></Stack>
        </>}
      </Stack></Paper>
      <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
        <Typography variant="h6" component="h2">현재 검토 기록 저장</Typography><Typography variant="body2">후보·분석 범위와 사용자 검토를 저장합니다. 병원 소견은 위 선택 기능을 켰을 때만 포함됩니다.</Typography>
        <Button variant="contained" disabled={busy || !!error} onClick={() => perform(async () => { const saved = await request<Data>(`series/${seriesId}/ct-reviews`, undefined, { batch_id: batchId || null, include_report: includeReport, comparison_id: includeReport ? comparisonId || null : null }, 'POST'); if (alive.current) { setSaveId(saved.id); setMessage('소견서 없이도 사용할 수 있는 CT 종합 검토 기록을 저장했습니다.'); } })}>CT 종합 검토 저장</Button>
        {!!saved.length && <Select size="small" value={selectedSaveId} onChange={e => setSaveId(e.target.value)} inputProps={{ 'aria-label': '저장한 CT 검토 기록' }}>{saved.map(s => <MenuItem key={s.id} value={s.id}>{displayTime(s.created_at)} · {s.id.slice(0, 8)}</MenuItem>)}</Select>}
        {!!saved.length && <Stack direction="row" gap={1} flexWrap="wrap"><Button href={`/api/summaries/${selectedSaveId}/export/pdf`}>CT 검토 PDF 저장</Button><Button href={`/api/summaries/${selectedSaveId}/export/json`}>CT 검토 JSON 저장</Button></Stack>}
      </Stack></Paper>
    </>}
  </Stack>;
}

/** The compact card keeps raw model IDs/scores and editing out of the default
 * reading path. Stored decisions are user records, never validated diagnoses. */
function CandidateCard({ candidate: c, studyId, disabled, onOpen, onSaved }: { candidate: Data; studyId: string; disabled: boolean; onOpen: () => void; onSaved: () => void }) {
  const [decision, setDecision] = useState(c.user_review?.decision || 'deferred'), [note, setNote] = useState(c.user_review?.note || '');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const dirty = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (!dirty.current) { setDecision(c.user_review?.decision || 'deferred'); setNote(c.user_review?.note || ''); } }, [c.user_review?.id]);
  async function save() {
    setBusy(true); setError('');
    try { await request(`studies/${studyId}/reviews`, undefined, { target_type: 'finding', target_id: c.ref, decision, note, question: '' }, 'POST'); if (alive.current) { dirty.current = false; onSaved(); window.dispatchEvent(new Event('review-updated')); } }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '검토 저장 실패'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <Paper variant="outlined" sx={{ p: 2, minWidth: 0 }} data-proposal-ref={c.ref}><Stack spacing={1}>
    <Stack direction="row" gap={1} flexWrap="wrap"><Chip size="small" variant="outlined" label="영상 확인 후보" /><Chip size="small" label={reviewLabels[c.user_review?.decision || 'not_reviewed']} /></Stack>
    <Typography variant="h6" component="h3">{c.title} · {c.location}</Typography>
    <Typography variant="body2">{c.explanation}</Typography><Typography variant="body2" fontWeight={700}>{c.measurement_text}</Typography>
    <Typography variant="caption" color="text.secondary">{c.model_title} · {c.slice_number}/{c.slice_count}번째 단면</Typography>
    {!!c.related_proposals.length && <Typography variant="caption">가까운 위치의 다른 모델 제안 {c.related_proposals.length}건이 있습니다. 같은 병변인지는 아직 확인하지 않았습니다.</Typography>}
    {c.touches_boundary && <Alert severity="info">영상 가장자리에 닿아 범위·측정이 일부만 포함됐을 수 있습니다.</Alert>}
    <Button variant="outlined" startIcon={<VisibilityOutlined />} onClick={onOpen}>CT에서 위치 확인</Button>
    <Accordion disableGutters><AccordionSummary expandIcon={<ExpandMore />}><Typography variant="body2">측정·출처와 검토 기록</Typography></AccordionSummary><AccordionDetails><Stack spacing={1}>
      <Typography variant="caption">{c.location_basis}</Typography><Typography variant="caption">계산 방법: {c.diameter_method}</Typography>
      {c.volume_mm3 !== null && <Typography variant="caption">분류된 영역 부피 {c.volume_mm3.toFixed(2)} mm³ ({c.volume_ml.toFixed(3)} mL)</Typography>}
      <Typography variant="caption">모델 점수 {c.score ?? '제공 없음'} · 악성 확률이 아니며 모델 간 평균하지 않습니다.</Typography>
      <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>근거 {c.ref} · 원본 {c.source_instance_id} · LPS(mm) {c.representative_lps_mm.join(', ')}</Typography>
      <Button size="small" href={c.glossary_source} target="_blank" rel="noreferrer">용어 설명 출처</Button>
      <Select size="small" value={decision} onChange={e => { dirty.current = true; setDecision(e.target.value); }} inputProps={{ 'aria-label': 'CT 후보 사용자 검토 상태' }}>{Object.entries(reviewLabels).map(([key, label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}</Select>
      <TextField size="small" multiline label="CT 후보 검토 메모" value={note} onChange={e => { dirty.current = true; setNote(e.target.value); }} />
      <Typography variant="caption">사용자 검토 기록이며 진단 확정 표시가 아닙니다.</Typography>{error && <Alert severity="error">{error}</Alert>}
      <Button disabled={disabled || busy} onClick={save}>후보 검토 기록 저장</Button>
    </Stack></AccordionDetails></Accordion>
  </Stack></Paper>;
}
