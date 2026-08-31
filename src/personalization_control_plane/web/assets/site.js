document.documentElement.classList.add("js");

const publishedStaticSite = (
  window.location.hostname.endsWith(".github.io")
  || new URLSearchParams(window.location.search).get("public-site") === "true"
);
document.documentElement.dataset.publicSite = String(publishedStaticSite);

if (publishedStaticSite) {
  document.querySelectorAll("[data-local-api-link]").forEach((link) => {
    link.href = "https://github.com/hk-775/personalization-control-plane/blob/main/docs/API.md";
    link.textContent = "API reference";
  });
}

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
  if (publishedStaticSite) {
    serviceStatus.textContent = "published synthetic preview";
  } else {
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
}
