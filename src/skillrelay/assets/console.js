import { paths } from "./icons.js";

const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icon = (name) =>
  `<svg class="icon" viewBox="0 0 256 256" aria-hidden="true">${paths[name] || paths.book}</svg>`;
const pretty = (value) => esc(JSON.stringify(value, null, 2));
const labels = {
  active: "Active",
  pending_review: "Needs review",
  superseded: "Previous version",
  changes_requested: "Changes requested",
  needs_requalification: "Needs requalification",
  evidence_supported: "Evidence supported",
  incompatible: "Incompatible",
  pass: "Passed",
  fail: "Failed",
  unknown: "Unknown",
  completed: "Completed",
  queued: "Queued",
  running: "Running",
  single: "Single agent",
  skill_use: "Skill applied",
  verification: "Verification",
  failure: "Failure",
};
const human = (value) => labels[value] || String(value).replaceAll("_", " ");
const badge = (value) =>
  `<span class="badge ${["active", "pass", "completed"].includes(value) ? "success" : ["pending_review", "unknown", "needs_requalification", "queued"].includes(value) ? "warning" : ["fail", "failure", "revoked", "rejected", "incompatible", "failed"].includes(value) ? "danger" : ""}">${esc(human(value))}</span>`;
const status = (v) => (v.freshness === "current" ? v.state : v.freshness);
const short = (value) => String(value || "").slice(0, 10);
const time = (at) =>
  new Date(at * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
let token = "",
  state = {},
  view = "skills",
  filter = "all",
  search = "",
  selected = null,
  busy = false;
let toastTimer;
const pages = {
  skills: [
    "The skill library",
    "Experience, ready to use.",
    "Reusable skills, grounded in real work and reviewed before they reach your agents.",
  ],
  traces: [
    "Observable experience",
    "Follow the work.",
    "See what happened, what failed, and what your agents learned along the way.",
  ],
  jobs: [
    "The learning loop",
    "From evidence to insight.",
    "Distillation and evaluation jobs, with the source evidence behind every attempt.",
  ],
  audit: [
    "Workspace history",
    "Every decision has a record.",
    "Follow approvals, exact-version retrieval, policy changes, and rollback.",
  ],
  settings: [
    "Workspace settings",
    "Keep people in control.",
    "Decide how evaluated skills become available to your agents.",
  ],
};

function fillIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    node.innerHTML = icon(node.dataset.icon);
  });
}
async function api(op, data) {
  const response = await fetch("/api/" + op, {
    method: data ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + token,
      "Content-Type": "application/json",
    },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });
  const body = await response.json();
  if (!response.ok)
    throw Error(body.error || "Could not connect to the workspace.");
  return body;
}
function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 5000);
}
async function refresh() {
  state = await api("snapshot");
  render();
}
async function connect(event) {
  event.preventDefault();
  token = $("token").value;
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  $("login-error").hidden = true;
  try {
    await refresh();
    $("login").hidden = true;
    $("workspace").hidden = false;
    $("connection").hidden = false;
    $("lock").hidden = false;
    $("token").value = "";
    document.querySelectorAll("[data-view]").forEach((b) => {
      b.disabled = false;
    });
  } catch (error) {
    token = "";
    $("login-error").textContent =
      error.message === "Unauthorized"
        ? "That credential was not accepted. Use your reviewer token."
        : error.message;
    $("login-error").hidden = false;
  } finally {
    button.disabled = false;
  }
}
function navigate(next) {
  view = next;
  $("app").classList.remove("sidebar-open");
  $("mobile-toggle").setAttribute("aria-expanded", "false");
  render();
  window.scrollTo({ top: 0 });
}
function render() {
  const p = state.policy;
  $("mode").textContent =
    p.mode === "human"
      ? "Human review · enforced"
      : `Automatic ≥ ${p.threshold} · human fallback`;
  $("breadcrumb").textContent = document
    .querySelector(`[data-view="${view}"] > span:nth-child(2)`)
    .textContent.trim();
  document.querySelectorAll("[data-view]").forEach((b) => {
    if (b.dataset.view === view) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  const [kicker, title, description] = pages[view];
  $("page-kicker").textContent = kicker;
  $("page-title").textContent = title;
  $("page-description").textContent = description;
  const pending = state.version.filter(
    (v) => v.state === "pending_review",
  ).length;
  $("review-count").textContent = pending;
  $("stats").hidden = view === "settings";
  $("stats").innerHTML = [
    ["Observed runs", state.run.length, "Real workflow evidence"],
    [
      "Available skills",
      state.version.filter((v) => status(v) === "active").length,
      "Approved & compatible",
    ],
    ["Awaiting review", pending, "Your decision, your control"],
    [
      "Queued jobs",
      state.job.filter((j) => j.status === "queued").length,
      "Ready for a learning agent",
    ],
  ]
    .map(
      ([name, n, note]) =>
        `<div class="metric"><div class="metric-label">${name}</div><div class="metric-value">${n}</div><div class="metric-note">${note}</div></div>`,
    )
    .join("");
  ({
    skills: renderSkills,
    traces: renderTraces,
    jobs: renderJobs,
    audit: renderAudit,
    settings: renderSettings,
  })[view]();
}
function empty(title, description, glyph = "book") {
  return `<div class="empty">${icon(glyph)}<h3>${title}</h3><p>${description}</p></div>`;
}
function renderSkills() {
  $("content").innerHTML =
    `<div class="section-head"><h2>Skill versions <small>(${state.version.length})</small></h2><small>Evidence before activation</small></div>
    <div class="toolbar"><div class="filters" aria-label="Filter skills">${[
      ["all", "All versions"],
      ["active", "Active"],
      ["pending_review", "Needs review"],
      ["history", "History"],
    ]
      .map(
        ([key, label]) =>
          `<button class="filter" data-filter="${key}" aria-pressed="${filter === key}">${label}</button>`,
      )
      .join(
        "",
      )}</div><label class="search">${icon("search")}<input id="search" type="search" aria-label="Search skills" placeholder="Search your skills…" value="${esc(search)}"></label></div><div id="skill-list"></div><p class="helper">Skills are available to your agents only after they pass the required checks and your activation policy.</p>`;
  updateSkillList();
  $("search").addEventListener("input", (event) => {
    search = event.target.value;
    updateSkillList();
  });
}
function updateSkillList() {
  const versions = state.version
    .slice()
    .reverse()
    .filter(
      (v) =>
        (filter === "all" ||
          (filter === "history"
            ? !["active", "pending_review"].includes(status(v))
            : status(v) === filter)) &&
        `${v.data.title} ${v.task} ${v.data.summary}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    );
  $("skill-list").innerHTML = versions.length
    ? `<div class="library"><div class="library-head"><span>Skill</span><span>Version</span><span>Confidence</span><span>Status</span><span></span></div>${versions
        .map(
          (v) => `
    <button class="skill-row" data-open="${esc(v.id)}" aria-label="Open ${esc(v.data.title)} version ${v.number}"><span class="skill-name"><span class="skill-symbol">${icon("book")}</span><span><strong class="skill-title">${esc(v.data.title)}</strong><small>${esc(v.task)} · ${esc(human(v.validation))}</small></span></span><span class="version">v${v.number}</span><span class="confidence">${v.confidence}<small> / 100</small><span class="mini-bar"><span style="width:${v.confidence}%"></span></span></span>${badge(status(v))}${icon("chevron")}</button>`,
        )
        .join("")}</div>`
    : empty(
        state.version.length
          ? "No matching skills"
          : "Your next run starts the library",
        state.version.length
          ? "Try a different search or filter."
          : "Connect an agent, capture a run, and let a learning agent propose a skill. Review it here before reuse.",
      );
}
function eventCard(e) {
  return `<article class="event" data-kind="${esc(e.kind)}"><div class="event-head">${badge(e.kind)}<small>${esc(e.tool || "Workflow event")}</small></div><p>${esc(e.action)}</p>${e.result ? `<pre>${esc(e.result)}</pre>` : ""}${e.skill_version ? `<button class="text-button" data-open="${esc(e.skill_version)}">Applied ${esc(e.skill_version)}</button>` : ""}<small>${e.causes.length ? "Caused by " + e.causes.map(esc).join(", ") : "Event " + esc(short(e.id))}${e.recipient ? " · To " + esc(e.recipient) : ""}</small></article>`;
}
function renderTraces() {
  $("content").innerHTML = state.workflow.length
    ? state.workflow
        .slice()
        .reverse()
        .map(
          (w) =>
            `<section class="card"><div class="card-top"><div><div class="kicker">${esc(human(w.pattern))} workflow</div><h2>${esc(w.task)}</h2></div>${badge(w.outcome)}</div><small>Workflow ${esc(short(w.id))} · ${time(w.created)}</small>${state.run
              .filter((r) => r.workflow_id === w.id)
              .map(
                (r) =>
                  `<section class="run"><div class="run-title"><strong>${esc(r.agent)} <small> / ${esc(r.role)}</small></strong>${badge(r.outcome)}</div><p class="muted">${esc(r.goal)}</p><p class="helper">Outcome source: ${esc(human(r.outcome_source))}${r.parent ? " · Parent " + esc(short(r.parent)) : ""}</p>${state.event
                    .filter((e) => e.run_id === r.id)
                    .map(eventCard)
                    .join(
                      "",
                    )}<details><summary>Verify this run's outcome</summary><p class="helper">Use your own review of the evidence. Completion alone does not prove success.</p><div class="actions">${["pass", "fail", "unknown"].map((outcome) => `<button data-verify="${r.id}" data-outcome="${outcome}">Verify ${outcome}</button>`).join("")}</div></details></section>`,
              )
              .join("")}</section>`,
        )
        .join("")
    : empty(
        "No workflows yet",
        "Connect an agent and report observable actions to start capturing evidence.",
        "traces",
      );
}
function renderJobs() {
  $("content").innerHTML =
    `<div class="notice">${icon("jobs")}<div><strong>Learning is enabled</strong>Queued work waits for a connected learner. Distillation creates proposals; independent evaluation checks their evidence.</div></div>` +
    (state.job.length
      ? state.job
          .slice()
          .reverse()
          .map(
            (j) =>
              `<article class="card"><div class="card-top"><div><div class="kicker">${j.kind === "distill" ? "Distillation" : "Evaluation"}</div><h3>${esc(j.task)}</h3></div>${badge(j.status)}</div><p class="muted">${j.kind === "distill" ? "Find a reusable lesson in the observed work." : "Check support, applicability, completeness, and contradictions."}</p><p class="helper">Attempt ${j.attempts} of 3 · ${j.worker ? esc(j.worker) : "Waiting for a learning agent"} · Job ${esc(short(j.id))}</p><details><summary>Source evidence & job details</summary><pre>${pretty(j)}</pre></details></article>`,
          )
          .join("")
      : empty(
          "No learning jobs yet",
          "A completed run or checkpoint will automatically queue the next learning opportunity.",
          "jobs",
        ));
}
const auditLabels = {
  skill_proposed: "Skill proposed",
  evaluated: "Evaluation recorded",
  approve: "Version approved",
  rollback: "Version rolled back",
  review: "Review decision",
  discovery: "Skills discovered",
  retrieved: "Exact version retrieved",
  policy_changed: "Activation policy changed",
  automatic: "Automatically activated",
  outcome_verified: "Outcome verified",
};
function renderAudit() {
  $("content").innerHTML = state.audit.length
    ? `<div class="table-wrap"><table><thead><tr><th>When</th><th>What happened</th><th>Actor</th><th>Evidence</th></tr></thead><tbody>${state.audit.map((a) => `<tr><td><small>${time(a.at)}</small></td><td>${esc(auditLabels[a.action] || human(a.action))}</td><td>${esc(a.actor)}</td><td><details><summary>${a.body.version ? esc(a.body.version) : a.body.action ? esc(human(a.body.action)) : "View record"}</summary><pre>${pretty(a.body)}</pre></details></td></tr>`).join("")}</tbody></table></div>`
    : empty(
        "Every decision will appear here",
        "Approvals, retrieval, and policy changes are recorded as they happen.",
        "audit",
      );
}
function renderSettings() {
  const p = state.policy;
  $("content").innerHTML =
    `<form id="policy-form" class="card policy-card"><div class="card-top"><h2>Activation policy</h2>${badge(p.mode === "human" ? "Human review" : "Automatic with fallback")}</div><p class="muted">Learning runs automatically. You choose when the resulting skills become available.</p><div class="policy-choices"><label class="policy-choice"><input type="radio" name="mode" value="human" ${p.mode === "human" ? "checked" : ""}><span>Human review</span><small>Every skill needs an explicit approval. Confidence never bypasses your decision.</small></label><label class="policy-choice"><input type="radio" name="mode" value="automatic" ${p.mode === "automatic" ? "checked" : ""}><span>Automatic with fallback</span><small>High-confidence skills can activate. Uncertain results come to you for review.</small></label></div><label class="field">Confidence threshold<input name="threshold" type="number" min="80" max="100" value="${p.threshold}" required><small>80–100. Required checks and evaluator trust always apply.</small></label><label class="field">Trusted evaluator identities<input name="evaluators" value="${esc(p.trusted_evaluators.join(", "))}" placeholder="evaluator-agent"><small>Separate multiple identities with commas. Trust is configured here, never claimed by an agent.</small></label><div class="notice">${icon("shield")}<div><strong>Enforced at activation time</strong>Changes apply to proposals already in flight. The confidence score is an evidence rubric, not a probability or a performance benchmark.</div></div><button class="primary" type="submit">Save enforced policy</button><p class="helper">Policy revision ${p.revision} · Auto-distillation enabled</p></form>`;
  $("policy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await mutate(
      "policy",
      {
        mode: form.get("mode"),
        threshold: Number(form.get("threshold")),
        trusted_evaluators: form
          .get("evaluators")
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      },
      "Activation policy saved",
    );
  });
}
function openDialog(title, body) {
  $("detail-title").textContent = title;
  $("detail-body").innerHTML = body;
  if (!$("detail").open) $("detail").showModal();
  $("detail").scrollTop = 0;
}
function openSkill(id) {
  const v = state.version.find((v) => v.id === id);
  if (!v) return toast("That version is not in this workspace.");
  selected = id;
  const evaluation = v.evaluation;
  const eligible =
    Object.values(v.checks).every(Boolean) &&
    evaluation?.verdict === "pass" &&
    v.freshness === "current" &&
    !["revoked", "rejected", "changes_requested"].includes(v.state);
  const explanation =
    v.state === "pending_review"
      ? state.policy.mode === "human"
        ? "Human review is required before this version can be used."
        : v.confidence < state.policy.threshold
          ? `Confidence is below ${state.policy.threshold}. This version needs human review.`
          : !evaluation?.trusted
            ? "A trusted evaluation is required for automatic activation."
            : "This version is awaiting a reviewer decision."
      : v.state === "active"
        ? "This exact version is available to connected agents."
        : "This version is retained with its evidence and review history.";
  const rubrics = [
    ["support", "Evidence support"],
    ["applicability", "Applicability"],
    ["completeness", "Completeness"],
    ["contradictions", "No contradictions"],
  ];
  openDialog(
    `Skill version ${v.number}`,
    `<div class="tags">${badge(status(v))}<span class="badge">v${v.number}</span><span class="tag">${esc(v.task)}</span></div><h2>${esc(v.data.title)}</h2><p>${esc(v.data.summary)}</p><div class="score-panel"><div class="score-number">${v.confidence}<small> / 100</small></div><div class="score-caption"><strong>Evidence confidence</strong>${esc(explanation)}<br>Rubric score, not a probability.</div></div><h3>When to use this skill</h3><ul>${v.data.applicability.map((a) => `<li>${esc(a)}</li>`).join("")}</ul><h3>Procedure & source evidence</h3><ol>${v.data.steps.map((s) => `<li>${esc(s.instruction)}<br>${s.evidence.map((ref, i) => `<button class="citation" data-evidence="${esc(ref)}">Source ${i + 1} · ${esc(ref.split(":").at(-1).slice(0, 26))}</button>`).join("")}</li>`).join("")}</ol><h3>Required checks</h3><div class="gates">${Object.entries(
      v.checks,
    )
      .map(
        ([name, pass]) =>
          `<span class="gate ${pass ? "" : "failed"}">${icon(pass ? "check" : "close")}${esc(human(name))} · ${pass ? "pass" : "fail"}</span>`,
      )
      .join(
        "",
      )}</div><details><summary>Evaluation & limitations</summary>${evaluation ? `<p class="helper">${esc(evaluation.actor)} · ${esc(evaluation.evaluator_version)} · ${esc(evaluation.verdict)}</p><p>${esc(evaluation.rationale)}</p><div class="gates">${rubrics.map(([key, label]) => `<span class="gate">${label}: ${evaluation[key]}/4</span>`).join("")}</div>` : '<p class="helper">Waiting for an independent evaluation or your assessment.</p>'}<ul>${v.data.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></details><details><summary>Evaluate as reviewer</summary><p class="helper">Use a score from 0 (absent) to 4 (complete). A passing assessment still follows the activation policy.</p><form id="assessment-form"><div class="rubric">${rubrics.map(([key, label]) => `<label>${label}<input name="${key}" type="number" min="0" max="4" value="0" required></label>`).join("")}</div><label class="field">Verdict<select name="verdict"><option value="unknown">Unknown</option><option value="pass">Pass</option><option value="fail">Fail</option></select></label><label class="field">Rationale<textarea name="rationale" placeholder="Explain what the observable evidence supports" required></textarea></label><button type="submit">Record human assessment</button></form></details><details><summary>Exact version & content hash</summary><pre>${pretty({ id: v.id, hash: v.hash, validation: v.validation, freshness: v.freshness, dependencies: v.data.dependencies })}</pre></details><div class="review-footer"><label class="field">Review note <span class="muted">Optional</span><textarea id="review-reason" placeholder="Add context for this decision"></textarea></label><div class="actions"><button class="primary" data-review="approve" ${!eligible || v.state === "active" ? "disabled" : ""}>${icon("check")}Approve version</button><button data-diff="${esc(v.id)}">Version diff</button><button data-review="rollback" ${!eligible || v.state === "active" ? "disabled" : ""}>Rollback to this version</button></div><div class="actions">${[
      ["request_changes", "Request changes"],
      ["defer", "Defer"],
      ["reject", "Reject"],
      ["revoke", "Revoke"],
    ]
      .map(
        ([action, label]) =>
          `<button data-review="${action}" class="${action === "revoke" || action === "reject" ? "danger-button" : "quiet-button"}" ${["revoked", "rejected", "changes_requested"].includes(v.state) ? "disabled" : ""}>${label}</button>`,
      )
      .join(
        "",
      )}</div><p class="helper">Decisions bind to this exact version and content hash.</p></div>`,
  );
  $("assessment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget),
      assessment = {};
    rubrics.forEach(([key]) => {
      assessment[key] = Number(form.get(key));
    });
    Object.assign(assessment, {
      verdict: form.get("verdict"),
      rationale: form.get("rationale"),
      evaluator_version: "human-rubric-v1",
      evidence: [...new Set(v.data.steps.flatMap((s) => s.evidence))],
    });
    await mutate(
      "assess",
      { version_id: v.id, assessment },
      "Human assessment recorded",
      v.id,
    );
  });
}
async function mutate(op, data, message, versionId = null) {
  if (busy) return;
  busy = true;
  try {
    await api(op, data);
    await refresh();
    if (versionId) openSkill(versionId);
    toast(message);
  } catch (error) {
    toast(error.message);
  } finally {
    busy = false;
  }
}
async function showDiff(right) {
  const current = state.version.find((v) => v.id === right);
  const prior = state.version
    .filter((v) => v.skill_id === current.skill_id && v.number < current.number)
    .sort((a, b) => a.number - b.number)
    .at(-1);
  if (!prior)
    return toast(
      "This is the first version. There is no earlier version to compare.",
    );
  try {
    const diff = await api(
      `diff?left=${encodeURIComponent(prior.id)}&right=${encodeURIComponent(right)}`,
    );
    openDialog(
      `Version ${prior.number} → version ${current.number}`,
      `<h2>What changed</h2><p class="helper">Comparing immutable skill content.</p><pre>${diff
        .split("\n")
        .map(
          (line) =>
            `<span class="${line.startsWith("+") ? "diff-add" : line.startsWith("-") ? "diff-remove" : ""}">${esc(line)}</span>`,
        )
        .join(
          "\n",
        )}</pre><button data-open="${esc(right)}">Back to version ${current.number}</button>`,
    );
  } catch (error) {
    toast(error.message);
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  const data = button.dataset;
  if (data.view) navigate(data.view);
  if (data.filter) {
    filter = data.filter;
    renderSkills();
  }
  if (data.open) openSkill(data.open);
  if (data.diff) await showDiff(data.diff);
  if (data.evidence) {
    const e = state.event.find((e) => e.id === data.evidence);
    if (e)
      openDialog(
        "Source evidence",
        `<h2>Observed work</h2><p class="helper">The original trace event supporting this instruction.</p>${eventCard(e)}<button data-open="${esc(selected)}">Back to skill</button>`,
      );
    else toast("Source event not found.");
  }
  if (data.review) {
    const v = state.version.find((v) => v.id === selected);
    await mutate(
      "review",
      {
        version_id: v.id,
        expected_hash: v.hash,
        action: data.review,
        reason: $("review-reason").value,
      },
      "Decision recorded",
      v.id,
    );
  }
  if (data.verify)
    await mutate(
      "outcome",
      { run_id: data.verify, outcome: data.outcome },
      "Outcome verified",
    );
});
$("login-form").addEventListener("submit", connect);
$("refresh").addEventListener("click", async () => {
  try {
    await refresh();
    toast("Workspace refreshed");
  } catch (error) {
    toast(error.message);
  }
});
$("lock").addEventListener("click", () => {
  token = "";
  location.reload();
});
$("mobile-toggle").addEventListener("click", () => {
  $("mobile-toggle").setAttribute(
    "aria-expanded",
    String($("app").classList.toggle("sidebar-open")),
  );
});
$("close-detail").addEventListener("click", () => {
  $("detail").close();
});
$("detail").addEventListener("click", (event) => {
  if (event.target === $("detail")) {
    const r = $("detail").getBoundingClientRect();
    if (
      event.clientX < r.left ||
      event.clientX > r.right ||
      event.clientY < r.top ||
      event.clientY > r.bottom
    )
      $("detail").close();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    $("app").classList.remove("sidebar-open");
    $("mobile-toggle").setAttribute("aria-expanded", "false");
  }
});
fillIcons();
