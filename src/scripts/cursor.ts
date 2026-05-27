/*
 * paper-brief · client-side effects
 *   1. mouse → CSS vars (--mouse-x / --mouse-y) for spotlight follow
 *   2. DOM-spawned meteors into #cyber-fx
 *   3. IntersectionObserver → add .in to .paper-card for stagger rise
 *   4. respect prefers-reduced-motion + small screens + tab visibility
 */

(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia('(max-width: 768px)').matches;

  // ---- 1. cursor → CSS vars ----
  let lastMove = 0;
  document.addEventListener(
    'mousemove',
    (e) => {
      const now = performance.now();
      if (now - lastMove < 16) return;
      lastMove = now;
      const root = document.documentElement;
      root.style.setProperty('--mouse-x', `${e.clientX}px`);
      root.style.setProperty('--mouse-y', `${e.clientY}px`);
    },
    { passive: true },
  );

  // ---- 3. IntersectionObserver for paper-card stagger ----
  const cards = document.querySelectorAll<HTMLElement>('.paper-card');
  if (cards.length) {
    if (reduceMotion || !('IntersectionObserver' in window)) {
      cards.forEach((c) => c.classList.add('in'));
    } else {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry, i) => {
            if (entry.isIntersecting) {
              const el = entry.target as HTMLElement;
              const delay = Math.min(i * 80, 320);
              window.setTimeout(() => el.classList.add('in'), delay);
              io.unobserve(el);
            }
          });
        },
        { rootMargin: '0px 0px -10% 0px', threshold: 0.05 },
      );
      cards.forEach((c) => io.observe(c));
    }
  }

  if (reduceMotion || isMobile) return;

  // ---- 2. DOM meteors ----
  const host = document.getElementById('cyber-fx');
  if (!host) return;

  const spawn = () => {
    if (document.hidden) return;
    const m = document.createElement('span');
    m.className = 'fx-meteor';
    m.style.left = `${Math.random() * 100}vw`;
    const dur = 4 + Math.random() * 3; // 4-7s,比之前慢
    m.style.animationDuration = `${dur}s`;
    const hue = 180 + Math.random() * 160;
    m.style.filter = `hue-rotate(${hue - 200}deg)`;
    host.appendChild(m);
    window.setTimeout(() => m.remove(), (dur + 0.5) * 1000);
  };

  for (let i = 0; i < 3; i++) window.setTimeout(spawn, i * 800);
  window.setInterval(spawn, 1200); // refined:1.2s 一颗
})();
