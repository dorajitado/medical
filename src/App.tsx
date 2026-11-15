import { useEffect, useState } from 'react';
import { Alert, Box, Button, ButtonBase, Chip, CircularProgress, Divider, FormControlLabel, LinearProgress, Paper, Stack, Switch, Typography } from '@mui/material';
import { AutoAwesome, DescriptionOutlined, FolderOutlined, HubOutlined, Refresh, ViewInAr } from '@mui/icons-material';
import { request, type Health, type Preferences, type Study } from './api';
import IntakePanel from './IntakePanel';
import Viewer, { type SelectedSeries } from './Viewer';

function Empty({ title, children, dark = false }: { title: string; children: React.ReactNode; dark?: boolean }) {
  return <Stack spacing={1.5} alignItems="center" justifyContent="center" sx={{ minHeight: 270, px: 3, textAlign: 'center', color: dark ? '#abbcc9' : 'text.secondary' }}><HubOutlined sx={{ fontSize: 36, opacity: .6 }}/><Typography sx={{ color: dark ? '#edf3f8' : 'text.primary', fontWeight: 600 }}>{title}</Typography><Typography variant="body2" sx={{ maxWidth: 300 }}>{children}</Typography></Stack>;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [prefs, setPrefs] = useState<Preferences>({ show_structure: true });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [selectedSeries,setSelectedSeries]=useState<SelectedSeries|null>(null);
  const [selectedStudy,setSelectedStudy]=useState('');
  const [studySelectionLocked,setStudySelectionLocked]=useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setHealth(null); setStudies([]);
    Promise.all([request<Health>('health', controller.signal), request<{ items: Study[] }>('studies', controller.signal), request<Preferences>('preferences', controller.signal)])
      .then(([h, s, p]) => { if (!controller.signal.aborted) { setHealth(h); setStudies(s.items); setPrefs(p); setSelectedStudy(current=>s.items.some(study=>study.id===current)?current:s.items.length===1?s.items[0].id:''); } })
      .catch(e => { if (!controller.signal.aborted) setError(`서버에 연결하지 못했습니다. 로컬 서버 실행 상태를 확인해 주세요. ${e.message}`); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [attempt]);
  async function toggleStructure() {
    setSaving(true); setError('');
    try { setPrefs(await request<Preferences>('preferences', undefined, { show_structure: !prefs.show_structure })); }
    catch { setError('화면 설정을 저장하지 못했습니다. 다시 시도해 주세요.'); }
    finally { setSaving(false); }
  }
  const connected = !!health;
  return <Box sx={{ minHeight: '100vh', display: { xs: 'block', lg: 'flex' } }}>
    <Box component="aside" sx={{ width: { lg: 210 }, flexShrink: 0, bgcolor: '#f8fbfd', borderRight: 1, borderColor: 'divider', p: 2.5 }}>
      <Stack direction="row" spacing={1.2} alignItems="center" sx={{ mb: { xs: 2, lg: 5 } }}><Box sx={{ bgcolor: 'primary.main', color: 'white', borderRadius: 2, p: .8, display: 'flex' }}><HubOutlined/></Box><Box><Typography fontWeight={700}>흉부 CT 검토실</Typography><Typography variant="caption" color="text.secondary">LOCAL WORKSPACE</Typography></Box></Stack>
      <Stack spacing={1}><Button startIcon={<FolderOutlined/>} variant="contained" fullWidth sx={{ justifyContent: 'flex-start' }}>검사 작업 공간</Button><Typography variant="caption" color="text.secondary" sx={{ px: 1, pt: 2 }}>영상 · 병원 판독 · AI 결과를<br/>같은 검사에서 확인합니다.</Typography></Stack>
      <Divider sx={{ my: 3 }}/><Stack spacing={1}><Typography variant="overline" color="text.secondary">등록된 검사</Typography>{loading ? <CircularProgress size={18} aria-label="검사 목록 불러오는 중"/> : !connected ? <Typography variant="body2">조회할 수 없음</Typography> : studies.length === 0 ? <Typography variant="body2" color="text.secondary">아직 등록된 검사가 없습니다.</Typography> : studies.map(s => <Paper variant="outlined" sx={{overflow:'hidden',borderColor:selectedStudy===s.id?'primary.main':'divider'}} key={s.id}><ButtonBase disabled={studySelectionLocked||!connected} onClick={()=>setSelectedStudy(s.id)} aria-pressed={selectedStudy===s.id} aria-label={`검사 선택: ${s.description||'설명 미기재'}`} sx={{p:1.5,width:'100%',display:'block',textAlign:'left'}}><Typography variant="body2">{s.description || '설명 미기재'}</Typography><Typography variant="caption">{s.study_date || '검사일 미기재'}</Typography><Typography variant="caption" color="primary" sx={{display:'block'}}>검사 선택</Typography></ButtonBase></Paper>)}</Stack>
    </Box>
    <Box component="main" sx={{ flex: 1, minWidth: 0, p: { xs: 2, md: 3.5 } }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={2} sx={{ mb: 3 }}><Box><Typography variant="overline" color="text.secondary">CHEST REVIEW</Typography><Typography variant="h4">검사 작업 공간</Typography><Typography variant="body2" color="text.secondary" sx={{ mt: .6 }}>원본 영상부터 판독소견서 대조까지</Typography></Box><Stack direction="row" gap={1}><Chip variant="outlined" label={loading ? '연결 확인 중' : connected ? '로컬 저장소 연결됨' : '서버 연결 필요'} color={connected ? 'success' : 'default'}/><Button onClick={() => setAttempt(v => v + 1)} startIcon={<Refresh/>} disabled={loading}>새로고침</Button></Stack></Stack>
      {loading && <LinearProgress aria-label="작업 공간 불러오는 중" sx={{ mb: 2 }}/ >}
      {error && <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" onClick={() => setAttempt(v => v + 1)}>재시도</Button>}>{error}</Alert>}
      {!loading && connected && <Alert severity="info" sx={{ mb: 3 }}>CT를 등록하고 시리즈의 ‘영상 열기’를 선택하세요. 판독소견서는 검사별로 직접 입력합니다. AI 분석·자동 대조는 준비 중입니다.</Alert>}
      <IntakePanel connected={connected} studies={studies} selected={selectedStudy} onStudySelected={setSelectedStudy} onBusyChange={setStudySelectionLocked} onRefresh={() => setAttempt(v => v + 1)} onSeriesSelected={setSelectedSeries}/>
      <Viewer selection={selectedSeries}/>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}><Typography variant="h6">영상과 소견 검토</Typography><FormControlLabel control={<Switch checked={prefs.show_structure} onChange={toggleStructure} disabled={!connected || saving}/>} label="입체 구조 영역"/></Stack>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: prefs.show_structure ? 'minmax(200px,1fr) minmax(240px,1fr)' : '1fr' }, gap: 2 }}>
        {prefs.show_structure && <Paper variant="outlined" sx={{ height: '100%', minHeight: 440, p: 2 }}><Stack direction="row" alignItems="center" spacing={1}><ViewInAr color="primary"/><Typography variant="h6">내 CT의 입체 구조</Typography></Stack><Divider sx={{ my: 2 }}/><Empty title="분할 결과가 필요합니다">본인 CT에서 생성한 구조가 여기에 표시됩니다.</Empty><Chip label="미생성" variant="outlined"/></Paper>}
        <Paper variant="outlined" sx={{ p: 2, gridColumn: { md: '1 / -1', xl: 'auto' } }}><Stack direction="row" spacing={1} alignItems="center"><DescriptionOutlined color="primary"/><Typography variant="h6">병원 소견과 AI 대조</Typography></Stack><Divider sx={{ my: 2 }}/><Empty title="대조할 자료가 없습니다">병원 판독소견서와 분석 결과가 준비되면 소견별로 대조합니다.</Empty><Stack direction="row" alignItems="center" spacing={1}><AutoAwesome color="disabled"/><Typography variant="caption" color="text.secondary">AI 분석 미연결 · 정상 여부 판단 전</Typography></Stack></Paper>
      </Box>
      <Typography component="footer" variant="caption" color="text.secondary" sx={{ display: 'block', mt: 3 }}>데이터 처리: 로컬 PC · {health ? `API v${health.version}` : 'API 상태 미확인'}</Typography>
    </Box>
  </Box>;
}
