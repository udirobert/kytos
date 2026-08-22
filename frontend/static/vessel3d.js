// vessel3d.js — Three.js κύτος vessel instrument
// Data-bound 3D vessel: liquid fill = ceiling headroom, amber cracks = warn/error
// audit flags, cyan droplets = info flags. The vessel's shape IS the run's state.
//
// Loaded as an ES module via import map (see meta.py). Falls back to the SVG
// vessel (in the HTML) if WebGL is unavailable.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

function initVessel3D() {
  var container = document.getElementById("vessel-canvas");
  var dataEl = document.getElementById("vessel-data");
  if (!container || !dataEl) return;

  var reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  // ── Parse vessel data ────────────────────────────────────────────────────
  var params;
  try {
    params = JSON.parse(dataEl.textContent || "{}");
  } catch (e) {
    return; // malformed data — SVG fallback
  }
  var fillPct = Math.max(6, Math.min(100, params.fill_pct || 0));
  var warnCount = params.warns || 0;
  var infoCount = params.infos || 0;

  // ── Constants ───────────────────────────────────────────────────────────
  var VESSEL_SEGMENTS = 64;
  var LIQUID_SEGMENTS = 48;
  var VESSEL_H = 5.0;
  var VESSEL_BOTTOM = -VESSEL_H / 2;
  var LIQUID_SCALE = 0.93;
  var fillLevel = VESSEL_BOTTOM + (fillPct / 100) * VESSEL_H;

  // ── Vessel profile (radius, y) — a κύtos flask shape ──────────────────────
  var profileRaw = [
    [0.02, -2.5],
    [0.8, -2.45],
    [1.5, -2.3],
    [2.2, -2.0],
    [2.8, -1.5],
    [3.2, -0.8],
    [3.4, -0.2],
    [3.3, 0.4],
    [3.0, 1.0],
    [2.4, 1.5],
    [2.0, 1.9],
    [2.0, 2.3],
    [1.5, 2.42],
    [0.5, 2.48],
    [0.02, 2.5],
  ];
  var profilePts = profileRaw.map(function (p) {
    return new THREE.Vector2(p[0], p[1]);
  });

  function vesselRadiusAt(y) {
    for (var i = 0; i < profilePts.length - 1; i++) {
      if (y >= profilePts[i].y && y <= profilePts[i + 1].y) {
        var t = (y - profilePts[i].y) / (profilePts[i + 1].y - profilePts[i].y);
        return profilePts[i].x + t * (profilePts[i + 1].x - profilePts[i].x);
      }
    }
    return 0;
  }

  // ── Renderer ────────────────────────────────────────────────────────────
  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch (e) {
    return; // No WebGL — SVG fallback stays visible
  }

  var w = container.clientWidth || 400;
  var h = container.clientHeight || 400;

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.localClippingEnabled = true;
  container.appendChild(renderer.domElement);
  container.classList.add("is-3d"); // hide SVG fallback

  // ── Scene & camera ──────────────────────────────────────────────────────
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
  camera.position.set(0, 1.5, 12);

  // ── Environment (for glass reflections) ──────────────────────────────────
  var pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();

  // ── Vessel group (bobs together) ─────────────────────────────────────────
  var vesselGroup = new THREE.Group();
  scene.add(vesselGroup);

  // ── Glass vessel ─────────────────────────────────────────────────────────
  var vesselGeo = new THREE.LatheGeometry(profilePts, VESSEL_SEGMENTS);
  var vesselMat = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    transmission: 1.0,
    roughness: 0.05,
    metalness: 0,
    thickness: 0.5,
    ior: 1.5,
    clearcoat: 1.0,
    clearcoatRoughness: 0.05,
    envMapIntensity: 1.0,
    side: THREE.DoubleSide,
  });
  var vessel = new THREE.Mesh(vesselGeo, vesselMat);
  vesselGroup.add(vessel);

  // ── Liquid ───────────────────────────────────────────────────────────────
  // Build liquid profile: vessel profile truncated at fillLevel, scaled to
  // fit inside the glass.
  var liquidPts = [];
  for (var i = 0; i < profilePts.length; i++) {
    var p = profilePts[i];
    if (p.y <= fillLevel) {
      liquidPts.push(new THREE.Vector2(p.x * LIQUID_SCALE, p.y));
    } else {
      var prev = liquidPts[liquidPts.length - 1];
      if (prev) {
        var tt = (fillLevel - prev.y) / (p.y - prev.y);
        var rr = prev.x + tt * (p.x * LIQUID_SCALE - prev.x);
        liquidPts.push(new THREE.Vector2(rr, fillLevel));
      }
      break;
    }
  }
  if (liquidPts.length < 2) {
    liquidPts.push(new THREE.Vector2(0.01, VESSEL_BOTTOM + 0.02));
  }

  var liquidGeo = new THREE.LatheGeometry(liquidPts, LIQUID_SEGMENTS);
  var liquidMat = new THREE.MeshPhysicalMaterial({
    color: 0x5eead4,
    emissive: 0x5eead4,
    emissiveIntensity: 0.35,
    roughness: 0.1,
    metalness: 0,
    transmission: 0.5,
    thickness: 2.0,
    ior: 1.33,
    opacity: 0.85,
    transparent: true,
    side: THREE.DoubleSide,
  });
  var liquid = new THREE.Mesh(liquidGeo, liquidMat);
  vesselGroup.add(liquid);

  // Inner glow at the liquid surface
  var liquidLight = new THREE.PointLight(0x5eead4, 2.0, 8);
  liquidLight.position.set(0, fillLevel + 0.4, 0);
  vesselGroup.add(liquidLight);

  // Clipping plane — animates from bottom to fillLevel on load
  var fillPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), VESSEL_BOTTOM);
  liquidMat.clippingPlanes = [fillPlane];

  // Top ring vertex indices for wave animation
  var topRingStart = (liquidPts.length - 1) * (LIQUID_SEGMENTS + 1);

  // ── Cracks (warn/error audit flags) ──────────────────────────────────────
  var cracksGroup = new THREE.Group();
  for (var ci = 0; ci < Math.min(warnCount, 6); ci++) {
    var baseAngle = (ci / Math.min(warnCount, 6)) * Math.PI * 2 + 0.3;
    var baseY = -0.8 + (ci % 3) * 0.6;
    var crackPts = [];
    for (var cj = 0; cj <= 6; cj++) {
      var ct = cj / 6;
      var cy = baseY + ct * 1.8;
      var cr = vesselRadiusAt(cy) * 1.02;
      var wobble = Math.sin(ct * 8 + ci * 2) * 0.12;
      var ca = baseAngle + wobble;
      crackPts.push(
        new THREE.Vector3(Math.cos(ca) * cr, cy, Math.sin(ca) * cr),
      );
    }
    var curve = new THREE.CatmullRomCurve3(crackPts);
    var tubeGeo = new THREE.TubeGeometry(curve, 20, 0.025, 6, false);
    var tubeMat = new THREE.MeshBasicMaterial({ color: 0xfbbf24 });
    cracksGroup.add(new THREE.Mesh(tubeGeo, tubeMat));
  }
  vesselGroup.add(cracksGroup);

  // ── Droplets (info audit flags) ──────────────────────────────────────────
  var dropletsGroup = new THREE.Group();
  for (var di = 0; di < Math.min(infoCount, 5); di++) {
    var sphereGeo = new THREE.SphereGeometry(0.1, 12, 12);
    var sphereMat = new THREE.MeshBasicMaterial({ color: 0x67e8f9 });
    var droplet = new THREE.Mesh(sphereGeo, sphereMat);
    var da = (di / Math.min(infoCount, 5)) * Math.PI * 2;
    droplet.position.set(
      Math.cos(da) * 1.5,
      fillLevel + 0.8 + (di % 2) * 0.5,
      Math.sin(da) * 1.5,
    );
    droplet.userData = { baseY: droplet.position.y, phase: di * 0.7 };
    dropletsGroup.add(droplet);
  }
  vesselGroup.add(dropletsGroup);

  // ── Ambient particles (atmosphere) ────────────────────────────────────────
  var particleCount = 80;
  var particleGeo = new THREE.BufferGeometry();
  var particlePos = new Float32Array(particleCount * 3);
  for (var pi = 0; pi < particleCount; pi++) {
    particlePos[pi * 3] = (Math.random() - 0.5) * 14;
    particlePos[pi * 3 + 1] = (Math.random() - 0.5) * 10;
    particlePos[pi * 3 + 2] = (Math.random() - 0.5) * 14;
  }
  particleGeo.setAttribute("position", new THREE.BufferAttribute(particlePos, 3));
  var particleMat = new THREE.PointsMaterial({
    color: 0x5eead4,
    size: 0.04,
    transparent: true,
    opacity: 0.35,
    sizeAttenuation: true,
  });
  var particles = new THREE.Points(particleGeo, particleMat);
  scene.add(particles);

  // ── Lighting ────────────────────────────────────────────────────────────
  scene.add(new THREE.AmbientLight(0x1a2535, 0.4));

  var belowLight = new THREE.PointLight(0x5eead4, 1.5, 12);
  belowLight.position.set(0, -3.5, 0);
  scene.add(belowLight);

  var aboveLight = new THREE.PointLight(0xffeed4, 0.4, 15);
  aboveLight.position.set(3, 4, 3);
  scene.add(aboveLight);

  // ── Controls ─────────────────────────────────────────────────────────────
  var controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.autoRotate = !reducedMotion;
  controls.autoRotateSpeed = 0.6;
  controls.minPolarAngle = Math.PI / 4.5;
  controls.maxPolarAngle = Math.PI / 1.8;
  controls.minDistance = 9;
  controls.maxDistance = 16;
  controls.enablePan = false;
  controls.enableZoom = false;
  controls.target.set(0, 0, 0);

  // ── Post-processing (bloom) ───────────────────────────────────────────────
  var composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));

  var bloomPass = new UnrealBloomPass(
    new THREE.Vector2(w, h),
    0.45, // strength
    0.4, // radius
    0.82, // threshold — only bright things bloom
  );
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  // ── Resize ────────────────────────────────────────────────────────────────
  function resize() {
    w = container.clientWidth || 400;
    h = container.clientHeight || 400;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    composer.setSize(w, h);
    bloomPass.setSize(w, h);
  }
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(container);
  }

  // ── Animation loop ───────────────────────────────────────────────────────
  var clock = new THREE.Clock();
  var fillT = reducedMotion ? 1 : 0;
  var fillDuration = 1.8;

  function animate() {
    requestAnimationFrame(animate);
    var dt = clock.getDelta();
    var t = clock.getElapsedTime();

    // Fill animation — clipping plane rises from bottom to fillLevel
    if (fillT < 1) {
      fillT = Math.min(1, fillT + dt / fillDuration);
      var eased = fillT * fillT * (3 - 2 * fillT); // smoothstep
      fillPlane.constant = VESSEL_BOTTOM + eased * (fillLevel - VESSEL_BOTTOM);
    }

    // Wave animation on the liquid surface
    if (!reducedMotion && fillT >= 1) {
      for (var wi = 0; wi <= LIQUID_SEGMENTS; wi++) {
        var angle = (wi / LIQUID_SEGMENTS) * Math.PI * 2;
        var wave =
          Math.sin(t * 2.0 + angle * 3) * 0.025 +
          Math.sin(t * 1.3 + angle * 5) * 0.012;
        liquidGeo.attributes.position.setY(topRingStart + wi, fillLevel + wave);
      }
      liquidGeo.attributes.position.needsUpdate = true;
    }

    // Droplet float
    if (!reducedMotion) {
      dropletsGroup.children.forEach(function (d) {
        d.position.y =
          d.userData.baseY + Math.sin(t * 1.5 + d.userData.phase) * 0.12;
      });

      // Particle drift upward
      var pos = particles.geometry.attributes.position;
      for (var ppi = 0; ppi < particleCount; ppi++) {
        pos.array[ppi * 3 + 1] += dt * 0.15;
        if (pos.array[ppi * 3 + 1] > 5) pos.array[ppi * 3 + 1] = -5;
      }
      pos.needsUpdate = true;

      // Subtle vessel bob
      vesselGroup.position.y = Math.sin(t * 0.5) * 0.05;
    }

    controls.update();
    composer.render();
  }

  animate();
}

initVessel3D();
