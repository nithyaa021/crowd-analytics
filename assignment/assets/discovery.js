/* ==========================================================================
   discovery.js — search, filtering, sorting and form behaviour for the
   Practo for Animals prototype.

   Why this file exists: the brief asks for a working search prototype, not a
   picture of one. Everything here is client-side so the page runs from a
   double-click with no server.

   Reading order:
     1. PROVIDERS  — the sample dataset (one object per listing)
     2. state      — what the user has currently selected
     3. render()   — turns state + data into cards
     4. events     — wiring the controls to state
   ========================================================================== */

(function () {
  "use strict";

  /* ---------------------------------------------------------------------
     1. Sample dataset
     Each listing mirrors the fields a real directory would store. Keeping
     them explicit (rather than clever shorthand) makes it obvious to a
     reviewer which provider information the MVP actually needs.
     --------------------------------------------------------------------- */
  const PROVIDERS = [
    {
      id: "p1",
      name: "Cessna Lifeline Veterinary Hospital",
      type: "hospital",
      typeLabel: "24-hour multi-specialty hospital",
      area: "Domlur",
      distanceKm: 2.4,
      rating: 4.8,
      reviews: 612,
      phone: "+91 80 4123 6677",
      to: "+91 80 4123 6677",
      openNow: true,
      hours24: true,
      homeVisit: false,
      species: ["dog", "cat", "bird", "rabbit", "exotic"],
      services: ["Surgery", "ICU", "X-ray", "Blood work", "Ultrasound"],
      cost: "standard",
      responseMins: 4,
      verifiedDays: 6,
      note: "Overnight ICU with a vet on the floor. Accepts critical transfers.",
      accent: "coral",
      icon: "hospital",
    },
    {
      id: "p2",
      name: "Indiranagar Pet Clinic",
      type: "vet",
      typeLabel: "Neighbourhood veterinary clinic",
      area: "Indiranagar",
      distanceKm: 0.6,
      rating: 4.6,
      reviews: 348,
      phone: "+91 98860 22114",
      to: "+91 98860 22114",
      openNow: true,
      hours24: false,
      homeVisit: true,
      species: ["dog", "cat"],
      services: ["Vaccination", "Deworming", "Dental scaling", "Consultation"],
      cost: "standard",
      responseMins: 11,
      verifiedDays: 12,
      note: "Walk-ins until 8pm. Dr. Rao has 14 years in small-animal practice.",
      accent: "green",
      icon: "vet",
    },
    {
      id: "p3",
      name: "Paws & Play Boarding",
      type: "boarding",
      typeLabel: "Boarding and daycare",
      area: "Koramangala",
      distanceKm: 3.1,
      rating: 4.7,
      reviews: 204,
      phone: "+91 90080 55120",
      to: "+91 90080 55120",
      openNow: true,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat"],
      services: ["AC kennels", "Daily walks", "Webcam access", "Medication given"],
      cost: "standard",
      responseMins: 18,
      verifiedDays: 21,
      note: "CCTV access for owners. Separate cat wing away from the dogs.",
      accent: "amber",
      icon: "boarding",
    },
    {
      id: "p4",
      name: "VetScan Diagnostics",
      type: "diagnostics",
      typeLabel: "Diagnostic lab & imaging",
      area: "Jayanagar",
      distanceKm: 5.8,
      rating: 4.5,
      reviews: 156,
      phone: "+91 80 2663 9900",
      to: "+91 80 2663 9900",
      openNow: false,
      hours24: false,
      homeVisit: true,
      species: ["dog", "cat", "bird", "rabbit"],
      services: ["Digital X-ray", "Ultrasound", "CBC panel", "Home sample pickup"],
      cost: "standard",
      responseMins: 26,
      verifiedDays: 9,
      note: "Reports by email in 4–6 hours. Sample pickup available in 5 zones.",
      accent: "blue",
      icon: "diagnostics",
    },
    {
      id: "p5",
      name: "CUPA Animal Rescue",
      type: "ngo",
      typeLabel: "NGO · rescue and low-cost treatment",
      area: "Hebbal",
      distanceKm: 8.2,
      rating: 4.9,
      reviews: 891,
      phone: "+91 80 2542 7222",
      to: "+91 80 2542 7222",
      openNow: true,
      hours24: true,
      homeVisit: false,
      species: ["dog", "cat", "bird"],
      services: ["Rescue", "Sterilisation", "Free treatment", "Ambulance"],
      cost: "free",
      responseMins: 7,
      verifiedDays: 3,
      note: "Free treatment for strays and community animals. Call before arriving.",
      accent: "green",
      icon: "ngo",
    },
    {
      id: "p6",
      name: "PetAmbulance 24x7",
      type: "ambulance",
      typeLabel: "Pet ambulance & critical transport",
      area: "City-wide",
      distanceKm: 1.2,
      rating: 4.4,
      reviews: 118,
      phone: "+91 91080 40404",
      to: "+91 91080 40404",
      openNow: true,
      hours24: true,
      homeVisit: true,
      species: ["dog", "cat", "bird", "rabbit", "exotic"],
      services: ["Oxygen support", "Stretcher", "Trained handler", "ICU van"],
      cost: "standard",
      responseMins: 9,
      verifiedDays: 5,
      note: "Average pickup 18 minutes inside ORR. Oxygen-equipped van.",
      accent: "coral",
      icon: "ambulance",
    },
    {
      id: "p7",
      name: "Whitefield Cat Clinic",
      type: "vet",
      typeLabel: "Feline-only clinic",
      area: "Whitefield",
      distanceKm: 12.4,
      rating: 4.8,
      reviews: 267,
      phone: "+91 99001 78345",
      to: "+91 99001 78345",
      openNow: true,
      hours24: false,
      homeVisit: false,
      species: ["cat"],
      services: ["Feline medicine", "Dental", "Behaviour consult", "Senior cat care"],
      cost: "standard",
      responseMins: 14,
      verifiedDays: 8,
      note: "Cats only — no dogs in the waiting room. Reduces stress for anxious cats.",
      accent: "green",
      icon: "vet",
    },
    {
      id: "p8",
      name: "Dr. Menon's Home Vet Visits",
      type: "vet",
      typeLabel: "Mobile veterinary practice",
      area: "HSR Layout",
      distanceKm: 4.6,
      rating: 4.7,
      reviews: 143,
      phone: "+91 98450 66781",
      to: "+91 98450 66781",
      openNow: true,
      hours24: false,
      homeVisit: true,
      species: ["dog", "cat", "rabbit"],
      services: ["Home consultation", "Vaccination", "Euthanasia support", "Sample collection"],
      cost: "standard",
      responseMins: 22,
      verifiedDays: 15,
      note: "Best for anxious pets and older animals who can't travel.",
      accent: "green",
      icon: "vet",
    },
    {
      id: "p9",
      name: "BBMP Veterinary Hospital",
      type: "hospital",
      typeLabel: "Government veterinary hospital",
      area: "Shivajinagar",
      distanceKm: 6.9,
      rating: 4.1,
      reviews: 402,
      phone: "+91 80 2286 5120",
      to: "+91 80 2286 5120",
      openNow: false,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat", "bird"],
      services: ["Low-cost treatment", "Sterilisation", "Vaccination"],
      cost: "low",
      responseMins: 45,
      verifiedDays: 27,
      note: "Subsidised rates. Long queues in the morning; go before 9am.",
      accent: "blue",
      icon: "hospital",
    },
    {
      id: "p10",
      name: "Feathers & Scales Exotics",
      type: "vet",
      typeLabel: "Exotic and avian practice",
      area: "Malleshwaram",
      distanceKm: 7.3,
      rating: 4.6,
      reviews: 87,
      phone: "+91 97400 33129",
      to: "+91 97400 33129",
      openNow: true,
      hours24: false,
      homeVisit: false,
      species: ["bird", "exotic", "rabbit"],
      services: ["Avian medicine", "Reptile care", "Beak trimming", "Nutrition plans"],
      cost: "standard",
      responseMins: 19,
      verifiedDays: 11,
      note: "One of only three practices in the city that sees reptiles.",
      accent: "amber",
      icon: "vet",
    },
    {
      id: "p11",
      name: "Happy Tails Boarding & Spa",
      type: "boarding",
      typeLabel: "Boarding, grooming and daycare",
      area: "Marathahalli",
      distanceKm: 9.8,
      rating: 4.3,
      reviews: 176,
      phone: "+91 88840 21660",
      to: "+91 88840 21660",
      openNow: false,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat"],
      services: ["Grooming", "Daycare", "Long-stay boarding", "Pickup"],
      cost: "standard",
      responseMins: 31,
      verifiedDays: 34,
      note: "Pickup and drop inside 10km. Ask for the allergy-friendly kennel block.",
      accent: "amber",
      icon: "boarding",
    },
    {
      id: "p12",
      name: "Karuna Animal Shelter",
      type: "ngo",
      typeLabel: "NGO · shelter and rehoming",
      area: "Bannerghatta",
      distanceKm: 14.6,
      rating: 4.5,
      reviews: 523,
      phone: "+91 80 2842 9333",
      to: "+91 80 2842 9333",
      openNow: true,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat"],
      services: ["Rehoming", "Rescue", "Low-cost sterilisation", "Foster network"],
      cost: "free",
      responseMins: 38,
      verifiedDays: 18,
      note: "Adoption hours 10am–5pm. Bring ID for adoption paperwork.",
      accent: "green",
      icon: "ngo",
    },
    {
      id: "p13",
      name: "Nova Emergency Vet Hospital",
      type: "hospital",
      typeLabel: "24-hour emergency hospital",
      area: "BTM Layout",
      distanceKm: 4.1,
      rating: 4.7,
      reviews: 389,
      phone: "+91 80 4155 2020",
      to: "+91 80 4155 2020",
      openNow: true,
      hours24: true,
      homeVisit: false,
      species: ["dog", "cat", "rabbit"],
      services: ["Trauma care", "Blood transfusion", "Oxygen", "On-site lab"],
      cost: "standard",
      responseMins: 5,
      verifiedDays: 2,
      note: "Trauma and poisoning cases go to the front of the queue.",
      accent: "coral",
      icon: "hospital",
    },
    {
      id: "p14",
      name: "Sampoorna Low-Cost Vet Camp",
      type: "vet",
      typeLabel: "Low-cost community clinic",
      area: "Yeshwanthpur",
      distanceKm: 11.2,
      rating: 4.2,
      reviews: 94,
      phone: "+91 80 2337 4411",
      to: "+91 80 2337 4411",
      openNow: false,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat"],
      services: ["Vaccination camps", "Sterilisation", "Basic treatment"],
      cost: "low",
      responseMins: 52,
      verifiedDays: 41,
      note: "Runs free vaccination camps on the first Sunday of every month.",
      accent: "blue",
      icon: "vet",
    },
    {
      id: "p15",
      name: "Bengaluru Pet Imaging Centre",
      type: "diagnostics",
      typeLabel: "Advanced imaging & pathology",
      area: "Rajajinagar",
      distanceKm: 10.4,
      rating: 4.4,
      reviews: 61,
      phone: "+91 80 2311 7788",
      to: "+91 80 2311 7788",
      openNow: true,
      hours24: false,
      homeVisit: false,
      species: ["dog", "cat", "bird", "rabbit", "exotic"],
      services: ["CT scan", "MRI referral", "Endoscopy", "Histopathology"],
      cost: "standard",
      responseMins: 28,
      verifiedDays: 13,
      note: "The only private CT for animals in the city. Appointment only.",
      accent: "blue",
      icon: "diagnostics",
    },
    {
      id: "p16",
      name: "SOS Stray Ambulance",
      type: "ambulance",
      typeLabel: "Free stray rescue ambulance",
      area: "City-wide",
      distanceKm: 2.0,
      rating: 4.6,
      reviews: 312,
      phone: "+91 97310 90000",
      to: "+91 97310 90000",
      openNow: true,
      hours24: true,
      homeVisit: true,
      species: ["dog", "cat", "bird"],
      services: ["Stray rescue", "Injury transport", "Free pickup"],
      cost: "free",
      responseMins: 16,
      verifiedDays: 4,
      note: "Free for injured strays and community animals. Volunteer-run.",
      accent: "coral",
      icon: "ambulance",
    },
  ];

  /* Icon path markup per service type, so cards are visually scannable. */
  const ICONS = {
    vet: '<path d="M6 4v5a6 6 0 0 0 12 0V4"/><path d="M9 4v5a3 3 0 0 0 6 0V4"/><path d="M12 15v5"/><path d="M8 20h8"/>',
    hospital: '<path d="M4 21V7l8-4 8 4v14"/><path d="M12 9v6M9 12h6"/>',
    boarding: '<path d="M3 10 12 3l9 7"/><path d="M5 9v11h14V9"/><path d="M9.5 20v-5h5v5"/>',
    diagnostics: '<path d="M9 3h6"/><path d="M10 3v6.2L5.6 17A3 3 0 0 0 8.2 21h7.6a3 3 0 0 0 2.6-4.4L14 9.2V3"/><path d="M7.6 14h8.8"/>',
    ambulance: '<path d="M3 16V8h11v8"/><path d="M14 11h4l3 3v2h-7"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/><path d="M8.5 11v3M7 12.5h3"/>',
    ngo: '<path d="M12 21s-7-4.6-7-10a4.2 4.2 0 0 1 7-3 4.2 4.2 0 0 1 7 3c0 5.4-7 10-7 10Z"/>',
  };

  /* ---------------------------------------------------------------------
     2. State
     One plain object holds every filter. Every render reads from it and
     every control writes to it, so there is exactly one source of truth.
     --------------------------------------------------------------------- */
  const state = {
    query: "",
    species: "all",
    service: "all",
    openNow: false,
    hours24: false,
    homeVisit: false,
    minRating: 0,
    cost: "all",
    sort: "recommended",
  };

  /* Element handles, resolved once. */
  const el = {
    form: document.getElementById("searchForm"),
    q: document.getElementById("q"),
    loc: document.getElementById("loc"),
    species: document.getElementById("species"),
    cards: document.getElementById("cards"),
    empty: document.getElementById("empty"),
    count: document.getElementById("resultCount"),
    eyebrow: document.getElementById("resultsEyebrow"),
    sort: document.getElementById("sort"),
    activeFilters: document.getElementById("activeFilters"),
  };

  /* ---------------------------------------------------------------------
     3. Filtering and sorting
     --------------------------------------------------------------------- */

  /**
   * WHY: A user typing "24 hours" or "boarding" into one box should not need
   * to know which field that maps to. So we search across the fields a person
   * would say out loud, not just the name.
   */
  function matchesQuery(provider, query) {
    if (!query) return true;

    const haystack = [
      provider.name,
      provider.typeLabel,
      provider.area,
      provider.note,
      provider.services.join(" "),
      provider.hours24 ? "24 hours emergency open all night" : "",
      provider.homeVisit ? "home visit mobile" : "",
      provider.cost === "free" ? "free ngo low cost" : "",
    ]
      .join(" ")
      .toLowerCase();

    /* Every word must appear somewhere — behaves like an AND search. */
    return query
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .every(function (word) {
        return haystack.indexOf(word) !== -1;
      });
  }

  /** WHY: Filters combine with AND, which is what users expect from a rail. */
  function matchesFilters(provider) {
    if (state.service !== "all" && provider.type !== state.service) return false;
    if (state.species !== "all" && provider.species.indexOf(state.species) === -1) return false;
    if (state.openNow && !provider.openNow) return false;
    if (state.hours24 && !provider.hours24) return false;
    if (state.homeVisit && !provider.homeVisit) return false;
    if (provider.rating < state.minRating) return false;
    if (state.cost !== "all" && provider.cost !== state.cost) return false;
    return true;
  }

  /**
   * WHY: "Recommended" is not rating alone — a 4.9 star clinic 14km away is
   * useless in an emergency. We blend rating, distance and openness into one
   * score so the default order is the genuinely most helpful order.
   */
  function recommendationScore(provider) {
    const ratingPart = (provider.rating - 4) * 10; // 0–9 points
    const distancePart = Math.max(0, 8 - provider.distanceKm * 0.5); // closer scores higher
    const openPart = provider.openNow ? 4 : 0;
    const verifiedPart = Math.max(0, 3 - provider.verifiedDays / 15);
    return ratingPart + distancePart + openPart + verifiedPart;
  }

  function sortProviders(list) {
    const sorted = list.slice();

    if (state.sort === "rating") {
      sorted.sort(function (a, b) {
        return b.rating - a.rating;
      });
    } else if (state.sort === "distance") {
      sorted.sort(function (a, b) {
        return a.distanceKm - b.distanceKm;
      });
    } else if (state.sort === "response") {
      sorted.sort(function (a, b) {
        return a.responseMins - b.responseMins;
      });
    } else {
      sorted.sort(function (a, b) {
        return recommendationScore(b) - recommendationScore(a);
      });
    }

    return sorted;
  }

  /* ---------------------------------------------------------------------
     4. Rendering
     --------------------------------------------------------------------- */

  /** WHY: Keeps the price signal honest and short enough to fit the media badge. */
  function costLabel(provider) {
    if (provider.cost === "free") return "Free / NGO";
    if (provider.cost === "low") return "Low cost";
    return "Standard";
  }

  /** WHY: Trust is a date, not a badge — so we say how stale it is. */
  function verifiedLabel(days) {
    if (days <= 7) return "Verified this week";
    if (days <= 30) return "Verified " + days + " days ago";
    return "Re-check due";
  }

  function starIcon() {
    return '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M12 2.6l2.9 5.9 6.5.9-4.7 4.6 1.1 6.5-5.8-3.1-5.8 3.1 1.1-6.5L2.6 9.4l6.5-.9z"/></svg>';
  }

  function pinIcon() {
    return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7-5.2-7-11a7 7 0 1 1 14 0c0 5.8-7 11-7 11Z"/><circle cx="12" cy="10" r="2.4"/></svg>';
  }

  function clockIcon() {
    return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/></svg>';
  }

  function shieldIcon() {
    return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21c4.5-2 7-5.6 7-10V5.5L12 3 5 5.5V11c0 4.4 2.5 8 7 10Z"/><path d="m9 11.5 2.2 2.2L15.5 9"/></svg>';
  }

  /** Builds the badge row: open state, 24h, home visit. */
  function statusTags(provider) {
    const tags = [];

    tags.push(
      provider.openNow
        ? '<span class="tag tag--open">Open now</span>'
        : '<span class="tag tag--soon">Opens 9:00 am</span>'
    );

    if (provider.hours24) tags.push('<span class="tag tag--24">24 hours</span>');
    if (provider.homeVisit) tags.push('<span class="tag">Home visit</span>');

    return tags.join("");
  }

  /**
   * WHY: One function per card keeps the markup readable and means a change
   * to the card design happens in exactly one place.
   */
  function cardHTML(provider) {
    const media = ICONS[provider.icon] || ICONS.vet;
    const services = provider.services
      .slice(0, 3)
      .map(function (service) {
        return '<span class="tag">' + service + "</span>";
      })
      .join("");

    return (
      '<article class="pcard">' +
      '<div class="pcard__media pcard__media--' +
      provider.accent +
      '">' +
      '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
      media +
      "</svg>" +
      '<span class="pcard__media-tag">' +
      costLabel(provider) +
      "</span>" +
      "</div>" +
      '<div class="pcard__body">' +
      '<div class="pcard__top">' +
      '<div style="min-width:0">' +
      '<h3 class="pcard__name">' +
      provider.name +
      "</h3>" +
      '<p class="pcard__type">' +
      provider.typeLabel +
      "</p>" +
      "</div>" +
      "</div>" +
      '<div class="pcard__meta">' +
      '<span class="pcard__rating">' +
      starIcon() +
      provider.rating.toFixed(1) +
      "</span>" +
      "<span>" +
      pinIcon() +
      provider.area +
      " · " +
      provider.distanceKm.toFixed(1) +
      " km</span>" +
      "<span>" +
      clockIcon() +
      "Replies in ~" +
      provider.responseMins +
      " min</span>" +
      "</div>" +
      '<div class="pcard__tags">' +
      statusTags(provider) +
      services +
      "</div>" +
      '<div class="row wraprow" style="gap:10px;margin-top:4px">' +
      '<span class="pcard__verified">' +
      shieldIcon() +
      verifiedLabel(provider.verifiedDays) +
      "</span>" +
      '<span class="small muted">' +
      provider.reviews +
      " owner reviews</span>" +
      "</div>" +
      "</div>" +
      '<div class="pcard__actions">' +
      '<a class="btn btn--sm" href="tel:' +
      provider.phone.replace(/\s/g, "") +
      '">Call now</a>' +
      '<span class="pcard__phone">' +
      provider.phone +
      "</span>" +
      '<a class="pcard__link" href="#list">Submit a correction</a>' +
      "</div>" +
      "</article>"
    );
  }

  /** WHY: Users need to see what is filtering their results, and undo it. */
  function activeFilterPills() {
    const pills = [];

    if (state.query) {
      pills.push({ key: "query", label: '“' + state.query + '”' });
    }
    if (state.service !== "all") {
      pills.push({ key: "service", label: labelFor("service", state.service) });
    }
    if (state.species !== "all") {
      pills.push({ key: "species", label: labelFor("species", state.species) });
    }
    if (state.minRating > 0) {
      pills.push({ key: "rating", label: state.minRating.toFixed(1) + "+ rated" });
    }
    if (state.cost !== "all") {
      pills.push({ key: "cost", label: labelFor("cost", state.cost) });
    }
    if (state.openNow) pills.push({ key: "openNow", label: "Open now" });
    if (state.hours24) pills.push({ key: "hours24", label: "24 hours" });
    if (state.homeVisit) pills.push({ key: "homeVisit", label: "Home visit" });

    return pills
      .map(function (pill) {
        return (
          '<span class="activepill">' +
          pill.label +
          '<button type="button" data-clear="' +
          pill.key +
          '" aria-label="Remove filter ' +
          pill.label +
          '">✕</button></span>'
        );
      })
      .join("");
  }

  /** Human-readable labels for pill text. */
  function labelFor(filter, value) {
    const labels = {
      service: {
        vet: "Vet clinic",
        hospital: "Hospital",
        boarding: "Boarding",
        diagnostics: "Diagnostics",
        ambulance: "Ambulance",
        ngo: "NGO",
      },
      species: { dog: "Dog", cat: "Cat", bird: "Bird", rabbit: "Rabbit", exotic: "Exotic" },
      cost: { low: "Low cost", free: "Free / NGO" },
    };

    return (labels[filter] && labels[filter][value]) || value;
  }

  /** The main render pass: filter → sort → paint → update counts. */
  function render() {
    const filtered = PROVIDERS.filter(function (provider) {
      return matchesQuery(provider, state.query) && matchesFilters(provider);
    });

    const ordered = sortProviders(filtered);

    el.cards.innerHTML = ordered.map(cardHTML).join("");
    el.count.textContent = ordered.length;
    el.empty.hidden = ordered.length > 0;
    el.activeFilters.innerHTML = activeFilterPills();

    /* The eyebrow reflects the location box, so search feels connected. */
    const place = (el.loc.value || "").trim();
    el.eyebrow.textContent = place ? "Near " + place : "Near you";
  }

  /* ---------------------------------------------------------------------
     5. Controls
     --------------------------------------------------------------------- */

  /** WHY: Chip groups behave like radio buttons but look lighter. */
  function selectChip(group, value) {
    group.querySelectorAll(".chip").forEach(function (chip) {
      chip.classList.toggle("is-active", chip.dataset.value === value);
    });
  }

  function bindChips(groupId, filterName, stateKey, parser) {
    const group = document.getElementById(groupId);
    if (!group) return;

    group.addEventListener("click", function (event) {
      const chip = event.target.closest(".chip");
      if (!chip) return;

      const raw = chip.dataset.value;
      state[stateKey] = parser ? parser(raw) : raw;
      selectChip(group, raw);
      render();
    });
  }

  function bindToggles() {
    const map = [
      ["fOpenNow", "openNow"],
      ["f24h", "hours24"],
      ["fHome", "homeVisit"],
    ];

    map.forEach(function (pair) {
      const input = document.getElementById(pair[0]);
      if (!input) return;

      input.addEventListener("change", function () {
        state[pair[1]] = input.checked;
        render();
      });
    });
  }

  /** WHY: Search only runs on submit so typing never causes jumpy results. */
  function bindSearchForm() {
    el.form.addEventListener("submit", function (event) {
      event.preventDefault();

      state.query = el.q.value.trim();
      state.species = el.species.value;
      render();

      const results = document.getElementById("results");
      if (results) {
        const top = results.getBoundingClientRect().top + window.scrollY - 80;
        window.scrollTo({ top: top, behavior: "smooth" });
      }

      window.UI.toast(
        state.query
          ? "Showing results for “" + state.query + "”"
          : "Showing all care near you"
      );
    });

    /* Live results while typing would be jarring; instead we hint. */
    el.q.addEventListener("input", function () {
      if (!el.q.value) {
        state.query = "";
        render();
      }
    });

    el.loc.addEventListener("change", function () {
      render();
    });
  }

  /**
   * WHY: The six big service tiles are the fastest path through the page, so
   * clicking one should scroll to results with that filter already applied.
   */
  function bindServiceTiles() {
    document.querySelectorAll(".service").forEach(function (tile) {
      tile.addEventListener("click", function () {
        const service = tile.dataset.service;
        state.service = service;

        const group = document.getElementById("serviceFilters");
        selectChip(group, service);
        render();
        scrollToResults();

        window.UI.toast(labelFor("service", service) + " near you");
      });
    });
  }

  /** WHY: Popular-search chips pre-fill the box — they must actually search. */
  function bindQuickChips() {
    const presets = {
      emergency: { query: "24 hours", service: "all", hours24: true, cost: "all" },
      vaccination: { query: "vaccination", service: "all", hours24: false, cost: "all" },
      boarding: { query: "", service: "boarding", hours24: false, cost: "all" },
      ambulance: { query: "", service: "ambulance", hours24: false, cost: "all" },
      ngo: { query: "", service: "ngo", hours24: false, cost: "all" },
      vet: { query: "", service: "vet", hours24: false, cost: "all" },
      hospital: { query: "", service: "hospital", hours24: false, cost: "all" },
    };

    document.querySelectorAll("[data-quick]").forEach(function (trigger) {
      trigger.addEventListener("click", function (event) {
        const preset = presets[trigger.dataset.quick];
        if (!preset) return;

        event.preventDefault();
        applyPreset(preset);
      });
    });
  }

  /** Shared by quick chips, the emergency CTA and the footer links. */
  function applyPreset(preset) {
    state.query = preset.query || "";
    state.service = preset.service || "all";
    state.hours24 = Boolean(preset.hours24);
    state.cost = preset.cost || "all";
    state.openNow = false;
    state.homeVisit = false;
    state.minRating = 0;
    state.species = "all";

    /* Reflect the new state back into every control. */
    el.q.value = state.query;
    el.species.value = "all";
    selectChip(document.getElementById("serviceFilters"), state.service);
    selectChip(document.getElementById("speciesFilters"), "all");
    selectChip(document.getElementById("ratingFilters"), "0");
    selectChip(document.getElementById("costFilters"), state.cost);
    document.getElementById("fOpenNow").checked = false;
    document.getElementById("f24h").checked = state.hours24;
    document.getElementById("fHome").checked = false;

    render();
    scrollToResults();
    window.UI.toast("Filters applied — " + el.count.textContent + " places match");
  }

  function scrollToResults() {
    const results = document.getElementById("results");
    if (!results) return;
    const top = results.getBoundingClientRect().top + window.scrollY - 80;
    window.scrollTo({ top: top, behavior: "smooth" });
  }

  /** WHY: One shared reset path means "Reset" and "Clear all" never diverge. */
  function resetAll(silent) {
    state.query = "";
    state.species = "all";
    state.service = "all";
    state.openNow = false;
    state.hours24 = false;
    state.homeVisit = false;
    state.minRating = 0;
    state.cost = "all";

    el.q.value = "";
    el.species.value = "all";
    selectChip(document.getElementById("serviceFilters"), "all");
    selectChip(document.getElementById("speciesFilters"), "all");
    selectChip(document.getElementById("ratingFilters"), "0");
    selectChip(document.getElementById("costFilters"), "all");
    document.getElementById("fOpenNow").checked = false;
    document.getElementById("f24h").checked = false;
    document.getElementById("fHome").checked = false;

    render();
    if (!silent) window.UI.toast("All filters cleared");
  }

  /** WHY: Removing a pill is faster than hunting for the control that set it. */
  function bindActivePills() {
    el.activeFilters.addEventListener("click", function (event) {
      const button = event.target.closest("[data-clear]");
      if (!button) return;

      const key = button.dataset.clear;

      if (key === "query") {
        state.query = "";
        el.q.value = "";
      } else if (key === "service") {
        state.service = "all";
        selectChip(document.getElementById("serviceFilters"), "all");
      } else if (key === "species") {
        state.species = "all";
        el.species.value = "all";
        selectChip(document.getElementById("speciesFilters"), "all");
      } else if (key === "rating") {
        state.minRating = 0;
        selectChip(document.getElementById("ratingFilters"), "0");
      } else if (key === "cost") {
        state.cost = "all";
        selectChip(document.getElementById("costFilters"), "all");
      } else {
        state[key] = false;
        const map = { openNow: "fOpenNow", hours24: "f24h", homeVisit: "fHome" };
        const input = document.getElementById(map[key]);
        if (input) input.checked = false;
      }

      render();
    });
  }

  /* ---------------------------------------------------------------------
     6. Small forms (listing + correction)
     --------------------------------------------------------------------- */

  /** WHY: Inline validation beats an alert box — it points at the field. */
  function showFieldError(input, message) {
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

  function clearFieldError(input) {
    input.classList.remove("is-error");
    input.removeAttribute("aria-invalid");
    const hint = input.parentElement.querySelector(".field__error");
    if (hint) hint.remove();
  }

  function bindListingForm() {
    const form = document.getElementById("listForm");
    if (!form) return;

    const name = document.getElementById("bizName");
    const phone = document.getElementById("bizPhone");
    const note = document.getElementById("listNote");

    [name, phone].forEach(function (input) {
      input.addEventListener("input", function () {
        clearFieldError(input);
      });
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      let valid = true;

      if (name.value.trim().length < 2) {
        showFieldError(name, "Please enter your business name.");
        valid = false;
      }

      /* Indian mobiles are 10 digits; we accept spaces and +91. */
      const digits = phone.value.replace(/\D/g, "");
      if (digits.length < 10) {
        showFieldError(phone, "Enter a 10-digit phone number.");
        valid = false;
      }

      if (!valid) {
        window.UI.toast("Please check the highlighted fields", "warn");
        return;
      }

      note.textContent = "Request received — we'll call " + phone.value + " within one working day.";
      note.style.color = "var(--green-700)";
      form.reset();
      window.UI.toast("Listing request sent. Thank you!");
    });
  }

  function bindCorrectionForm() {
    const form = document.getElementById("correctForm");
    if (!form) return;

    const target = document.getElementById("corrName");
    const note = document.getElementById("corrNote");

    target.addEventListener("input", function () {
      clearFieldError(target);
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      if (target.value.trim().length < 2) {
        showFieldError(target, "Tell us which listing needs fixing.");
        window.UI.toast("Please add the listing name", "warn");
        return;
      }

      note.textContent = "Correction logged for “" + target.value.trim() + "”. We verify before editing.";
      note.style.color = "var(--green-700)";
      form.reset();
      window.UI.toast("Correction submitted — thank you", "coral");
    });
  }

  /* ---------------------------------------------------------------------
     7. Boot
     --------------------------------------------------------------------- */
  function init() {
    if (!el.cards) return;

    bindChips("serviceFilters", "service", "service");
    bindChips("speciesFilters", "species", "species");
    bindChips("ratingFilters", "rating", "minRating", Number);
    bindChips("costFilters", "cost", "cost");
    bindToggles();
    bindSearchForm();
    bindServiceTiles();
    bindQuickChips();
    bindActivePills();
    bindListingForm();
    bindCorrectionForm();

    el.sort.addEventListener("change", function () {
      state.sort = el.sort.value;
      render();
    });

    document.getElementById("resetFilters").addEventListener("click", function () {
      resetAll(false);
    });

    document.getElementById("emptyReset").addEventListener("click", function () {
      resetAll(false);
    });

    document.getElementById("emergencyBtn").addEventListener("click", function () {
      applyPreset({ query: "", service: "all", hours24: true, cost: "all" });
    });

    document.getElementById("correctionBtn").addEventListener("click", function () {
      const target = document.getElementById("list");
      if (!target) return;
      const top = target.getBoundingClientRect().top + window.scrollY - 80;
      window.scrollTo({ top: top, behavior: "smooth" });
      document.getElementById("corrName").focus({ preventScroll: true });
    });

    /* First paint. */
    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
