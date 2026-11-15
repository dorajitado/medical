import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, CircularProgress, Paper, Stack, TextField, Typography } from '@mui/material';
import { request } from './api';

export type SelectedSeries = { studyId: string; seriesId: string; description: string };
type Geometry = { supported: boolean; reasons?: string[]; shape_xyz?: number[]; spacing_xyz?: (number|null)[]; warnings?: string[] };
type Probe = { hu: number|null; patient_lps_mm: number[]; padding: boolean; source_instance_id: string };
export default function Viewer({ selection }: { selection: SelectedSeries|null }) {
  const [url,setUrl] = useState('');
  const [geometry,setGeometry] = useState<Geometry|null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [retry,setRetry] = useState(0);
  const [point,setPoint] = useState([0,0,0]);
  const [end,setEnd] = useState([0,0,0]);
  const [sample,setSample] = useState<Probe|null>(null);
  const [length,setLength] = useState<number|null>(null);
  const [measuring,setMeasuring] = useState(false);
  const generation=useRef(0);
  useEffect(() => {
    generation.current+=1;
    const abort=new AbortController();
    setUrl('');setGeometry(null);setError('');setSample(null);setLength(null);setPoint([0,0,0]);setEnd([0,0,0]);
    if(!selection) { setBusy(false);return; }
    setBusy(true);
    request<Geometry>(`series/${selection.seriesId}/geometry`,abort.signal)
      .then(async geo => {
        if(abort.signal.aborted)return;
        setGeometry(geo);
        if(!geo.supported) return;
        const result=await request<{url:string}>(`series/${selection.seriesId}/open`,abort.signal,{},'POST');
        if(!abort.signal.aborted)setUrl(result.url);
      }).catch(e => {if(!abort.signal.aborted)setError(e.message);})
      .finally(()=>{if(!abort.signal.aborted)setBusy(false);});
    return()=>abort.abort();
  },[selection,retry]);
  async function measure() {
    if(!selection)return;
    const current=generation.current;
    setMeasuring(true);setError('');setSample(null);setLength(null);
    try {
      const [probe,distance]=await Promise.all([
        request<Probe>(`series/${selection.seriesId}/probe`,undefined,{x:point[0],y:point[1],z:point[2]},'POST'),
        request<{distance_mm:number}>(`series/${selection.seriesId}/distance`,undefined,{start:point,end},'POST')]);
      if(current===generation.current){setSample(probe);setLength(distance.distance_mm);}
    }catch(e){if(current===generation.current)setError(e instanceof Error?e.message:'측정 실패');}
    finally{setMeasuring(false);}
  }
  return <Paper variant="outlined" sx={{p:2,mb:3,minWidth:0}}>
    <Stack direction="row" justifyContent="space-between" gap={1} flexWrap="wrap"><Typography variant="h6">CT 영상 열람</Typography><Chip variant="outlined" label={selection?selection.description:'시리즈 선택 전'}/></Stack>
    {!selection&&<Typography color="text.secondary" sx={{py:5,textAlign:'center'}}>검사를 선택한 뒤 시리즈의 ‘영상 열기’를 눌러 주세요.</Typography>}
    {busy&&<Stack direction="row" spacing={1} sx={{my:2}}><CircularProgress size={20}/><Typography>원본 픽셀·절편 좌표 확인 및 로컬 뷰어 연결 중</Typography></Stack>}
    {geometry&&!geometry.supported&&<Alert severity="warning" sx={{my:2}}>{geometry.reasons?.join(' ')}</Alert>}
    {geometry?.warnings?.map(w=><Alert key={w} severity="info" sx={{my:1}}>{w}</Alert>)}
    {error&&<Alert severity="error" sx={{my:2}} action={<Button color="inherit" disabled={busy} onClick={()=>setRetry(n=>n+1)}>다시 연결</Button>}>{error}</Alert>}
    {url&&<>
      <Typography variant="body2" color="text.secondary" sx={{my:1}}>OHIF 도구에서 창 조절·확대·이동·거리·Probe를 사용할 수 있습니다. MPR은 3개 이상 절편에서 선택하세요.</Typography>
      <Box component="iframe" title="OHIF CT 영상 뷰어" src={url} sx={{width:'100%',height:'min(760px, 80vh)',minHeight:460,border:0,bgcolor:'#111b24'}}/>
      <Button href={url} target="_blank" rel="noopener">뷰어를 별도 창으로 열기</Button>
    </>}
    {geometry?.supported&&<Box sx={{mt:2}}>
      <Typography variant="subtitle2">원본 복셀의 HU·거리 확인</Typography>
      <Typography variant="caption" color="text.secondary">0부터 시작하는 열 X·행 Y·정렬 절편 Z 인덱스. 환자 좌표는 DICOM LPS(mm)입니다. 화면 보간값과 구분합니다.</Typography>
      {[{label:'시작점',values:point,set:setPoint},{label:'끝점',values:end,set:setEnd}].map(group=><Stack key={group.label} direction="row" spacing={1} sx={{my:1,flexWrap:'wrap',rowGap:1}}><Typography sx={{minWidth:50}}>{group.label}</Typography>{group.values.map((value,axis)=><TextField key={axis} size="small" type="number" label={`${group.label} ${'XYZ'[axis]}`} value={value} disabled={measuring} onChange={e=>{const next=[...group.values];next[axis]=Number(e.target.value);group.set(next);setSample(null);setLength(null);}} slotProps={{htmlInput:{min:0,max:(geometry.shape_xyz?.[axis]??1)-1,step:1}}} sx={{width:100}}/>)}</Stack>)}
      <Button onClick={()=>void measure()} disabled={measuring||busy} variant="outlined">원본 HU·거리 계산</Button>
      <Box aria-live="polite" sx={{mt:1}}>{sample&&<Typography>원본 HU: {sample.hu===null?'패딩 픽셀 (측정 제외)':sample.hu.toFixed(3)} · LPS: {sample.patient_lps_mm.map(v=>v.toFixed(3)).join(', ')} mm</Typography>}{length!==null&&<Typography>거리: {length.toFixed(3)} mm</Typography>}</Box>
    </Box>}
  </Paper>;
}
