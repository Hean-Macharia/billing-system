(function () {
  'use strict';
  const root = document.getElementById('portal-carousel');
  if (!root) return;
  const slides = Array.from(root.querySelectorAll('[data-carousel-slide]'));
  const dots = Array.from(root.querySelectorAll('[data-carousel-dot]'));
  if (slides.length < 2) return;
  let index = 0;
  let timer = null;
  let touchStartX = null;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(next) {
    index = (next + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      const active = i === index;
      slide.classList.toggle('is-active', active);
      slide.setAttribute('aria-hidden', String(!active));
      if ('inert' in slide) slide.inert = !active;
    });
    dots.forEach((dot, i) => {
      const active = i === index;
      dot.classList.toggle('is-active', active);
      if (active) dot.setAttribute('aria-current', 'true');
      else dot.removeAttribute('aria-current');
    });
  }
  function pause() { if (timer) window.clearInterval(timer); timer = null; }
  function play() { pause(); if (!reducedMotion) timer = window.setInterval(() => show(index + 1), 6000); }
  root.querySelector('[data-carousel-prev]')?.addEventListener('click', () => { show(index - 1); play(); });
  root.querySelector('[data-carousel-next]')?.addEventListener('click', () => { show(index + 1); play(); });
  dots.forEach((dot) => dot.addEventListener('click', () => { show(Number(dot.dataset.carouselDot)); play(); }));
  root.addEventListener('mouseenter', pause);
  root.addEventListener('mouseleave', play);
  root.addEventListener('focusin', pause);
  root.addEventListener('focusout', (event) => { if (!root.contains(event.relatedTarget)) play(); });
  root.addEventListener('touchstart', (event) => { touchStartX = event.changedTouches[0]?.clientX ?? null; }, { passive: true });
  root.addEventListener('touchend', (event) => {
    if (touchStartX === null) return;
    const delta = event.changedTouches[0].clientX - touchStartX;
    if (Math.abs(delta) > 45) { show(index + (delta < 0 ? 1 : -1)); play(); }
    touchStartX = null;
  }, { passive: true });
  play();
}());
