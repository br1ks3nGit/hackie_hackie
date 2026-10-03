// Alpine component for the overview tier chart. Reads #tier-data (JSON rendered by the server)
// and rebuilds the chart whenever HTMX swaps the stats partial.
document.addEventListener("alpine:init", () => {
  Alpine.data("tierChart", () => ({
    chart: null,
    rendered: false,
    lastJson: null,
    init() {
      this.render();
      this.$el.addEventListener("htmx:afterSwap", (event) => {
        if (event.detail.target.id === "overview-stats") this.render();
      });
    },
    destroy() {
      if (this.chart) this.chart.destroy();
    },
    render() {
      const canvas = this.$el.querySelector("canvas[data-tier-chart]");
      const data = this.$el.querySelector("#tier-data");
      if (!canvas || !data || !window.Chart) {
        if (this.chart) this.chart.destroy();
        this.chart = null;
        this.lastJson = null;
        return;
      }
      if (this.chart && data.textContent === this.lastJson && this.chart.canvas === canvas) return;
      if (this.chart) this.chart.destroy();
      this.lastJson = data.textContent;
      const tiers = JSON.parse(data.textContent);
      const tk = window.DS_TOKENS;
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const valueLabels = {
        id: "valueLabels",
        afterDatasetsDraw(chart) {
          const { ctx } = chart;
          ctx.save();
          ctx.fillStyle = tk.text;
          ctx.font = "12px ui-sans-serif, system-ui, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          chart.getDatasetMeta(0).data.forEach((bar, i) => {
            ctx.fillText(String(chart.data.datasets[0].data[i]), bar.x, bar.y - 4);
          });
          ctx.restore();
        },
      };
      this.chart = new window.Chart(canvas, {
        type: "bar",
        data: {
          labels: tiers.map((t) => t.tier),
          datasets: [
            {
              label: "Scored trips",
              data: tiers.map((t) => t.count),
              backgroundColor: tiers.map((t) => tk.tier[t.tier]),
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: reduce || this.rendered ? false : undefined,
          plugins: { legend: { display: false } },
          layout: { padding: { top: 20 } },
          scales: {
            x: { grid: { color: tk.border }, ticks: { color: tk.textMuted, font: { size: 12 } } },
            y: {
              beginAtZero: true,
              grid: { color: tk.border },
              ticks: { color: tk.textMuted, font: { size: 12 }, precision: 0 },
            },
          },
        },
        plugins: [valueLabels],
      });
      this.rendered = true;
    },
  }));
});
