/* 论文速递 — cosmic interactions
   1. cursor spotlight (CSS custom props driven by mouse)
   2. starfield canvas (low-density twinkling stars)
   3. meteor trail (particles spawn at cursor, fade)
   4. respect prefers-reduced-motion
*/

(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- 1. cursor spotlight ----------
  let lastMove = 0;
  document.addEventListener("mousemove", (e) => {
    const now = performance.now();
    if (now - lastMove < 16) return; // ~60fps cap
    lastMove = now;
    document.documentElement.style.setProperty("--mouse-x", e.clientX + "px");
    document.documentElement.style.setProperty("--mouse-y", e.clientY + "px");
  }, { passive: true });

  if (reduceMotion) return; // skip canvas effects if user opts out

  // ---------- 2 + 3. canvas: starfield + meteor trail ----------
  const canvas = document.createElement("canvas");
  canvas.id = "starfield";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  let w = 0, h = 0;
  function resize() {
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize, { passive: true });

  // starfield
  const STAR_COUNT = Math.min(110, Math.floor((w * h) / 14000));
  const stars = Array.from({ length: STAR_COUNT }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    r: Math.random() * 1.1 + 0.2,
    a: Math.random() * 0.5 + 0.25,
    phase: Math.random() * Math.PI * 2,
    speed: Math.random() * 0.015 + 0.005,
    drift: Math.random() * 0.05 + 0.02,
  }));

  // meteor trail particles
  const trail = [];
  const MAX_TRAIL = 180;
  document.addEventListener("mousemove", (e) => {
    if (trail.length >= MAX_TRAIL) return;
    const count = 2;
    for (let i = 0; i < count; i++) {
      trail.push({
        x: e.clientX + (Math.random() - 0.5) * 8,
        y: e.clientY + (Math.random() - 0.5) * 8,
        vx: (Math.random() - 0.5) * 1.4,
        vy: (Math.random() - 0.5) * 1.4 + 0.4,
        life: 1.0,
        size: Math.random() * 2.2 + 0.8,
        hue: 250 + Math.random() * 80, // purple → pink range
      });
    }
  }, { passive: true });

  // pause when tab hidden (saves cycles)
  let running = true;
  document.addEventListener("visibilitychange", () => {
    running = !document.hidden;
    if (running) requestAnimationFrame(frame);
  });

  function frame() {
    if (!running) return;
    ctx.clearRect(0, 0, w, h);

    // stars
    for (const s of stars) {
      s.phase += s.speed;
      s.y += s.drift * 0.1; // very slow drift
      if (s.y > h) { s.y = -2; s.x = Math.random() * w; }
      const alpha = s.a * (0.55 + 0.45 * Math.sin(s.phase));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(220, 220, 255, ${alpha})`;
      ctx.fill();

      // occasional bright star with cross sparkle
      if (s.r > 1.0) {
        ctx.strokeStyle = `rgba(220, 220, 255, ${alpha * 0.4})`;
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.moveTo(s.x - s.r * 2.5, s.y);
        ctx.lineTo(s.x + s.r * 2.5, s.y);
        ctx.moveTo(s.x, s.y - s.r * 2.5);
        ctx.lineTo(s.x, s.y + s.r * 2.5);
        ctx.stroke();
      }
    }

    // meteor trail
    for (let i = trail.length - 1; i >= 0; i--) {
      const p = trail[i];
      p.x += p.vx;
      p.y += p.vy;
      p.life -= 0.028;
      if (p.life <= 0) {
        trail.splice(i, 1);
        continue;
      }
      const size = p.size * p.life;
      ctx.beginPath();
      ctx.arc(p.x, p.y, size, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 100%, 70%, ${p.life})`;
      ctx.shadowBlur = 14;
      ctx.shadowColor = `hsla(${p.hue}, 100%, 70%, ${p.life * 0.8})`;
      ctx.fill();
    }
    ctx.shadowBlur = 0;

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  // ---------- 4. card tilt on mouse position ----------
  document.addEventListener("DOMContentLoaded", () => {
    const cards = document.querySelectorAll(".paper-card");
    cards.forEach((card) => {
      card.addEventListener("mousemove", (e) => {
        const rect = card.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width - 0.5;
        const y = (e.clientY - rect.top) / rect.height - 0.5;
        card.style.transform = `translateY(-3px) perspective(900px) rotateX(${-y * 2.2}deg) rotateY(${x * 2.2}deg)`;
      });
      card.addEventListener("mouseleave", () => {
        card.style.transform = "";
      });
    });
  });
})();
