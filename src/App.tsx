// App.tsx — 흉부 CT 검토실 메인 어플리케이션 레이아웃
// 좌측 메뉴로 작업을 나누고 선택한 기능만 표시한다. 검토 초안과 분석 선택은 메뉴 전환 동안 보존한다.

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, Drawer, FormControl, FormControlLabel, IconButton, InputLabel, LinearProgress, List, ListItemButton, ListItemIcon, ListItemText, MenuItem, Paper, Select, Stack, Switch, Typography } from '@mui/material';
import { AssessmentOutlined, BackupOutlined, CompareArrows, DescriptionOutlined, DocumentScannerOutlined, FactCheckOutlined, FolderOutlined, HelpOutline, History, HubOutlined, Menu as MenuIcon, Refresh, ViewInAr, VisibilityOutlined } from '@mui/icons-material';
import { request, type Health, type Preferences, type Study } from './api';
import {
  IntakeProvider,
  ModelStatusCard,
  ReportCard,
  SeriesToolbar,
  UploadCard,
} from './IntakePanel';
import Viewer, { type SelectedSeries } from './Viewer';
import AnalysisPanel from './AnalysisPanel';
import { AnalysisReviewProvider, type FindingFocus } from './AnalysisReview';
import CandidateDetail from './CandidateDetail';
import ReviewWorkspace, { ComparisonOverview } from './ReviewWorkspace';
import UtilityWorkspace from './UtilityWorkspace';
import ExtendedWorkspace from './ExtendedWorkspace';
import IntegratedReview from './IntegratedReview';

// Three.js is local and loaded only when the 3D area is enabled. This keeps
// initial intake/report rendering independent of a WebGL-capable browser.
const SurfacePanel = lazy(() => import('./SurfacePanel'));

/** Menu IDs are UI routes only; no patient identifiers enter browser history. */
const menus = [
  {id:'integrated',title:'종합 검토',icon:<FactCheckOutlined/>},
  {id:'home',title:'검사 등록',icon:<FolderOutlined/>},
  {id:'viewer',title:'CT 영상 열람',icon:<VisibilityOutlined/>},
  {id:'analysis',title:'AI 분석 · 3D',icon:<ViewInAr/>},
  {id:'reports',title:'판독소견 · 구조화',icon:<DescriptionOutlined/>},
  {id:'compare',title:'소견 · AI 대조',icon:<CompareArrows/>},
  {id:'summary',title:'검토 · 정리본',icon:<FactCheckOutlined/>},
  {id:'documents',title:'문서 · OCR',icon:<DocumentScannerOutlined/>},
  {id:'models',title:'독립 모델 비교',icon:<HubOutlined/>},
  {id:'prior',title:'이전 CT 비교',icon:<History/>},
  {id:'evaluation',title:'평가 · 지원 범위',icon:<AssessmentOutlined/>},
  {id:'maintenance',title:'백업 · 데이터 관리',icon:<BackupOutlined/>},
] as const;
type MenuId=typeof menus[number]['id'];
function initialMenu():MenuId { const id=window.location.hash.slice(1);return menus.some(m=>m.id===id)?id as MenuId:'integrated'; }

/**
 * 흉부 CT 검토실 최상위 컴포넌트
 * 서버 연결, 등록된 검사 목록, 사용자 화면 환경설정을 관리하고
 * 선택한 메뉴의 작업 영역만 노출하고 필요한 보조 패널을 함께 제공한다.
 */
export default function App() {
  // 로컬 백엔드 서버 상태
  const [health, setHealth] = useState<Health | null>(null);
  // 등록된 검사(Study) 목록
  const [studies, setStudies] = useState<Study[]>([]);
  // 사용자 환경설정 (입체 구조 표시 여부 등)
  const [prefs, setPrefs] = useState<Preferences>({ show_structure: true });
  // 초기 로딩 상태
  const [loading, setLoading] = useState(true);
  // 전체 통신 오류 메시지
  const [error, setError] = useState('');
  // 환경설정 저장 중 상태
  const [saving, setSaving] = useState(false);
  // 연결 재시도 트리거 카운터
  const [attempt, setAttempt] = useState(0);

  // 현재 열람을 위해 선택된 시리즈 정보
  const [selectedSeries, setSelectedSeries] = useState<SelectedSeries | null>(null);
  // 현재 선택된 검사 ID
  const [selectedStudy, setSelectedStudy] = useState('');
  const [findingFocus, setFindingFocus] = useState<FindingFocus | null>(null);
  const focusNonce = useRef(0);
  // This stable callback preserves Intake's source boundary effect identity.
  const handleSeriesSelected = useCallback((value: SelectedSeries | null) => {
    setSelectedSeries(value); if (!value) setFindingFocus(null);
  }, []);
  // 파일 전송 등 작업 중일 때 검사 변경 잠금 상태
  const [studySelectionLocked, setStudySelectionLocked] = useState(false);

  // 서버 연결 확인, 등록된 검사 목록 및 환경설정 비동기 조회
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setHealth(null);
    setStudies([]);

    Promise.all([
      request<Health>('health', controller.signal),
      request<{ items: Study[] }>('studies', controller.signal),
      request<Preferences>('preferences', controller.signal),
    ])
      .then(([h, s, p]) => {
        if (!controller.signal.aborted) {
          setHealth(h);
          setStudies(s.items);
          setPrefs(p);
          // 기존 선택 검사가 유효하면 유지하고, 등록된 검사가 1개인 경우 자동 선택
          setSelectedStudy((current) =>
            s.items.some((study) => study.id === current)
              ? current
              : s.items.length === 1
                ? s.items[0].id
                : '',
          );
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(
            `서버에 연결하지 못했습니다. 로컬 서버 실행 상태를 확인해 주세요. ${e.message}`,
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [attempt]);

  /** 입체 구조 영역 노출 여부 토글 및 서버 저장 */
  async function toggleStructure() {
    setSaving(true);
    setError('');
    try {
      setPrefs(
        await request<Preferences>('preferences', undefined, {
          show_structure: !prefs.show_structure,
        }),
      );
    } catch {
      setError('화면 설정을 저장하지 못했습니다. 다시 시도해 주세요.');
    } finally {
      setSaving(false);
    }
  }

  // Menu changes only visibility; mounted editors retain unsaved drafts and
  // selected results. Switching the actual study still resets study-owned state.
  const [menu,setMenu]=useState<MenuId>(initialMenu);
  const [mobileMenu,setMobileMenu]=useState(false);
  const [focus,setFocus]=useState(false);
  const contentRef=useRef<HTMLDivElement|null>(null);
  const connected=!!health;
  const active=menus.find(m=>m.id===menu)!;
  const reviewMenu=['reports','compare','summary'].includes(menu);
  const rightVisible=!focus&&['analysis','reports','compare'].includes(menu);
  useEffect(()=>{window.history.replaceState(null,'',`#${menu}`);contentRef.current?.scrollTo(0,0);},[menu]);
  // Browser back/hash links are bounded to the known UI routes.
  useEffect(()=>{const update=()=>setMenu(initialMenu());window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);
  function navigate(id:MenuId){setMenu(id);setMobileMenu(false);setFocus(false);}
  const navigation=<Stack sx={{height:'100%',p:2,boxSizing:'border-box'}} spacing={1.5}>
    <Stack direction="row" spacing={1} alignItems="center" sx={{py:1}}><HubOutlined color="primary"/><Box><Typography variant="subtitle1" fontWeight={750}>흉부 CT 검토실</Typography><Typography variant="caption" color="text.secondary">LOCAL WORKSPACE</Typography></Box></Stack>
    <FormControl fullWidth size="small"><InputLabel id="navigation-study-label">작업할 검사</InputLabel><Select labelId="navigation-study-label" label="작업할 검사" value={selectedStudy} onChange={e=>setSelectedStudy(e.target.value)} disabled={!connected||studySelectionLocked}>
      <MenuItem value="">검사 선택</MenuItem>{studies.map(study=><MenuItem key={study.id} value={study.id}>{study.study_date||'날짜 미상'} · {study.description||study.id.slice(0,8)}</MenuItem>)}
    </Select></FormControl>
    <List aria-label="작업 메뉴" sx={{flex:1,minHeight:0,overflowY:'auto',py:0}}>{menus.map(item=><ListItemButton key={item.id} selected={menu===item.id} aria-current={menu===item.id?'page':undefined} onClick={()=>navigate(item.id)} sx={{borderRadius:1.5,mb:.4,py:.7,transition:'none','&.Mui-selected.Mui-focusVisible':{bgcolor:'primary.dark',color:'primary.contrastText',outline:'2px solid',outlineColor:'primary.light',outlineOffset:1},'&.Mui-selected':{bgcolor:'primary.main',color:'primary.contrastText','&:hover':{bgcolor:'primary.dark'},'& .MuiListItemIcon-root':{color:'inherit'}}}}><ListItemIcon sx={{minWidth:34}}>{item.icon}</ListItemIcon><ListItemText primary={item.title} primaryTypographyProps={{fontSize:13,fontWeight:menu===item.id?700:500}}/>{['reports','compare','documents'].includes(item.id)&&<Chip aria-hidden size="small" label="선택" sx={{height:18,fontSize:10,bgcolor:menu===item.id?'rgba(255,255,255,.18)':undefined,color:menu===item.id?'inherit':'text.secondary'}}/>}</ListItemButton>)}</List>
    <Typography variant="caption" color="text.secondary">분석·문서 처리는 이 PC에서 실행</Typography>
  </Stack>;
  return <IntakeProvider connected={connected} studies={studies} selected={selectedStudy} onStudySelected={setSelectedStudy} onBusyChange={setStudySelectionLocked} onRefresh={()=>setAttempt(v=>v+1)} onSeriesSelected={handleSeriesSelected}>
    <AnalysisReviewProvider seriesId={selectedSeries?.seriesId||''}>
      <Box sx={{display:'flex',height:'100dvh',overflow:'hidden',bgcolor:'background.default'}}>
        <Box component="nav" aria-label="왼쪽 작업 탐색" sx={{display:{xs:'none',md:'block'},width:248,flexShrink:0,bgcolor:'#f8fbfd',borderRight:1,borderColor:'divider'}}>{navigation}</Box>
        <Drawer open={mobileMenu} onClose={()=>setMobileMenu(false)} sx={{display:{xs:'block',md:'none'},'& .MuiDrawer-paper':{width:264,bgcolor:'#f8fbfd'}}}>{navigation}</Drawer>
        <Box component="main" sx={{flex:1,minWidth:0,display:'flex',flexDirection:'column',height:'100%'}}>
          <Stack spacing={1} sx={{px:{xs:2,lg:3},py:1.5,borderBottom:1,borderColor:'divider',bgcolor:'#fcfdfe'}}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
              <Stack direction="row" alignItems="center" spacing={1}><IconButton aria-label="작업 메뉴 열기" onClick={()=>setMobileMenu(true)} sx={{display:{md:'none'}}}><MenuIcon/></IconButton><Box><Typography variant="overline" color="text.secondary">CHEST REVIEW</Typography><Typography variant="h5" component="h1">{active.title}</Typography></Box></Stack>
              <Stack direction="row" gap={1} flexWrap="wrap">
                <Chip size="small" variant="outlined" color={connected?'success':'default'} label={loading?'연결 확인 중':connected?'로컬 저장소 연결됨':'서버 연결 필요'}/>
                {/* Local help opens independently so current CT selection and
                    unsaved editing state stay in the original workspace. */}
                <Button size="small" startIcon={<HelpOutline/>} href="/user-manual.html" target="_blank" rel="noreferrer" aria-label="사용자 매뉴얼 (새 창)">사용자 매뉴얼</Button>
                {['analysis','reports','compare'].includes(menu)&&<Button size="small" aria-pressed={focus} onClick={()=>setFocus(v=>!v)}>{focus?'보조 패널 펼치기':'작업 영역 확대'}</Button>}
                <Button size="small" variant="outlined" startIcon={<Refresh/>} disabled={loading} onClick={()=>setAttempt(v=>v+1)}>새로고침</Button>
              </Stack>
            </Stack>
            {loading&&<LinearProgress aria-label="작업 공간 불러오는 중"/>}
            {error&&<Alert severity="error" action={<Button onClick={()=>setAttempt(v=>v+1)}>재시도</Button>}>{error}</Alert>}
          </Stack>
          <Box sx={{display:{xs:'block',lg:'flex'},flex:1,minHeight:0,overflowY:{xs:'auto',lg:'hidden'}}}>
            <Box ref={contentRef} sx={{flex:1,minWidth:0,p:{xs:2,lg:3},height:{lg:'100%'},overflowY:{lg:'auto'},boxSizing:'border-box'}}>
              <Box hidden={menu!=='home'}>
                <Box sx={{display:'grid',gridTemplateColumns:{xs:'1fr',xl:'minmax(0,1fr) minmax(320px,.8fr)'},gap:2}}>
                  <Stack spacing={2}><Paper variant="outlined" sx={{p:2.5}}><Typography variant="h6" component="h2" sx={{mb:1}}>등록된 검사</Typography>{!studies.length?<Typography color="text.secondary">{connected?'아직 등록된 검사가 없습니다.':'조회할 수 없음'}</Typography>:<Stack spacing={1}>{studies.map(study=><Button key={study.id} aria-label={`검사 선택: ${study.description||study.id.slice(0,8)}`} variant={selectedStudy===study.id?'contained':'outlined'} disabled={studySelectionLocked} onClick={()=>setSelectedStudy(study.id)} sx={{justifyContent:'flex-start',textAlign:'left',overflowWrap:'anywhere'}}>{study.study_date||'날짜 미상'} · {study.description||study.id.slice(0,8)}</Button>)}</Stack>}<Button sx={{mt:2}} onClick={()=>navigate('viewer')}>선택 검사 영상으로 이동</Button></Paper><UploadCard/></Stack>
                  <ModelStatusCard/>
                </Box>
              </Box>
              <Box hidden={menu!=='integrated'}><IntegratedReview key={`ct-${selectedStudy}`} onNavigate={navigate} onFinding={target=>{focusNonce.current+=1;setFindingFocus({...target,nonce:focusNonce.current});navigate('analysis');}}/></Box>
              <Box hidden={!['viewer','analysis'].includes(menu)}><SeriesToolbar/></Box>
              {/* Keep the viewer and analysis state mounted, so menu changes do
                  not reload DICOM or clear the candidate selected for review. */}
              <Box hidden={menu!=='viewer'}><Viewer selection={selectedSeries}/></Box>
              <Box hidden={menu!=='analysis'}><AnalysisPanel key={selectedSeries?.seriesId||'no-analysis-series'} selection={selectedSeries} focusRequest={findingFocus}/></Box>
              <Box hidden={!reviewMenu}><ReviewWorkspace key={`review-${selectedStudy}`} section={menu==='compare'?1:menu==='summary'?2:0}/></Box>
              <Box hidden={!['documents','maintenance'].includes(menu)}><UtilityWorkspace key={`utility-${selectedStudy}`} section={menu==='maintenance'?'maintenance':'documents'}/></Box>
              <Box hidden={!['models','prior','evaluation'].includes(menu)}><ExtendedWorkspace key={`extended-${selectedStudy}-${selectedSeries?.seriesId||''}`} section={menu==='prior'?'prior':menu==='evaluation'?'evaluation':'models'}/></Box>
            </Box>
            {rightVisible&&<Box component="aside" aria-label="선택 작업 보조 패널" sx={{width:{lg:360,xl:400},flexShrink:0,p:2,boxSizing:'border-box',height:{lg:'100%'},overflowY:{lg:'auto'},borderLeft:{lg:1},borderTop:{xs:1,lg:0},borderColor:'divider',bgcolor:'#fcfdfe'}}><Stack spacing={2}>
              {menu==='reports'&&<ReportCard/>}
              {menu==='analysis'&&<><CandidateDetail/><FormControlLabel control={<Switch checked={prefs.show_structure} onChange={toggleStructure} disabled={!connected||saving}/>} label="입체 구조 영역"/>{prefs.show_structure&&<Suspense fallback={<LinearProgress aria-label="3D 화면 준비 중"/>}><SurfacePanel/></Suspense>}</>}
              {menu==='compare'&&<><ComparisonOverview onOpen={()=>navigate('compare')}/><CandidateDetail/></>}
            </Stack></Box>}
          </Box>
        </Box>
      </Box>
    </AnalysisReviewProvider>
  </IntakeProvider>;
}
