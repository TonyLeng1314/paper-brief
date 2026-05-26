/* 论文速递 — interactions
   1. cursor → CSS vars (spotlight 跟随)
   2. DOM meteors (setInterval spawn into #cyber-fx)
   3. respect prefers-reduced-motion + visibilitychange
*/

(function () {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- 1. cursor → CSS vars ----------
  let lastMove = 0;
  document.addEventListener("mousemove", (e) => {
    const now = performance.now();
    if (now - lastMove < 16) return; // ~60fps cap
    lastMove = now;
    document.documentElement.style.setProperty("--mouse-x", e.clientX + "px");
    document.documentElement.style.setProperty("--mouse-y", e.clientY + "px");
  }, { passive: true });

  if (reduceMotion) return;

  // ---------- 2. DOM meteors ----------
  const isMobile = window.matchMedia("(max-width: 768px)").matches;
  if (isMobile) return;

  function spawnMeteor() {
    if (document.hidden) return;
    const host = document.getElementById("cyber-fx");
    if (!host) return;
    const m = document.createElement("span");
    m.className = "fx-meteor";
    m.style.left = (Math.random() * 100) + "vw";
    const dur = 3 + Math.random() * 4; // 3-7s
    m.style.animationDuration = dur + "s";
    m.style.animationDelay = "0s";
    // subtle hue jitter
    const hue = 180 + Math.random() * 160; // cyan → pink range
    m.style.filter = `hue-rotate(${hue - 200}deg)`;
    host.appendChild(m);
    setTimeout(() => m.remove(), (dur + 0.5) * 1000);
  }

  // initial burst then steady cadence
  for (let i = 0; i < 3; i++) {
    setTimeout(spawnMeteor, i * 600);
  }
  const meteorInterval = setInterval(spawnMeteor, 900);

  document.addEventListener("visibilitychange", () => {
    // setInterval keeps ticking but spawnMeteor early-returns when hidden
    // — nothing else to do
  });

  // ---------- 3. ensure #cyber-fx exists (fallback for non-overridden pages) ----------
  if (!document.getElementById("cyber-fx")) {
    const fx = document.createElement("div");
    fx.id = "cyber-fx";
    fx.setAttribute("aria-hidden", "true");
    fx.innerHTML =
      '<div class="fx-aurora"></div>' +
      '<div class="fx-scanlines"></div>' +
      '<div class="fx-noise"></div>';
    document.body.prepend(fx);
  }
})();
