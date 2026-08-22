(function () {
  "use strict";

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  // ── Metrics chart (Plotly) — lazy loaded when scrolled into view ────────
  // Plotly is 1.3 MB. Instead of loading it in <head>, we inject the script
  // only when the metrics-chart section enters the viewport. This saves
  // ~1.3 MB of render-blocking JS on the run detail page.
  function initPlotly() {
    var el = document.getElementById("metrics-chart");
    var dataEl = document.getElementById("metrics-chart-data");
    if (!el || !dataEl) {
      return;
    }

    function boot() {
      if (typeof Plotly !== "undefined") {
        _renderPlotly(el, dataEl);
        return;
      }
      if (typeof IntersectionObserver === "undefined") {
        _loadPlotly(el, dataEl);
        return;
      }
      var observer = new IntersectionObserver(
        function (entries) {
          if (entries.some(function (e) { return e.isIntersecting; })) {
            observer.disconnect();
            _loadPlotly(el, dataEl);
          }
        },
        { rootMargin: "200px" },
      );
      observer.observe(el);
    }

    var chartDetails = el.closest("details.chart-details");
    if (chartDetails && !chartDetails.open) {
      chartDetails.addEventListener("toggle", function onToggle() {
        if (chartDetails.open) {
          chartDetails.removeEventListener("toggle", onToggle);
          boot();
        }
      });
      return;
    }
    boot();
  }

  function _loadPlotly(el, dataEl) {
    var script = document.createElement("script");
    script.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    script.onload = function () { _renderPlotly(el, dataEl); };
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

      countdown.textContent = fmt(Math.max(0, end - now));
      if (dayEl) {
        dayEl.textContent = String(buildDay);
      }
      if (testEl) {
        testEl.textContent = fmt(Math.max(0, testSet - now));
      }
      if (hackathonEl) {
        var hackLeft = hackathonEnd - now;
        hackathonEl.textContent =
          hackLeft > 0 ? fmt(hackLeft) : "closed ✅ keep building";
      }
      if (homeBuild) {
        homeBuild.textContent = "day " + buildDay;
      }
      if (homeLeft) {
        homeLeft.textContent = fmtShort(Math.max(0, end - now));
      }
    }

    tick();
    setInterval(tick, 1000);
  }

  // ── Run navigation: j/k between runs + auto-scroll the active pill ───────
  function initRunNav() {
    var pills = Array.prototype.slice.call(document.querySelectorAll(".run-strip .run-pill"));
    if (pills.length < 2) {
      return;
    }
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
      var idx = pills.indexOf(active);
      var next = null;
      if (e.key === "j" || e.key === "J") {
        next = pills[(idx + 1) % pills.length];
      } else if (e.key === "k" || e.key === "K") {
        next = pills[(idx - 1 + pills.length) % pills.length];
      }
      if (next && next.href) {
        window.location.href = next.href;
      }
    });
  }

  // ── Count-up: data strip numbers rise on load ────────────────────────────
  function initCountUp() {
    var els = document.querySelectorAll("[data-count-to]");
    if (!els.length || prefersReducedMotion()) {
      // Reduced motion: jump straight to the real value.
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
        }
      }
      requestAnimationFrame(step);
    });
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
        var done = function () {
          btn.textContent = "copied ✓";
          setTimeout(function () {
            btn.textContent = "copy";
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
    document.querySelectorAll(".evidence-sub-panel").forEach(function (panel) {
      panel.open = true;
    });
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
        var playPromise = video.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(function () {});
        }
        playBtn.hidden = true;
        if (unmuteBtn) {
          unmuteBtn.hidden = false;
        }
      });
      if (unmuteBtn) {
        unmuteBtn.addEventListener("click", function () {
          video.muted = false;
          unmuteBtn.hidden = true;
        });
      }
    });
  }

  function onReady() {
    initPlotly();
    initVccRail();
    initRunNav();
    initCountUp();
    initCopyButtons();
    initScrollReveal();
    initBriefingUnmute();
    initBriefingPlay();
    initGeneEvidenceLinks();
    initHashDisclosure();
    setTimeout(animateVesselFallback, 2000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
