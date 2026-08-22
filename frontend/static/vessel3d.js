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
  var VESSEL_SEGMENTS = 80;
  var LIQUID_SEGMENTS = 56;
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
    envMapIntensity: 1.2,
    side: THREE.DoubleSide,
    attenuationColor: new THREE.Color(0x5eead4),
    attenuationDistance: 3.0,
  });
  var vessel = new THREE.Mesh(vesselGeo, vesselMat);
  vesselGroup.add(vessel);

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
    color: 0x5eead4,
    emissive: 0x5eead4,
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
  var liquidLight = new THREE.PointLight(0x5eead4, 2.5, 9);
  liquidLight.position.set(0, fillLevel + 0.4, 0);
  vesselGroup.add(liquidLight);

  // Clipping plane — animates from bottom to fillLevel on load
  var fillPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), VESSEL_BOTTOM);
  liquidMat.clippingPlanes = [fillPlane];

  // Top ring vertex indices for wave animation
  var topRingStart = (liquidPts.length - 1) * (LIQUID_SEGMENTS + 1);

  // ── Bubbles (rising through the liquid) ──────────────────────────────────
  var bubbleCount = 12;
  var bubbles = [];
  for (var bi = 0; bi < bubbleCount; bi++) {
    var bGeo = new THREE.SphereGeometry(0.04 + Math.random() * 0.05, 8, 8);
    var bMat = new THREE.MeshPhysicalMaterial({
      color: 0xcffafe,
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

    // Glow halo
    var dGlowGeo = new THREE.SphereGeometry(0.2, 12, 12);
    var dGlowMat = new THREE.MeshBasicMaterial({
      color: 0x67e8f9,
      transparent: true,
      opacity: 0.15,
    });
    var dGlow = new THREE.Mesh(dGlowGeo, dGlowMat);
    dGlow.position.copy(droplet.position);
    dGlow.userData = { parent: droplet };
    dropletsGroup.add(dGlow);
  }
  vesselGroup.add(dropletsGroup);

  // ── Reflective floor ─────────────────────────────────────────────────────
  var floorGeo = new THREE.CircleGeometry(8, 64);
  var floorMat = new THREE.MeshStandardMaterial({
    color: 0x0a0f17,
    roughness: 0.15,
    metalness: 0.9,
    envMapIntensity: 0.5,
  });
  var floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = VESSEL_BOTTOM - 0.3;
  scene.add(floor);

  // Caustics light projection on the floor
  var causticsLight = new THREE.SpotLight(0x5eead4, 3.0, 12, Math.PI / 5, 0.5);
  causticsLight.position.set(0, fillLevel + 2, 0);
  causticsLight.target.position.set(0, VESSEL_BOTTOM - 0.3, 0);
  vesselGroup.add(causticsLight);
  vesselGroup.add(causticsLight.target);

  // ── Ambient particles (atmosphere) ────────────────────────────────────────
  var particleCount = 120;
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
  pgrad.addColorStop(0, "rgba(94, 234, 212, 1)");
  pgrad.addColorStop(0.4, "rgba(94, 234, 212, 0.4)");
  pgrad.addColorStop(1, "rgba(94, 234, 212, 0)");
  pctx.fillStyle = pgrad;
  pctx.fillRect(0, 0, 64, 64);
  var particleTexture = new THREE.CanvasTexture(particleCanvas);

  var particleMat = new THREE.PointsMaterial({
    map: particleTexture,
    color: 0x5eead4,
    size: 0.08,
    transparent: true,
    opacity: 0.4,
    sizeAttenuation: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  var particles = new THREE.Points(particleGeo, particleMat);
  scene.add(particles);

  // ── Lighting ────────────────────────────────────────────────────────────
  scene.add(new THREE.AmbientLight(0x1a2535, 0.3));

  var belowLight = new THREE.PointLight(0x5eead4, 2.0, 14);
  belowLight.position.set(0, -3.5, 0);
  scene.add(belowLight);

  var aboveLight = new THREE.PointLight(0xffeed4, 0.5, 18);
  aboveLight.position.set(3, 5, 4);
  scene.add(aboveLight);

  var rimLight = new THREE.DirectionalLight(0x67e8f9, 0.4);
  rimLight.position.set(-5, 2, -3);
  scene.add(rimLight);

  // ── Controls ─────────────────────────────────────────────────────────────
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
  controls.enableZoom = false;
  controls.target.set(0, 0, 0);

  // ── Mouse parallax ──────────────────────────────────────────────────────
  var mouseX = 0,
    mouseY = 0;
  var targetMouseX = 0,
    targetMouseY = 0;

  function onMouseMove(e) {
    var rect = container.getBoundingClientRect();
    var x = (e.clientX - rect.left) / rect.width;
    var y = (e.clientY - rect.top) / rect.height;
    targetMouseX = (x - 0.5) * 2;
    targetMouseY = (y - 0.5) * 2;
  }
  container.addEventListener("mousemove", onMouseMove);

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
  var composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));

  var bloomPass = new UnrealBloomPass(
    new THREE.Vector2(w, h),
    0.5, // strength
    0.45, // radius
    0.78, // threshold — only bright things bloom
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
    var dt = Math.min(clock.getDelta(), 0.05);
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

      // Droplet float
      dropletsGroup.children.forEach(function (d) {
        if (d.userData.parent) {
          d.position.copy(d.userData.parent.position);
          d.scale.setScalar(1 + Math.sin(t * 2 + (d.userData.parent.userData.phase || 0)) * 0.15);
        } else {
          d.position.y =
            d.userData.baseY + Math.sin(t * 1.5 + d.userData.phase) * 0.12;
        }
      });

      // Crack pulse
      cracksGroup.children.forEach(function (c, ci) {
        if (ci % 2 === 0) {
          // Main crack — pulse opacity slightly
          var pulse = 0.8 + Math.sin(t * 2 + ci) * 0.2;
          c.material.opacity = pulse;
          c.material.transparent = true;
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

      // Vessel bob
      vesselGroup.position.y = Math.sin(t * 0.5) * 0.06;
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

  animate();
}

initVessel3D();
