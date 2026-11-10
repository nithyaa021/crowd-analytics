/* ==========================================================================
   workflow.js — the sample carousel and its annotations.

   Why this file exists: the page claims that slide copy comes out of an AI
   pipeline as structured data. The most honest way to prove that is to keep
   the copy here as a data array and render the slides from it — exactly what
   stage 05 would consume.

   Reading order:
     1. SLIDES   — the pipeline output (8 objects)
     2. render() — builds slides, dots, contact sheet
     3. controls — arrows, dots, keyboard, swipe
     4. misc     — copy-to-clipboard for the prompt pack
   ========================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------------
     1. Pipeline output
     Each object is what stage 03 returns and stage 04 annotates. The fields
     match the JSON contract shown in the prompt pack, on purpose.
     --------------------------------------------------------------------- */
  const SLIDES = [
    {
      role: "hook",
      template: "T1",
      kicker: "It's 11pm",
      headline: "Your dog is vomiting. Every clinic near you is shut. Now what?",
      body: "",
      why: "The hook does not describe the post. It drops the reader into a specific, uncomfortable moment they can picture — which is what earns the second slide.",
      note: "No emoji. No 'here are 5 tips'. The tension is the whole job of slide 1.",
      meta: ["Hook", "Dark template", "0 facts"],
    },
    {
      role: "point",
      template: "T2",
      kicker: "First 10 minutes",
      headline: "Check the gums before you check Google.",
      body: "Press a thumb on the gum, release. Healthy colour returns in under 2 seconds. If it stays pale, that's an emergency, not a wait-and-see.",
      why: "Point one is something the reader can do immediately, with their hands, at 11pm. Actionable beats informative when someone is panicking.",
      note: "One instruction, one threshold (2 seconds). A number gives the reader a decision rule.",
      meta: ["Point", "Light template", "1 checkable rule"],
    },
    {
      role: "point",
      template: "T2",
      kicker: "Then",
      headline: "Count the breaths. Twelve to thirty is normal for a dog.",
      body: "Watch the chest for 15 seconds and multiply by four. Above 40 at rest, or open-mouth breathing in a cat, means go now.",
      why: "Point two gives a second decision rule in the same format, so the reader learns a repeatable way to judge urgency rather than memorising facts.",
      note: "Numbers are the most screenshot-able content in the set. This is the slide people save.",
      meta: ["Point", "Light template", "2 thresholds"],
    },
    {
      role: "point",
      template: "T2",
      kicker: "Not a checklist",
      headline: "Do not give human medicine. Ever.",
      body: "Paracetamol and ibuprofen are toxic to dogs and cats at doses humans take without thinking. No vet has ever been annoyed by you asking first.",
      why: "The strongest slide is a prohibition, because the most common harm is an action, not inaction. It also gives the post a shareable 'I didn't know that' moment.",
      note: "Medical claim — this is exactly what the [VERIFIED] tag in the research prompt exists for.",
      meta: ["Point", "Light template", "Needs sourcing"],
    },
    {
      role: "point",
      template: "T2",
      kicker: "Meanwhile",
      headline: "Call ahead, even at midnight. Someone usually answers.",
      body: "Ask one question: 'Can you take a vomiting dog in the next thirty minutes?' If the answer is no, ask who can.",
      why: "This slide converts the reader from research to action. The scripted question exists so a panicking person does not have to find words.",
      note: "Giving exact words to say is the highest-converting move in a practical carousel.",
      meta: ["Point", "Light template", "1 script"],
    },
    {
      role: "point",
      template: "T3",
      kicker: "Why it matters",
      headline: "The first hour is often the difference.",
      body: "In poisoning and bloat cases, outcome is strongly tied to how fast treatment starts. Transport time is the part you control.",
      why: "The one slide that justifies the urgency. It comes late on purpose — by now the reader is invested enough to accept a heavier line.",
      note: "Deliberately non-specific ('often', 'strongly tied') because precise statistics need a source we don't have.",
      meta: ["Proof", "Dark template", "Soft claim"],
    },
    {
      role: "proof",
      template: "T3",
      kicker: "The one thing to remember",
      headline: "Pale gums, 40+ breaths, or a swollen belly. Go.",
      body: "",
      why: "A three-item memory aid. Carousels get remembered for one line, so this slide is designed to be that line — and the one that gets screenshotted and shared.",
      note: "Three items, seven words total. Anything longer is not memorable at 11pm.",
      meta: ["Summary", "Dark template", "Saveable"],
    },
    {
      role: "cta",
      template: "T4",
      kicker: "Before you need it",
      headline: "Find the 24-hour clinic near you — now, while nothing is wrong.",
      body: "Save the number tonight. At 11pm you should not be searching.",
      why: "The CTA asks for a tiny, obviously useful action that benefits the reader even if they never come back. That is why it works.",
      note: "One ask only. The secondary ask (follow) is left out deliberately.",
      meta: ["CTA", "Brand template", "1 action"],
    },
  ];

  /* Element handles. */
  const viewport = document.getElementById("viewport");
  const dots = document.getElementById("dots");
  const slideNow = document.getElementById("slideNow");
  const noteBody = document.getElementById("slideNote");
  const noteSlide = document.getElementById("noteSlide");
  const contactSheet = document.getElementById("contactSheet");
  const prev = document.getElementById("prev");
  const next = document.getElementById("next");

  let current = 0;

  /* ---------------------------------------------------------------------
     2. Rendering
     --------------------------------------------------------------------- */

  /** WHY: role maps to a visual template so the design system stays closed. */
  function slideClass(slide) {
    if (slide.role === "cta") return "slide slide--cta";
    if (slide.template === "T1") return "slide slide--dark slide--hook";
    if (slide.template === "T3") return "slide slide--dark";
    return "slide slide--light";
  }

  function slideHTML(slide, index) {
    const isLast = index === SLIDES.length - 1;

    /* The big numeral is decorative rhythm, not information. */
    const numeral =
      slide.template === "T2" && index > 0
        ? '<span class="slide__num">0' + index + "</span>"
        : "";

    const cta = slide.role === "cta" ? '<span class="slide__cta">Save this for tonight →</span>' : "";

    return (
      '<div class="' +
      slideClass(slide) +
      '" data-index="' +
      index +
      '" role="group" aria-roledescription="slide" aria-label="Slide ' +
      (index + 1) +
      ' of ' +
      SLIDES.length +
      '">' +
      '<div class="slide__top">' +
      '<span class="slide__kicker">' +
      slide.kicker +
      "</span>" +
      '<span class="slide__mark">practo for animals</span>' +
      "</div>" +
      '<div class="slide__mid">' +
      numeral +
      '<h3 class="slide__headline">' +
      slide.headline +
      "</h3>" +
      (slide.body ? '<p class="slide__body">' + slide.body + "</p>" : "") +
      cta +
      "</div>" +
      '<div class="slide__foot">' +
      '<span class="slide__swipe">' +
      (isLast ? "Save · Share" : "Swipe →") +
      "</span>" +
      '<span class="slide__handle">@practoforanimals</span>' +
      "</div>" +
      "</div>"
    );
  }

  function thumbClass(slide) {
    if (slide.role === "cta") return "thumb thumb--cta";
    if (slide.template === "T1" || slide.template === "T3") return "thumb thumb--dark";
    return "thumb thumb--light";
  }

  /**
   * WHY: The contact sheet lets a reviewer see the whole set's rhythm at a
   * glance — which is a design decision you cannot judge one slide at a time.
   * The button's accessible name comes from its visible text (number + headline)
   * so screen-reader users hear exactly what sighted users see.
   */
  function renderContactSheet() {
    if (!contactSheet) return;

    contactSheet.innerHTML = SLIDES.map(function (slide, index) {
      return (
        '<button type="button" class="' +
        thumbClass(slide) +
        '" data-goto="' +
        index +
        '">' +
        '<span class="thumb__n" aria-hidden="true">0' +
        (index + 1) +
        "</span>" +
        '<span class="thumb__t">' +
        slide.headline +
        "</span>" +
        "</button>"
      );
    }).join("");
  }

  function renderDots() {
    if (!dots) return;

    dots.innerHTML = SLIDES.map(function (slide, index) {
      return (
        '<button type="button" class="carousel__dot" role="tab" data-goto="' +
        index +
        '" aria-label="Slide ' +
        (index + 1) +
        '" aria-selected="' +
        (index === 0) +
        '"></button>'
      );
    }).join("");
  }

  /** WHY: The annotation panel is the teaching layer for the sample carousel. */
  function renderNote(index) {
    const slide = SLIDES[index];
    if (!slide || !noteBody) return;

    noteBody.innerHTML =
      '<h4>' +
      slide.headline +
      "</h4>" +
      "<p>" +
      slide.why +
      "</p>" +
      '<div class="notes__why"><strong>Build note:</strong> ' +
      slide.note +
      "</div>" +
      '<div class="notes__meta">' +
      slide.meta
        .map(function (tag) {
          return '<span class="tag">' + tag + "</span>";
        })
        .join("") +
      "</div>";

    if (noteSlide) noteSlide.textContent = "Slide " + (index + 1) + " of " + SLIDES.length;
  }

  /* ---------------------------------------------------------------------
     3. Navigation
     --------------------------------------------------------------------- */

  /**
   * WHY: One goTo() function means arrows, dots, thumbs, keyboard and swipe
   * all behave identically. Bug surface shrinks to a single place.
   */
  function goTo(index) {
    const clamped = Math.max(0, Math.min(SLIDES.length - 1, index));
    current = clamped;

    /* Swap the visible slide. */
    document.querySelectorAll(".slide").forEach(function (slide) {
      const isTarget = Number(slide.dataset.index) === clamped;
      slide.classList.toggle("is-on", isTarget);
      slide.setAttribute("aria-hidden", String(!isTarget));
    });

    /* Sync dots. */
    document.querySelectorAll(".carousel__dot").forEach(function (dot, i) {
      const on = i === clamped;
      dot.classList.toggle("is-on", on);
      dot.setAttribute("aria-selected", String(on));
    });

    /* Sync contact sheet highlight. */
    document.querySelectorAll(".thumb").forEach(function (thumb, i) {
      thumb.classList.toggle("is-on", i === clamped);
    });

    if (slideNow) slideNow.textContent = String(clamped + 1);
    if (prev) prev.disabled = clamped === 0;
    if (next) next.disabled = clamped === SLIDES.length - 1;

    renderNote(clamped);
  }

  function bindControls() {
    if (prev) {
      prev.addEventListener("click", function () {
        goTo(current - 1);
      });
    }

    if (next) {
      next.addEventListener("click", function () {
        goTo(current + 1);
      });
    }

    /* Delegate: dots and thumbnails share the data-goto attribute. */
    document.addEventListener("click", function (event) {
      const trigger = event.target.closest("[data-goto]");
      if (!trigger) return;
      goTo(Number(trigger.dataset.goto));
    });

    /* Keyboard support is required for a control that is a div. */
    if (viewport) {
      viewport.addEventListener("keydown", function (event) {
        if (event.key === "ArrowRight") {
          event.preventDefault();
          goTo(current + 1);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          goTo(current - 1);
        }
      });

      /* Touch swipe: 40px is the threshold that avoids accidental changes. */
      let startX = 0;
      let startY = 0;

      viewport.addEventListener(
        "touchstart",
        function (event) {
          startX = event.touches[0].clientX;
          startY = event.touches[0].clientY;
        },
        { passive: true }
      );

      viewport.addEventListener(
        "touchend",
        function (event) {
          const dx = event.changedTouches[0].clientX - startX;
          const dy = event.changedTouches[0].clientY - startY;

          /* Ignore mostly-vertical gestures so page scrolling still works. */
          if (Math.abs(dx) < 40 || Math.abs(dy) > Math.abs(dx)) return;

          goTo(dx < 0 ? current + 1 : current - 1);
        },
        { passive: true }
      );
    }
  }

  /* ---------------------------------------------------------------------
     4. Prompt copy buttons
     --------------------------------------------------------------------- */

  /**
   * WHY: The prompt pack is meant to be reused, so copying must work without
   * a selection dance. The clipboard API needs a fallback for file:// pages.
   */
  function initCopyButtons() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        const source = document.getElementById(button.dataset.copy);
        if (!source) return;

        const text = source.textContent;

        const done = function () {
          const original = button.textContent;
          button.textContent = "Copied";
          window.setTimeout(function () {
            button.textContent = original;
          }, 1600);
        };

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(done, function () {
            window.UI.toast("Copy blocked by the browser — select the text manually", "warn");
          });
          return;
        }

        /* Legacy path, works from file:// in most browsers. */
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();

        try {
          document.execCommand("copy");
          done();
        } catch (error) {
          window.UI.toast("Copy blocked by the browser — select the text manually", "warn");
        } finally {
          document.body.removeChild(area);
        }
      });
    });
  }

  /* ---------------------------------------------------------------------
     5. Boot
     --------------------------------------------------------------------- */
  function init() {
    if (!viewport) return;

    viewport.innerHTML = SLIDES.map(slideHTML).join("");
    renderDots();
    renderContactSheet();
    bindControls();
    initCopyButtons();
    goTo(0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
