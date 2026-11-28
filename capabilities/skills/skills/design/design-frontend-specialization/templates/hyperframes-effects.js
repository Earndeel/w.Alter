// Scena — Hyperframes-style effects engine (vanilla, zero deps)
// Template: copy to assets/ and include with <script src="assets/hyperframes-effects.js"></script>
(function() {
  'use strict';

  // ── Particle canvas background ──
  const canvas = document.createElement('canvas');
  canvas.id = 'particle-canvas';
  canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:-1;';
  document.body.insertBefore(canvas, document.body.firstChild);

  const ctx = canvas.getContext('2d');
  let particles = [];
  const PARTICLE_COUNT = 50;
  const ACCENT = '167,139,250'; // violet rgb

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  class Particle {
    constructor() { this.reset(); }
    reset() {
      this.x = Math.random() * canvas.width;
      this.y = Math.random() * canvas.height;
      this.vx = (Math.random() - .5) * .3;
      this.vy = (Math.random() - .5) * .3;
      this.r = Math.random() * 1.5 + .5;
      this.alpha = Math.random() * .4 + .2;
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
      if (this.y < 0 || this.y > canvas.height) this.vy *= -1;
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${ACCENT},${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());

  function animateParticles() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist < 150) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(${ACCENT},${.06 * (1 - dist/150)})`;
          ctx.lineWidth = .5;
          ctx.stroke();
        }
      }
    }
    particles.forEach(p => { p.update(); p.draw(); });
    requestAnimationFrame(animateParticles);
  }
  animateParticles();

  // ── Spotlight cursor tracking ──
  document.querySelectorAll('.spotlight-card, .card, .price-card, .step, .kpi, .video-cell').forEach(el => {
    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      el.style.setProperty('--mouse-x', `${x}%`);
      el.style.setProperty('--mouse-y', `${y}%`);
    });
  });

  // ── Scroll reveal ──
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -60px 0px' });

  document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

  // Stagger children
  const staggerObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const children = entry.target.children;
        Array.from(children).forEach((child, i) => {
          child.style.opacity = '0';
          child.style.transform = 'translateY(30px)';
          setTimeout(() => {
            child.style.transition = 'all .7s cubic-bezier(.16,1,.3,1)';
            child.style.opacity = '1';
            child.style.transform = 'translateY(0)';
          }, i * 100);
        });
        staggerObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.card-grid, .pricing-grid, .steps, .page-kpis, .video-grid').forEach(el => staggerObserver.observe(el));

  // ── 3D Tilt on cards ──
  document.querySelectorAll('.card, .price-card, .video-cell').forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const rx = (y - cy) / cy * -10;
      const ry = (x - cx) / cx * 10;
      card.style.transform = `perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(20px)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
      card.style.transition = 'transform .6s cubic-bezier(.16,1,.3,1)';
    });
    card.addEventListener('mouseenter', () => {
      card.style.transition = 'transform .1s ease';
    });
  });

  // ── Nav scroll effect ──
  const nav = document.querySelector('.nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 50) {
        nav.style.background = 'rgba(10,10,10,.9)';
        nav.style.borderColor = 'rgba(255,255,255,.1)';
      } else {
        nav.style.background = 'rgba(10,10,10,.7)';
        nav.style.borderColor = 'var(--border)';
      }
    }, { passive: true });
  }

  // ── Mobile toggle ──
  window.toggleNav = function() {
    document.querySelector('.nav-center').classList.toggle('open');
  };

  // ── Year ──
  const yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // ── Typing effect ──
  const heroH1 = document.querySelector('.hero h1');
  if (heroH1 && !heroH1.dataset.typed) {
    const text = heroH1.textContent;
    heroH1.dataset.typed = 'true';
    heroH1.innerHTML = '<span class="typing-text"></span><span class="typing-cursor">|</span>';
    const typingEl = heroH1.querySelector('.typing-text');
    let i = 0;
    function type() {
      if (i < text.length) {
        typingEl.textContent += text.charAt(i);
        i++;
        setTimeout(type, 40);
      }
    }
    setTimeout(type, 400);
  }
})();
