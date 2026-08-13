const $ = (id) => document.getElementById(id);

let scanTimer = null;
let boardKey = "";   // rebuild the board DOM only when the target list changes

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return { ok: res.ok, data: await res.json() };
}

async function refresh() {
  render(await (await fetch("/state")).json());
}

// --- board rendering ---
function groupTargets(targets) {
  const g = { char: [], control: [], word: [], phrase: [], recent: [] };
  const controls = ["space", "backspace", "clear", "confirm"];
  targets.forEach((t, i) => {
    const bucket = t.kind === "char" ? "char"
      : controls.includes(t.kind) ? "control"
      : t.kind === "word" ? "word" : t.kind;
    g[bucket].push({ label: t.label, i });
  });
  return g;
}

function buttonsInto(el, items, cls) {
  el.innerHTML = "";
  items.forEach(({ label, i }) => {
    const b = document.createElement("button");
    b.className = cls;
    b.textContent = label;
    b.dataset.index = i;
    b.addEventListener("click", () => pick(i));
    el.appendChild(b);
  });
}

function buildBoard(data) {
  const g = groupTargets(data.targets);
  buttonsInto($("keys"), g.char, "key");
  buttonsInto($("controls"), g.control, "key wide");
  buttonsInto($("words"), g.word, "key wide");
  buttonsInto($("phrases"), g.phrase, "key phrase");
  buttonsInto($("recents"), g.recent, "key phrase");
}

function highlight(index) {
  document.querySelectorAll("#board .key").forEach((b) => {
    b.classList.toggle("hi", Number(b.dataset.index) === index);
  });
}

// --- render ---
function render(data) {
  const ready = data.state === "READY_TO_SPEAK";
  $("board").classList.toggle("hidden", ready);
  $("confirmPanel").classList.toggle("hidden", !ready);

  $("message").textContent = data.message || "";
  if (!data.message) $("message").innerHTML = '<span class="placeholder">Build a message…</span>';
  $("current").textContent = data.current || "—";
  $("notice").textContent = data.notice || "";

  if (ready) {
    $("confirmMessage").textContent = data.message;
    document.querySelectorAll(".confirm-opt").forEach((b, i) => {
      b.classList.toggle("hi", i === data.confirm_index);
    });
  } else {
    const key = data.targets.map((t) => t.label).join("|");
    if (key !== boardKey) { buildBoard(data); boardKey = key; }
    highlight(data.index);
  }

  // input status
  const o = data.ocular || {};
  const ok = (v) => (v ? "✓" : "!");
  $("ioCamera").textContent = data.camera === "RUNNING" ? "✓" : data.camera;
  $("ioFace").textContent = ok(o.face === "FACE_FOUND");
  $("ioEyes").textContent = o.ear != null ? "✓" : "!";
  $("ioInput").textContent = o.reliability === "GOOD" ? "✓" : (o.reliability === "UNCERTAIN" ? "…" : "!");
  $("ioCal").textContent = ok(o.calibrated);

  $("statusText").textContent = ready ? "confirm" : data.input.toLowerCase();
  $("statusDot").className = "dot " + (o.reliability === "GOOD" || data.input === "SIMULATION" ? "green" : "amber");

  // debug
  $("debugToggle").checked = data.debug;
  $("debugPanel").classList.toggle("hidden", !data.debug);
  $("dEar").textContent = o.ear ?? "—";
  $("dPhase").textContent = o.blink_phase || "—";
  $("dGaze").textContent = o.gaze || "—";
  $("dRel").textContent = o.reliability || "—";
  $("dState").textContent = data.state;
  $("dTarget").textContent = data.current || "—";

  $("ocularSetup").classList.toggle("hidden", data.input !== "OCULAR");
  if (data.input === "OCULAR" && !$("videoFeed").src) $("videoFeed").src = "/video_feed";
  if (data.input !== "OCULAR") $("videoFeed").src = "";
}

// --- actions ---
async function pick(index) {
  await post("/highlight", { index });
  render((await post("/simulate", { event: "SELECT" })).data);
}

async function sendEvent(name) {
  render((await post("/simulate", { event: name })).data);
}

document.querySelectorAll("button[data-event]").forEach((b) =>
  b.addEventListener("click", () => sendEvent(b.dataset.event)));

document.querySelectorAll(".confirm-opt").forEach((b) =>
  b.addEventListener("click", () => sendEvent(b.dataset.confirm === "speak" ? "CONFIRM" : "CANCEL")));

document.querySelectorAll("button[data-mode]").forEach((b) =>
  b.addEventListener("click", async () => {
    $("modeError").textContent = "";
    const { ok, data } = await post("/input_mode", { mode: b.dataset.mode });
    if (!ok) $("modeError").textContent = data.error || "failed";
    render(data);
  }));

$("scanBtn").addEventListener("click", async () => {
  if (scanTimer) {
    clearInterval(scanTimer); scanTimer = null;
    $("scanBtn").textContent = "Scan: off";
  } else {
    const interval = (await (await fetch("/state")).json()).scan_interval * 1000;
    scanTimer = setInterval(async () => render((await post("/scan", {})).data), interval);
    $("scanBtn").textContent = "Scan: on";
  }
});

$("debugToggle").addEventListener("change", async (e) =>
  render((await post("/debug", { on: e.target.checked })).data));

document.querySelectorAll("button[data-phase]").forEach((b) =>
  b.addEventListener("click", async () => {
    const { ok, data } = await post("/calibration/start", { phase: b.dataset.phase });
    $("calResult").textContent = ok ? `collecting: ${b.dataset.phase}` : (data.error || "failed");
  }));

$("calFinish").addEventListener("click", async () => {
  const { data } = await post("/calibration/finish", {});
  $("calResult").textContent = data.ok ? "Calibration complete" : `Failed: ${data.reason || data.error}`;
  refresh();
});

refresh();
setInterval(refresh, 1500);
