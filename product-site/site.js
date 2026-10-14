(() => {
  'use strict';
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 对比滑块：标签淡出 + 位置记忆 ---------- */
  document.querySelectorAll('[data-comparison]').forEach(group => {
    const comparison = group.querySelector('.comparison');
    const range = group.querySelector('.comparison-range');
    const zoom = group.querySelector('[data-zoom]');
    const reset = group.querySelector('[data-reset]');
    if (!comparison || !range || !zoom || !reset) return;
    const before = group.dataset.beforeLabel;
    const after = group.dataset.afterLabel;
    const storeKey = 'rnp-split:' + (comparison.id || 'default');

    const update = () => {
      const raw = Number(range.value);
      const split = Math.max(0, Math.min(100, Number.isFinite(raw) ? raw : 50));
      comparison.style.setProperty('--split', split + '%');
      range.setAttribute('aria-valuetext', before + ' ' + split + '%，' + after + ' ' + (100 - split) + '%');
    };
    const persist = () => {
      try { localStorage.setItem(storeKey, String(range.value)); } catch (e) { /* 隐私模式等：忽略 */ }
    };

    try {
      const saved = localStorage.getItem(storeKey);
      if (saved !== null) {
        const v = Number(saved);
        if (Number.isFinite(v) && v >= 0 && v <= 100) range.value = String(v);
      }
    } catch (e) { /* 忽略 */ }

    let dragTimer = null;
    const dragOn = () => {
      comparison.classList.add('is-dragging');
      clearTimeout(dragTimer);
    };
    const dragOff = () => comparison.classList.remove('is-dragging');
    range.addEventListener('input', () => {
      update();
      dragOn();
      dragTimer = setTimeout(dragOff, 650);
    });
    range.addEventListener('pointerdown', dragOn);
    range.addEventListener('keydown', dragOn);
    window.addEventListener('pointerup', dragOff);
    window.addEventListener('touchend', dragOff);
    range.addEventListener('change', persist);

    zoom.addEventListener('click', () => {
      const enlarged = comparison.classList.toggle('is-zoomed');
      zoom.setAttribute('aria-pressed', String(enlarged));
      zoom.innerHTML = enlarged ? '还原倍率 <span aria-hidden="true">−</span>' : '放大细节 <span aria-hidden="true">＋</span>';
    });
    reset.addEventListener('click', () => {
      range.value = '50';
      update();
      persist();
      comparison.classList.remove('is-zoomed');
      zoom.setAttribute('aria-pressed', 'false');
      zoom.innerHTML = '放大细节 <span aria-hidden="true">＋</span>';
    });
    update();
  });

  /* ---------- 滚动淡入（无 JS / 减少动效偏好时内容默认可见） ---------- */
  const revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length && 'IntersectionObserver' in window && !reduced) {
    document.documentElement.classList.add('js-reveal');
    const io = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting) {
          en.target.classList.add('is-visible');
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    revealEls.forEach(el => io.observe(el));
  }

  /* ---------- 导航当前章节高亮 ---------- */
  const navLinks = Array.from(document.querySelectorAll('.site-header nav a[href^="#"]'));
  const spyTargets = new Map();
  navLinks.forEach(a => spyTargets.set(a.getAttribute('href').slice(1), a));
  if ('IntersectionObserver' in window) {
    const mark = id => {
      navLinks.forEach(a => {
        if (a.getAttribute('href') === '#' + id) a.setAttribute('aria-current', 'true');
        else a.removeAttribute('aria-current');
      });
    };
    const spy = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting && spyTargets.has(en.target.id)) mark(en.target.id);
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
    document.querySelectorAll('main section[id]').forEach(s => {
      if (spyTargets.has(s.id)) spy.observe(s);
    });
  }

  /* ---------- 一键复制 SHA-256 ---------- */
  document.querySelectorAll('[data-copy-target]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const el = document.getElementById(btn.dataset.copyTarget);
      if (!el) return;
      const text = el.textContent.trim();
      let ok = false;
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          ok = true;
        } else {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.setAttribute('readonly', '');
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          ok = document.execCommand('copy');
          ta.remove();
        }
      } catch (e) { ok = false; }
      const old = btn.dataset.labelIdle || btn.textContent;
      btn.dataset.labelIdle = old;
      btn.textContent = ok ? '已复制' : '复制失败';
      btn.classList.toggle('is-copied', ok);
      btn.classList.toggle('is-failed', !ok);
      setTimeout(() => {
        btn.textContent = old;
        btn.classList.remove('is-copied', 'is-failed');
      }, 1800);
    });
  });

  /* ---------- 移动端底部浮动获取条 ---------- */
  const bar = document.querySelector('[data-get-bar]');
  const hero = document.querySelector('.hero');
  const download = document.getElementById('download');
  if (bar && hero) {
    let pastHero = false;
    let inDownload = false;
    const apply = () => {
      const shown = pastHero && !inDownload;
      bar.classList.toggle('is-shown', shown);
      document.body.classList.toggle('bar-on', shown);
    };
    bar.removeAttribute('hidden');
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(es => {
        es.forEach(e => { pastHero = !e.isIntersecting; });
        apply();
      }, { threshold: 0.05 }).observe(hero);
      if (download) {
        new IntersectionObserver(es => {
          es.forEach(e => { inDownload = e.isIntersecting; });
          apply();
        }, { rootMargin: '-10% 0px -74% 0px', threshold: 0 }).observe(download);
      }
    }
  }
})();
