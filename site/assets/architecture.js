const flows = {
  rank: {
    danger: [],
    steps: [
      ["client", "Product client submits a bounded rank request", "The API accepts a pseudonymous subject, exact purpose, cohort, and normalized candidate features."],
      ["consent", "Consent and purpose are enforced first", "Missing consent, purpose drift, or sensitive attribute keys fail closed before scoring."],
      ["allocation", "The control plane selects a safe policy", "The kill switch and cohort floor can force baseline fallback; eligible traffic receives a stable experiment bucket."],
      ["policy", "An immutable active policy supplies objectives", "Only allowlisted objectives and features are accepted, and exploration is capped."],
      ["scorer", "Candidates receive deterministic, inspectable scores", "Unsafe candidates are excluded and each remaining score includes factor-level contributions."],
      ["audit", "The decision becomes evidence", "Only a subject hash prefix and bounded decision context enter the SHA-256-linked audit chain."],
    ],
  },
  launch: {
    danger: [],
    steps: [
      ["experiment", "An operator advances an experiment from review", "The lifecycle service re-checks policies, purpose, cohort size, guardrails, and global traffic capacity."],
      ["policy", "Control and treatment versions are compared", "Large objective movement and higher exploration contribute to the risk classification."],
      ["approval", "Risk crosses the autonomous boundary", "Traffic above 5% or exploration above 3% creates a pending human approval instead of launching."],
      ["audit", "The request and reasons are recorded", "The approval id, actor, risk reasons, and lifecycle state enter the audit chain."],
      ["approval", "A named human records a decision", "Approval moves the experiment to approved; denial returns it to review."],
      ["experiment", "Only an approved experiment can start", "A second launch check prevents starts during a kill switch or over the global traffic cap."],
    ],
  },
  breach: {
    danger: ["guardrail", "experiment"],
    steps: [
      ["metrics", "Aggregate metrics arrive above the privacy floor", "Values remain hidden when sample size is below 50; eligible aggregates continue to evaluation."],
      ["guardrail", "The guardrail engine compares bounded thresholds", "Quality, harm, complaints, and fairness are evaluated together."],
      ["guardrail", "One or more hard limits fail", "A running experiment is not allowed to continue while a required guardrail is breached."],
      ["experiment", "The experiment is rolled back immediately", "Serving stops because rolled-back experiments are excluded from allocation."],
      ["allocation", "Subsequent traffic uses the approved baseline", "Recommendation service continues without the failed treatment."],
      ["audit", "Evaluation and rollback remain inspectable", "Thresholds, values, failed checks, actor, and reason are linked in the audit chain."],
    ],
  },
  outcome: {
    danger: [],
    steps: [
      ["exposure", "A client records a displayed candidate", "The exposure must reference an existing decision and one of its returned candidate ids."],
      ["outcome", "An allowlisted outcome references the exposure", "Purpose must match and the idempotency key cannot be reused with different data."],
      ["metrics", "Outcomes become privacy-bounded aggregates", "Small samples are suppressed rather than returned with unstable or identifying values."],
      ["guardrail", "Aggregates feed quality and fairness checks", "Evaluation can pass, remain incomplete, or trigger rollback."],
      ["experiment", "Lifecycle state responds to evidence", "Healthy experiments continue; failed experiments become terminally rolled back."],
      ["audit", "The feedback loop closes with evidence", "Events and resulting control actions share one verifiable audit history."],
    ],
  },
};

const selectorButtons = [...document.querySelectorAll("[data-flow]")];
const nodes = [...document.querySelectorAll("[data-node]")];
const packet = document.querySelector("#arch-packet");
const progress = document.querySelector("#flow-progress");
const title = document.querySelector("#flow-title");
const description = document.querySelector("#flow-description");
const toggle = document.querySelector("#flow-toggle");
const canvas = document.querySelector("#architecture-canvas");

let activeFlow = "rank";
let stepIndex = 0;
let timer = null;
let paused = false;

packet?.classList.add("is-ready");

function positionPacket(node) {
  if (!packet || !canvas || !node) return;
  const canvasRect = canvas.getBoundingClientRect();
  const nodeRect = node.getBoundingClientRect();
  packet.style.left = `${nodeRect.left - canvasRect.left + nodeRect.width / 2 - 5}px`;
  packet.style.top = `${nodeRect.top - canvasRect.top + nodeRect.height / 2 - 5}px`;
}

function renderStep() {
  const flow = flows[activeFlow];
  const [nodeName, stepTitle, stepDescription] = flow.steps[stepIndex];
  nodes.forEach((node) => {
    const nodeStep = flow.steps.findIndex(([name]) => name === node.dataset.node);
    node.classList.toggle("is-active", node.dataset.node === nodeName);
    node.classList.toggle("is-complete", nodeStep >= 0 && nodeStep < stepIndex);
    node.classList.toggle("is-muted", nodeStep < 0);
    node.classList.toggle("is-danger", flow.danger.includes(node.dataset.node));
  });
  const activeNode = document.querySelector(`[data-node="${nodeName}"]`);
  positionPacket(activeNode);
  progress.textContent = `STEP ${String(stepIndex + 1).padStart(2, "0")} / ${String(flow.steps.length).padStart(2, "0")}`;
  title.textContent = stepTitle;
  description.textContent = stepDescription;
}

function schedule() {
  window.clearInterval(timer);
  if (!paused) {
    timer = window.setInterval(() => {
      stepIndex = (stepIndex + 1) % flows[activeFlow].steps.length;
      renderStep();
    }, 2300);
  }
}

function selectFlow(name) {
  activeFlow = name;
  stepIndex = 0;
  selectorButtons.forEach((button) => {
    const active = button.dataset.flow === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  renderStep();
  schedule();
}

selectorButtons.forEach((button) => {
  button.addEventListener("click", () => selectFlow(button.dataset.flow));
});

toggle.addEventListener("click", () => {
  paused = !paused;
  toggle.textContent = paused ? "Resume animation" : "Pause animation";
  schedule();
});

window.addEventListener("resize", () => renderStep());
selectFlow("rank");
