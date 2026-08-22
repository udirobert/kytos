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

function markNoWebGL() {
  document.documentElement.classList.add("no-webgl");
}

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
    markNoWebGL();
    return; // malformed data — SVG fallback
  }
  var fillPct = Math.max(6, Math.min(100, params.fill_pct || 0));
  var warnCount = params.warns || 0;
  var infoCount = params.infos || 0;

  // ── Constants ───────────────────────────────────────────────────────────
  // Reduce geometry segments on mobile/low-DPI for better performance.
  // Mobile devices have smaller screens so lower poly count is imperceptible.
  var isMobile = window.matchMedia("(max-width: 768px)").matches;
  var lowPerf = isMobile || (window.devicePixelRatio || 1) < 1.5;
  var VESSEL_SEGMENTS = lowPerf ? 48 : 80;
  var LIQUID_SEGMENTS = lowPerf ? 32 : 56;
  var VESSEL_H = 5.0;
  var VESSEL_BOTTOM = -VESSEL_H / 2;
  var LIQUID_SCALE = 0.93;
  var fillLevel = VESSEL_BOTTOM + (fillPct / 100) * VESSEL_H;
  var isHome = container.classList.contains("vessel-home");
  var isFullscreen = container.classList.contains("vessel-fullscreen");

  // ── Vessel profile (radius, y) — a κύτος flask shape ──────────────────────
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
    markNoWebGL();
    return; // No WebGL — SVG fallback stays visible
  }

  var w = container.clientWidth || 400;
  var h = container.clientHeight || 400;

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, lowPerf ? 1.5 : 2));
  renderer.setSize(w, h);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.4;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.localClippingEnabled = true;
  container.appendChild(renderer.domElement);
  container.classList.add("is-3d"); // hide SVG fallback
  document.documentElement.classList.remove("no-webgl");
  document.documentElement.classList.remove("vessel-pending");

  // ── Scene & camera ──────────────────────────────────────────────────────
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
  camera.position.set(0, 1.0, 13);

  // ── Environment (for glass reflections) ──────────────────────────────────
  var pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();

  // ── Vessel group ─────────────────────────────────────────────────────────
  var vesselGroup = new THREE.Group();
  scene.add(vesselGroup);

  // ── Glass vessel (outer shell) ──────────────────────────────────────────
  var vesselGeo = new THREE.LatheGeometry(profilePts, VESSEL_SEGMENTS);
  var vesselMat = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    transmission: 1.0,
    roughness: 0.04,
    metalness: 0,
    thickness: 0.6,
    ior: 1.5,
    clearcoat: 1.0,
    clearcoatRoughness: 0.03,
    envMapIntensity: 1.8,
    side: THREE.DoubleSide,
    attenuationColor: new THREE.Color(0x2dd4bf),
    attenuationDistance: 3.0,
  });
  var vessel = new THREE.Mesh(vesselGeo, vesselMat);
  vesselGroup.add(vessel);

  // Entrance choreography: glass fades in first, then liquid rises,
  // then bubbles/cracks/droplets appear. Each stage scales opacity.
  vesselMat.opacity = 0;
  vesselMat.transparent = true;

  // ── Liquid ───────────────────────────────────────────────────────────────
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
    color: 0x2dd4bf,
    emissive: 0x2dd4bf,
    emissiveIntensity: 0.4,
    roughness: 0.08,
    metalness: 0,
    transmission: 0.6,
    thickness: 2.5,
    ior: 1.33,
    opacity: 0.82,
    transparent: true,
    side: THREE.DoubleSide,
  });
  var liquid = new THREE.Mesh(liquidGeo, liquidMat);
  vesselGroup.add(liquid);

  // Inner glow at the liquid surface
  var liquidLight = new THREE.PointLight(0x2dd4bf, 2.5, 9);
  liquidLight.position.set(0, fillLevel + 0.4, 0);
  vesselGroup.add(liquidLight);

  // Clipping plane — animates from bottom to fillLevel on load
  var fillPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), VESSEL_BOTTOM);
  liquidMat.clippingPlanes = [fillPlane];

  // Top ring vertex indices for wave animation
  var topRingStart = (liquidPts.length - 1) * (LIQUID_SEGMENTS + 1);

  // ── The cell — biological specimen floating in the vessel ────────────────
  // The vessel is the Observatory (the instrument). The cell is the specimen
  // inside it — the prediction subject. Its health glow scales with fill level,
  // and membrane damage appears as amber fissures (audit warnings).
  var cellGroup = new THREE.Group();
  vesselGroup.add(cellGroup);

  // Cell membrane — organic, slightly irregular sphere (not a perfect ball)
  var cellRadius = 1.1;
  var CELL_SEGMENTS = lowPerf ? 32 : 48;
  var cellGeo = new THREE.IcosahedronGeometry(cellRadius, 3);
  // Deform vertices for organic irregularity — multi-octave noise for a
  // real membrane texture, not just smooth bumps
  var cellPos = cellGeo.attributes.position;
  for (var ci = 0; ci < cellPos.count; ci++) {
    var cx = cellPos.getX(ci);
    var cy = cellPos.getY(ci);
    var cz = cellPos.getZ(ci);
    var noise =
      Math.sin(cx * 3) * 0.04 +
      Math.cos(cy * 4) * 0.03 +
      Math.sin(cz * 5) * 0.02 +
      Math.sin(cx * 7 + cy * 3) * 0.015 +
      Math.cos(cz * 9 + cx * 2) * 0.01;
    cellPos.setXYZ(ci, cx * (1 + noise), cy * (1 + noise), cz * (1 + noise));
  }
  cellGeo.computeVertexNormals();

  // Membrane health = fill level. A healthy cell (high fill) glows bright teal.
  // A sick cell (low fill) glows dim. This is biologically literal.
  var cellHealth = fillPct / 100;
  var cellMat = new THREE.MeshPhysicalMaterial({
    color: 0x2dd4bf,
    emissive: 0x2dd4bf,
    emissiveIntensity: 0.3 + cellHealth * 0.5,
    roughness: 0.12,
    metalness: 0,
    transmission: 0.35,
    thickness: 1.5,
    ior: 1.4,
    clearcoat: 0.8,
    clearcoatRoughness: 0.1,
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
  });
  var cellMembrane = new THREE.Mesh(cellGeo, cellMat);
  // Cell sits in the upper portion of the liquid, floating at the surface
  cellGroup.position.y = fillLevel + 0.3;
  cellGroup.add(cellMembrane);

  // Nucleus — the prediction core, brightest point
  var nucleusGeo = new THREE.SphereGeometry(0.35, 24, 24);
  var nucleusMat = new THREE.MeshBasicMaterial({
    color: 0x22d3ee,
    transparent: true,
    opacity: 0,
  });
  var nucleus = new THREE.Mesh(nucleusGeo, nucleusMat);
  cellGroup.add(nucleus);

  // Nucleus glow
  var nucleusGlowGeo = new THREE.SphereGeometry(0.55, 16, 16);
  var nucleusGlowMat = new THREE.MeshBasicMaterial({
    color: 0x22d3ee,
    transparent: true,
    opacity: 0,
    blending: THREE.AdditiveBlending,
  });
  var nucleusGlow = new THREE.Mesh(nucleusGlowGeo, nucleusGlowMat);
  cellGroup.add(nucleusGlow);

  // Nucleus point light — illuminates the cell interior
  var nucleusLight = new THREE.PointLight(0x22d3ee, 0.5 + cellHealth * 0.8, 5);
  cellGroup.add(nucleusLight);

  // Organelles — 6 color-coded, orbiting the nucleus. Each represents a metric.
  var organelleColors = [
    0x2dd4bf, // teal — primary
    0x22d3ee, // cyan
    0xa78bfa, // violet
    0xfbbf24, // amber
    0xf472b6, // pink
    0x4ade80, // green
  ];
  var organellesGroup = new THREE.Group();
  cellGroup.add(organellesGroup);
  var organelles = [];
  for (var oi = 0; oi < 6; oi++) {
    var orgGeo = new THREE.SphereGeometry(0.08 + Math.random() * 0.04, 12, 12);
    var orgMat = new THREE.MeshBasicMaterial({
      color: organelleColors[oi],
      transparent: true,
      opacity: 0,
    });
    var organelle = new THREE.Mesh(orgGeo, orgMat);
    var orgAngle = (oi / 6) * Math.PI * 2;
    var orgTilt = (oi % 2 === 0 ? 1 : -1) * 0.3;
    organelle.userData = {
      angle: orgAngle,
      tilt: orgTilt,
      radius: 0.55 + Math.random() * 0.15,
      speed: 0.3 + Math.random() * 0.2,
      phase: Math.random() * Math.PI * 2,
    };
    organelle.position.set(
      Math.cos(orgAngle) * organelle.userData.radius,
      orgTilt,
      Math.sin(orgAngle) * organelle.userData.radius,
    );
    organelles.push(organelle);
    organellesGroup.add(organelle);

    // Glow halo for each organelle
    var orgGlowGeo = new THREE.SphereGeometry(0.14, 8, 8);
    var orgGlowMat = new THREE.MeshBasicMaterial({
      color: organelleColors[oi],
      transparent: true,
      opacity: 0,
      blending: THREE.AdditiveBlending,
    });
    var orgGlow = new THREE.Mesh(orgGlowGeo, orgGlowMat);
    orgGlow.userData = { parent: organelle };
    organellesGroup.add(orgGlow);
  }

  // ── Bubbles (rising through the liquid) ──────────────────────────────────
  var bubbleCount = 12;
  var bubbles = [];
  for (var bi = 0; bi < bubbleCount; bi++) {
    var bGeo = new THREE.SphereGeometry(0.04 + Math.random() * 0.05, 8, 8);
    var bMat = new THREE.MeshPhysicalMaterial({
      color: 0xa5f3fc,
      transmission: 0.9,
      roughness: 0.0,
      ior: 1.0,
      transparent: true,
      opacity: 0.6,
    });
    var bubble = new THREE.Mesh(bGeo, bMat);
    var bAngle = Math.random() * Math.PI * 2;
    var bRadius = vesselRadiusAt(VESSEL_BOTTOM + 0.2) * 0.5 * Math.random();
    bubble.position.set(
      Math.cos(bAngle) * bRadius,
      VESSEL_BOTTOM + Math.random() * (fillLevel - VESSEL_BOTTOM),
      Math.sin(bAngle) * bRadius,
    );
    bubble.userData = {
      speed: 0.3 + Math.random() * 0.5,
      phase: Math.random() * Math.PI * 2,
      wobble: 0.1 + Math.random() * 0.15,
      baseAngle: bAngle,
      radius: bRadius,
    };
    bubbles.push(bubble);
    vesselGroup.add(bubble);
  }

  // ── Cracks (warn/error audit flags) — emissive glow ──────────────────────
  var cracksGroup = new THREE.Group();
  for (var ci = 0; ci < Math.min(warnCount, 6); ci++) {
    var baseAngle = (ci / Math.min(warnCount, 6)) * Math.PI * 2 + 0.3;
    var baseY = -0.8 + (ci % 3) * 0.6;
    var crackPts = [];
    for (var cj = 0; cj <= 8; cj++) {
      var ct = cj / 8;
      var cy = baseY + ct * 1.8;
      var cr = vesselRadiusAt(cy) * 1.01;
      var wobble = Math.sin(ct * 9 + ci * 2) * 0.1;
      var ca = baseAngle + wobble;
      crackPts.push(
        new THREE.Vector3(Math.cos(ca) * cr, cy, Math.sin(ca) * cr),
      );
    }
    var curve = new THREE.CatmullRomCurve3(crackPts);
    var tubeGeo = new THREE.TubeGeometry(curve, 24, 0.028, 8, false);
    var tubeMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
    });
    var crackMesh = new THREE.Mesh(tubeGeo, tubeMat);
    crackMesh.userData = { baseY: baseY };
    cracksGroup.add(crackMesh);

    // Glow halo for each crack
    var glowGeo = new THREE.TubeGeometry(curve, 24, 0.06, 8, false);
    var glowMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
      transparent: true,
      opacity: 0.15,
    });
    cracksGroup.add(new THREE.Mesh(glowGeo, glowMat));
  }
  vesselGroup.add(cracksGroup);

  // ── Droplets (info audit flags) ──────────────────────────────────────────
  var dropletsGroup = new THREE.Group();
  for (var di = 0; di < Math.min(infoCount, 5); di++) {
    var sphereGeo = new THREE.SphereGeometry(0.1, 16, 16);
    var sphereMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee });
    var droplet = new THREE.Mesh(sphereGeo, sphereMat);
    var da = (di / Math.min(infoCount, 5)) * Math.PI * 2;
    droplet.position.set(
      Math.cos(da) * 1.5,
      fillLevel + 0.8 + (di % 2) * 0.5,
      Math.sin(da) * 1.5,
    );
    droplet.userData = { baseY: droplet.position.y, phase: di * 0.7 };
    dropletsGroup.add(droplet);

    // Glow halo
    var dGlowGeo = new THREE.SphereGeometry(0.2, 12, 12);
    var dGlowMat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.15,
    });
    var dGlow = new THREE.Mesh(dGlowGeo, dGlowMat);
    dGlow.position.copy(droplet.position);
    dGlow.userData = { parent: droplet };
    dropletsGroup.add(dGlow);
  }
  vesselGroup.add(dropletsGroup);

  // ── Reflective floor — catches and scatters the teal glow ─────────────────
  var floorGeo = new THREE.CircleGeometry(8, 64);
  var floorMat = new THREE.MeshStandardMaterial({
    color: 0x11304a,
    roughness: 0.08,
    metalness: 0.85,
    envMapIntensity: 1.0,
  });
  var floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = VESSEL_BOTTOM - 0.3;
  scene.add(floor);

  // Caustics light projection on the floor — brighter, warmer spread
  var causticsLight = new THREE.SpotLight(0x2dd4bf, 4.5, 14, Math.PI / 4.5, 0.6);
  causticsLight.position.set(0, fillLevel + 2, 0);
  causticsLight.target.position.set(0, VESSEL_BOTTOM - 0.3, 0);
  vesselGroup.add(causticsLight);
  vesselGroup.add(causticsLight.target);

  // ── Ambient particles (atmosphere) ────────────────────────────────────────
  var particleCount = lowPerf ? 40 : 120;
  var particleGeo = new THREE.BufferGeometry();
  var particlePos = new Float32Array(particleCount * 3);
  var particleVel = new Float32Array(particleCount);
  for (var pi = 0; pi < particleCount; pi++) {
    particlePos[pi * 3] = (Math.random() - 0.5) * 16;
    particlePos[pi * 3 + 1] = (Math.random() - 0.5) * 12;
    particlePos[pi * 3 + 2] = (Math.random() - 0.5) * 16;
    particleVel[pi] = 0.08 + Math.random() * 0.15;
  }
  particleGeo.setAttribute("position", new THREE.BufferAttribute(particlePos, 3));

  // Custom circular sprite texture for particles
  var particleCanvas = document.createElement("canvas");
  particleCanvas.width = 64;
  particleCanvas.height = 64;
  var pctx = particleCanvas.getContext("2d");
  var pgrad = pctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  pgrad.addColorStop(0, "rgba(45, 212, 191, 1)");
  pgrad.addColorStop(0.4, "rgba(45, 212, 191, 0.4)");
  pgrad.addColorStop(1, "rgba(45, 212, 191, 0)");
  pctx.fillStyle = pgrad;
  pctx.fillRect(0, 0, 64, 64);
  var particleTexture = new THREE.CanvasTexture(particleCanvas);

  var particleMat = new THREE.PointsMaterial({
    map: particleTexture,
    color: 0x2dd4bf,
    size: 0.08,
    transparent: true,
    opacity: 0.4,
    sizeAttenuation: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  var particles = new THREE.Points(particleGeo, particleMat);
  scene.add(particles);

  // ── DNA helix strands — subtle biological motif in the background ─────────
  // Two slow-rotating double-helix strands float behind the vessel, evoking
  // the molecular biology without dominating the scene. Inspired by plant-dna
  // and cell-architecture-studio repos.
  var dnaGroup = new THREE.Group();
  scene.add(dnaGroup);
  var dnaStrands = [];
  var dnaColors = [0x2dd4bf, 0xa78bfa, 0x4ade80];
  for (var si = 0; si < 2; si++) {
    var helixGroup = new THREE.Group();
    var helixColor = dnaColors[si];
    var helixPoints = lowPerf ? 14 : 22;
    for (var hi = 0; hi < helixPoints; hi++) {
      var tH = hi / (helixPoints - 1);
      var angle = tH * Math.PI * 4;
      var y = (tH - 0.5) * 6;
      var radius = 0.4;
      // Two dots per rung — the double helix pair
      var dotGeo = new THREE.SphereGeometry(0.06, 8, 8);
      var dotMat = new THREE.MeshBasicMaterial({
        color: helixColor,
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
      });
      var dot1 = new THREE.Mesh(dotGeo, dotMat);
      dot1.position.set(Math.cos(angle) * radius, y, Math.sin(angle) * radius);
      helixGroup.add(dot1);
      var dotMat2 = dotMat.clone();
      var dot2 = new THREE.Mesh(dotGeo, dotMat2);
      dot2.position.set(
        Math.cos(angle + Math.PI) * radius,
        y,
        Math.sin(angle + Math.PI) * radius,
      );
      helixGroup.add(dot2);
      // Rung (ladder bar) every other step
      if (hi % 2 === 0) {
        var rungGeo = new THREE.CylinderGeometry(0.01, 0.01, radius * 2, 6);
        var rungMat = new THREE.MeshBasicMaterial({
          color: helixColor,
          transparent: true,
          opacity: 0,
          blending: THREE.AdditiveBlending,
        });
        var rung = new THREE.Mesh(rungGeo, rungMat);
        rung.position.set(0, y, 0);
        rung.lookAt(dot1.position);
        rung.rotateX(Math.PI / 2);
        helixGroup.add(rung);
      }
    }
    // Position the strands behind/beside the vessel
    helixGroup.position.set(
      si === 0 ? -3.5 : 3.2,
      0,
      -2,
    );
    helixGroup.scale.setScalar(0.8);
    helixGroup.userData = { rotSpeed: 0.1 + si * 0.05, phase: si * 1.5 };
    dnaStrands.push(helixGroup);
    dnaGroup.add(helixGroup);
  }

  // ── Lighting — bright biological medium, not dark void ───────────────────
  scene.add(new THREE.AmbientLight(0x3a6b8c, 0.8));

  var belowLight = new THREE.PointLight(0x2dd4bf, 3.5, 16);
  belowLight.position.set(0, -3.5, 0);
  scene.add(belowLight);

  var aboveLight = new THREE.PointLight(0xfff0d4, 1.2, 20);
  aboveLight.position.set(3, 5, 4);
  scene.add(aboveLight);

  var rimLight = new THREE.DirectionalLight(0x22d3ee, 0.8);
  rimLight.position.set(-5, 2, -3);
  scene.add(rimLight);

  // Botanical accent — subtle green side-light evoking plant biology
  var bioLight = new THREE.PointLight(0x4ade80, 0.6, 12);
  bioLight.position.set(-4, 1, 2);
  scene.add(bioLight);

  // ── Controls ─────────────────────────────────────────────────────────────
  // Interactive: judges can drag to rotate and scroll to zoom. Auto-rotate
  // pauses on interaction and resumes after 3s of idle — this makes the
  // vessel feel alive without fighting the user.
  var controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = !reducedMotion;
  controls.autoRotateSpeed = 0.5;
  controls.minPolarAngle = Math.PI / 4.5;
  controls.maxPolarAngle = Math.PI / 1.8;
  controls.minDistance = 9;
  controls.maxDistance = 18;
  controls.enablePan = false;
  controls.enableZoom = true;
  controls.target.set(0, 0, 0);

  // Idle detection — resume auto-rotate after 3s of no user interaction
  var idleTimer = null;
  function onUserInteraction() {
    controls.autoRotate = false;
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      if (!reducedMotion) controls.autoRotate = true;
    }, 3000);
  }
  renderer.domElement.addEventListener("pointerdown", onUserInteraction);
  renderer.domElement.addEventListener("wheel", onUserInteraction, { passive: true });
  renderer.domElement.addEventListener("touchstart", onUserInteraction, { passive: true });

  // ── Pointer parallax (mouse + touch) ─────────────────────────────────────
  var mouseX = 0,
    mouseY = 0;
  var targetMouseX = 0,
    targetMouseY = 0;

  function onPointerMove(e) {
    var rect = container.getBoundingClientRect();
    var x = (e.clientX - rect.left) / rect.width;
    var y = (e.clientY - rect.top) / rect.height;
    targetMouseX = (x - 0.5) * 2;
    targetMouseY = (y - 0.5) * 2;
  }
  container.addEventListener("pointermove", onPointerMove);

  // ── Scroll-driven camera (home page only) ────────────────────────────────
  var scrollProgress = 0;
  function onScroll() {
    if (!isHome) return;
    var rect = container.getBoundingClientRect();
    var viewportH = window.innerHeight;
    // 0 at top of page, 1 when container is fully scrolled past
    scrollProgress = Math.min(1, Math.max(0, -rect.top / viewportH));
  }
  window.addEventListener("scroll", onScroll, { passive: true });

  // ── Post-processing (bloom) ───────────────────────────────────────────────
  // Bloom is the most expensive pass. Skip it on mobile/low-perf — the emissive
  // materials still glow, just without the blooming halo.
  var composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));

  var bloomPass = null;
  if (!lowPerf) {
    bloomPass = new UnrealBloomPass(
      new THREE.Vector2(w, h),
      0.5, // strength
      0.45, // radius
      0.78, // threshold — only bright things bloom
    );
    composer.addPass(bloomPass);
  }
  composer.addPass(new OutputPass());

  // ── Resize ────────────────────────────────────────────────────────────────
  function resize() {
    w = container.clientWidth || 400;
    h = container.clientHeight || 400;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    composer.setSize(w, h);
    if (bloomPass) bloomPass.setSize(w, h);
  }
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(container);
  }

  // ── Animation loop ───────────────────────────────────────────────────────
  var clock = new THREE.Clock();
  var fillT = reducedMotion ? 1 : 0;
  var fillDuration = 1.8;
  var running = true;

  // Staggered entrance: glass → liquid → cell → nucleus → organelles → bubbles → cracks → droplets
  // Each element has a start time and fade-in duration.
  var entranceT = 0;
  var ENTRANCE = {
    glass: { start: 0.0, dur: 0.8 },
    liquid: { start: 0.4, dur: 1.2 },
    cell: { start: 1.0, dur: 1.0 },
    nucleus: { start: 1.4, dur: 0.6 },
    organelles: { start: 1.8, dur: 0.6 },
    bubbles: { start: 2.0, dur: 0.6 },
    cracks: { start: 2.3, dur: 0.8 },
    droplets: { start: 2.6, dur: 0.6 },
    particles: { start: 0.2, dur: 1.0 },
    dna: { start: 1.5, dur: 1.5 },
  };
  var entranceDone = reducedMotion;
  if (entranceDone) {
    vesselMat.opacity = 1;
    vesselMat.transparent = false;
  }

  function fadeFactor(stage) {
    if (entranceDone) return 1;
    var s = ENTRANCE[stage];
    if (entranceT < s.start) return 0;
    var p = Math.min(1, (entranceT - s.start) / s.dur);
    return p * p * (3 - 2 * p); // smoothstep
  }

  function animate() {
    if (!running) return;
    requestAnimationFrame(animate);
    var dt = Math.min(clock.getDelta(), 0.05);
    var t = clock.getElapsedTime();

    // Entrance timeline advances in real time
    if (!entranceDone) {
      entranceT += dt;
      if (entranceT > 3.5) entranceDone = true;
    }

    // Glass fade-in
    var glassA = fadeFactor("glass");
    vesselMat.opacity = glassA;
    vesselMat.transparent = glassA < 1;

    // Particle fade-in
    particleMat.opacity = 0.4 * fadeFactor("particles");

    // Fill animation — clipping plane rises from bottom to fillLevel
    // Delayed until glass is partially visible
    if (fillT < 1 && entranceT >= ENTRANCE.liquid.start) {
      fillT = Math.min(1, fillT + dt / fillDuration);
      var eased = fillT * fillT * (3 - 2 * fillT); // smoothstep
      fillPlane.constant = VESSEL_BOTTOM + eased * (fillLevel - VESSEL_BOTTOM);
    }
    liquidMat.opacity = 0.82 * fadeFactor("liquid");

    // Bubble opacity — fade in after liquid starts rising
    var bubbleA = fadeFactor("bubbles");
    if (bubbleA < 1) {
      bubbles.forEach(function (b) { b.material.opacity = 0.6 * bubbleA; });
    }

    // Cell membrane fade-in
    var cellA = fadeFactor("cell");
    cellMat.opacity = 0.7 * cellA;

    // Nucleus fade-in + pulse
    var nucleusA = fadeFactor("nucleus");
    nucleusMat.opacity = nucleusA;
    nucleusGlowMat.opacity = 0.4 * nucleusA;
    if (!reducedMotion) {
      var pulse = 1 + Math.sin(t * 1.8) * 0.08;
      nucleus.scale.setScalar(pulse);
      nucleusGlow.scale.setScalar(pulse * 1.2);
      nucleusLight.intensity = (0.5 + cellHealth * 0.8) * nucleusA * (0.8 + Math.sin(t * 1.8) * 0.2);
    }

    // Organelles fade-in + orbit
    var orgA = fadeFactor("organelles");
    organelles.forEach(function (org) { org.material.opacity = orgA; });
    organellesGroup.children.forEach(function (og) {
      if (og.userData.parent) {
        // Glow halo follows its organelle
        og.material.opacity = 0.25 * orgA;
      }
    });
    if (!reducedMotion) {
      organelles.forEach(function (org) {
        var d = org.userData;
        d.angle += d.speed * dt;
        org.position.set(
          Math.cos(d.angle) * d.radius,
          d.tilt + Math.sin(t * 1.5 + d.phase) * 0.08,
          Math.sin(d.angle) * d.radius,
        );
      });
      organellesGroup.children.forEach(function (og) {
        if (og.userData.parent) {
          og.position.copy(og.userData.parent.position);
        }
      });
      // Cell membrane gentle rotation + breathing
      cellMembrane.rotation.y += dt * 0.15;
      cellGroup.position.y = fillLevel + 0.3 + Math.sin(t * 0.6) * 0.05;
    }

    // Crack opacity — fade in after bubbles
    var crackA = fadeFactor("cracks");
    cracksGroup.children.forEach(function (c, ci) {
      if (ci % 2 === 0) {
        c.material.opacity = (0.8 + Math.sin(t * 2 + ci) * 0.2) * crackA;
        c.material.transparent = true;
      } else {
        c.material.opacity = 0.15 * crackA;
      }
    });

    // Droplet opacity — fade in last
    var dropletA = fadeFactor("droplets");
    dropletsGroup.children.forEach(function (d) {
      d.material.opacity = (d.userData.parent ? 0.15 : 1) * dropletA;
      d.material.transparent = true;
    });

    // Wave animation on the liquid surface — dual sine waves + ripples
    // that expand outward from random points, simulating droplet impacts
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

    // Bubble rising
    if (!reducedMotion) {
      for (var bo = 0; bo < bubbles.length; bo++) {
        var b = bubbles[bo];
        b.position.y += b.userData.speed * dt;
        // Wobble in XZ
        var wob = Math.sin(t * 2 + b.userData.phase) * b.userData.wobble;
        b.position.x = Math.cos(b.userData.baseAngle + wob) * b.userData.radius;
        b.position.z = Math.sin(b.userData.baseAngle + wob) * b.userData.radius;
        // Reset to bottom when reaching surface
        if (b.position.y > fillLevel - 0.1) {
          b.position.y = VESSEL_BOTTOM + 0.2;
          b.userData.baseAngle = Math.random() * Math.PI * 2;
          b.userData.radius = vesselRadiusAt(VESSEL_BOTTOM + 0.2) * 0.5 * Math.random();
        }
      }

      // Droplet float — movement only, opacity handled by entrance fade above
      dropletsGroup.children.forEach(function (d) {
        if (d.userData.parent) {
          d.position.copy(d.userData.parent.position);
          d.scale.setScalar(1 + Math.sin(t * 2 + (d.userData.parent.userData.phase || 0)) * 0.15);
        } else {
          d.position.y =
            d.userData.baseY + Math.sin(t * 1.5 + d.userData.phase) * 0.12;
        }
      });

      // Particle drift
      var pos = particles.geometry.attributes.position;
      for (var ppi = 0; ppi < particleCount; ppi++) {
        pos.array[ppi * 3 + 1] += particleVel[ppi] * dt * 0.3;
        pos.array[ppi * 3] += Math.sin(t * 0.5 + ppi) * 0.003;
        if (pos.array[ppi * 3 + 1] > 6) {
          pos.array[ppi * 3 + 1] = -6;
          pos.array[ppi * 3] = (Math.random() - 0.5) * 16;
        }
      }
      pos.needsUpdate = true;

      // DNA helix strands — slow rotation + fade-in
      var dnaA = fadeFactor("dna");
      dnaStrands.forEach(function (strand) {
        strand.rotation.y += strand.userData.rotSpeed * dt;
        strand.position.y = Math.sin(t * 0.3 + strand.userData.phase) * 0.3;
        strand.children.forEach(function (child) {
          if (child.material) {
            child.material.opacity = (child.geometry.type === "CylinderGeometry" ? 0.12 : 0.3) * dnaA;
          }
        });
      });

      // Vessel bob
      vesselGroup.position.y = Math.sin(t * 0.5) * 0.06;
    } else {
      // Reduced motion: still set DNA opacity (no rotation/movement)
      var dnaA = fadeFactor("dna");
      dnaStrands.forEach(function (strand) {
        strand.children.forEach(function (child) {
          if (child.material) {
            child.material.opacity = (child.geometry.type === "CylinderGeometry" ? 0.12 : 0.3) * dnaA;
          }
        });
      });
    }

    // Mouse parallax — smooth follow
    mouseX += (targetMouseX - mouseX) * 0.04;
    mouseY += (targetMouseY - mouseY) * 0.04;

    // Scroll-driven camera (home page)
    if (isHome) {
      // Pull camera back and slightly up as user scrolls
      var scrollZ = 13 + scrollProgress * 5;
      var scrollY = 1.0 - scrollProgress * 1.5;
      camera.position.z += (scrollZ - camera.position.z) * 0.05;
      camera.position.y += (scrollY - camera.position.y) * 0.05;
    }

    // Apply parallax offset to the vessel group rotation
    vesselGroup.rotation.x = mouseY * 0.05;
    // Parallax shifts the camera slightly, not the vessel, for depth feel
    camera.position.x += (mouseX * 0.8 - camera.position.x) * 0.03;

    controls.update();
    composer.render();
  }

  // ── Pause rendering when the tab is hidden (saves GPU/CPU) ───────────────
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      running = false;
    } else if (!running) {
      running = true;
      clock.getDelta(); // reset delta so we don't jump after resuming
      animate();
    }
  });

  animate();
}

initVessel3D();
