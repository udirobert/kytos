(function () {
  "use strict";

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  // ── Metrics chart (Plotly) ────────────────────────────────────────────────
  function initPlotly() {
    var el = document.getElementById("metrics-chart");
    var dataEl = document.getElementById("metrics-chart-data");
    if (!el || !dataEl || typeof Plotly === "undefined") {
      return;
    }
    try {
      var spec = JSON.parse(dataEl.textContent || "{}");
      if (!spec.data || !spec.data.length) {
        return;
      }
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

  // ── VCC timeline rail: live needle + countdown to Nov 5 ───────────────────
  function initVccRail() {
    var track = document.querySelector(".vcc-track");
    if (!track) {
      return;
    }
    var start = new Date("2026-08-20T00:00:00Z").getTime();
    var end = new Date("2026-11-05T23:59:59Z").getTime();
    var markers = Array.prototype.slice.call(track.querySelectorAll(".vcc-marker"));
    var needle = document.getElementById("vcc-needle");
    var fill = document.getElementById("vcc-fill");
    var countdown = document.getElementById("vcc-countdown");
    if (!needle || !fill || !countdown) {
      return;
    }

    function pct(date) {
      return Math.min(1, Math.max(0, (date - start) / (end - start)));
    }

    function tick() {
      var now = Date.now();
      var progress = pct(now);

      markers.forEach(function (marker) {
        var date = new Date(marker.getAttribute("data-date")).getTime();
        marker.style.left = (pct(date) * 100).toFixed(2) + "%";
      });

      needle.style.left = (progress * 100).toFixed(2) + "%";
      fill.style.width = (progress * 100).toFixed(2) + "%";

      var remaining = Math.max(0, end - now);
      var days = Math.floor(remaining / 86400000);
      var hours = Math.floor((remaining % 86400000) / 3600000);
      var minutes = Math.floor((remaining % 3600000) / 60000);
      var seconds = Math.floor((remaining % 60000) / 1000);
      var pad = function (n) {
        return String(n).padStart(2, "0");
      };
      countdown.textContent = days + "d " + pad(hours) + ":" + pad(minutes) + ":" + pad(seconds);
    }

    tick();
    setInterval(tick, 1000);
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

  function onReady() {
    initPlotly();
    initVccRail();
    initCopyButtons();
    initScrollReveal();
    setTimeout(animateVesselFallback, 2000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onReady);
  } else {
    onReady();
  }
})();
