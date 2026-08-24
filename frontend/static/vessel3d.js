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

  // Organelles — color-coded, orbiting the nucleus. Each represents a metric.
  // Clickable: clicking an organelle scrolls to the audit panel.
  var metricData = params.metrics || [];
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
  var organelleCount = Math.max(2, Math.min(6, metricData.length || 2));
  for (var oi = 0; oi < organelleCount; oi++) {
    var orgGeo = new THREE.SphereGeometry(0.09, 14, 14);
    var orgMat = new THREE.MeshBasicMaterial({
      color: organelleColors[oi % organelleColors.length],
      transparent: true,
      opacity: 0,
    });
    var organelle = new THREE.Mesh(orgGeo, orgMat);
    var orgAngle = (oi / organelleCount) * Math.PI * 2;
    var orgTilt = (oi % 2 === 0 ? 1 : -1) * 0.3;
    var md = metricData[oi] || {};
    organelle.userData = {
      angle: orgAngle,
      tilt: orgTilt,
      radius: 0.55 + Math.random() * 0.15,
      speed: 0.3 + Math.random() * 0.2,
      phase: Math.random() * Math.PI * 2,
      interactive: true,
      type: "organelle",
      label: md.label || ("metric " + (oi + 1)),
      ceiling: md.ceiling || "",
      target: md.target || "audit",
    };
    organelle.position.set(
      Math.cos(orgAngle) * organelle.userData.radius,
      orgTilt,
      Math.sin(orgAngle) * organelle.userData.radius,
    );
    organelles.push(organelle);
    organellesGroup.add(organelle);

    // Glow halo for each organelle
    var orgGlowGeo = new THREE.SphereGeometry(0.15, 8, 8);
    var orgGlowMat = new THREE.MeshBasicMaterial({
      color: organelleColors[oi % organelleColors.length],
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

  // ── Cracks (warn/error audit flags) — emissive glow, clickable ──────────────
  var crackData = params.cracks || [];
  var cracksGroup = new THREE.Group();
  var crackMeshes = [];
  var numCracks = Math.min(warnCount, 6);
  for (var ci = 0; ci < numCracks; ci++) {
    var baseAngle = (ci / numCracks) * Math.PI * 2 + 0.3;
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
    // Make cracks slightly thicker so they're easier to click
    var tubeGeo = new THREE.TubeGeometry(curve, 24, 0.04, 8, false);
    var tubeMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
      transparent: true,
      opacity: 0,
    });
    var crackMesh = new THREE.Mesh(tubeGeo, tubeMat);
    var cd = crackData[ci] || {};
    crackMesh.userData = {
      baseY: baseY,
      interactive: true,
      type: "crack",
      label: cd.rule || "audit warning",
      message: cd.message || "",
      target: cd.target || "audit",
    };
    crackMeshes.push(crackMesh);
    cracksGroup.add(crackMesh);

    // Glow halo for each crack
    var glowGeo = new THREE.TubeGeometry(curve, 24, 0.07, 8, false);
    var glowMat = new THREE.MeshBasicMaterial({
      color: 0xfbbf24,
      transparent: true,
      opacity: 0.15,
    });
    var glowMesh = new THREE.Mesh(glowGeo, glowMat);
    glowMesh.userData = { parent: crackMesh };
    cracksGroup.add(glowMesh);
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

  // ── Backdrop world — the vessel sits in a living field, not a void ───────
  // Inspired by low-poly island scenes: a soft gradient sky, a low-poly
  // meadow with grass and flowers, distant hills, drifting pollen, and a
  // sun/moon glow. The whole world is adaptive — it crossfades between a
  // bright Nordic day and a warm ember dusk as the site's theme changes,
  // so the instrument evolves in and out of its states instead of snapping.
  var WORLD = {
    light: {
      skyTop: new THREE.Color("#6fc3ca"),
      skyHorizon: new THREE.Color("#f7ecd2"),
      skyGround: new THREE.Color("#e7eed6"),
      meadow: new THREE.Color("#cfe0bd"),
      hill: new THREE.Color("#a9c79a"),
      tuft: new THREE.Color("#7fae6a"),
      flower: new THREE.Color("#f2a6b8"),
      flower2: new THREE.Color("#f0c75e"),
      pollen: new THREE.Color("#e8b64a"),
      glow: new THREE.Color("#ffd9a6"),
      ambient: new THREE.Color("#9fd0c8"),
      ambientI: 0.95,
      below: new THREE.Color("#2dd4bf"),
      belowI: 3.2,
      above: new THREE.Color("#fff3d6"),
      aboveI: 1.7,
      rim: new THREE.Color("#7fd3d6"),
      rimI: 0.9,
    },
    dark: {
      skyTop: new THREE.Color("#0d0f14"),
      skyHorizon: new THREE.Color("#3a2418"),
      skyGround: new THREE.Color("#191a13"),
      meadow: new THREE.Color("#1c2118"),
      hill: new THREE.Color("#2a2a1c"),
      tuft: new THREE.Color("#4a5a30"),
      flower: new THREE.Color("#f59e0b"),
      flower2: new THREE.Color("#a78bfa"),
      pollen: new THREE.Color("#f59e0b"),
      glow: new THREE.Color("#fbbf24"),
      ambient: new THREE.Color("#6a5a3a"),
      ambientI: 0.6,
      below: new THREE.Color("#2dd4bf"),
      belowI: 2.6,
      above: new THREE.Color("#ffc97a"),
      aboveI: 0.9,
      rim: new THREE.Color("#f59e0b"),
      rimI: 0.7,
    },
  };

  function worldTheme() {
    return document.documentElement.getAttribute("data-theme") === "light"
      ? "light"
      : "dark";
  }

  // themeBlend: 0 = dusk, 1 = day. Crossfades on change so the world evolves.
  var themeBlend = worldTheme() === "light" ? 1 : 0;
  var themeTarget = themeBlend;
  var worldTrack = [];
  function trackWorld(apply) {
    worldTrack.push(apply);
  }

  window.addEventListener("kytos:theme", function (event) {
    themeTarget = event.detail && event.detail.theme === "light" ? 1 : 0;
  });

  // ── Sky dome — soft gradient sky, the island's backdrop ──────────────────
  var skyGeo = new THREE.SphereGeometry(60, 24, 16);
  var skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uTop: { value: new THREE.Color() },
      uHorizon: { value: new THREE.Color() },
      uGround: { value: new THREE.Color() },
    },
    vertexShader: [
      "varying vec3 vPos;",
      "void main() {",
      "  vPos = position;",
      "  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);",
      "}",
    ].join("\n"),
    fragmentShader: [
      "varying vec3 vPos;",
      "uniform vec3 uTop;",
      "uniform vec3 uHorizon;",
      "uniform vec3 uGround;",
      "void main() {",
      "  vec3 d = normalize(vPos);",
      "  float h = clamp(d.y, -1.0, 1.0);",
      "  float zen = smoothstep(0.02, 0.55, h);",
      "  float gnd = smoothstep(-0.12, 0.10, h);",
      "  vec3 col = mix(uHorizon, uTop, zen);",
      "  col = mix(uGround, col, gnd);",
      "  gl_FragColor = vec4(col, 1.0);",
      "}",
    ].join("\n"),
  });
  var sky = new THREE.Mesh(skyGeo, skyMat);
  sky.frustumCulled = false;
  scene.add(sky);
  trackWorld(function (b) {
    skyMat.uniforms.uTop.value.copy(WORLD.dark.skyTop).lerp(WORLD.light.skyTop, b);
    skyMat.uniforms.uHorizon.value
      .copy(WORLD.dark.skyHorizon)
      .lerp(WORLD.light.skyHorizon, b);
    skyMat.uniforms.uGround.value
      .copy(WORLD.dark.skyGround)
      .lerp(WORLD.light.skyGround, b);
  });

  // ── Sun / moon glow — a soft additive disc near the horizon ──────────────
  var glowCanvas = document.createElement("canvas");
  glowCanvas.width = 128;
  glowCanvas.height = 128;
  var gctx = glowCanvas.getContext("2d");
  var ggrad = gctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  ggrad.addColorStop(0, "rgba(255,255,255,1)");
  ggrad.addColorStop(0.25, "rgba(255,255,255,0.45)");
  ggrad.addColorStop(1, "rgba(255,255,255,0)");
  gctx.fillStyle = ggrad;
  gctx.fillRect(0, 0, 128, 128);
  var glowTex = new THREE.CanvasTexture(glowCanvas);
  var glowMat = new THREE.SpriteMaterial({
    map: glowTex,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  var glow = new THREE.Sprite(glowMat);
  glow.position.set(0, 3.4, -17);
  glow.scale.set(8, 8, 1);
  scene.add(glow);
  trackWorld(function (b) {
    glowMat.color.copy(WORLD.dark.glow).lerp(WORLD.light.glow, b);
    glowMat.opacity = 0.3 + b * 0.45;
  });

  // ── Meadow — low-poly field where the vessel stands ──────────────────────
  var floorY = VESSEL_BOTTOM - 0.3;
  var meadowGeo = new THREE.CircleGeometry(24, 48);
  var meadowMat = new THREE.MeshStandardMaterial({
    roughness: 0.6,
    metalness: 0,
  });
  var meadow = new THREE.Mesh(meadowGeo, meadowMat);
  meadow.rotation.x = -Math.PI / 2;
  meadow.position.y = floorY;
  scene.add(meadow);
  trackWorld(function (b) {
    meadowMat.color.copy(WORLD.dark.meadow).lerp(WORLD.light.meadow, b);
  });

  // ── Ecology — grass tufts and flowers scattered on the field ─────────────
  var ecologyGroup = new THREE.Group();
  scene.add(ecologyGroup);
  var tuftBlades = [];
  var flowerHeads = [];
  var tuftCount = lowPerf ? 16 : 36;
  var flowerCount = lowPerf ? 8 : 18;
  function randRange(a, b) {
    return a + Math.random() * (b - a);
  }
  for (var gi = 0; gi < tuftCount; gi++) {
    var tAng = Math.random() * Math.PI * 2;
    var tRad = randRange(2.4, 10);
    var tuft = new THREE.Group();
    for (var bi = 0; bi < 3; bi++) {
      var bladeGeo = new THREE.ConeGeometry(0.05, randRange(0.22, 0.5), 4);
      var bladeMat = new THREE.MeshStandardMaterial({ roughness: 0.85 });
      var blade = new THREE.Mesh(bladeGeo, bladeMat);
      blade.position.set(
        (Math.random() - 0.5) * 0.2,
        bladeGeo.parameters.height / 2 - 0.02,
        (Math.random() - 0.5) * 0.2,
      );
      blade.rotation.z = (Math.random() - 0.5) * 0.5;
      blade.rotation.x = (Math.random() - 0.5) * 0.5;
      tuft.add(blade);
      tuftBlades.push(bladeMat);
    }
    tuft.position.set(Math.cos(tAng) * tRad, floorY, Math.sin(tAng) * tRad);
    tuft.userData = {
      sway: 0.6 + Math.random() * 1.2,
      phase: Math.random() * Math.PI * 2,
    };
    ecologyGroup.add(tuft);
  }
  for (var fi = 0; fi < flowerCount; fi++) {
    var fAng = Math.random() * Math.PI * 2;
    var fRad = randRange(2.6, 9.4);
    var flower = new THREE.Group();
    var stemGeo = new THREE.CylinderGeometry(0.012, 0.012, 0.4, 4);
    var stemMat = new THREE.MeshStandardMaterial({ color: 0x7fae6a, roughness: 0.85 });
    var stem = new THREE.Mesh(stemGeo, stemMat);
    stem.position.y = 0.2;
    flower.add(stem);
    var headGeo = new THREE.SphereGeometry(0.05, 6, 6);
    var headMat = new THREE.MeshStandardMaterial({ roughness: 0.5 });
    var head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 0.42;
    head.userData = {
      sway: 1 + Math.random(),
      phase: Math.random() * Math.PI * 2,
    };
    flower.add(head);
    flowerHeads.push(headMat);
    flower.position.set(Math.cos(fAng) * fRad, floorY, Math.sin(fAng) * fRad);
    flower.userData = {
      sway: 0.8 + Math.random(),
      phase: Math.random() * Math.PI * 2,
    };
    ecologyGroup.add(flower);
  }
  trackWorld(function (b) {
    var tuftC = WORLD.dark.tuft.clone().lerp(WORLD.light.tuft, b);
    var flowerC = WORLD.dark.flower.clone().lerp(WORLD.light.flower, b);
    var flower2C = WORLD.dark.flower2.clone().lerp(WORLD.light.flower2, b);
    for (var i = 0; i < tuftBlades.length; i++) tuftBlades[i].color.copy(tuftC);
    for (var j = 0; j < flowerHeads.length; j++) {
      flowerHeads[j].color.copy(j % 2 ? flower2C : flowerC);
    }
  });

  // ── Horizon hills — low-poly mounds for depth, like a distant treeline ────
  var hillMat = new THREE.MeshStandardMaterial({ roughness: 1 });
  var horizonGroup = new THREE.Group();
  scene.add(horizonGroup);
  var hillSpots = [
    [-14, -12],
    [0, -17],
    [13, -10],
    [18, -4],
    [-19, -1],
  ];
  for (var hi = 0; hi < hillSpots.length; hi++) {
    var hh = randRange(1.4, 2.8);
    var hillGeo = new THREE.ConeGeometry(randRange(3.5, 6.5), hh, 5);
    var hill = new THREE.Mesh(hillGeo, hillMat);
    hill.position.set(hillSpots[hi][0], floorY + hh / 2, hillSpots[hi][1]);
    hill.rotation.y = Math.random() * Math.PI * 2;
    horizonGroup.add(hill);
  }
  trackWorld(function (b) {
    hillMat.color.copy(WORLD.dark.hill).lerp(WORLD.light.hill, b);
  });

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
  // Pollen — warm gold by day, ember spores at dusk.
  trackWorld(function (b) {
    particleMat.color.copy(WORLD.dark.pollen).lerp(WORLD.light.pollen, b);
  });

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

  // ── Lighting — bright biological medium, warm with the sun by day and
  //     ember at dusk. Colors and intensities follow the world palette.
  var ambientLight = new THREE.AmbientLight(0x6a5a3a, 0.6);
  scene.add(ambientLight);

  var belowLight = new THREE.PointLight(0x2dd4bf, 2.6, 16);
  belowLight.position.set(0, -3.5, 0);
  scene.add(belowLight);

  var aboveLight = new THREE.PointLight(0xffc97a, 0.9, 20);
  aboveLight.position.set(3, 5, 4);
  scene.add(aboveLight);

  var rimLight = new THREE.DirectionalLight(0xf59e0b, 0.7);
  rimLight.position.set(-5, 2, -3);
  scene.add(rimLight);

  trackWorld(function (b) {
    ambientLight.color.copy(WORLD.dark.ambient).lerp(WORLD.light.ambient, b);
    ambientLight.intensity += (WORLD.dark.ambientI + (WORLD.light.ambientI - WORLD.dark.ambientI) * b - ambientLight.intensity) * 0.06;
    belowLight.color.copy(WORLD.dark.below).lerp(WORLD.light.below, b);
    aboveLight.color.copy(WORLD.dark.above).lerp(WORLD.light.above, b);
    rimLight.color.copy(WORLD.dark.rim).lerp(WORLD.light.rim, b);
  });

  // Botanical accent — subtle green side-light evoking plant biology
  var bioLight = new THREE.PointLight(0x4ade80, 0.6, 12);
  bioLight.position.set(-4, 1, 2);
  scene.add(bioLight);

  // Evidence journey state: the instrument changes emphasis as the reader
  // moves from audit stress to evidence, digest, and independent trust.
  var journeyColors = {
    audit: new THREE.Color(0xfbbf24),
    evidence: new THREE.Color(0x2dd4bf),
    narrative: new THREE.Color(0xc4b5fd),
    trust: new THREE.Color(0x22d3ee),
  };
  var journeyState = "audit";
  var journeyTargetColor = journeyColors.audit.clone();
  var crackBaseColor = new THREE.Color(0xfbbf24);
  var journeyIntensity = 1;
  var journeyTargetIntensity = 1;
  function setJourneyState(state) {
    if (!journeyColors[state]) return;
    journeyState = state;
    journeyTargetColor.copy(journeyColors[state]);
    journeyTargetIntensity = state === "audit" ? 1.18 : state === "trust" ? 1.08 : 0.92;
    container.setAttribute("data-journey-state", state);
  }
  window.addEventListener("kytos:journey-state", function (event) {
    setJourneyState(event.detail && event.detail.state);
  });
  setJourneyState(container.getAttribute("data-journey-state") || "audit");

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

  // ── Scroll-driven camera (home + run detail) ──────────────────────────────
  var scrollProgress = 0;
  function onScroll() {
    var rect = container.getBoundingClientRect();
    var viewportH = window.innerHeight;
    // 0 at top of page, 1 when container is fully scrolled past
    scrollProgress = Math.min(1, Math.max(0, -rect.top / viewportH));
  }
  window.addEventListener("scroll", onScroll, { passive: true });

  // ── Raycasting: clickable organelles + cracks ──────────────────────────────
  // The vessel is an instrument, not decoration. Organelles link to metrics,
  // cracks link to audit flags. Hover shows a floating callout; click navigates.
  var raycaster = new THREE.Raycaster();
  var pointer = new THREE.Vector2();
  var calloutEl = document.getElementById("vessel-callout");
  var hoveredObj = null;
  var interactables = [];
  // Build the interactable list once entrance is well underway (objects visible)
  var interactablesReady = false;
  function buildInteractables() {
    interactables = [];
    organelles.forEach(function (o) { interactables.push(o); });
    crackMeshes.forEach(function (c) { interactables.push(c); });
    interactablesReady = true;
  }

  function worldToScreen(obj) {
    var v = new THREE.Vector3();
    obj.getWorldPosition(v);
    v.project(camera);
    var rect = container.getBoundingClientRect();
    return {
      x: (v.x * 0.5 + 0.5) * rect.width,
      y: (-v.y * 0.5 + 0.5) * rect.height,
    };
  }

  function showCallout(obj, x, y) {
    if (!calloutEl || !obj.userData.label) return;
    var html = "<strong>" + obj.userData.label + "</strong>";
    if (obj.userData.ceiling) {
      html += " <span class='vessel-callout-sub'>" + obj.userData.ceiling + "</span>";
    }
    if (obj.userData.message) {
      html += "<span class='vessel-callout-msg'>" + obj.userData.message + "</span>";
    }
    html += "<span class='vessel-callout-action'>click to view →</span>";
    calloutEl.innerHTML = html;
    calloutEl.style.left = x + "px";
    calloutEl.style.top = y + "px";
    calloutEl.classList.add("frag-showing");
    calloutEl.classList.add("is-visible");
    calloutEl.setAttribute("aria-hidden", "false");
  }

  function hideCallout() {
    if (!calloutEl) return;
    calloutEl.classList.remove("frag-showing");
    calloutEl.classList.remove("is-visible");
    calloutEl.setAttribute("aria-hidden", "true");
  }

  function navigateToTarget(target) {
    if (!target) return;
    var el = document.getElementById(target);
    if (el && el.tagName === "DETAILS") {
      el.open = true;
    }
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (target === "audit") {
      // Fall back to the main content
      var main = document.querySelector(".run-evidence");
      if (main) main.scrollIntoView({ behavior: "smooth" });
    }
  }

  function onPointerMoveRay(e) {
    if (!interactablesReady) return;
    var rect = container.getBoundingClientRect();
    pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    var hits = raycaster.intersectObjects(interactables, false);
    if (hits.length > 0) {
      var hit = hits[0].object;
      if (hoveredObj !== hit) {
        hoveredObj = hit;
        container.style.cursor = "pointer";
      }
      var screen = worldToScreen(hit);
      // Offset callout above the object
      showCallout(hit, screen.x, screen.y - 20);
    } else {
      if (hoveredObj) {
        hoveredObj = null;
        container.style.cursor = "";
        hideCallout();
      }
    }
  }

  function onClickRay(e) {
    if (!interactablesReady || !hoveredObj) return;
    navigateToTarget(hoveredObj.userData.target);
    hideCallout();
  }

  container.addEventListener("pointermove", onPointerMoveRay);
  container.addEventListener("click", onClickRay);

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

    // World palette crossfades between day and dusk as the theme changes.
    themeBlend += (themeTarget - themeBlend) * 0.03;
    for (var wti = 0; wti < worldTrack.length; wti++) worldTrack[wti](themeBlend);

    // Entrance timeline advances in real time
    if (!entranceDone) {
      entranceT += dt;
      if (entranceT > 3.5) {
        entranceDone = true;
        buildInteractables();
      }
    }

    // Journey state eases instead of snapping, preserving the specimen feel.
    nucleusMat.color.lerp(journeyTargetColor, 0.045);
    nucleusGlowMat.color.lerp(journeyTargetColor, 0.045);
    nucleusLight.color.copy(journeyTargetColor);
    nucleusLight.intensity += (0.5 * journeyIntensity - nucleusLight.intensity) * 0.04;
    bioLight.color.lerp(journeyTargetColor, 0.035);
    bioLight.intensity += (0.6 * journeyTargetIntensity - bioLight.intensity) * 0.04;
    journeyIntensity += (journeyTargetIntensity - journeyIntensity) * 0.04;
    if (bloomPass) {
      bloomPass.strength += (0.5 * journeyTargetIntensity - bloomPass.strength) * 0.04;
    }
    organelles.forEach(function (organelle, index) {
      var emphasis = journeyState === "evidence" ? 1.15 : journeyState === "trust" ? 1.05 : 0.9;
      organelle.material.opacity = Math.min(1, organelle.material.opacity + (0.55 * emphasis - organelle.material.opacity) * 0.03);
      if (organelle.userData && organelle.userData.phase !== undefined) {
        organelle.userData.journeyEmphasis = emphasis + index * 0.01;
      }
    });

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

    // Organelles fade-in + orbit + hover scale
    var orgA = fadeFactor("organelles");
    organelles.forEach(function (org) {
      org.material.opacity = orgA;
      // Hover scale — smooth grow on hover
      var targetScale = (hoveredObj === org) ? 1.5 : 1.0;
      if (!org.userData.curScale) org.userData.curScale = 1.0;
      org.userData.curScale += (targetScale - org.userData.curScale) * 0.15;
      org.scale.setScalar(org.userData.curScale);
    });
    organellesGroup.children.forEach(function (og) {
      if (og.userData.parent) {
        // Glow halo follows its organelle, brighter on hover
        var hoverBoost = (hoveredObj === og.userData.parent) ? 0.4 : 0.25;
        og.material.opacity = hoverBoost * orgA;
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

    // Crack opacity — fade in after bubbles, pulse brighter on hover
    var crackA = fadeFactor("cracks");
    cracksGroup.children.forEach(function (c, ci) {
      var isParent = ci % 2 === 0;
      var parentMesh = isParent ? c : c.userData.parent;
      var isHovered = parentMesh && hoveredObj === parentMesh;
      if (isParent) {
        var crackColor = journeyState === "audit" ? journeyTargetColor : crackBaseColor;
        c.material.color.lerp(crackColor, 0.06);
        c.material.opacity = (0.8 + Math.sin(t * 2 + ci) * 0.2) * crackA * (journeyState === "audit" ? 1.1 : 0.72);
        c.material.transparent = true;
        // Hover scale on crack tubes
        var targetScale = isHovered ? 1.4 : 1.0;
        if (!c.userData.curScale) c.userData.curScale = 1.0;
        c.userData.curScale += (targetScale - c.userData.curScale) * 0.15;
        c.scale.setScalar(c.userData.curScale);
      } else {
        c.material.color.lerp(journeyState === "audit" ? journeyTargetColor : crackBaseColor, 0.06);
        c.material.opacity = (isHovered ? 0.45 : 0.15) * crackA * (journeyState === "audit" ? 1.1 : 0.72);
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

      // Ecology — grass and flowers sway in the breeze
      ecologyGroup.children.forEach(function (e) {
        var sw = e.userData.sway || 0;
        e.rotation.z = Math.sin(t * sw + e.userData.phase) * 0.06;
        e.children.forEach(function (c) {
          if (c.userData && c.userData.sway) {
            c.rotation.z = Math.sin(t * c.userData.sway + c.userData.phase) * 0.12;
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

    // Scroll-driven camera (home + run detail) — pull back as user scrolls past
    if (isHome || container.classList.contains("vessel-run")) {
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

  // ── Global API for cross-component interactions (from Cell Studio / Plant DNA) ──
  window.kytosVessel = {
    focusCrack: function (indexOrLabel) {
      if (typeof indexOrLabel === "string") {
        for (var i = 0; i < crackMeshes.length; i++) {
          if (crackMeshes[i].userData.label === indexOrLabel || (crackMeshes[i].userData.message && crackMeshes[i].userData.message.indexOf(indexOrLabel) !== -1)) {
            indexOrLabel = i;
            break;
          }
        }
      }
      var crack = crackMeshes[indexOrLabel];
      if (!crack) return;
      var wp = new THREE.Vector3();
      crack.getWorldPosition(wp);
      // Smoothly orbit camera towards crack position
      var targetAngle = Math.atan2(wp.x, wp.z);
      controls.autoRotate = false;
      var targetPos = new THREE.Vector3(
        Math.sin(targetAngle) * 12,
        wp.y + 1.2,
        Math.cos(targetAngle) * 12
      );
      var startPos = camera.position.clone();
      var tweenT = 0;
      function tweenCam() {
        tweenT += 0.04;
        camera.position.lerpVectors(startPos, targetPos, Math.min(1, tweenT * (2 - tweenT)));
        controls.target.set(0, wp.y * 0.5, 0);
        controls.update();
        if (tweenT < 1) {
          requestAnimationFrame(tweenCam);
        }
      }
      tweenCam();
      var screen = worldToScreen(crack);
      showCallout(crack, screen.x, screen.y - 20);
    },
    toggleMembrane: function () {
      if (cellMembrane && cellMembrane.material) {
        var current = cellMembrane.material.opacity;
        cellMembrane.material.opacity = current > 0.4 ? 0.15 : 0.85;
      }
    },
  };

  // ── Resource Management: Pause render loop when offscreen or hidden ──
  function resumeLoop() {
    if (!running) {
      running = true;
      clock.getDelta();
      animate();
    }
  }

  function pauseLoop() {
    running = false;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      pauseLoop();
    } else {
      resumeLoop();
    }
  });

  if (typeof IntersectionObserver !== "undefined") {
    var viewObserver = new IntersectionObserver(
      function (entries) {
        var isVisible = entries.some(function (e) {
          return e.isIntersecting;
        });
        if (isVisible) {
          resumeLoop();
        } else {
          pauseLoop();
        }
      },
      { rootMargin: "150px" },
    );
    viewObserver.observe(container);
  }

  animate();
}

initVessel3D();
