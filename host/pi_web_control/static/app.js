const stateUrl = "/api/state";
const el = (id) => document.getElementById(id);

async function api(path, body = undefined) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function refreshPorts() {
  const data = await api("/api/ports");
  const select = el("portSelect");
  const current = select.value;
  select.innerHTML = "";
  data.ports.forEach((port) => {
    const option = document.createElement("option");
    option.value = port;
    option.textContent = port;
    select.appendChild(option);
  });
  if (current) select.value = current;
}

function renderState(state) {
  el("connectionText").textContent = state.connected ? `Connected to ${state.port}` : "Disconnected";
  el("speedLimit").value = state.speedLimit.toFixed(2);
  el("speedLimitValue").textContent = state.speedLimit.toFixed(2);
  el("leftSlider").value = state.speedLimit > 0 ? (state.leftPower / state.speedLimit).toFixed(2) : 0;
  el("rightSlider").value = state.speedLimit > 0 ? (state.rightPower / state.speedLimit).toFixed(2) : 0;

  state.applied.forEach((value, index) => { el(`applied${index}`).textContent = value; });
  state.pulseTotals.forEach((value, index) => { el(`total${index}`).textContent = value; });
  state.pulseRates.forEach((value, index) => { el(`pulseBar${index}`).value = Math.min(value, 50); });
  el("log").textContent = state.log.join("\n");
  el("log").scrollTop = el("log").scrollHeight;
}

async function pollState() {
  try {
    renderState(await api(stateUrl));
  } catch (error) {
    el("connectionText").textContent = "Web app offline";
  }
}

function bindHoldButton(button, left, right) {
  const start = async (event) => {
    event.preventDefault();
    await api("/api/tank", {left, right});
  };
  const stop = async (event) => {
    event.preventDefault();
    await api("/api/stop", {});
  };
  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", stop);
  button.addEventListener("pointerleave", stop);
  button.addEventListener("pointercancel", stop);
}

function bindMotorButton(button, motor, direction) {
  const start = async (event) => {
    event.preventDefault();
    await api("/api/motor", {motor, direction});
  };
  const stop = async (event) => {
    event.preventDefault();
    await api("/api/stop", {});
  };
  button.addEventListener("pointerdown", start);
  button.addEventListener("pointerup", stop);
  button.addEventListener("pointerleave", stop);
  button.addEventListener("pointercancel", stop);
}

document.querySelectorAll(".pad button[data-left]").forEach((button) => {
  bindHoldButton(button, Number(button.dataset.left), Number(button.dataset.right));
});

document.querySelectorAll(".motor button").forEach((button) => {
  bindMotorButton(button, Number(button.dataset.motor), Number(button.dataset.direction));
});

el("refreshPorts").addEventListener("click", refreshPorts);
el("connect").addEventListener("click", async () => {
  renderState(await api("/api/connect", {port: el("portSelect").value}));
});
el("disconnect").addEventListener("click", async () => { renderState(await api("/api/disconnect", {})); });
el("emergencyStop").addEventListener("click", async () => { renderState(await api("/api/stop", {})); });
el("padStop").addEventListener("click", async () => { renderState(await api("/api/stop", {})); });
el("speedLimit").addEventListener("input", async () => {
  el("speedLimitValue").textContent = Number(el("speedLimit").value).toFixed(2);
  renderState(await api("/api/speed-limit", {value: Number(el("speedLimit").value)}));
});
el("applySliders").addEventListener("click", async () => {
  renderState(await api("/api/tank", {
    left: Number(el("leftSlider").value),
    right: Number(el("rightSlider").value),
  }));
});
el("sendRaw").addEventListener("click", async () => {
  const command = el("rawCommand").value.trim();
  if (command) renderState(await api("/api/raw", {command}));
});

document.addEventListener("keydown", async (event) => {
  if (event.repeat) return;
  if (event.key === " " || event.key === "Escape") {
    event.preventDefault();
    renderState(await api("/api/stop", {}));
    return;
  }
  const map = {
    w: [1, 1], ArrowUp: [1, 1],
    s: [-1, -1], ArrowDown: [-1, -1],
    a: [-0.5, 0.5], ArrowLeft: [-0.5, 0.5],
    d: [0.5, -0.5], ArrowRight: [0.5, -0.5],
  };
  if (map[event.key]) {
    event.preventDefault();
    await api("/api/tank", {left: map[event.key][0], right: map[event.key][1]});
  }
});

document.addEventListener("keyup", async (event) => {
  if (["w", "s", "a", "d", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    renderState(await api("/api/stop", {}));
  }
});

refreshPorts();
pollState();
setInterval(pollState, 500);
