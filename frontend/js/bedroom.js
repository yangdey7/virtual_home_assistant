let currentState = null;
let currentRevision = -1;
let currentSession = null;
let busy = false;
let online = false;

const byId = (id) => document.getElementById(id);

export function setControlsAvailable(available, pending = false) {
  online = available;
  busy = pending;
  refreshButtons();
}

function refreshButtons() {
  const container = byId('device-controls');
  container.setAttribute('aria-busy', String(busy || !online));
  container.querySelectorAll('button').forEach((button) => {
    button.disabled = !online || busy || !currentState;
    if (button.disabled) return;
    const { device, intent } = button.dataset;
    if (device === 'Fan' && intent.endsWith('Speed')) {
      button.disabled = currentState.fan.state === 'OFF' ||
        (intent === 'IncreaseSpeed' && currentState.fan.speed >= 3) ||
        (intent === 'DecreaseSpeed' && currentState.fan.speed <= 1);
    }
    if (device === 'AC' && intent.endsWith('Temp')) {
      const input = byId('ac-temperature');
      button.disabled = (intent === 'IncreaseTemp' && currentState.ac.temperature >= Number(input.max)) ||
        (intent === 'DecreaseTemp' && currentState.ac.temperature <= Number(input.min));
    }
  });
  byId('ac-temperature').disabled = !online || busy || !currentState;
}

export function renderBedroom(snapshot) {
  if (!snapshot?.devices) return;
  if (snapshot.session_id !== currentSession) {
    currentSession = snapshot.session_id;
    currentRevision = -1;
    historySignature = null;
  }
  if (snapshot.revision < currentRevision) return;
  currentRevision = snapshot.revision;
  currentState = snapshot.devices;
  const { light, fan, ac, curtain } = currentState;
  const room = byId('bedroom');
  Object.assign(room.dataset, { light: light.state, fan: fan.state, ac: ac.state, curtain: curtain.state, speed: fan.speed });
  byId('ac-scene-temp').textContent = ac.state === 'ON' ? `${ac.temperature}°` : 'OFF';
  byId('light-state').textContent = light.state;
  byId('light-state').classList.toggle('active', light.state === 'ON');
  byId('fan-state').textContent = fan.state;
  byId('fan-speed').textContent = `Level ${fan.speed}`;
  byId('fan-description').textContent = fan.state === 'ON' ? 'A comfortable breeze' : 'Turn on to adjust speed';
  byId('ac-state').textContent = ac.state;
  byId('ac-description').textContent = ac.state === 'ON' ? 'Cooling your space' : 'Saved temperature · AC off';
  const temperatureInput = byId('ac-temperature');
  temperatureInput.dataset.savedTemperature = ac.temperature;
  if (document.activeElement !== temperatureInput || busy) temperatureInput.value = ac.temperature;
  temperatureInput.min = snapshot.limits.temperature_min;
  temperatureInput.max = snapshot.limits.temperature_max;
  byId('curtain-state').textContent = curtain.state;
  byId('curtain-state').classList.toggle('active', curtain.state === 'OPEN');
  byId('curtain-description').textContent = curtain.state === 'OPEN' ? 'Let the daylight in' : 'A little privacy';
  for (const [device, state] of [['Fan', fan.state], ['AC', ac.state]]) {
    const button = byId(`${device.toLowerCase()}-power`);
    button.dataset.intent = state === 'ON' ? 'TurnOff' : 'TurnOn';
    button.setAttribute('aria-label', `Turn ${state === 'ON' ? 'off' : 'on'} bedroom ${device.toLowerCase()}`);
    button.setAttribute('aria-pressed', String(state === 'ON'));
  }
  document.querySelectorAll('.segmented button').forEach((button) => {
    const active = button.dataset.device === 'Light'
      ? (button.dataset.intent === 'TurnOn') === (light.state === 'ON')
      : (button.dataset.intent === 'Open') === (curtain.state === 'OPEN');
    button.setAttribute('aria-pressed', String(active));
  });
  const activeCount = [light, fan, ac].filter((device) => device.state === 'ON').length;
  const curtainText = `Curtains ${curtain.state.toLowerCase()}`;
  byId('scene-caption').textContent = `${curtainText} · Light ${light.state.toLowerCase()}`;
  byId('room-summary').textContent = `${activeCount} ${activeCount === 1 ? 'device' : 'devices'} on · ${curtainText.toLowerCase()}`;
  byId('scene-live-status').textContent = activeCount ? `${activeCount} ${activeCount === 1 ? 'device' : 'devices'} on · Your room, your way` : 'All quiet. Make yourself at home.';
  byId('scene-description').textContent = `Bedroom light ${light.state.toLowerCase()}. Fan ${fan.state.toLowerCase()}, level ${fan.speed}. AC ${ac.state.toLowerCase()}, set to ${ac.temperature} degrees Celsius. Curtains ${curtain.state.toLowerCase()}.`;
  refreshButtons();
  renderHistory(snapshot.history);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function resultIcon(success) {
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.classList.add('icon');
  icon.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', success ? '#i-check' : '#i-info');
  icon.append(use);
  return icon;
}

export function renderPrediction(prediction) {
  const target = byId('prediction');
  target.replaceChildren();
  if (!prediction) {
    target.append(element('span', 'empty-result', 'No prediction available'));
    return;
  }
  for (const [label, value] of [['Intent', prediction.intent], ['Device', prediction.device], ['Value', prediction.value]]) {
    if (value != null) target.append(element('span', 'prediction-chip', `${label}: ${value}${label === 'Value' ? '°C' : ''}`));
  }
  if (typeof prediction.confidence === 'number') target.append(element('span', 'prediction-chip', `${Math.round(prediction.confidence * 100)}% confidence`));
}

let historySignature = null;
const emptyHistory = byId('history-list').firstElementChild.cloneNode(true);
function renderHistory(history) {
  if (!history) return;
  const signature = history.map((entry) => entry.id).join(',');
  if (historySignature === signature) return;
  historySignature = signature;
  byId('history-count').textContent = `${history.length} recent ${history.length === 1 ? 'command' : 'commands'}`;
  if (!history.length) {
    byId('history-list').replaceChildren(emptyHistory.cloneNode(true));
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const entry of history) {
    const row = element('article', 'history-entry');
    const time = element('time', 'history-time', new Intl.DateTimeFormat('en', { timeZone: 'Asia/Thimphu', hour: 'numeric', minute: '2-digit' }).format(new Date(entry.timestamp)));
    time.dateTime = entry.timestamp;
    const transcript = element('div', 'history-transcript', entry.transcript || 'Manual control');
    transcript.append(element('span', 'history-source', `${entry.source === 'manual' ? 'Manual control' : entry.source === 'voice' ? 'Voice command' : 'Typed command'} · ${entry.success ? 'Successful' : 'Not executed'}`));
    const prediction = element('div', 'history-prediction');
    if (entry.prediction) {
      for (const key of ['intent', 'device', 'value']) {
        if (entry.prediction[key] != null) prediction.append(element('span', 'prediction-chip', `${key}: ${entry.prediction[key]}${key === 'value' ? '°C' : ''}`));
      }
    } else prediction.append(element('span', 'history-source', 'No model prediction'));
    const result = element('div', `history-result${entry.success ? '' : ' failed'}`);
    result.append(resultIcon(entry.success), element('span', '', entry.message));
    row.append(time, transcript, prediction, result);
    fragment.append(row);
  }
  byId('history-list').replaceChildren(fragment);
}

