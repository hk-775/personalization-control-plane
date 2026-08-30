document.documentElement.classList.add("js");

const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.querySelector(".nav-links");

if (navToggle && navLinks) {
  navToggle.addEventListener("click", () => {
    const open = navLinks.classList.toggle("is-open");
    navToggle.setAttribute("aria-expanded", String(open));
  });
  navLinks.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navLinks.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.1 },
);

document.querySelectorAll(".reveal").forEach((element) => revealObserver.observe(element));

const serviceStatus = document.querySelector("#service-status");
if (serviceStatus) {
  fetch("/api/v1/health", { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error("not running");
      return response.json();
    })
    .then((health) => {
      serviceStatus.textContent = `${health.status} · local API`;
    })
    .catch(() => {
      serviceStatus.textContent = "static product site";
    });
}
