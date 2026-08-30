const state = {
  health: null,
  portfolio: null,
  experiments: [],
  policies: [],
  cohorts: [],
  metrics: [],
  approvals: [],
  audit: { records: [], verification: {} },
  demo: { scenarios: [] },
  staticMode: false,
};

const viewTitles = {
  overview: "Portfolio overview",
  experiments: "Experiment lifecycle",
  policies: "Recommendation policies",
  cohorts: "Segments & cohorts",
  metrics: "Privacy-bounded metrics",
  guardrails: "Guardrails & fairness",
  approvals: "Approvals & audit",
  demo: "Guided meeting demo",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortId(value, length = 18) {
  const text = String(value ?? "—");
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function stateBadge(value) {
  const normalized = String(value || "unknown").toLowerCase().replaceAll(" ", "_");
  return `<span class="state state--${escapeHtml(normalized)}">${escapeHtml(String(value || "unknown").replaceAll("_", " "))}</span>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error?.message || `Request failed (${response.status})`);
    error.code = body.error?.code || "request_failed";
    error.details = body.error?.details || {};
    throw error;
  }
  return body;
}

function toast(title, message = "", type = "success") {
  const region = document.querySelector("#toast-region");
  const element = document.createElement("div");
  element.className = `toast ${type === "error" ? "toast--error" : ""}`;
  element.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(message)}`;
  region.appendChild(element);
  window.setTimeout(() => element.remove(), 4200);
}

function showView(name) {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === name);
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.viewPanel === name);
  });
  document.querySelector("#current-view-title").textContent = viewTitles[name] || name;
  document.querySelector("#sidebar").classList.remove("is-open");
  window.history.replaceState(null, "", `#${name}`);
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});

document.querySelector("#mobile-dashboard-toggle").addEventListener("click", () => {
  document.querySelector("#sidebar").classList.toggle("is-open");
});

function renderTopbar() {
  const healthChip = document.querySelector("#health-chip");
  healthChip.textContent = state.staticMode
    ? "static preview · read only"
    : state.health
      ? `${state.health.status} · audit ${state.health.audit_chain.valid ? "verified" : "failed"}`
      : "offline";
  const kill = state.portfolio?.kill_switch || { enabled: false };
  const button = document.querySelector("#kill-switch-button");
  button.innerHTML = `<span>Kill switch:</span> ${kill.enabled ? "ACTIVE" : "inactive"}`;
  button.classList.toggle("button--danger", Boolean(kill.enabled));
  button.classList.toggle("button--secondary", !kill.enabled);
}

function renderOverview() {
  const summary = state.portfolio?.summary || {};
  const cards = [
    ["Active experiments", summary.active_experiments, "Bounded treatment traffic"],
    ["Pending approvals", summary.pending_approvals, "Human decisions required"],
    ["Active policies", summary.active_policies, "Immutable serving versions"],
    ["Audit records", summary.audit_records, state.audit.verification.valid ? "Hash chain verified" : "Verification warning"],
  ];
  document.querySelector("#overview-metrics").innerHTML = cards
    .map(
      ([label, value, note]) => `
        <article class="metric-card">
          <span class="metric-card__label">${escapeHtml(label)} <span aria-hidden="true">↗</span></span>
          <strong class="metric-card__value">${escapeHtml(value ?? "—")}</strong>
          <span class="metric-card__note">${escapeHtml(note)}</span>
        </article>`,
    )
    .join("");

  const domainMeta = {
    commerce: ["MM", "Mercury Market", "Value, quality, satisfaction"],
    media: ["NM", "Northstar Media", "Trust, breadth, quality"],
    community: ["CG", "CommonGround", "Trust, safety, contribution quality"],
  };
  document.querySelector("#overview-domains").innerHTML = (state.portfolio?.domains || [])
    .map((domain) => {
      const [mark, name, note] = domainMeta[domain] || [domain.slice(0, 2), domain, "Governed recommendation domain"];
      const active = state.experiments.filter((experiment) => experiment.domain === domain && experiment.status === "running").length;
      return `
        <div class="domain-row">
          <span class="domain-row__mark">${escapeHtml(mark)}</span>
          <span><strong>${escapeHtml(name)}</strong><small>${escapeHtml(note)}</small></span>
          <span class="state state--${active ? "running" : "paused"}">${active} running</span>
        </div>`;
    })
    .join("");

  const governance = state.portfolio?.governance || {};
  const controls = [
    ["C", "Consent + purpose", "Required on every rank and event path", "verified"],
    ["50", "Minimum cohort", `${governance.minimum_cohort_size || 50} subjects before launch or metric visibility`, "enforced"],
    ["5%", "Autonomous traffic", `Above ${governance.autonomous_traffic_cap_percent || 5}% requires approval`, "capped"],
    ["∅", "Sensitive attributes", "Rejected from scoring inputs and policy contracts", "prohibited"],
  ];
  document.querySelector("#overview-controls").innerHTML = controls
    .map(
      ([mark, title, note, status]) => `
        <div class="control-row">
          <span class="control-row__mark">${escapeHtml(mark)}</span>
          <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(note)}</small></span>
          ${stateBadge(status)}
        </div>`,
    )
    .join("");

  document.querySelector("#overview-experiments").innerHTML = state.experiments
    .map(
      (experiment) => `
        <tr>
          <td><span class="table-title">${escapeHtml(experiment.name)}</span><span class="table-subtitle">${escapeHtml(experiment.hypothesis)}</span></td>
          <td>${escapeHtml(experiment.domain)}</td>
          <td>${stateBadge(experiment.status)}</td>
          <td>${escapeHtml(experiment.traffic_percent)}%</td>
          <td>${stateBadge(experiment.risk_level)}</td>
        </tr>`,
    )
    .join("");

  document.querySelector("#overview-activity").innerHTML = state.audit.records
    .slice(0, 6)
    .map(
      (record) => `
        <div class="activity-row">
          <span class="activity-row__mark">${escapeHtml(record.action.split(".")[0].slice(0, 2))}</span>
          <span><strong>${escapeHtml(record.action.replaceAll(".", " "))}</strong><small>${escapeHtml(record.actor)} · ${escapeHtml(record.resource_id)}</small></span>
          <small>${escapeHtml(formatDate(record.timestamp))}</small>
        </div>`,
    )
    .join("");
}

function experimentActions(experiment) {
  if (state.staticMode) return '<span class="table-subtitle">Start the local service to mutate state</span>';
  const actions = [];
  if (experiment.status === "draft") actions.push(["review", "Send to review", "button--secondary"]);
  if (experiment.status === "review") actions.push(["approved", "Request approval", ""]);
  if (experiment.status === "approved") actions.push(["running", "Launch", ""]);
  if (experiment.status === "running") {
    actions.push(["paused", "Pause", "button--secondary"]);
    actions.push(["rolled_back", "Rollback", "button--warning"]);
  }
  if (experiment.status === "paused") {
    actions.push(["running", "Resume", ""]);
    actions.push(["rolled_back", "Rollback", "button--warning"]);
  }
  if (!actions.length) return "—";
  return `<div class="inline-actions">${actions
    .map(
      ([target, label, cls]) =>
        `<button type="button" class="button button--small ${cls}" data-transition="${escapeHtml(target)}" data-experiment="${escapeHtml(experiment.id)}">${escapeHtml(label)}</button>`,
    )
    .join("")}</div>`;
}

function renderExperiments() {
  const runningTraffic = state.experiments
    .filter((experiment) => experiment.status === "running")
    .reduce((sum, experiment) => sum + Number(experiment.traffic_percent), 0);
  document.querySelector("#running-traffic-chip").textContent = `${runningTraffic.toFixed(1)}% active traffic / 30% cap`;
  document.querySelector("#experiments-table").innerHTML = state.experiments
    .map((experiment) => {
      const control = state.policies.find((policy) => policy.id === experiment.control_policy_id);
      const treatment = state.policies.find((policy) => policy.id === experiment.treatment_policy_id);
      return `
        <tr>
          <td><span class="table-title">${escapeHtml(experiment.name)}</span><span class="table-subtitle">${escapeHtml(experiment.hypothesis)}</span></td>
          <td><span class="table-title">${escapeHtml(experiment.cohort_id)}</span><span class="table-subtitle">n ≈ ${formatNumber(experiment.cohort_size)} · min ${formatNumber(experiment.minimum_cohort_size)}</span></td>
          <td><span class="table-title">${escapeHtml(control?.name || experiment.control_policy_id)}</span><span class="table-subtitle">vs. ${escapeHtml(treatment?.name || experiment.treatment_policy_id)}</span></td>
          <td><span class="table-title">${escapeHtml(experiment.traffic_percent)}%</span><span class="table-subtitle">${Math.round(Number(experiment.treatment_share) * 100)}% treatment share</span></td>
          <td>${stateBadge(experiment.risk_level)}<span class="table-subtitle">${escapeHtml(experiment.risk_reasons?.[0] || `fairness ≥ ${experiment.guardrails.min_fairness_ratio}`)}</span></td>
          <td>${stateBadge(experiment.status)}${experiment.pending_approval_id ? `<span class="table-subtitle">${escapeHtml(shortId(experiment.pending_approval_id))}</span>` : ""}</td>
          <td>${experimentActions(experiment)}</td>
        </tr>`;
    })
    .join("");
}

function renderPolicies() {
  document.querySelector("#policies-grid").innerHTML = state.policies
    .map((policy) => {
      const weights = Object.entries(policy.objective_weights)
        .sort((a, b) => b[1] - a[1])
        .map(
          ([name, value]) => `
            <div class="weight-row">
              <span>${escapeHtml(name.replaceAll("_", " "))}</span>
              <span class="weight-bar"><span style="width: ${Math.round(Number(value) * 100)}%"></span></span>
              <strong>${Math.round(Number(value) * 100)}%</strong>
            </div>`,
        )
        .join("");
      return `
        <article class="policy-card">
          <div class="policy-card__top">
            <div><h3>${escapeHtml(policy.name)}</h3><span class="table-subtitle">${escapeHtml(policy.domain)} · v${escapeHtml(policy.version)}</span></div>
            ${stateBadge(policy.status)}
          </div>
          <p class="policy-card__purpose">${escapeHtml(policy.purpose)}</p>
          <div class="weight-list">${weights}</div>
          <div class="policy-card__footer">
            <span>exploration ${(Number(policy.exploration_rate) * 100).toFixed(1)}%</span>
            <span>safety floor ${Number(policy.constraints.candidate_safety_floor || 0).toFixed(2)}</span>
          </div>
        </article>`;
    })
    .join("");
}

function renderCohorts() {
  document.querySelector("#cohorts-table").innerHTML = state.cohorts
    .map(
      (cohort) => `
        <tr>
          <td><span class="table-title">${escapeHtml(cohort.name)}</span><span class="table-subtitle">${escapeHtml(cohort.description)}</span></td>
          <td>${escapeHtml(cohort.domain)}</td>
          <td><span class="table-subtitle purpose-cell">${escapeHtml(cohort.purpose)}</span></td>
          <td><span class="table-title">${formatNumber(cohort.estimated_size)}</span><span class="table-subtitle">minimum ${formatNumber(cohort.privacy.minimum_size)}</span></td>
          <td>${stateBadge(cohort.privacy.launch_eligible ? "eligible" : "privacy_blocked")}</td>
          <td>${stateBadge(cohort.privacy.metric_visibility)}</td>
        </tr>`,
    )
    .join("");
}

function renderMetrics() {
  const suppressed = state.metrics.filter((metric) => metric.privacy_status === "suppressed").length;
  document.querySelector("#suppressed-count").textContent = `${suppressed} value${suppressed === 1 ? "" : "s"} suppressed`;
  document.querySelector("#metrics-table").innerHTML = state.metrics
    .map((metric) => {
      const experiment = state.experiments.find((item) => item.id === metric.experiment_id);
      return `
        <tr>
          <td><span class="table-title">${escapeHtml(experiment?.name || metric.experiment_id)}</span><span class="table-subtitle">${escapeHtml(metric.cohort_id)}</span></td>
          <td>${escapeHtml(metric.metric_name.replaceAll("_", " "))}</td>
          <td>${escapeHtml(metric.variant)}</td>
          <td>${formatNumber(metric.sample_size)}</td>
          <td><span class="table-title">${metric.value === null ? "suppressed" : Number(metric.value).toFixed(3)}</span></td>
          <td>${stateBadge(metric.privacy_status)}</td>
          <td>${escapeHtml(formatDate(metric.observed_at))}</td>
        </tr>`;
    })
    .join("");
}

function renderGuardrails() {
  const visible = state.metrics
    .filter((metric) => metric.privacy_status === "visible")
    .slice(0, 6);
  document.querySelector("#guardrail-evidence").innerHTML = visible
    .map((metric) => {
      const experiment = state.experiments.find((item) => item.id === metric.experiment_id);
      return `
        <div class="activity-row">
          <span class="activity-row__mark">${escapeHtml(metric.metric_name.slice(0, 2))}</span>
          <span><strong>${escapeHtml(metric.metric_name.replaceAll("_", " "))} · ${Number(metric.value).toFixed(3)}</strong><small>${escapeHtml(experiment?.name || metric.experiment_id)} · n ${formatNumber(metric.sample_size)}</small></span>
          ${stateBadge("visible")}
        </div>`;
    })
    .join("");
  const kill = state.portfolio?.kill_switch || { enabled: false };
  document.querySelector("#kill-switch-panel").innerHTML = `
    <div class="kill-switch-card ${kill.enabled ? "is-active" : ""}">
      <span class="state state--${kill.enabled ? "failed" : "passed"}">${kill.enabled ? "active" : "inactive"}</span>
      <strong>${kill.enabled ? "Experimental serving is paused" : "Experimental serving is enabled"}</strong>
      <p>${escapeHtml(kill.reason || "Activating the switch pauses all running experiments and routes ranking to approved baselines.")}</p>
      <button type="button" class="button button--small ${kill.enabled ? "button--secondary" : "button--danger"}" data-kill-toggle="${kill.enabled ? "false" : "true"}">${kill.enabled ? "Disable switch" : "Activate switch"}</button>
    </div>`;
}

function renderApprovals() {
  document.querySelector("#audit-verification").textContent = state.audit.verification.valid
    ? `${formatNumber(state.audit.verification.records_checked)} records verified`
    : "chain verification failed";
  document.querySelector("#audit-verification").className = `state state--${state.audit.verification.valid ? "passed" : "failed"}`;
  document.querySelector("#approvals-table").innerHTML = state.approvals
    .map(
      (approval) => `
        <tr>
          <td><span class="table-title">${escapeHtml(approval.action)}</span><span class="table-subtitle">${escapeHtml(shortId(approval.id, 24))}</span></td>
          <td><span class="table-title">${escapeHtml(approval.resource_id)}</span><span class="table-subtitle">${escapeHtml(approval.resource_type)}</span></td>
          <td><span class="table-subtitle">${escapeHtml((approval.reasons || []).join(" · "))}</span></td>
          <td><span class="table-title">${escapeHtml(approval.requested_by)}</span><span class="table-subtitle">${escapeHtml(formatDate(approval.requested_at))}</span></td>
          <td>${stateBadge(approval.status)}${approval.decided_by ? `<span class="table-subtitle">by ${escapeHtml(approval.decided_by)}</span>` : ""}</td>
          <td>${approval.status === "pending" && !state.staticMode ? `<div class="inline-actions"><button type="button" class="button button--small" data-approval="${escapeHtml(approval.id)}" data-decision="approved">Approve</button><button type="button" class="button button--secondary button--small" data-approval="${escapeHtml(approval.id)}" data-decision="denied">Deny</button></div>` : `<span class="table-subtitle">${escapeHtml(approval.decision_reason || (state.staticMode ? "Start the local service to decide" : "Decision recorded"))}</span>`}</td>
        </tr>`,
    )
    .join("");
  document.querySelector("#audit-table").innerHTML = state.audit.records
    .map(
      (record) => `
        <tr>
          <td><span class="table-title">#${escapeHtml(record.seq)}</span></td>
          <td>${escapeHtml(formatDate(record.timestamp))}</td>
          <td>${escapeHtml(record.actor)}</td>
          <td><span class="table-title">${escapeHtml(record.action)}</span></td>
          <td><span class="table-title">${escapeHtml(record.resource_id)}</span><span class="table-subtitle">${escapeHtml(record.resource_type)}</span></td>
          <td><code class="hash-code">${escapeHtml(shortId(record.record_hash, 18))}</code></td>
        </tr>`,
    )
    .join("");
}

function renderDemoManifest() {
  document.querySelector("#scenario-list").innerHTML = state.demo.scenarios
    .map(
      (scenario, index) => `
        <button type="button" class="scenario-button" data-scenario="${escapeHtml(scenario.id)}">
          <span class="scenario-button__number">0${index + 1}</span>
          <span><strong>${escapeHtml(scenario.title)}</strong><small>${escapeHtml(scenario.duration_seconds)} second talk track</small></span>
          <span aria-hidden="true">→</span>
        </button>`,
    )
    .join("");
}

function renderAll() {
  renderTopbar();
  renderOverview();
  renderExperiments();
  renderPolicies();
  renderCohorts();
  renderMetrics();
  renderGuardrails();
  renderApprovals();
  renderDemoManifest();
}

async function loadAll({ quiet = false } = {}) {
  try {
    const [
      health,
      portfolio,
      experiments,
      policies,
      cohorts,
      metrics,
      approvals,
      audit,
      demo,
    ] = await Promise.all([
      api("/api/v1/health"),
      api("/api/v1/portfolio"),
      api("/api/v1/experiments"),
      api("/api/v1/policies"),
      api("/api/v1/cohorts"),
      api("/api/v1/metrics"),
      api("/api/v1/approvals"),
      api("/api/v1/audit?limit=80"),
      api("/api/v1/demo"),
    ]);
    Object.assign(state, {
      health,
      portfolio,
      experiments: experiments.experiments,
      policies: policies.policies,
      cohorts: cohorts.cohorts,
      metrics: metrics.metrics,
      approvals: approvals.approvals,
      audit,
      demo,
    });
    renderAll();
    if (!quiet) toast("Seeded control plane loaded", "All dashboard views are backed by the local API.");
  } catch (error) {
    if (window.PCP_STATIC_STATE) {
      const fallback = structuredClone(window.PCP_STATIC_STATE);
      Object.assign(state, fallback, { staticMode: true });
      renderAll();
      toast("Static portfolio preview", "Start ./scripts/demo.sh on port 8102 to enable live mutations.");
      return;
    }
    toast("Could not load the control plane", `${error.code}: ${error.message}`, "error");
    document.querySelector("#health-chip").textContent = "API unavailable";
  }
}

async function transitionExperiment(experimentId, target) {
  const labels = {
    review: "Move this experiment to review?",
    approved: "Evaluate launch risk and request approval if required?",
    running: "Launch or resume this experiment?",
    paused: "Pause treatment allocation?",
    rolled_back: "Roll back this experiment?",
  };
  if (!window.confirm(labels[target] || `Transition to ${target}?`)) return;
  try {
    const experiment = await api(`/api/v1/experiments/${encodeURIComponent(experimentId)}/transition`, {
      method: "POST",
      body: JSON.stringify({
        target_state: target,
        actor: "dashboard-operator",
        reason: `Operator requested ${target} from the local dashboard.`,
      }),
    });
    toast("Experiment state updated", `${experiment.name} is now ${experiment.status.replaceAll("_", " ")}.`);
    await loadAll({ quiet: true });
  } catch (error) {
    const detail = error.details?.minimum_cohort_size
      ? ` Cohort ${error.details.cohort_size} / minimum ${error.details.minimum_cohort_size}.`
      : "";
    toast("Transition blocked", `${error.code}: ${error.message}${detail}`, "error");
  }
}

async function decideApproval(approvalId, decision) {
  if (!window.confirm(`${decision === "approved" ? "Approve" : "Deny"} this high-risk launch request?`)) return;
  try {
    await api(`/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        actor: "dashboard-reviewer",
        reason: decision === "approved"
          ? "Risk reasons, purpose, cohort, and guardrails reviewed in the local demo."
          : "Launch risk is not acceptable at the proposed scope.",
      }),
    });
    toast("Approval decision recorded", `The request was ${decision}.`);
    await loadAll({ quiet: true });
  } catch (error) {
    toast("Decision failed", `${error.code}: ${error.message}`, "error");
  }
}

async function toggleKillSwitch(enabled) {
  if (state.staticMode) {
    toast("Read-only static preview", "Start the local service on port 8102 to change the kill switch.", "error");
    return;
  }
  const message = enabled
    ? "Activate the global kill switch and pause every running experiment?"
    : "Disable the kill switch? Paused experiments will remain paused.";
  if (!window.confirm(message)) return;
  try {
    const result = await api("/api/v1/control/kill-switch", {
      method: "POST",
      body: JSON.stringify({
        enabled,
        actor: "dashboard-operator",
        reason: enabled
          ? "Manual emergency stop from the operator dashboard."
          : "Operator reviewed system state and disabled the global stop.",
      }),
    });
    toast(
      enabled ? "Kill switch activated" : "Kill switch disabled",
      enabled
        ? `${result.paused_experiments.length} running experiment(s) paused.`
        : "No experiment was automatically resumed.",
    );
    await loadAll({ quiet: true });
  } catch (error) {
    toast("Kill switch update failed", `${error.code}: ${error.message}`, "error");
  }
}

async function resetDemo() {
  if (state.staticMode) {
    toast("Read-only static preview", "Start the local service on port 8102 to reset seeded state.", "error");
    return;
  }
  if (!window.confirm("Reset all local state to the canonical fictional seed? This clears demo actions and decisions.")) return;
  try {
    const result = await api("/api/v1/demo/reset", {
      method: "POST",
      body: JSON.stringify({
        actor: "dashboard-operator",
        reason: "Restore canonical meeting-ready seed.",
      }),
    });
    toast("Demo reset complete", `Seed generation ${result.generation} is ready.`);
    document.querySelector("#demo-stage").innerHTML = `<div class="demo-stage__empty"><div><strong>Canonical seed restored.</strong><p>Choose any scenario to continue the walkthrough.</p></div></div>`;
    await loadAll({ quiet: true });
  } catch (error) {
    toast("Reset failed", `${error.code}: ${error.message}`, "error");
  }
}

async function runScenario(scenarioId) {
  const stage = document.querySelector("#demo-stage");
  document.querySelectorAll("[data-scenario]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.scenario === scenarioId);
  });
  stage.innerHTML = `<div class="demo-stage__empty"><div><strong>Running scenario…</strong><p>The local API is applying real control-plane behavior.</p></div></div>`;
  if (state.staticMode && window.PCP_STATIC_SCENARIOS?.[scenarioId]) {
    const result = window.PCP_STATIC_SCENARIOS[scenarioId];
    stage.innerHTML = `
      <div class="demo-result">
        <span class="state state--visible">static walkthrough</span>
        <h3>${escapeHtml(result.title)}</h3>
        <ul class="talk-track">${(result.talk_track || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <pre class="json-view">${escapeHtml(JSON.stringify(result.result, null, 2))}</pre>
      </div>`;
    toast("Static scenario preview", "Run the local service to execute the state change.");
    return;
  }
  try {
    const result = await api(`/api/v1/demo/scenarios/${encodeURIComponent(scenarioId)}`, {
      method: "POST",
      body: JSON.stringify({ actor: "guided-demo" }),
    });
    stage.innerHTML = `
      <div class="demo-result">
        <span class="state state--passed">scenario complete</span>
        <h3>${escapeHtml(result.title)}</h3>
        <ul class="talk-track">${(result.talk_track || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        <pre class="json-view">${escapeHtml(JSON.stringify(result.result, null, 2))}</pre>
      </div>`;
    toast("Scenario complete", result.title);
    await loadAll({ quiet: true });
  } catch (error) {
    stage.innerHTML = `<div class="demo-stage__empty"><div><strong>Scenario blocked safely.</strong><p>${escapeHtml(error.code)}: ${escapeHtml(error.message)}</p></div></div>`;
    toast("Scenario blocked", `${error.code}: ${error.message}`, "error");
  }
}

document.addEventListener("click", (event) => {
  const transitionButton = event.target.closest("[data-transition]");
  if (transitionButton) {
    transitionExperiment(transitionButton.dataset.experiment, transitionButton.dataset.transition);
    return;
  }
  const approvalButton = event.target.closest("[data-approval]");
  if (approvalButton) {
    decideApproval(approvalButton.dataset.approval, approvalButton.dataset.decision);
    return;
  }
  const killButton = event.target.closest("[data-kill-toggle]");
  if (killButton) {
    toggleKillSwitch(killButton.dataset.killToggle === "true");
    return;
  }
  const scenarioButton = event.target.closest("[data-scenario]");
  if (scenarioButton) runScenario(scenarioButton.dataset.scenario);
});

document.querySelector("#kill-switch-button").addEventListener("click", () => {
  toggleKillSwitch(!Boolean(state.portfolio?.kill_switch?.enabled));
});
document.querySelector("#reset-button").addEventListener("click", resetDemo);
document.querySelector("#run-breach-button").addEventListener("click", () => {
  showView("demo");
  runScenario("guardrail-rollback");
});

const initialView = window.location.hash.slice(1);
if (viewTitles[initialView]) showView(initialView);
loadAll();
