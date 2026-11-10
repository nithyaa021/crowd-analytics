/* ==========================================================================
   base.js — behaviour shared by every page.
   Why this file exists: the sticky nav, the mobile menu, the scroll reveal and
   the toast are identical on all three prototypes. Writing them once keeps the
   pages consistent and keeps each page's own script small.
   No libraries, no build step: plain ES2020 in one <script defer> tag.
   ========================================================================== */

(function () {
  "use strict";

  /* The <html> tag starts with class="no-js"; replace it so CSS knows JS ran. */
  document.documentElement.classList.remove("no-js");

  /**
   * WHY: On a long page the nav should feel attached to the content, so we add
   * a border + shadow only once the user has scrolled past the hero top.
   */
  function initStickyNav() {
    const nav = document.querySelector(".nav");
    if (!nav) return;

    const sync = function () {
      nav.classList.toggle("is-stuck", window.scrollY > 8);
    };

    sync();
    window.addEventListener("scroll", sync, { passive: true });
  }

  /**
   * WHY: A 70px sticky bar would cover the top of any section we jump to, so we
   * push those targets down by the bar height when they are scrolled to.
   */
  function initAnchorOffset() {
    document.querySelectorAll('a[href^="#"]').forEach(function (link) {
      link.addEventListener("click", function (event) {
        const id = link.getAttribute("href");
        if (!id || id === "#") return;

        const target = document.querySelector(id);
        if (!target) return;

        event.preventDefault();
        const top = target.getBoundingClientRect().top + window.scrollY - 82;
        window.scrollTo({ top: top, behavior: "smooth" });
        closeMobileMenu();
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      });
    });
  }

  /**
   * WHY: On phones the nav links collapse into a sheet. This toggles that sheet
   * and keeps aria-expanded honest for screen readers.
   */
  function initMobileMenu() {
    const toggle = document.querySelector(".nav__toggle");
    const links = document.querySelector(".nav__links");
    if (!toggle || !links) return;

    /* Mirror the bar's CTA buttons into the sheet, since base.css hides them
       in the bar at narrow widths to stop it overflowing. */
    const actions = document.querySelector(".nav__actions");
    if (actions && !links.querySelector(".nav__cta-menu")) {
      const mirror = document.createElement("div");
      mirror.className = "nav__cta-menu";

      actions.querySelectorAll("a.btn").forEach(function (link) {
        mirror.appendChild(link.cloneNode(true));
      });

      links.appendChild(mirror);
    }

    toggle.addEventListener("click", function () {
      const open = links.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  /** WHY: Shared by the anchor handler and the menu button so both can close it. */
  function closeMobileMenu() {
    const links = document.querySelector(".nav__links");
    const toggle = document.querySelector(".nav__toggle");
    if (links) links.classList.remove("is-open");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
  }

  /**
   * WHY: Gentle entrance animations make a static prototype feel like a real
   * product. We use IntersectionObserver so it costs nothing while offscreen,
   * and we never hide content if the browser lacks support.
   */
  function initReveal() {
    const items = document.querySelectorAll(".reveal");
    if (!items.length) return;

    if (!("IntersectionObserver" in window)) {
      items.forEach(function (item) {
        item.classList.add("is-in");
      });
      return;
    }

    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-in");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.06 }
    );

    items.forEach(function (item) {
      observer.observe(item);
    });
  }

  /**
   * WHY: Prototype forms have no backend, so a toast is how we prove the
   * journey "works" end to end without inventing a fake success screen.
   */
  let toastTimer = null;

  function toast(message, tone) {
    let el = document.querySelector(".toast");

    if (!el) {
      el = document.createElement("div");
      el.className = "toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }

    el.textContent = message;
    el.dataset.tone = tone || "default";
    el.classList.add("is-on");

    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      el.classList.remove("is-on");
    }, 3800);
  }

  /* Expose the small helpers the page scripts need. */
  window.UI = { toast: toast, closeMobileMenu: closeMobileMenu };

  /**
   * WHY: Counting numbers up is the cheapest way to signal "data". We keep it
   * short (under one second) so nobody waits to read a statistic.
   */
  function initCounters() {
    const nodes = document.querySelectorAll("[data-count]");
    if (!nodes.length) return;

    const run = function (node) {
      const target = Number(node.dataset.count);
      const suffix = node.dataset.suffix || "";
      const prefix = node.dataset.prefix || "";
      const decimals = Number(node.dataset.decimals || 0);
      const duration = 850;
      const start = performance.now();

      function frame(now) {
        const progress = Math.min((now - start) / duration, 1);
        /* easeOutCubic keeps the motion quick then settles, not linear. */
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = target * eased;
        node.textContent =
          prefix +
          value.toLocaleString("en-IN", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suffix;
        if (progress < 1) requestAnimationFrame(frame);
      }

      requestAnimationFrame(frame);
    };

    if (!("IntersectionObserver" in window)) {
      nodes.forEach(run);
      return;
    }

    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          run(entry.target);
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.4 }
    );

    nodes.forEach(function (node) {
      observer.observe(node);
    });
  }

  function boot() {
    initStickyNav();
    initAnchorOffset();
    initMobileMenu();
    initReveal();
    initCounters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
