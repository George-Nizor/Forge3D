import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const DEG = Math.PI / 180;

function name(object, value, metadata = {}) {
  object.name = value;
  object.userData = { ...object.userData, ...metadata };
  return object;
}

function mesh(geometry, material, objectName, metadata) {
  const value = name(new THREE.Mesh(geometry, material), objectName, metadata);
  value.castShadow = true;
  value.receiveShadow = true;
  return value;
}

function roundedBox(width, height, depth, radius, material, objectName) {
  return mesh(
    new RoundedBoxGeometry(width, height, depth, 5, radius),
    material,
    objectName,
  );
}

function createWingGeometry(side) {
  const shape = new THREE.Shape();
  const sign = Math.sign(side);
  shape.moveTo(0, -0.28);
  shape.lineTo(1.12 * sign, -0.2);
  shape.lineTo(1.34 * sign, 0.08);
  shape.lineTo(0.76 * sign, 0.28);
  shape.lineTo(0.12 * sign, 0.22);
  shape.closePath();

  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: 0.12,
    bevelEnabled: true,
    bevelSegments: 3,
    steps: 1,
    bevelSize: 0.035,
    bevelThickness: 0.035,
  });
  geometry.center();
  geometry.rotateX(90 * DEG);
  return geometry;
}

function createVentBank(material, side) {
  const group = name(new THREE.Group(), `${side > 0 ? 'Right' : 'Left'}VentBank`, {
    forge3dRole: 'detail',
  });
  const geometry = new RoundedBoxGeometry(0.05, 0.045, 0.34, 2, 0.015);

  for (let index = 0; index < 5; index += 1) {
    const vent = mesh(geometry, material, `Vent_${side}_${index}`);
    vent.position.set(side * (0.37 + index * 0.075), 0.225, 0.31);
    vent.rotation.z = side * -8 * DEG;
    group.add(vent);
  }

  return group;
}

function createThruster(materials, side) {
  const label = side > 0 ? 'Right' : 'Left';
  const root = name(new THREE.Group(), `${label}Thruster`, {
    forge3dRole: 'thruster',
    exportPart: true,
  });
  root.position.set(side * 1.04, -0.02, 0.14);

  const outer = mesh(
    new THREE.CylinderGeometry(0.32, 0.36, 0.42, 32, 2, true),
    materials.darkMetal,
    `${label}ThrusterHousing`,
  );
  outer.rotation.x = 90 * DEG;
  root.add(outer);

  const frontRing = mesh(
    new THREE.TorusGeometry(0.285, 0.055, 10, 32),
    materials.edgeMetal,
    `${label}ThrusterFrontRing`,
  );
  frontRing.position.z = 0.22;
  root.add(frontRing);

  const rearRing = frontRing.clone();
  rearRing.name = `${label}ThrusterRearRing`;
  rearRing.position.z = -0.22;
  root.add(rearRing);

  const glow = mesh(
    new THREE.CircleGeometry(0.235, 32),
    materials.thrusterGlow,
    `${label}ThrusterGlow`,
    { forge3dRole: 'emissive' },
  );
  glow.position.z = -0.235;
  glow.rotation.y = 180 * DEG;
  glow.castShadow = false;
  root.add(glow);

  const rotor = name(new THREE.Group(), `${label}ThrusterRotor`, {
    forge3dRole: 'animated',
  });
  rotor.position.z = -0.25;
  const bladeGeometry = new RoundedBoxGeometry(0.42, 0.035, 0.055, 2, 0.015);
  for (let index = 0; index < 4; index += 1) {
    const blade = mesh(bladeGeometry, materials.thrusterBlade, `${label}Blade_${index}`);
    blade.rotation.z = index * 45 * DEG;
    rotor.add(blade);
  }
  root.add(rotor);

  const brace = roundedBox(0.18, 0.18, 0.62, 0.04, materials.armor, `${label}ThrusterBrace`);
  brace.position.set(-side * 0.25, 0.02, -0.02);
  brace.rotation.z = side * 18 * DEG;
  root.add(brace);

  return { root, rotor, glow };
}

function createSensorHead(materials) {
  const yaw = name(new THREE.Group(), 'SensorYaw', {
    forge3dRole: 'animationPivot',
    exportPart: true,
  });
  yaw.position.set(0, 0.42, -0.02);

  const neck = mesh(
    new THREE.CylinderGeometry(0.2, 0.24, 0.18, 24),
    materials.darkMetal,
    'SensorNeck',
  );
  yaw.add(neck);

  const pitch = name(new THREE.Group(), 'SensorPitch', {
    forge3dRole: 'animationPivot',
  });
  pitch.position.y = 0.14;
  yaw.add(pitch);

  const housing = roundedBox(0.62, 0.34, 0.42, 0.11, materials.armor, 'SensorHousing');
  housing.position.z = 0.02;
  pitch.add(housing);

  const brow = roundedBox(0.54, 0.09, 0.12, 0.025, materials.edgeMetal, 'SensorBrow');
  brow.position.set(0, 0.11, 0.24);
  pitch.add(brow);

  const lensFrame = mesh(
    new THREE.CylinderGeometry(0.15, 0.15, 0.08, 32),
    materials.darkMetal,
    'PrimaryLensFrame',
  );
  lensFrame.rotation.x = 90 * DEG;
  lensFrame.position.set(0, -0.025, 0.245);
  pitch.add(lensFrame);

  const lens = mesh(
    new THREE.CircleGeometry(0.105, 32),
    materials.lens,
    'PrimaryLens',
    { forge3dRole: 'sensor' },
  );
  lens.position.set(0, -0.025, 0.29);
  lens.castShadow = false;
  pitch.add(lens);

  for (const side of [-1, 1]) {
    const auxiliary = mesh(
      new THREE.CircleGeometry(0.042, 20),
      materials.signal,
      `${side < 0 ? 'Left' : 'Right'}AuxiliaryLens`,
    );
    auxiliary.position.set(side * 0.205, -0.04, 0.235);
    auxiliary.castShadow = false;
    pitch.add(auxiliary);
  }

  const antenna = mesh(
    new THREE.CylinderGeometry(0.018, 0.028, 0.36, 12),
    materials.edgeMetal,
    'AntennaMast',
  );
  antenna.position.set(0.21, 0.33, -0.06);
  antenna.rotation.z = -8 * DEG;
  pitch.add(antenna);

  const antennaTip = mesh(
    new THREE.SphereGeometry(0.045, 16, 12),
    materials.signal,
    'AntennaBeacon',
  );
  antennaTip.position.set(0.235, 0.52, -0.06);
  pitch.add(antennaTip);

  return { yaw, pitch, lens };
}

function createUndercarriage(materials) {
  const root = name(new THREE.Group(), 'Undercarriage', {
    forge3dRole: 'support',
    exportPart: true,
  });

  const keel = roundedBox(0.54, 0.18, 0.72, 0.07, materials.darkMetal, 'Keel');
  keel.position.y = -0.37;
  root.add(keel);

  for (const side of [-1, 1]) {
    const strut = roundedBox(0.12, 0.5, 0.12, 0.035, materials.edgeMetal, `Strut_${side}`);
    strut.position.set(side * 0.34, -0.5, 0.02);
    strut.rotation.z = side * -20 * DEG;
    root.add(strut);

    const foot = roundedBox(0.35, 0.08, 0.2, 0.035, materials.darkMetal, `Foot_${side}`);
    foot.position.set(side * 0.43, -0.76, 0.08);
    root.add(foot);
  }

  return root;
}

function createMaterials() {
  const armor = new THREE.MeshPhysicalMaterial({
    color: 0xc9d2d6,
    metalness: 0.72,
    roughness: 0.3,
    clearcoat: 0.35,
    clearcoatRoughness: 0.25,
  });
  armor.name = 'M_ArmorCeramic';

  const darkMetal = new THREE.MeshStandardMaterial({
    color: 0x161d23,
    metalness: 0.92,
    roughness: 0.25,
  });
  darkMetal.name = 'M_DarkMechanism';

  const edgeMetal = new THREE.MeshStandardMaterial({
    color: 0x63737b,
    metalness: 0.88,
    roughness: 0.22,
  });
  edgeMetal.name = 'M_EdgeMetal';

  const accent = new THREE.MeshPhysicalMaterial({
    color: 0xc86a28,
    metalness: 0.7,
    roughness: 0.28,
    clearcoat: 0.4,
  });
  accent.name = 'M_IndustrialOrange';

  const lens = new THREE.MeshPhysicalMaterial({
    color: 0x102c34,
    emissive: 0x00d8ff,
    emissiveIntensity: 4.5,
    metalness: 0.25,
    roughness: 0.12,
    clearcoat: 1,
    clearcoatRoughness: 0.08,
  });
  lens.name = 'M_SensorCyan';

  const signal = new THREE.MeshStandardMaterial({
    color: 0xffb15a,
    emissive: 0xff5200,
    emissiveIntensity: 3.2,
    metalness: 0.25,
    roughness: 0.2,
  });
  signal.name = 'M_SignalOrange';

  const thrusterGlow = new THREE.MeshBasicMaterial({
    color: 0x58eaff,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  thrusterGlow.name = 'M_ThrusterGlow';

  const thrusterBlade = new THREE.MeshStandardMaterial({
    color: 0x263239,
    metalness: 0.8,
    roughness: 0.3,
  });
  thrusterBlade.name = 'M_ThrusterBlade';

  return {
    armor,
    darkMetal,
    edgeMetal,
    accent,
    lens,
    signal,
    thrusterGlow,
    thrusterBlade,
  };
}

function registerExplodable(object, direction, distance) {
  object.userData.homePosition = object.position.clone();
  object.userData.explodeOffset = direction.clone().normalize().multiplyScalar(distance);
}

function createAnimationClips() {
  const sensorTrack = new THREE.NumberKeyframeTrack(
    'SensorYaw.rotation[y]',
    [0, 1.8, 3.6],
    [-0.5, 0.5, -0.5],
  );
  sensorTrack.setInterpolation(THREE.InterpolateSmooth);

  const pitchTrack = new THREE.NumberKeyframeTrack(
    'SensorPitch.rotation[x]',
    [0, 0.9, 1.8, 2.7, 3.6],
    [0.03, -0.08, 0.03, 0.1, 0.03],
  );
  pitchTrack.setInterpolation(THREE.InterpolateSmooth);

  const leftThrusterTrack = new THREE.NumberKeyframeTrack(
    'LeftThruster.rotation[z]',
    [0, 1.8, 3.6],
    [0.015, -0.035, 0.015],
  );
  const rightThrusterTrack = new THREE.NumberKeyframeTrack(
    'RightThruster.rotation[z]',
    [0, 1.8, 3.6],
    [-0.015, 0.035, -0.015],
  );

  const clip = new THREE.AnimationClip('PatrolScan', 3.6, [
    sensorTrack,
    pitchTrack,
    leftThrusterTrack,
    rightThrusterTrack,
  ]);
  clip.optimize();
  return [clip];
}

export function createAegisDrone() {
  const materials = createMaterials();
  const root = name(new THREE.Group(), 'AegisM4', {
    forge3dSchema: 'forge3d.three.asset.v1',
    assetType: 'sentry_drone',
    units: 'meters',
    upAxis: 'Y',
    version: 1,
  });

  const chassis = name(new THREE.Group(), 'Chassis', {
    forge3dRole: 'body',
    exportPart: true,
  });
  root.add(chassis);

  const body = roundedBox(1.24, 0.5, 0.86, 0.16, materials.armor, 'MainArmor');
  chassis.add(body);

  const belly = roundedBox(0.98, 0.28, 0.7, 0.12, materials.darkMetal, 'MainBelly');
  belly.position.y = -0.24;
  chassis.add(belly);

  const topPlate = roundedBox(0.72, 0.08, 0.54, 0.025, materials.accent, 'TopServicePlate');
  topPlate.position.set(0, 0.29, -0.03);
  chassis.add(topPlate);

  const nose = roundedBox(0.74, 0.24, 0.18, 0.055, materials.edgeMetal, 'NoseFascia');
  nose.position.set(0, -0.02, 0.47);
  chassis.add(nose);

  const noseInset = roundedBox(0.48, 0.1, 0.04, 0.025, materials.darkMetal, 'NoseInset');
  noseInset.position.set(0, -0.02, 0.575);
  chassis.add(noseInset);

  chassis.add(createVentBank(materials.darkMetal, -1));
  chassis.add(createVentBank(materials.darkMetal, 1));

  for (const side of [-1, 1]) {
    const wing = mesh(
      createWingGeometry(side),
      materials.armor,
      `${side < 0 ? 'Left' : 'Right'}Wing`,
      { forge3dRole: 'wing', exportPart: true },
    );
    wing.position.set(0, 0.02, -0.06);
    root.add(wing);
    registerExplodable(wing, new THREE.Vector3(side, 0.2, 0), 0.55);

    const stripe = roundedBox(0.55, 0.055, 0.09, 0.02, materials.accent, `WingStripe_${side}`);
    stripe.position.set(side * 0.72, 0.13, -0.18);
    stripe.rotation.z = side * -8 * DEG;
    root.add(stripe);
    registerExplodable(stripe, new THREE.Vector3(side, 0.2, 0), 0.55);
  }

  const leftThruster = createThruster(materials, -1);
  const rightThruster = createThruster(materials, 1);
  root.add(leftThruster.root, rightThruster.root);
  registerExplodable(leftThruster.root, new THREE.Vector3(-1, 0.1, 0), 0.7);
  registerExplodable(rightThruster.root, new THREE.Vector3(1, 0.1, 0), 0.7);

  const sensor = createSensorHead(materials);
  root.add(sensor.yaw);
  registerExplodable(sensor.yaw, new THREE.Vector3(0, 1, 0), 0.55);

  const undercarriage = createUndercarriage(materials);
  root.add(undercarriage);
  registerExplodable(undercarriage, new THREE.Vector3(0, -1, 0), 0.45);

  const clips = createAnimationClips();

  root.traverse((object) => {
    if (object.isMesh) {
      object.userData.forge3dRole ??= 'renderMesh';
    }
  });

  return {
    root,
    materials,
    clips,
    animated: {
      sensorLens: sensor.lens,
      sensorPitch: sensor.pitch,
      leftRotor: leftThruster.rotor,
      rightRotor: rightThruster.rotor,
      leftGlow: leftThruster.glow,
      rightGlow: rightThruster.glow,
    },
  };
}

export function setExplodeAmount(root, amount) {
  root.traverse((object) => {
    const home = object.userData.homePosition;
    const offset = object.userData.explodeOffset;
    if (!home || !offset) return;
    object.position.copy(home).addScaledVector(offset, amount);
  });
}

export function setWireframe(materials, enabled) {
  Object.values(materials).forEach((material) => {
    if ('wireframe' in material) material.wireframe = enabled;
  });
}

export function disposeHierarchy(root, materials) {
  const geometries = new Set();
  root.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
  });
  geometries.forEach((geometry) => geometry.dispose());
  Object.values(materials).forEach((material) => material.dispose());
}
