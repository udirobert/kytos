(function () {
  "use strict";

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function markNoWebGL() {
    if (document.documentElement.classList.contains("no-webgl")) {
      return;
    }
    document.documentElement.classList.add("no-webgl");
    document.documentElement.classList.remove("vessel-pending");
    animateVesselFallback();
  }

  function isNoWebGL() {
    return document.documentElement.classList.contains("no-webgl");
  }

  function probeWebGL() {
    try {
      var canvas = document.createElement("canvas");
      return !!(
        canvas.getContext("webgl") || canvas.getContext("experimental-webgl")
      );
    } catch (err) {
      return false;
    }
  }

  function initNoWebGLDetect() {
    var container = document.getElementById("vessel-canvas");
    if (!container) {
      return;
    }
    if (!probeWebGL()) {
      markNoWebGL();
      return;
    }
    setTimeout(function () {
      if (!container.classList.contains("is-3d")) {
        markNoWebGL();
      }
    }, 1200);
  }

  // ── Text states swap (transitions.dev pattern) ──────────────────────────
  // Three-phase swap: old text exits up with blur, new text enters from below.
  // Skipped entirely under prefers-reduced-motion (plain textContent swap).
  var swapDur = 150;
  function swapText(el, next) {
    if (!el) return;
    if (prefersReducedMotion() || isNoWebGL() || !el.classList.contains("t-text-swap")) {
      el.textContent = next;
      return;
    }
    if (el._swapTimer) {
      // A swap is mid-flight — jump to the new text without animation.
      clearTimeout(el._swapTimer);
      el.classList.remove("is-exit", "is-enter-start");
      el.textContent = next;
      return;
    }
    if (el.textContent === next) return;
    el.classList.add("is-exit");
    el._swapTimer = setTimeout(function () {
      el.textContent = next;
      el.classList.remove("is-exit");
      el.classList.add("is-enter-start");
      void el.offsetHeight; // force reflow
      el.classList.remove("is-enter-start");
      el._swapTimer = null;
    }, swapDur);
  }

  // ── Metrics chart (Plotly) — lazy loaded when scrolled into view ────────
  // Plotly is 1.3 MB. Instead of loading it in <head>, we inject the script
  // only when the metrics-chart section enters the viewport. This saves
  // ~1.3 MB of render-blocking JS on the run detail page.
  function initPlotly() {
    var targets = [
      {
        el: document.getElementById("metrics-chart"),
        dataEl: document.getElementById("metrics-chart-data"),
        details: "details.chart-details",
      },
      {
        el: document.getElementById("volcano-chart"),
        dataEl: document.getElementById("volcano-chart-data"),
        details: "details.volcano-details",
      },
    ];
    var activeTargets = targets.filter(function (t) {
      return t.el && t.dataEl;
    });
    if (!activeTargets.length) {
      return;
    }

    function renderTargets() {
      activeTargets.forEach(function (t) {
        _renderPlotly(t.el, t.dataEl);
      });
    }

    function boot() {
      if (typeof Plotly !== "undefined") {
        renderTargets();
        return;
      }
      _loadPlotly(renderTargets);
    }

    activeTargets.forEach(function (t) {
      var d = t.el.closest(t.details);
      if (d) {
        d.addEventListener("toggle", function () {
          if (d.open) {
            boot();
          }
        });
      }
    });

    if (
      activeTargets.some(function (t) {
        var d = t.el.closest(t.details);
        return !d || d.open;
      })
    ) {
      boot();
    }
  }

  function _loadPlotly(callback) {
    if (typeof Plotly !== "undefined") {
      if (callback) callback();
      return;
    }
    var script = document.createElement("script");
    script.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    script.onload = function () {
      if (callback) callback();
    };
    document.head.appendChild(script);
  }

  function _renderPlotly(el, dataEl) {
    if (typeof Plotly === "undefined") return;
    try {
      var spec = JSON.parse(dataEl.textContent || "{}");
      if (!spec.data || !spec.data.length) return;
      Plotly.newPlot(el, spec.data, spec.layout || {}, spec.config || {});
    } catch (err) {
      console.warn("Plotly init failed", err);
    }
  }

  // ── Vessel SVG fallback animation (when WebGL is unavailable) ────────────
  // The 3D scene (vessel3d.js) handles animation when WebGL is available.
  // If the 3D container doesn't get .is-3d within 2s, animate the SVG fallback.
  function animateVesselFallback() {
    var container = document.getElementById("vessel-canvas");
    if (container && container.classList.contains("is-3d")) {
      return;
    }
    var liquid = document.querySelector(".vessel-liquid");
    if (!liquid || prefersReducedMotion()) {
      return;
    }
    var target = liquid.getAttribute("y");
    liquid.setAttribute("y", "250");
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        liquid.setAttribute("y", target);
      });
    });
  }

  // ── VCC timeline rail + hackathon countdown + home strip ───────────────
  function initVccRail() {
    var track = document.querySelector(".vcc-track");
    if (!track) {
      return;
    }
    var start = new Date(track.getAttribute("data-vcc-start") || "2026-08-20T00:00:00Z").getTime();
    var end = new Date(track.getAttribute("data-vcc-end") || "2026-11-05T23:59:59Z").getTime();
    var testSet = new Date(track.getAttribute("data-vcc-test") || "2026-10-22T00:00:00Z").getTime();
    var hackathonEnd = new Date(
      track.getAttribute("data-hackathon-end") || "2026-08-22T18:00:00Z"
    ).getTime();
    var vccDays = parseInt(track.getAttribute("data-vcc-days") || "78", 10);
    var markers = Array.prototype.slice.call(track.querySelectorAll(".vcc-marker"));
    var needle = document.getElementById("vcc-needle");
    var fill = document.getElementById("vcc-fill");
    var countdown = document.getElementById("vcc-countdown");
    var dayEl = document.getElementById("vcc-day");
    var testEl = document.getElementById("vcc-testsets");
    var hackathonEl = document.getElementById("hackathon-countdown");
    var homeBuild = document.getElementById("home-build-day");
    var homeLeft = document.getElementById("home-vcc-left");
    if (!needle || !fill || !countdown) {
      return;
    }

    function pct(date) {
      return Math.min(1, Math.max(0, (date - start) / (end - start)));
    }

    function fmt(ms) {
      var d = Math.floor(ms / 86400000);
      var h = Math.floor((ms % 86400000) / 3600000);
      var m = Math.floor((ms % 3600000) / 60000);
      var s = Math.floor((ms % 60000) / 1000);
      var pad = function (n) {
        return String(n).padStart(2, "0");
      };
      return d + "d " + pad(h) + ":" + pad(m) + ":" + pad(s);
    }

    function fmtShort(ms) {
      var d = Math.ceil(ms / 86400000);
      return d + "d";
    }

    function tick() {
      var now = Date.now();
      var progress = pct(now);
      var buildDay = Math.min(vccDays, Math.max(1, Math.floor((now - start) / 86400000) + 1));

      markers.forEach(function (marker) {
        var date = new Date(marker.getAttribute("data-date")).getTime();
        marker.style.left = (pct(date) * 100).toFixed(2) + "%";
      });

      needle.style.left = (progress * 100).toFixed(2) + "%";
      fill.style.width = (progress * 100).toFixed(2) + "%";

      swapText(countdown, fmt(Math.max(0, end - now)));
      if (dayEl) {
        dayEl.textContent = String(buildDay);
      }
      if (testEl) {
        swapText(testEl, fmt(Math.max(0, testSet - now)));
      }
      if (hackathonEl) {
        var hackLeft = hackathonEnd - now;
        swapText(hackathonEl, hackLeft > 0 ? fmt(hackLeft) : "closed ✅ keep building");
      }
      if (homeBuild) {
        homeBuild.textContent = "day " + buildDay;
      }
      if (homeLeft) {
        swapText(homeLeft, fmtShort(Math.max(0, end - now)));
      }
    }

    tick();
    setInterval(tick, 1000);
  }

  // ── Keyboard shortcuts: j/k runs, 1-4 sections, m membrane, c cracks ────
  function initKeyboardShortcuts() {
    var pills = Array.prototype.slice.call(document.querySelectorAll(".run-strip .run-pill"));
    var active = document.querySelector(".run-strip .run-pill.is-active");
    if (active && active.scrollIntoView) {
      active.scrollIntoView({ block: "nearest", inline: "center" });
    }

    document.addEventListener("keydown", function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) {
        return;
      }
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) {
        return;
      }

      // j/k: next/prev run
      if (pills.length > 1) {
        var idx = pills.indexOf(active);
        var next = null;
        if (e.key === "j" || e.key === "J") {
          next = pills[(idx + 1) % pills.length];
        } else if (e.key === "k" || e.key === "K") {
          next = pills[(idx - 1 + pills.length) % pills.length];
        }
        if (next && next.href) {
          window.location.href = next.href;
          return;
        }
      }

      // 1-4: jump to journey sections
      var sectionMap = { "1": "audit", "2": "evidence", "3": "narrative", "4": "trust" };
      if (sectionMap[e.key]) {
        openDisclosure(sectionMap[e.key]);
        var targetEl = document.getElementById(sectionMap[e.key]);
        if (targetEl) {
          targetEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return;
      }

      // m: toggle membrane (3D or SVG)
      if (e.key === "m" || e.key === "M") {
        if (
          window.kytosVessel &&
          typeof window.kytosVessel.toggleMembrane === "function"
        ) {
          window.kytosVessel.toggleMembrane();
          return;
        }
        var svgMembrane =
          document.querySelector(".cell-membrane") ||
          document.querySelector(".vessel-glass");
        if (svgMembrane) {
          var curOp = parseFloat(
            window.getComputedStyle(svgMembrane).opacity || "1",
          );
          svgMembrane.style.opacity = curOp < 0.5 ? "1" : "0.2";
          return;
        }
      }

      // c: focus next crack (3D or SVG)
      if (e.key === "c" || e.key === "C") {
        if (
          window.kytosVessel &&
          typeof window.kytosVessel.focusCrack === "function"
        ) {
          window.kytosVessel.focusCrack(0);
          return;
        }
        var firstCrack = document.querySelector(".vessel-crack");
        if (firstCrack) {
          firstCrack.style.transform = "scale(1.4)";
          firstCrack.style.filter = "drop-shadow(0 0 8px #fb923c)";
          setTimeout(function () {
            firstCrack.style.transform = "";
            firstCrack.style.filter = "";
          }, 800);
          openDisclosure("audit");
          var auditEl = document.getElementById("audit");
          if (auditEl) {
            auditEl.scrollIntoView({ behavior: "smooth", block: "start" });
          }
          return;
        }
      }
    });
  }

  // ── Count-up: data strip numbers rise on load ────────────────────────────
  // Uses the number-pop-in transition (transitions.dev) for the final value:
  // each digit re-enters with blur + stagger when the count reaches its target.
  function initCountUp() {
    var els = document.querySelectorAll("[data-count-to]");
    if (!els.length || prefersReducedMotion() || isNoWebGL()) {
      // Reduced motion / SVG path: jump straight to the real value.
      els.forEach(function (el) {
        el.textContent = el.getAttribute("data-count-to") + (el.getAttribute("data-suffix") || "");
      });
      return;
    }
    els.forEach(function (el) {
      var target = parseFloat(el.getAttribute("data-count-to")) || 0;
      var suffix = el.getAttribute("data-suffix") || "";
      var dur = 750;
      var t0 = null;
      function step(ts) {
        if (!t0) {
          t0 = ts;
        }
        var p = Math.min(1, (ts - t0) / dur);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (p < 1) {
          requestAnimationFrame(step);
        } else {
          // Count finished — replay with digit pop-in for the final value.
          playDigitPopIn(el, String(Math.round(target)) + suffix);
        }
      }
      requestAnimationFrame(step);
    });
  }

  // ── Number pop-in (transitions.dev pattern) ─────────────────────────────
  // Wrap each character in a .t-digit span, stagger the last two, then animate.
  function playDigitPopIn(el, str) {
    el.classList.remove("t-digit-group", "is-animating");
    el.replaceChildren();
    el.classList.add("t-digit-group");
    var chars = String(str).split("");
    chars.forEach(function (ch, i) {
      var span = document.createElement("span");
      span.className = "t-digit";
      span.textContent = ch;
      if (i === chars.length - 2) span.dataset.stagger = "1";
      else if (i === chars.length - 1) span.dataset.stagger = "2";
      el.appendChild(span);
    });
    void el.offsetHeight; // force reflow
    el.classList.add("is-animating");
  }

  // ── Provenance: copy-to-clipboard for the reproduce command ───────────────
  function initCopyButtons() {
    var buttons = document.querySelectorAll(".copy-btn");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = document.querySelector(btn.getAttribute("data-copy"));
        var text = target ? target.textContent.trim() : "";
        if (!text) {
          return;
        }
        var original = btn.getAttribute("data-copy-label") || btn.textContent;
        var done = function () {
          btn.textContent = "copied";
          btn.setAttribute("aria-label", "Reproduce command copied");
          btn.classList.add("is-copied");
          setTimeout(function () {
            btn.textContent = original;
            btn.setAttribute("aria-label", "Copy reproduce command");
            btn.classList.remove("is-copied");
          }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () {
            // Clipboard API unavailable (http/file) — fall back to a select box.
            if (target && target.select) {
              target.select();
            }
          });
        }
      });
    });
  }

  // ── Living specimen parallax ────────────────────────────────────────────
  // The biological atmosphere is a quiet depth layer, not a second interface.
  function initBioParallax() {
    var atmosphere = document.querySelector(".bio-atmosphere");
    if (!atmosphere || prefersReducedMotion()) {
      return;
    }
    var ticking = false;
    function update() {
      var max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
      var progress = Math.max(0, Math.min(1, window.scrollY / max));
      atmosphere.style.setProperty("--bio-scroll", progress.toFixed(4));
      ticking = false;
    }
    window.addEventListener("scroll", function () {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    }, { passive: true });
    update();
  }

  // ── Evidence journey ────────────────────────────────────────────────────
  // Sections stay as native <details>; this rail only makes the reading order
  // visible and keeps the active specimen stage in view while scrolling.
  function initEvidenceJourney() {
    var rail = document.querySelector(".evidence-journey");
    if (!rail) {
      return;
    }
    var links = Array.prototype.slice.call(rail.querySelectorAll("[data-journey-target]"));
    var navigationLock = null;
    var sections = links.map(function (link) {
      return document.getElementById(link.getAttribute("data-journey-target"));
    }).filter(Boolean);
    if (!sections.length) {
      return;
    }

    function setActive(section) {
      var accent = section.getAttribute("data-accent") || section.id;
      var stateMap = { amber: "audit", teal: "evidence", violet: "narrative", cyan: "trust" };
      var state = stateMap[accent] || accent;
      document.documentElement.setAttribute("data-journey-state", state);
      var atmosphere = document.querySelector(".bio-atmosphere");
      if (atmosphere) atmosphere.setAttribute("data-journey-state", state);
      window.dispatchEvent(new CustomEvent("kytos:journey-state", {
        detail: { state: state, section: section.id },
      }));
      links.forEach(function (link) {
        var active = link.getAttribute("data-journey-target") === section.id;
        link.classList.toggle("is-active", active);
        link.setAttribute("aria-current", active ? "step" : "false");
      });
      var index = Math.max(0, sections.indexOf(section));
      var progress = sections.length > 1 ? index / (sections.length - 1) : 1;
      var fill = rail.querySelector(".journey-progress span");
      if (fill) {
        fill.style.height = Math.round(progress * 100) + "%";
      }
      var liveTitle = rail.querySelector(".journey-live-title");
      var liveHint = rail.querySelector(".journey-live-hint");
      var activeLink = links[index];
      if (liveTitle && activeLink) {
        var title = activeLink.querySelector("strong");
        liveTitle.textContent = title ? title.textContent : section.id;
      }
      if (liveHint && activeLink) {
        var hint = activeLink.querySelector("small");
        liveHint.textContent = hint ? hint.textContent : "reading";
      }
      rail.setAttribute("data-active-state", state);
    }

    links.forEach(function (link) {
      link.addEventListener("click", function (event) {
        var target = document.getElementById(link.getAttribute("data-journey-target"));
        if (!target) return;
        event.preventDefault();
        target.open = true;
        target.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
        history.replaceState(null, "", "#" + target.id);
        setActive(target);
        if (navigationLock) window.clearTimeout(navigationLock);
        navigationLock = window.setTimeout(function () {
          navigationLock = null;
          setActive(target);
        }, prefersReducedMotion() ? 0 : 700);
      });
    });

    if (typeof IntersectionObserver === "undefined") {
      setActive(sections[0]);
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      var visible = entries.filter(function (entry) { return entry.isIntersecting; });
      if (!visible.length || navigationLock) return;
      visible.sort(function (a, b) {
        return Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top);
      });
      setActive(visible[0].target);
    }, { rootMargin: "-18% 0px -62% 0px", threshold: [0, 0.2, 0.6] });
    sections.forEach(function (section) { observer.observe(section); });
    setActive(sections[0]);
  }

  // ── Scroll reveal: evidence cards fade in ──────────────────────────────
  function initScrollReveal() {
    var panels = document.querySelectorAll(".evidence-rail .panel, .page-home .panel");
    if (!panels.length || prefersReducedMotion()) {
      return;
    }
    if (typeof IntersectionObserver === "undefined") {
      return;
    }
    panels.forEach(function (p) {
      p.classList.add("reveal-hidden");
    });
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("reveal-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    panels.forEach(function (p) {
      observer.observe(p);
    });
  }

  function initBriefingUnmute() {
    // The oracle broadcast autoplays muted (browser policy). Surface the
    // 'unmute — the oracle sings' affordance so the anthem isn't invisible.
    document.querySelectorAll(".hero-video").forEach(function (wrap) {
      var video = wrap.querySelector("video.briefing-video");
      var btn = wrap.querySelector(".briefing-unmute");
      if (!video || !btn) return;
      var update = function () {
        btn.hidden = !video.muted;
      };
      video.addEventListener("volumechange", update);
      btn.addEventListener("click", function () {
        video.muted = false;
        video.controls = true;
        update();
      });
      update();
    });
  }

  function slugifyGene(gene) {
    return String(gene || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "gene";
  }

  function openDisclosure(id) {
    var el = document.getElementById(id);
    if (el && el.tagName === "DETAILS") {
      el.open = true;
    }
  }

  function geneBlocksForSlug(slug) {
    return Array.prototype.slice
      .call(document.querySelectorAll(".evidence-gene-block"))
      .filter(function (block) {
        return slugifyGene(block.getAttribute("data-evidence-gene")) === slug;
      });
  }

  function initGeneEvidenceLinks() {
    document.querySelectorAll(".gene-evidence-link").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        var href = link.getAttribute("href") || "";
        var gene = link.getAttribute("data-gene") || "";
        if (window.kytosVessel && typeof window.kytosVessel.focusCrack === "function" && gene) {
          window.kytosVessel.focusCrack(gene);
        }
        if (href.charAt(0) === "#") {
          window.location.hash = href.slice(1);
        }
      });
    });
  }

  function applyHashDisclosure() {
    var hash = (window.location.hash || "").replace(/^#/, "");
    if (!hash) {
      return;
    }
    if (hash === "audit" || hash === "evidence" || hash === "narrative" || hash === "trust") {
      openDisclosure(hash);
      return;
    }
    if (hash.indexOf("evidence-gene-") !== 0) {
      return;
    }
    var slug = hash.slice("evidence-gene-".length);
    openDisclosure("evidence");
    var blocks = geneBlocksForSlug(slug);
    blocks.forEach(function (block) {
      block.open = true;
      block.classList.add("evidence-gene-highlight");
    });
    if (blocks[0]) {
      setTimeout(function () {
        blocks[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 60);
    }
  }

  function initHashDisclosure() {
    applyHashDisclosure();
    window.addEventListener("hashchange", applyHashDisclosure);
  }

  function initBriefingPlay() {
    document.querySelectorAll(".run-header-media-video").forEach(function (wrap) {
      var video = wrap.querySelector("video.briefing-video");
      var playBtn = wrap.querySelector(".briefing-play");
      var unmuteBtn = wrap.querySelector(".briefing-unmute");
      if (!video || !playBtn) {
        return;
      }
      playBtn.addEventListener("click", function () {
        video.controls = true;
        wrap.classList.add("is-playing");
        var playPromise = video.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(function () {});
        }
        playBtn.hidden = true;
        if (unmuteBtn) {
          unmuteBtn.hidden = false;
        }
      });
      video.addEventListener("ended", function () {
        wrap.classList.remove("is-playing");
        playBtn.hidden = false;
        playBtn.innerHTML = '<span aria-hidden="true">↻</span> replay bulletin';
        playBtn.setAttribute("aria-label", "Replay bulletin");
        wrap.setAttribute("data-bulletin-seen", "true");
      });
      if (unmuteBtn) {
        unmuteBtn.addEventListener("click", function () {
          video.muted = false;
          unmuteBtn.hidden = true;
        });
      }
    });
  }

  function initBulletinNext() {
    document.querySelectorAll(".bulletin-next").forEach(function (button) {
      button.addEventListener("click", function () {
        var targetId = button.getAttribute("data-bulletin-target");
        var target = targetId && document.getElementById(targetId);
        var journeyLink = targetId && document.querySelector(
          '[data-journey-target="' + targetId + '"]'
        );
        if (!target) return;
        target.open = true;
        if (journeyLink) {
          journeyLink.click();
          return;
        }
        target.scrollIntoView({
          behavior: prefersReducedMotion() ? "auto" : "smooth",
          block: "start",
        });
      });
    });
  }

  // ── Vessel onboarding tooltip — shown once, dismissed by the user ─────────
  // Appears after the 3D scene loads, explains what the vessel means.
  function initVesselOnboard() {
    var onboard = document.getElementById("vessel-onboard");
    if (!onboard) return;
    var key = "kytos-vessel-onboard-dismissed";
    try {
      if (sessionStorage.getItem(key)) return;
    } catch (e) {
      // sessionStorage may be blocked — show the tooltip anyway
    }

    function show() {
      var hint = onboard.querySelector(".vessel-onboard-hint");
      if (hint && isNoWebGL()) {
        hint.textContent = "Liquid fill = headroom · hover or click cracks for audit details";
      }
      onboard.hidden = false;
      requestAnimationFrame(function () {
        onboard.classList.add("is-visible");
      });
    }

    // Wait for 3D to load, then show after a brief delay
    var container = document.getElementById("vessel-canvas");
    if (container && container.classList.contains("is-3d")) {
      setTimeout(show, 1200);
    } else if (container) {
      // Watch for the is-3d class
      var observer = new MutationObserver(function () {
        if (container.classList.contains("is-3d")) {
          observer.disconnect();
          setTimeout(show, 1200);
        }
      });
      observer.observe(container, { attributes: true, attributeFilter: ["class"] });
      // Fallback: show after 1.5s in SVG mode
      setTimeout(function () {
        if (!onboard.hidden) return;
        show();
      }, 1500);
    }

    function dismiss() {
      onboard.classList.remove("is-visible");
      try {
        sessionStorage.setItem(key, "1");
      } catch (e) {}
      setTimeout(function () {
        onboard.hidden = true;
      }, 400);
    }

    var closeBtn = onboard.querySelector(".vessel-onboard-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", dismiss);
    }
    // Dismiss when clicking outside the tooltip (but not on the vessel itself)
    document.addEventListener("click", function (e) {
      if (onboard.hidden) return;
      if (onboard.contains(e.target)) return;
      dismiss();
    }, { passive: true });
  }

  // ── SVG Vessel Interactivity (No-WebGL mode) ─────────────────────────────
  function initSvgVesselInteractivity() {
    var svg = document.querySelector(".vessel-svg");
    var callout = document.getElementById("vessel-callout");
    if (!svg || !callout) return;

    var cracks = svg.querySelectorAll(".vessel-crack");
    var droplets = svg.querySelectorAll(".vessel-info");
    var nucleus = svg.querySelector(".cell-nucleus");

    function showSvgCallout(text, e) {
      callout.textContent = text;
      callout.style.opacity = "1";
      callout.style.transform = "none";
      var rect = svg.getBoundingClientRect();
      var x = e.clientX - rect.left;
      var y = e.clientY - rect.top;
      callout.style.left = x + "px";
      callout.style.top = y - 30 + "px";
    }

    function hideSvgCallout() {
      callout.style.opacity = "0";
    }

    cracks.forEach(function (crack) {
      crack.style.cursor = "pointer";
      crack.addEventListener("mouseenter", function (e) {
        showSvgCallout("⚠️ Audit Warning: Rule violation detected", e);
      });
      crack.addEventListener("mousemove", function (e) {
        showSvgCallout("⚠️ Audit Warning: Rule violation detected", e);
      });
      crack.addEventListener("mouseleave", hideSvgCallout);
      crack.addEventListener("click", function () {
        openDisclosure("audit");
        var auditEl = document.getElementById("audit");
        if (auditEl) {
          auditEl.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    droplets.forEach(function (droplet) {
      droplet.style.cursor = "pointer";
      droplet.addEventListener("mouseenter", function (e) {
        showSvgCallout("ℹ️ Audit Info: Biological observation", e);
      });
      droplet.addEventListener("mouseleave", hideSvgCallout);
    });

    if (nucleus) {
      nucleus.style.cursor = "pointer";
      nucleus.addEventListener("mouseenter", function (e) {
        showSvgCallout("🧬 Cellular Core: Headroom & baseline state", e);
      });
      nucleus.addEventListener("mouseleave", hideSvgCallout);
    }
  }

  function initViewModeToggle() {
    var toggle = document.getElementById("view-mode-toggle");
    if (!toggle) return;

    var btns = toggle.querySelectorAll(".btn-mode");
    var panels = document.querySelectorAll(".disclosure-panel");

    function setMode(mode) {
      btns.forEach(function (b) {
        if (b.getAttribute("data-mode") === mode) {
          b.classList.add("active");
        } else {
          b.classList.remove("active");
        }
      });
      document.body.setAttribute("data-view-mode", mode);
      if (mode === "science") {
        panels.forEach(function (p) {
          p.open = true;
        });
        var metricsDetails = document.querySelector(".chart-details");
        if (metricsDetails) metricsDetails.open = true;
        var volcanoDetails = document.querySelector(".volcano-details");
        if (volcanoDetails) volcanoDetails.open = true;
      } else {
        panels.forEach(function (p, idx) {
          if (idx !== 0) p.open = false;
        });
      }
      try {
        localStorage.setItem("kytos-view-mode", mode);
      } catch (e) {}
    }

    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mode = btn.getAttribute("data-mode");
        setMode(mode);
      });
    });

    try {
      var saved = localStorage.getItem("kytos-view-mode");
      if (
        saved === "science" ||
        window.location.hash.indexOf("mode=science") !== -1
      ) {
        setMode("science");
      }
    } catch (e) {}
  }

  // ── Home catch carousel ──────────────────────────────────────────────────
  // Auto-rotating 3-slide argument on the hero. Pauses on hover, click dots
  // to jump. Falls back to static first slide under reduced-motion.
  function initHomeCatchCarousel() {
    var carousel = document.getElementById("home-catch-carousel");
    if (!carousel) return;

    var slides = carousel.querySelectorAll(".home-catch-slide");
    var dots = carousel.querySelectorAll(".home-catch-dot");
    if (slides.length <= 1) return;

    if (prefersReducedMotion()) return; // CSS shows only active slide

    var current = 0;
    var timer = null;
    var interval = 4500;

    function show(idx) {
      slides.forEach(function (s, i) {
        if (i === idx) {
          s.classList.add("is-active");
          s.setAttribute("aria-hidden", "false");
        } else {
          s.classList.remove("is-active");
          s.setAttribute("aria-hidden", "true");
        }
      });
      dots.forEach(function (d, i) {
        if (i === idx) {
          d.classList.add("is-active");
          d.setAttribute("aria-selected", "true");
        } else {
          d.classList.remove("is-active");
          d.setAttribute("aria-selected", "false");
        }
      });
      current = idx;
    }

    function next() {
      show((current + 1) % slides.length);
    }

    function start() {
      stop();
      timer = setInterval(next, interval);
    }

    function stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }

    dots.forEach(function (dot, idx) {
      dot.addEventListener("click", function () {
        show(idx);
        start(); // restart timer from the clicked slide
      });
    });

    carousel.addEventListener("mouseenter", stop);
    carousel.addEventListener("mouseleave", start);

    // Pause when tab is hidden
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    });

    start();
  }

  function onReady() {
    initPlotly();
    initVccRail();
    initKeyboardShortcuts();
    initCountUp();
    initCopyButtons();
    initScrollReveal();
    initBioParallax();
    initEvidenceJourney();
    initBriefingUnmute();
    initBriefingPlay();
    initBulletinNext();
    initGeneEvidenceLinks();
    initHashDisclosure();
    initNoWebGLDetect();
    initVesselOnboard();
    initSvgVesselInteractivity();
    initViewModeToggle();
    initHomeCatchCarousel();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
