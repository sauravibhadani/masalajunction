const menuData = [
  {
    category: "Pizza",
    items: [
      ["Double Cheese Pizza", "₹140"],
      ["Triple Cheese Pizza", "₹160"],
      ["Baby Corn Pizza", "₹160"],
      ["Mushroom Pizza", "₹160"],
      ["Sweet Corn Pizza", "₹160"],
      ["Paneer Pizza", "₹200"],
      ["Jackpot Pizza", "₹220"]
    ]
  },
  {
    category: "Burger",
    items: [
      ["Veg Burger", "₹35"],
      ["Paneer Burger", "₹60"],
      ["Cheese Burger", "₹50"],
      ["Special Burger", "₹70"]
    ]
  },
  {
    category: "Chilli's",
    items: [
      ["Manchurian", "₹40/80"],
      ["Paneer Chilli", "₹75/150"],
      ["Special Paneer Chilli", "₹80/160"],
      ["Mushroom Chilli", "₹80/160"],
      ["Babycorn Chilli", "₹80/160"]
    ]
  },
  {
    category: "Rolls & Momos",
    items: [
      ["Spring Roll", "₹70"],
      ["Veg Roll", "₹30"],
      ["Paneer Roll", "₹60"],
      ["Cheese Roll", "₹50"],
      ["Veg Momos", "₹25/50"],
      ["Fried Momos", "₹30/60"],
      ["Paneer Cheese Roll", "₹80"]
    ]
  },
  {
    category: "Chowmein",
    items: [
      ["Veg Chowmein", "₹35/70"],
      ["Paneer Chowmein", "₹60/120"],
      ["Mushroom Chowmein", "₹60/120"],
      ["Baby Corn Chowmein", "₹60/120"],
      ["Jackpot Chowmein", "₹70/140"]
    ]
  },
  {
    category: "Pasta",
    items: [
      ["Veg Pasta", "₹45/90"],
      ["Paneer Pasta", "₹70/140"],
      ["Mushroom Pasta", "₹70/140"],
      ["Baby Corn Pasta", "₹70/140"],
      ["Jackpot Pasta", "₹80/160"],
      ["White Sauce Pasta", "₹60/120"]
    ]
  },
  {
    category: "Specials",
    items: [
      ["Sweet Corn Chaat", "₹60/120"],
      ["Mix Majza", "₹160"],
      ["French Fries", "₹50/100"]
    ]
  },
  {
    category: "Pav Bhaji",
    items: [
      ["Pav Bhaji", "₹50"],
      ["Extra Pav", "₹10"],
      ["Extra Bhaji", "₹30"],
      ["Seasonal Soup", "₹40/50"]
    ]
  },
  {
    category: "South Indian",
    items: [
      ["Masala Dosa", "₹70"],
      ["Paper Dosa", "₹60"],
      ["Paneer Dosa", "₹120"],
      ["Idli", "₹40"],
      ["Moong Dal Chilla", "₹60"]
    ]
  }
];

const header = document.querySelector("[data-header]");
const navToggle = document.querySelector(".nav-toggle");
const navMenu = document.querySelector("[data-nav-menu]");
const filterRow = document.querySelector("[data-filter-row]");
const menuGrid = document.querySelector("[data-menu-grid]");
const menuSearch = document.querySelector("#menu-search");
const emptyState = document.querySelector("[data-empty-state]");
const lightbox = document.querySelector("[data-lightbox-modal]");
const lightboxImage = document.querySelector("[data-lightbox-image]");
const lightboxClose = document.querySelector(".lightbox-close");
const reservationModal = document.querySelector("[data-reservation-modal]");
const reservationForm = document.querySelector("[data-reservation-form]");
const reservationStatus = document.querySelector("[data-reservation-status]");
const reservationOpenButtons = document.querySelectorAll("[data-reservation-open]");
const reservationCloseButtons = document.querySelectorAll("[data-reservation-close]");

let activeCategory = "All";
let lastFocusedElement = null;

function handleHeaderState() {
  header.classList.toggle("is-scrolled", window.scrollY > 20);
}

function closeMenu() {
  navToggle.setAttribute("aria-expanded", "false");
  navToggle.setAttribute("aria-label", "Open menu");
  navMenu.classList.remove("is-open");
  header.classList.remove("is-open");
  document.body.classList.remove("nav-open");
}

function toggleMenu() {
  const isOpen = navToggle.getAttribute("aria-expanded") === "true";
  navToggle.setAttribute("aria-expanded", String(!isOpen));
  navToggle.setAttribute("aria-label", isOpen ? "Open menu" : "Close menu");
  navMenu.classList.toggle("is-open", !isOpen);
  header.classList.toggle("is-open", !isOpen);
  document.body.classList.toggle("nav-open", !isOpen);
}

function createFilterButtons() {
  const categories = ["All", ...menuData.map((group) => group.category)];
  filterRow.innerHTML = categories.map((category, index) => (
    `<button class="filter-btn${index === 0 ? " is-active" : ""}" type="button" role="tab" aria-selected="${index === 0}" data-category="${category}">${category}</button>`
  )).join("");
}

function renderMenu() {
  const query = menuSearch.value.trim().toLowerCase();
  const groups = menuData
    .filter((group) => activeCategory === "All" || group.category === activeCategory)
    .map((group) => {
      const items = group.items.filter(([name]) => {
        const haystack = `${name} ${group.category}`.toLowerCase();
        return haystack.includes(query);
      });
      return { ...group, items };
    })
    .filter((group) => group.items.length);

  menuGrid.innerHTML = groups.map((group) => `
    <article class="menu-category reveal is-visible">
      <header>
        <h3>${group.category}</h3>
        <span>${group.items.length} items</span>
      </header>
      <div class="menu-list">
        ${group.items.map(([name, price]) => `
          <div class="menu-item">
            <strong>${name}</strong>
            <span>${price}</span>
          </div>
        `).join("")}
      </div>
    </article>
  `).join("");

  emptyState.hidden = groups.length > 0;
}

function setupMenu() {
  createFilterButtons();
  renderMenu();

  filterRow.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;

    activeCategory = button.dataset.category;
    filterRow.querySelectorAll(".filter-btn").forEach((filterButton) => {
      const isActive = filterButton === button;
      filterButton.classList.toggle("is-active", isActive);
      filterButton.setAttribute("aria-selected", String(isActive));
    });
    renderMenu();
  });

  menuSearch.addEventListener("input", renderMenu);
}

function setupRevealAnimations() {
  const revealItems = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.16 });

  revealItems.forEach((item) => observer.observe(item));
}

function setupCounters() {
  const counters = document.querySelectorAll("[data-count]");
  if (!("IntersectionObserver" in window)) {
    counters.forEach((counter) => {
      counter.textContent = `${counter.dataset.count}+`;
    });
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const counter = entry.target;
      const target = Number(counter.dataset.count);
      const start = performance.now();
      const duration = 900;

      function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const value = Math.floor(progress * target);
        counter.textContent = `${value}${target > 10 ? "+" : ""}`;
        if (progress < 1) requestAnimationFrame(tick);
      }

      requestAnimationFrame(tick);
      observer.unobserve(counter);
    });
  }, { threshold: 0.75 });

  counters.forEach((counter) => observer.observe(counter));
}

function openLightbox(src) {
  lightboxImage.src = src;
  lightbox.hidden = false;
  lightboxClose.focus();
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  lightbox.hidden = true;
  lightboxImage.src = "";
  document.body.style.overflow = "";
}

function setupLightbox() {
  document.querySelectorAll("[data-lightbox]").forEach((button) => {
    button.addEventListener("click", () => openLightbox(button.dataset.lightbox));
  });

  lightboxClose.addEventListener("click", closeLightbox);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !lightbox.hidden) closeLightbox();
  });
}

function setupNav() {
  handleHeaderState();
  window.addEventListener("scroll", handleHeaderState, { passive: true });
  navToggle.addEventListener("click", toggleMenu);
  navMenu.querySelectorAll("a, button").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });
}

function setReservationStatus(message, type = "") {
  reservationStatus.textContent = message;
  reservationStatus.classList.toggle("is-success", type === "success");
  reservationStatus.classList.toggle("is-error", type === "error");
}

function openReservationModal() {
  lastFocusedElement = document.activeElement;
  reservationModal.hidden = false;
  document.body.style.overflow = "hidden";
  setReservationStatus("");

  const dateInput = reservationForm.elements.date;
  if (dateInput && !dateInput.min) {
    dateInput.min = new Date().toISOString().split("T")[0];
  }

  reservationForm.elements.name.focus();
}

function closeReservationModal() {
  reservationModal.hidden = true;
  document.body.style.overflow = "";
  setReservationStatus("");
  if (lastFocusedElement) lastFocusedElement.focus();
}

async function submitReservation(event) {
  event.preventDefault();
  const submitButton = reservationForm.querySelector('button[type="submit"]');

  if (window.location.protocol === "file:") {
    setReservationStatus("Open this website through http://localhost:8000, not by opening index.html as a file.", "error");
    return;
  }

  const formData = new FormData(reservationForm);
  const payload = Object.fromEntries(formData.entries());

  submitButton.disabled = true;
  submitButton.textContent = "Submitting...";
  setReservationStatus("Saving your reservation request...");

  try {
    const response = await fetch("/api/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || "Reservation could not be saved.");
    }

    reservationForm.reset();
    setReservationStatus(`Reservation request #${result.reservation.id} saved. The cafe can confirm it from the admin dashboard.`, "success");
  } catch (error) {
    setReservationStatus(error.message || "Something went wrong. Please try again.", "error");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Submit Reservation";
  }
}

function setupReservation() {
  if (!reservationModal || !reservationForm) return;

  reservationOpenButtons.forEach((button) => {
    button.addEventListener("click", openReservationModal);
  });

  reservationCloseButtons.forEach((button) => {
    button.addEventListener("click", closeReservationModal);
  });

  reservationForm.addEventListener("submit", submitReservation);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !reservationModal.hidden) closeReservationModal();
  });
}

document.querySelector("[data-year]").textContent = new Date().getFullYear();
setupNav();
setupMenu();
setupRevealAnimations();
setupCounters();
setupLightbox();
setupReservation();
