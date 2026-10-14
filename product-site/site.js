(() => {
  'use strict';
  document.querySelectorAll('[data-comparison]').forEach(group => {
  const comparison = group.querySelector('.comparison');
  const range = group.querySelector('.comparison-range');
  const zoom = group.querySelector('[data-zoom]');
  const reset = group.querySelector('[data-reset]');
  if (!comparison || !range || !zoom || !reset) return;
  const before = group.dataset.beforeLabel;
  const after = group.dataset.afterLabel;
  const update = () => {
    const split = Math.max(0, Math.min(100, Number(range.value)));
    comparison.style.setProperty('--split', `${split}%`);
    range.setAttribute('aria-valuetext', `${before} ${split}%，${after} ${100 - split}%`);
  };
  range.addEventListener('input', update);
  zoom.addEventListener('click', () => {
    const enlarged = comparison.classList.toggle('is-zoomed');
    zoom.setAttribute('aria-pressed', String(enlarged));
    zoom.innerHTML = enlarged ? '还原倍率 <span aria-hidden="true">−</span>' : '放大细节 <span aria-hidden="true">＋</span>';
  });
  reset.addEventListener('click', () => {
    range.value = '50';
    update();
    comparison.classList.remove('is-zoomed');
    zoom.setAttribute('aria-pressed', 'false');
    zoom.innerHTML = '放大细节 <span aria-hidden="true">＋</span>';
  });
  update();
  });
})();
