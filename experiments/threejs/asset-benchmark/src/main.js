import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import {
  createAegisDrone,
  disposeHierarchy,
  setExplodeAmount,
  setWireframe,
} from './asset.js';
import './style.css';

const canvas = document.querySelector('#viewport');
const errorOverlay = document.querySelector('#error-overlay');
const errorMessage = document.querySelector('#error-message');

let renderer;
try {
  renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
  });
} catch (error) {
  errorMessage.textContent = error instanceof Error ? error.message : String(error);
  errorOverlay.hidden = false;
  throw error;
}

renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x080d12);
scene.fog = new THREE.FogExp2(0x080d12, 0.055);

const camera = new THREE.PerspectiveCamera(
  34,
  window.innerWidth / window.innerHeight,
  0.1,
  70,
);
camera.position.set(4.4, 2.7, 5.5);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.target.set(0, 0.1, 0);
controls.minDistance = 3.4;
controls.maxDistance = 9;
controls.maxPolarAngle = Math.PI * 0.72;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.65;

const pmrem = new THREE.PMREMGenerator(renderer);
const roomEnvironment = new RoomEnvironment();
scene.environment = pmrem.fromScene(roomEnvironment, 0.035).texture;
roomEnvironment.dispose();
pmrem.dispose();

const keyLight = new THREE.DirectionalLight(0xbde9ff, 3.6);
keyLight.name = 'KeyLight';
keyLight.position.set(4, 6, 5);
keyLight.castShadow = true;
keyLight.shadow.mapSize.set(1536, 1536);
keyLight.shadow.camera.near = 0.5;
keyLight.shadow.camera.far = 18;
keyLight.shadow.camera.left = -4;
keyLight.shadow.camera.right = 4;
keyLight.shadow.camera.top = 4;
keyLight.shadow.camera.bottom = -4;
keyLight.shadow.bias = -0.0003;
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0xff7a3d, 2.4);
rimLight.name = 'RimLight';
rimLight.position.set(-4, 2.5, -4);
scene.add(rimLight);

const fillLight = new THREE.HemisphereLight(0x7ec8e8, 0x111820, 1.15);
fillLight.name = 'FillLight';
scene.add(fillLight);

const ground = new THREE.Mesh(
  new THREE.CircleGeometry(12, 96),
  new THREE.MeshStandardMaterial({
    color: 0x0b1218,
    metalness: 0.35,
    roughness: 0.82,
  }),
);
ground.name = 'PreviewGround';
ground.rotation.x = -Math.PI / 2;
ground.position.y = -1.08;
ground.receiveShadow = true;
scene.add(ground);

const grid = new THREE.GridHelper(18, 36, 0x23414c, 0x16272f);
grid.name = 'PreviewGrid';
grid.position.y = -1.065;
grid.material.opacity = 0.38;
grid.material.transparent = true;
scene.add(grid);

const beaconGeometry = new THREE.CylinderGeometry(0.014, 0.014, 1.6, 8);
const beaconMaterial = new THREE.MeshBasicMaterial({
  color: 0x1f6e7d,
  transparent: true,
  opacity: 0.28,
  depthWrite: false,
});
const beacons = new THREE.InstancedMesh(beaconGeometry, beaconMaterial, 8);
beacons.name = 'PreviewBeacons';
const beaconMatrix = new THREE.Matrix4();
for (let index = 0; index < 8; index += 1) {
  const angle = (index / 8) * Math.PI * 2;
  beaconMatrix.makeTranslation(Math.cos(angle) * 4.5, -0.25, Math.sin(angle) * 4.5);
  beacons.setMatrixAt(index, beaconMatrix);
}
beacons.instanceMatrix.needsUpdate = true;
scene.add(beacons);

const asset = createAegisDrone();
asset.root.position.y = 0.02;
scene.add(asset.root);

const mixer = new THREE.AnimationMixer(asset.root);
const patrolAction = mixer.clipAction(asset.clips[0]);
patrolAction.play();

const clock = new THREE.Clock();
const state = {
  explodeTarget: 0,
  explodeValue: 0,
  wireframe: false,
};

const metrics = {
  triangles: document.querySelector('#triangles'),
  drawCalls: document.querySelector('#draw-calls'),
  geometries: document.querySelector('#geometries'),
  materials: document.querySelector('#materials'),
};

function updateMetrics() {
  metrics.triangles.textContent = renderer.info.render.triangles.toLocaleString();
  metrics.drawCalls.textContent = renderer.info.render.calls.toString();
  metrics.geometries.textContent = renderer.info.memory.geometries.toString();
  metrics.materials.textContent = Object.keys(asset.materials).length.toString();
}

function damp(current, target, lambda, delta) {
  return THREE.MathUtils.lerp(current, target, 1 - Math.exp(-lambda * delta));
}

function render() {
  const delta = Math.min(clock.getDelta(), 0.05);
  const elapsed = clock.elapsedTime;

  controls.update(delta);
  mixer.update(delta);

  state.explodeValue = damp(state.explodeValue, state.explodeTarget, 8, delta);
  setExplodeAmount(asset.root, state.explodeValue);

  asset.root.position.y = 0.02 + Math.sin(elapsed * 1.35) * 0.055;
  asset.root.rotation.z = Math.sin(elapsed * 0.72) * 0.012;
  asset.animated.leftRotor.rotation.z -= delta * 9;
  asset.animated.rightRotor.rotation.z += delta * 9;

  const pulse = 0.72 + Math.sin(elapsed * 4.2) * 0.28;
  asset.animated.sensorLens.material.emissiveIntensity = 3.6 + pulse * 2.4;
  asset.animated.leftGlow.scale.setScalar(0.95 + pulse * 0.08);
  asset.animated.rightGlow.scale.setScalar(0.95 + pulse * 0.08);

  renderer.render(scene, camera);
  updateMetrics();
}
renderer.setAnimationLoop(render);

function setActive(button, active) {
  button.classList.toggle('active', active);
}

async function exportAsset(button) {
  const previousLabel = button.lastChild.textContent;
  button.disabled = true;
  button.lastChild.textContent = ' EXPORTING…';

  try {
    asset.root.updateMatrixWorld(true);
    const exporter = new GLTFExporter();
    const data = await exporter.parseAsync(asset.root, {
      binary: true,
      trs: true,
      onlyVisible: true,
      animations: asset.clips,
      includeCustomExtensions: true,
    });
    const blob = new Blob([data], { type: 'model/gltf-binary' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'aegis-m4-threejs.glb';
    anchor.click();
    URL.revokeObjectURL(url);
    document.querySelector('#asset-state').textContent = 'GLB EXPORTED';
  } catch (error) {
    console.error(error);
    document.querySelector('#asset-state').textContent = 'EXPORT FAILED';
  } finally {
    button.disabled = false;
    button.lastChild.textContent = previousLabel;
  }
}

document.querySelector('.toolbar').addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;

  switch (button.dataset.action) {
    case 'rotate':
      controls.autoRotate = !controls.autoRotate;
      setActive(button, controls.autoRotate);
      break;
    case 'explode':
      state.explodeTarget = state.explodeTarget > 0.5 ? 0 : 1;
      setActive(button, state.explodeTarget > 0.5);
      document.querySelector('#asset-state').textContent =
        state.explodeTarget > 0.5 ? 'ASSEMBLY VIEW' : 'PATROL';
      break;
    case 'wireframe':
      state.wireframe = !state.wireframe;
      setWireframe(asset.materials, state.wireframe);
      setActive(button, state.wireframe);
      break;
    case 'reset':
      camera.position.set(4.4, 2.7, 5.5);
      controls.target.set(0, 0.1, 0);
      controls.update();
      break;
    case 'export':
      exportAsset(button);
      break;
    default:
      break;
  }
});

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
}
window.addEventListener('resize', resize);

canvas.addEventListener('webglcontextlost', (event) => {
  event.preventDefault();
  errorMessage.textContent = 'Graphics context lost. Waiting for recovery…';
  errorOverlay.hidden = false;
});

canvas.addEventListener('webglcontextrestored', () => {
  errorOverlay.hidden = true;
});

window.addEventListener(
  'pagehide',
  () => {
    renderer.setAnimationLoop(null);
    mixer.stopAllAction();
    mixer.uncacheRoot(asset.root);
    disposeHierarchy(asset.root, asset.materials);
    ground.geometry.dispose();
    ground.material.dispose();
    grid.geometry.dispose();
    grid.material.dispose();
    beaconGeometry.dispose();
    beaconMaterial.dispose();
    scene.environment?.dispose();
    controls.dispose();
    renderer.dispose();
  },
  { once: true },
);
