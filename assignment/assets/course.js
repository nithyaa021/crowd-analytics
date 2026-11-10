/* ==========================================================================
   course.js — interaction for the AI education landing page.
   Why this file exists: the page makes a promise about low friction, so the
   two-step lead form has to behave exactly as described. It also handles the
   curriculum accordion and the seat counter.

   Reading order:
     1. Accordion (curriculum weeks)
     2. Two-step lead form with validation
     3. Seat counter + intent pre-selection
   ========================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------------
     1. Curriculum accordion
     Why a hand-rolled accordion: <details> cannot animate its height smoothly
     and we want only one week open at a time, so the grid-rows trick is used
     with explicit ARIA state.
     --------------------------------------------------------------------- */
  function initWeeks() {
    const weeks = Array.prototype.slice.call(document.querySelectorAll(".week"));
    if (!weeks.length) return;

    weeks.forEach(function (week) {
      const head = week.querySelector(".week__head");
      if (!head) return;

      head.addEventListener("click", function () {
        const willOpen = !week.classList.contains("is-open");

        /* Close every week, then open the clicked one: accordion behaviour. */
        weeks.forEach(function (other) {
          other.classList.remove("is-open");
          const otherHead = other.querySelector(".week__head");
          if (otherHead) otherHead.setAttribute("aria-expanded", "false");
        });

        if (willOpen) {
          week.classList.add("is-open");
          head.setAttribute("aria-expanded", "true");
        }
      });
    });
  }

  /* ---------------------------------------------------------------------
     2. Two-step lead form
     Step 1 asks for name + phone. Step 2 asks one qualifying question.
     The order is deliberate: qualification after contact details reads like
     personalisation, before them it reads like a survey.
     --------------------------------------------------------------------- */

  const form = document.getElementById("leadForm");

  /* Field-level validation helpers, shared with the discovery page pattern. */
  function setError(input, message) {
    input.classList.add("is-error");
    input.setAttribute("aria-invalid", "true");

    let hint = input.parentElement.querySelector(".field__error");
    if (!hint) {
      hint = document.createElement("span");
      hint.className = "field__error";
      input.parentElement.appendChild(hint);
    }
    hint.textContent = message;
  }

  function clearError(input) {
    input.classList.remove("is-error");
    input.removeAttribute("aria-invalid");
    const hint = input.parentElement.querySelector(".field__error");
    if (hint) hint.remove();
  }

  /** WHY: Step changes must also move focus so screen readers follow along. */
  function showStep(number) {
    if (!form) return;

    form.querySelectorAll(".lead__step").forEach(function (step) {
      const isTarget = Number(step.dataset.step) === number;
      step.hidden = !isTarget;

      if (isTarget) {
        const heading = step.querySelector("h3");
        if (heading) {
          heading.setAttribute("tabindex", "-1");
          heading.focus({ preventScroll: true });
        }
      }
    });
  }

  function initLeadForm() {
    if (!form) return;

    const name = document.getElementById("leadName");
    const phone = document.getElementById("leadPhone");
    const donePhone = document.getElementById("donePhone");
    const seatsLeft = document.getElementById("seatsLeft");
    const back = form.querySelector("[data-back]");

    [name, phone].forEach(function (input) {
      input.addEventListener("input", function () {
        clearError(input);
      });
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      const onStepOne = !form.querySelector('[data-step="1"]').hidden;

      /* ---------- Step 1 validation ---------- */
      if (onStepOne) {
        let valid = true;

        if (name.value.trim().length < 2) {
          setError(name, "Please tell us your name.");
          valid = false;
        }

        const digits = phone.value.replace(/\D/g, "");
        if (digits.length < 10) {
          setError(phone, "That doesn't look like a 10-digit number.");
          valid = false;
        }

        if (!valid) {
          window.UI.toast("Two small fixes needed", "warn");
          return;
        }

        showStep(2);
        return;
      }

      /* ---------- Step 2: submit ---------- */
      const stageInput = form.querySelector('input[name="stage"]:checked');
      const stage = stageInput ? stageInput.value : "student";

      donePhone.textContent = phone.value.trim();
      showStep(3);
      window.UI.toast("Seat reserved — check WhatsApp");

      /* Decrement the seat counter so the page feels alive, not frozen. */
      if (seatsLeft) {
        const remaining = Math.max(0, Number(seatsLeft.textContent) - 1);
        seatsLeft.textContent = String(remaining);
      }

      /* WHY: We log the captured lead object so a reviewer can see exactly
         which fields the backend would receive. Nothing is transmitted. */
      console.info("[prototype] lead captured", {
        name: name.value.trim(),
        phone: phone.value.trim(),
        stage: stage,
        cohort: "04",
        timestamp: new Date().toISOString(),
      });
    });

    if (back) {
      back.addEventListener("click", function () {
        showStep(1);
      });
    }
  }

  /* ---------------------------------------------------------------------
     3. Intent pre-selection
     WHY: "Talk to us" from the Team plan should land on the form already
     knowing the visitor is a company — one less decision to make.
     --------------------------------------------------------------------- */
  function initIntent() {
    document.querySelectorAll("[data-intent]").forEach(function (trigger) {
      trigger.addEventListener("click", function () {
        if (trigger.dataset.intent !== "team") return;

        const teamChoice = form
          ? form.querySelector('input[name="stage"][value="team"]')
          : null;

        if (teamChoice) teamChoice.checked = true;

        window.setTimeout(function () {
          window.UI.toast("Team enquiry — we'll ask about seat count");
        }, 550);
      });
    });
  }

  function boot() {
    initWeeks();
    initLeadForm();
    initIntent();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
