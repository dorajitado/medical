// SurfacePanel.tsx — 서버가 실제 분할 마스크에서 만든 환자 좌표 3D 표면.
// 외부 모델/텍스처/폰트를 요청하지 않는다. 실행 변경과 unmount에서 GPU 자원을 해제한다.
import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Checkbox, FormControlLabel, LinearProgress, Paper, Slider, Stack, Typography } from '@mui/material';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { request } from './api';
import { useAnalysisReview } from './AnalysisReview';

type MeshData = {
  id: string; title: string; color: string; candidate_id: string | null;
  vertices_lps_mm: number[]; triangles: number[]; marching_step: number;
  representation?:string;
};
type Surfaces = { run_id: string; series_id: string; objects: MeshData[]; limitations: string[] };
type View = {
  meshes: Map<string, THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>>;
  marker: THREE.Mesh; camera: THREE.PerspectiveCamera; controls: OrbitControls;
  centre: THREE.Vector3; distance: number; render: () => void;
};

export default function SurfacePanel() {
  const { result, selectedFinding, selectCandidate } = useAnalysisReview();
  const [payload, setPayload] = useState<Surfaces | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [opacity, setOpacity] = useState(.65);
  const [wireframe, setWireframe] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<View | null>(null);
  const activePayload = payload?.run_id === result?.run_id ? payload : null;

  // A run ID is the fetch boundary: late results cannot replace another run.
  useEffect(() => {
    const control = new AbortController();
    setPayload(null); setError(''); setLoading(false); setEnabled([]);
    if (!result) return;
    setLoading(true);
    request<Surfaces>(`analyses/${result.run_id}/surfaces`, control.signal)
      .then(data => {
        if (!control.signal.aborted && data.run_id === result.run_id && data.series_id === result.series_id) {
          setPayload(data); setEnabled(data.objects.map(o => o.id));
        }
      })
      .catch(e => { if (!control.signal.aborted) setError(e.message); })
      .finally(() => { if (!control.signal.aborted) setLoading(false); });
    return () => control.abort();
  }, [result?.run_id, attempt]);

  useEffect(() => {
    const container = host.current;
    if (!activePayload?.objects.length || !container) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); }
    catch { setError('WebGL 3D 화면을 초기화할 수 없습니다. 브라우저의 하드웨어 가속을 확인해 주세요.'); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.domElement.setAttribute('aria-label', '본인 CT 분할 기반 3D');
    renderer.domElement.style.touchAction = 'none';
    renderer.domElement.style.display = 'block';
    const contextLost = (event: Event) => {
      event.preventDefault();
      setError('3D 그래픽 연결이 중단되었습니다. 재시도로 화면을 다시 생성해 주세요.');
    };
    renderer.domElement.addEventListener('webglcontextlost', contextLost);
    container.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#101923');
    scene.add(new THREE.AmbientLight(0xffffff, 1.8));
    const light = new THREE.DirectionalLight(0xffffff, 2.2);
    light.position.set(200, -500, 600); scene.add(light);
    const group = new THREE.Group(); scene.add(group);
    const meshes: View['meshes'] = new Map();
    for (const object of activePayload.objects) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(object.vertices_lps_mm, 3));
      geometry.setIndex(object.triangles); geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({ color: object.color, roughness: .65, side: THREE.DoubleSide, transparent: true, opacity: .65 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.userData.candidateId = object.candidate_id;
      mesh.userData.objectId = object.id;
      mesh.userData.isBox = object.representation==='detection_box_not_segmentation';
      group.add(mesh); meshes.set(object.id, mesh);
    }
    const bounds = new THREE.Box3().setFromObject(group);
    const centre = bounds.getCenter(new THREE.Vector3());
    const extent = Math.max(bounds.getSize(new THREE.Vector3()).length(), 10);
    const camera = new THREE.PerspectiveCamera(40, 1, .1, extent * 30);
    camera.up.set(0, 0, 1); // LPS +Z is superior; no arbitrary patient-axis flip.
    const distance = extent * 1.6;
    camera.position.copy(centre).add(new THREE.Vector3(0, -distance, distance * .12));
    const controls = new OrbitControls(camera, renderer.domElement);
    renderer.domElement.tabIndex = 0;
    controls.listenToKeyEvents(renderer.domElement);
    controls.target.copy(centre); controls.minDistance = extent * .03; controls.maxDistance = extent * 10;
    controls.update(); controls.saveState();
    const marker = new THREE.Mesh(new THREE.SphereGeometry(Math.max(extent * .013, 1), 20, 12),
      new THREE.MeshBasicMaterial({ color: '#ffff33', depthTest: false }));
    marker.visible = false; marker.renderOrder = 100; scene.add(marker);
    const render = () => renderer.render(scene, camera);
    const resize = () => {
      renderer.setSize(Math.max(1, container.clientWidth), 320, false);
      camera.aspect = Math.max(1, container.clientWidth) / 320; camera.updateProjectionMatrix(); render();
    };
    const observer = new ResizeObserver(resize); observer.observe(container);
    controls.addEventListener('change', render);
    resize();
    // Picking the actual candidate surface selects the same run-local candidate
    // used by the CT marker and detail panel. Dragging the camera is not a pick.
    let start: [number, number] | null = null;
    const down = (event: PointerEvent) => { start = [event.clientX, event.clientY]; };
    const up = (event: PointerEvent) => {
      if (!start || Math.hypot(start[0] - event.clientX, start[1] - event.clientY) > 4) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const pointer = new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      const ray = new THREE.Raycaster(); ray.setFromCamera(pointer, camera);
      const targets = [...meshes.values()].filter(m => m.visible && m.userData.candidateId);
      const hit = ray.intersectObjects(targets)[0];
      if (hit) selectCandidate(hit.object.userData.candidateId as string);
    };
    renderer.domElement.addEventListener('pointerdown', down);
    renderer.domElement.addEventListener('pointerup', up);
    view.current = { meshes, marker, camera, controls, centre, distance, render };
    return () => {
      view.current = null; observer.disconnect(); controls.dispose();
      renderer.domElement.removeEventListener('pointerdown', down); renderer.domElement.removeEventListener('pointerup', up);
      renderer.domElement.removeEventListener('webglcontextlost', contextLost);
      for (const mesh of meshes.values()) { mesh.geometry.dispose(); mesh.material.dispose(); }
      marker.geometry.dispose(); (marker.material as THREE.Material).dispose();
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
    };
  }, [activePayload, selectCandidate]);

  // Viewer settings never regenerate masks or quantitative measurements.
  useEffect(() => {
    const current = view.current;
    if (!current) return;
    for (const [id, mesh] of current.meshes) {
      mesh.visible = enabled.includes(id);
      mesh.material.opacity = opacity; mesh.material.wireframe = !!mesh.userData.isBox||wireframe;
      mesh.material.depthWrite = opacity > .95;
      mesh.material.emissive.set(mesh.userData.candidateId === selectedFinding?.id ? '#674600' : '#000000');
    }
    current.marker.visible = !!selectedFinding;
    if (selectedFinding) current.marker.position.fromArray(selectedFinding.representative_lps_mm);
    current.render();
  }, [enabled, opacity, wireframe, selectedFinding, payload]);

  function reset() {
    const current = view.current;
    if (!current) return;
    // OrbitControls also owns zoom/target state; reset through its public API
    // rather than only moving the camera while leaving internal state behind.
    current.controls.reset(); current.render();
  }
  return <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1}>
      <Typography variant="h6" component="h3">내 CT의 입체 구조</Typography>
      {!result && <Typography variant="body2" color="text.secondary">완료된 분석 결과를 선택하면 실제 분할로 3D를 생성합니다.</Typography>}
      {loading && <LinearProgress aria-label="실제 분할 3D 생성 중" />}
      {error && <Alert severity="error" action={<Button onClick={() => setAttempt(v => v + 1)}>재시도</Button>}>{error}</Alert>}
      {activePayload && !activePayload.objects.length && <Typography variant="body2">표시할 분할 영역이 없습니다. 정상 판정을 뜻하지 않습니다.</Typography>}
      <Box ref={host} sx={{ width: '100%', minWidth: 0, height: activePayload?.objects.length ? 320 : 0, overflow: 'hidden' }} />
      {!!activePayload?.objects.length && <>
        <Typography variant="caption">드래그 회전 · 휠 확대 · 오른쪽 드래그 이동 · LPS(mm)</Typography>
        <Button size="small" onClick={reset}>3D 시점 초기화</Button>
        <FormControlLabel control={<Checkbox checked={wireframe} onChange={(_, checked) => setWireframe(checked)} />} label="3D 윤곽선" />
        <Typography variant="caption">3D 불투명도 {Math.round(opacity * 100)}%</Typography>
        <Slider aria-label="3D 불투명도" min={.1} max={1} step={.05} value={opacity} onChange={(_, value) => setOpacity(value as number)} />
        {activePayload.objects.map(object => <FormControlLabel key={object.id} sx={{ m: 0 }}
          control={<Checkbox size="small" inputProps={{ 'aria-label': `3D 구조 표시: ${object.title}` }} checked={enabled.includes(object.id)} onChange={(_, checked) => setEnabled(previous => checked ? [...previous, object.id] : previous.filter(id => id !== object.id))} />}
          label={<Typography variant="caption">{object.title}{object.marching_step > 1 ? ` · 표시 간격 ${object.marching_step}` : ''}</Typography>} />)}
        {selectedFinding && <Typography variant="caption" data-testid="3d-selected-candidate">3D 표식: {selectedFinding.title} · {selectedFinding.id}</Typography>}
        <Typography variant="caption" color="text.secondary">표면은 시각화용입니다. 크기·부피는 원본 복셀에서 계산합니다.</Typography>
      </>}
    </Stack>
  </Paper>;
}
