import { api, post } from './api.js';
import { renderBedroom, renderPrediction, setControlsAvailable } from './bedroom.js';
import { VoiceController } from './voice.js';

const byId = (id) => document.getElementById(id);
const confirmation = byId('command-confirmation');
let online = false;
let busy = false;
let voiceAvailable = false;
let feedbackTimer;
let polling = false;
let pendingCommand = null;

function toast(message, error = false) {
  clearTimeout(feedbackTimer);
  const feedback = byId('feedback');
  feedback.textContent = message;
  feedback.className = `feedback visible${error ? ' error' : ''}`;
  feedbackTimer = setTimeout(() => feedback.classList.remove('visible'), error ? 9000 : 5000);
}

function availability() {
  const controlsBusy = busy || pendingCommand !== null;
  setControlsAvailable(online, controlsBusy);
  byId('command-input').disabled = !online || controlsBusy;
  byId('send-command').disabled = !online || controlsBusy;
  byId('microphone').disabled = !online || !voiceAvailable || (controlsBusy && !voice.active);
  byId('confirm-command').disabled = !online || busy;
}

const STATES = {
  idle: 'Tap to speak', listening: 'Listening…', processing: 'Processing your command…',
  confirming: 'Review your command', executing: 'Adjusting your room…',
  completed: 'All taken care of.', error: 'Let’s try that again.',
};

function setVoiceState(state, hint) {
  byId('voice-area').dataset.state = state;
  byId('voice-label').textContent = STATES[state] || STATES.idle;
  byId('voice-hint').textContent = hint || (state === 'idle' ? (voiceAvailable ? 'Tap the microphone, then say your command.' : 'Type a command or use the manual controls.') : state === 'completed' ? 'Your room has been updated. Tap to speak again.' : '');
  byId('microphone').setAttribute('aria-label', state === 'listening' ? 'Stop listening and process your voice command' : 'Start listening for a voice command');
  if (state === 'listening') {
    busy = true;
    renderPrediction(null);
    byId('transcript').textContent = 'Listening for your words…';
    byId('execution-result').textContent = 'Waiting for a command.';
    byId('execution-result').className = 'empty-result';
    byId('execution-marker').className = 'step-number';
  } else if (state === 'processing') busy = true;
  else if (state === 'idle') busy = false;
  availability();
}

function transcript(text, source = 'voice') {
  byId('transcript-heading').textContent = source === 'voice' ? 'Speech recognition output' : 'Typed command';
  byId('transcript').textContent = text;
  byId('transcript').className = '';
}

function execution(message, success) {
  byId('execution-result').textContent = message;
  byId('execution-result').className = success ? '' : 'error';
  byId('execution-marker').className = `step-number ${success ? 'success' : 'error'}`;
  byId('execution-marker').textContent = success ? '✓' : '!';
}

function showError(message, data) {
  if (data) {
    renderBedroom(data);
    if (data.prediction) renderPrediction(data.prediction);
  }
  execution(message, false);
  busy = false;
  setVoiceState('error', 'Nothing was confirmed. Check the message below and try again.');
  toast(message, true);
}

function confirmationQuestion({ intent, device, value }) {
  const target = { Light: 'bedroom light', Fan: 'fan', AC: 'AC', Curtain: 'curtains' }[device];
  const action = {
    TurnOn: `Turn on the ${target}`,
    TurnOff: `Turn off the ${target}`,
    Open: `Open the ${target}`,
    Close: `Close the ${target}`,
    IncreaseSpeed: `Increase the ${target} speed`,
    DecreaseSpeed: `Decrease the ${target} speed`,
    IncreaseTemp: `Raise the ${target} temperature`,
    DecreaseTemp: `Lower the ${target} temperature`,
    SetTemp: value == null ? `Set the ${target} temperature` : `Set the ${target} to ${value}°C`,
  }[intent];
  return `${action}?`;
}

async function runCommand(text, source = 'text') {
  busy = true;
  transcript(text, source);
  renderPrediction(null);
  byId('execution-result').textContent = 'Waiting for model understanding.';
  byId('execution-result').className = 'empty-result';
  byId('execution-marker').className = 'step-number';
  byId('execution-marker').textContent = '3';
  setVoiceState('processing', 'Passing your words to the trained language model.');
  try {
    const interpreted = await post('/api/interpret', { text, source });
    renderPrediction(interpreted.prediction);
    if (interpreted.requires_confirmation === false) {
      await applyCommand(interpreted.command_id, 'Applying the command.');
      return;
    }
    byId('confirmation-question').textContent = confirmationQuestion(interpreted.prediction);
    byId('confirmation-transcript').textContent = `${source === 'voice' ? 'You said' : 'You typed'} “${text}”`;
    confirmation.showModal();
    pendingCommand = { id: interpreted.command_id, source };
    byId('execution-result').textContent = 'Waiting for your confirmation.';
    setVoiceState('confirming');
  } catch (error) {
    showError(error.message, error.data);
  } finally {
    busy = false;
    availability();
  }
}

function takePendingCommand() {
  const command = pendingCommand;
  pendingCommand = null;
  confirmation.close();
  return command;
}

function focusCommandInput(source) {
  const input = byId(source === 'voice' ? 'microphone' : 'command-input');
  if (!input.disabled) input.focus({ preventScroll: true });
}

async function applyCommand(id, progressMessage) {
  byId('execution-result').textContent = progressMessage;
  byId('execution-result').className = 'empty-result';
  setVoiceState('executing', 'Applying the command to your bedroom.');
  const result = await post('/api/execute', { command_id: id });
  renderBedroom(result);
  execution(result.message, result.execution.success);
  setVoiceState('completed');
  toast(result.message);
}

async function confirmCommand() {
  if (busy || !online || !pendingCommand) return;
  const { id, source } = takePendingCommand();
  busy = true;
  try {
    await applyCommand(id, 'Applying the confirmed command.');
  } catch (error) {
    showError(error.message, error.data);
  } finally {
    busy = false;
    availability();
    focusCommandInput(source);
  }
}

function cancelCommand() {
  if (!pendingCommand) return;
  const { source } = takePendingCommand();
  byId('execution-result').textContent = 'Command canceled.';
  byId('execution-result').className = 'empty-result';
  setVoiceState('idle');
  focusCommandInput(source);
}

const voice = new VoiceController({
  onState: setVoiceState,
  onTranscript: (text) => transcript(text, 'voice'),
  onCommand: (text) => runCommand(text, 'voice'),
  onError: (message) => showError(message),
});

byId('microphone').addEventListener('click', () => voice.toggle());
byId('confirm-command').addEventListener('click', confirmCommand);
byId('cancel-command').addEventListener('click', cancelCommand);
confirmation.addEventListener('cancel', (event) => {
  event.preventDefault();
  cancelCommand();
});
byId('command-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const text = byId('command-input').value.trim();
  if (!busy && !pendingCommand && online && text) runCommand(text);
});

async function manual(command) {
  if (busy || pendingCommand || !online) return;
  busy = true;
  transcript(`${command.intent} · ${command.device}${command.value != null ? ` · ${command.value}°C` : ''}`, 'text');
  byId('transcript-heading').textContent = 'Manual control';
  renderPrediction(null);
  byId('prediction').firstChild.textContent = 'Manual control · model not used';
  setVoiceState('executing', 'Applying your manual adjustment.');
  try {
    const result = await post('/api/control', command);
    renderBedroom(result);
    execution(result.message, result.execution.success);
    toast(result.message);
    busy = false;
    setVoiceState('completed');
  } catch (error) {
    showError(error.message, error.data);
  } finally {
    busy = false;
    availability();
  }
}

byId('device-controls').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-device]');
  if (!button || button.disabled) return;
  manual({ device: button.dataset.device, intent: button.dataset.intent, value: null });
});
byId('ac-temperature').addEventListener('change', (event) => {
  const input = event.target;
  if (!input.value || !input.checkValidity()) {
    toast(`Choose a whole-number temperature between ${input.min}°C and ${input.max}°C.`, true);
    input.value = input.dataset.savedTemperature;
    return;
  }
  manual({ device: 'AC', intent: 'SetTemp', value: Number(input.value) });
});
byId('ac-temperature').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') event.target.blur();
});

function connection(connected) {
  online = connected;
  const status = byId('connection-status');
  status.dataset.online = String(connected);
  status.lastChild.textContent = connected ? 'Room connected' : 'Server offline';
  availability();
}

async function connect() {
  const [health, state] = await Promise.all([api('/api/health'), api('/api/state')]);
  renderBedroom(state);
  voiceAvailable = voice.configure(health.speech);
  byId('speech-engine').textContent = voice.description;
  const notice = byId('model-notice');
  notice.hidden = health.model.ready;
  byId('model-notice-text').textContent = health.model.ready ? '' : 'The trained language model is not connected. Voice and text commands cannot control devices yet. Manual controls are ready.';
  connection(true);
  if (!busy && !pendingCommand) setVoiceState('idle');
}

async function poll() {
  if (polling || document.hidden || busy) return;
  polling = true;
  try {
    if (!online) await connect();
    else renderBedroom(await api('/api/state'));
  } catch {
    connection(false);
  } finally {
    polling = false;
  }
}

function updateClock() {
  const clock = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Thimphu', hour: 'numeric', minute: '2-digit' }).format(new Date());
  byId('local-time').textContent = `${clock} · Thimphu`;
}
updateClock();
const clockInterval = setInterval(updateClock, 30000);
connect().catch((error) => {
  connection(false);
  setVoiceState('error', 'Start the Python server and reload, or wait for reconnection.');
  toast(error.message, true);
});
const pollInterval = setInterval(poll, 4000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
window.addEventListener('pagehide', () => {
  clearInterval(clockInterval);
  clearInterval(pollInterval);
  voice.dispose();
});
