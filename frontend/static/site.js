(function () {
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPlotly);
  } else {
    initPlotly();
  }
})();
