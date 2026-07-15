from __future__ import annotations


def investment_chart_script() -> str:
    return r"""
<script>
(() => {
  const root = document.querySelector('[data-equity-chart]');
  const source = document.getElementById('equity-chart-data');
  if (!root || !source) return;
  const data = JSON.parse(source.textContent);
  const svg = root.querySelector('svg');
  const crosshair = root.querySelector('[data-crosshair]');
  const strategyDot = root.querySelector('[data-strategy-dot]');
  const benchmarkDot = root.querySelector('[data-benchmark-dot]');
  const tooltip = root.querySelector('[data-chart-tooltip]');
  const left = 58, right = 18, top = 18, bottom = 40, width = 960, height = 280;
  const plotWidth = width - left - right;
  const values = data.strategy.map((point) => point.value).concat(data.benchmark.map((point) => point.value));
  const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const y = (value) => top + (height - top - bottom) * (high - value) / span;
  const show = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const relative = Math.min(Math.max(clientX - rect.left, 0), rect.width);
    const index = Math.round(relative / rect.width * (data.strategy.length - 1));
    const strategy = data.strategy[index], benchmark = data.benchmark[index];
    const x = left + plotWidth * index / Math.max(data.strategy.length - 1, 1);
    crosshair.setAttribute('x1', x); crosshair.setAttribute('x2', x);
    strategyDot.setAttribute('cx', x); strategyDot.setAttribute('cy', y(strategy.value));
    benchmarkDot.setAttribute('cx', x); benchmarkDot.setAttribute('cy', y(benchmark.value));
    [crosshair, strategyDot, benchmarkDot].forEach((node) => node.hidden = false);
    tooltip.innerHTML = `<strong>${strategy.date}</strong><span>Execution V1：${strategy.value.toFixed(4)}</span><span>510500 基准：${benchmark.value.toFixed(4)}</span><span>相对差值：${(strategy.value - benchmark.value).toFixed(4)}</span>`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(Math.max(relative, 92), rect.width - 92)}px`;
  };
  root.addEventListener('mousemove', (event) => show(event.clientX));
  root.addEventListener('touchmove', (event) => { show(event.touches[0].clientX); event.preventDefault(); }, {passive:false});
  root.addEventListener('mouseleave', () => { [crosshair, strategyDot, benchmarkDot].forEach((node) => node.hidden = true); tooltip.hidden = true; });
})();
</script>
"""
