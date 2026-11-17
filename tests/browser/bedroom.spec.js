import { test, expect } from '@playwright/test';

const button = (page, device, intent) => page.locator(`button[data-device="${device}"][data-intent="${intent}"]`);

async function ready(page) {
  await page.goto('/');
  await expect(page.locator('#connection-status')).toHaveAttribute('data-online', 'true');
}

async function predict(request, command) {
  await request.post('/__test__/prediction', { data: { ...command, confidence: command.confidence ?? .99 } });
}

async function speechFixture(page, behavior) {
  await page.addInitScript((behavior) => {
    window.SpeechRecognition = class {
      start() {
        this.timer = setTimeout(() => {
          if (behavior.error) this.onerror?.({ error: behavior.error });
          else if (!behavior.noSpeech) {
            const result = [{ transcript: behavior.text || 'Fan on bay nang.' }];
            result.isFinal = true;
            this.onresult?.({ results: [result] });
          }
          this.onend?.();
        }, 100);
      }
      stop() { clearTimeout(this.timer); this.onend?.(); }
      abort() { clearTimeout(this.timer); }
    };
  }, behavior);
}

test('all manual actions update the real backend and bedroom objects', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await ready(page);
  const room = page.locator('#bedroom');
  await expect(page.locator('#ac-scene-temp')).toHaveText('24°C');
  await expect(page.locator('#ac-scene-status')).toHaveText('OFF');
  await room.screenshot({ path: 'test-results/room-daylight-closed-v2.png' });
  await button(page, 'Light', 'TurnOn').click();
  await expect(room).toHaveAttribute('data-light', 'ON');
  await expect(page.locator('.light-glow')).toHaveCSS('opacity', '1');
  await room.screenshot({ path: 'test-results/room-warm-closed-v2.png' });
  await button(page, 'Light', 'TurnOff').click();
  await expect(room).toHaveAttribute('data-light', 'OFF');
  await expect(page.locator('.light-glow')).toHaveCSS('opacity', '0');

  await expect(button(page, 'Fan', 'IncreaseSpeed')).toBeDisabled();
  await button(page, 'Fan', 'TurnOn').click();
  await expect(room).toHaveAttribute('data-fan', 'ON');
  await expect(page.locator('.fan-rotor')).toHaveCSS('animation-play-state', 'running');
  await button(page, 'Fan', 'IncreaseSpeed').click();
  await expect(page.locator('#fan-speed')).toHaveText('Level 2');
  await button(page, 'Fan', 'IncreaseSpeed').click();
  await expect(page.locator('#fan-speed')).toHaveText('Level 3');
  await expect(button(page, 'Fan', 'IncreaseSpeed')).toBeDisabled();
  await button(page, 'Fan', 'DecreaseSpeed').click();
  await button(page, 'Fan', 'DecreaseSpeed').click();
  await expect(page.locator('#fan-speed')).toHaveText('Level 1');
  await expect(button(page, 'Fan', 'DecreaseSpeed')).toBeDisabled();
  await button(page, 'Fan', 'TurnOff').click();
  await expect(page.locator('.fan-rotor')).toHaveCSS('animation-play-state', 'paused');

  await button(page, 'AC', 'TurnOn').click();
  await expect(room).toHaveAttribute('data-ac', 'ON');
  await expect(page.locator('#ac-scene-status')).toHaveText('COOLING');
  await button(page, 'AC', 'IncreaseTemp').click();
  await expect(page.locator('#ac-temperature')).toHaveValue('25');
  await button(page, 'AC', 'DecreaseTemp').click();
  await expect(page.locator('#ac-temperature')).toHaveValue('24');
  await page.locator('#ac-temperature').fill('22');
  await page.locator('#ac-temperature').press('Enter');
  await expect(page.locator('#ac-scene-temp')).toHaveText('22°C');
  await button(page, 'AC', 'TurnOff').click();
  await expect(page.locator('#ac-scene-temp')).toHaveText('22°C');
  await expect(page.locator('#ac-scene-status')).toHaveText('OFF');
  await expect(page.locator('#ac-temperature')).toHaveValue('22');
  await button(page, 'AC', 'IncreaseTemp').click();
  await expect(page.locator('#ac-scene-temp')).toHaveText('23°C');
  await expect(room).toHaveAttribute('data-ac', 'OFF');
  await button(page, 'AC', 'DecreaseTemp').click();
  await expect(page.locator('#ac-scene-temp')).toHaveText('22°C');

  await button(page, 'Curtain', 'Open').click();
  await expect(room).toHaveAttribute('data-curtain', 'OPEN');
  await expect(page.locator('.daylight')).toHaveCSS('opacity', '1');
  await expect(page.locator('.curtain-left')).toHaveCSS('transform', 'matrix(0.18, 0, 0, 1, 0, 0)');
  await expect(page.locator('.curtain-left')).toHaveCSS('opacity', '0');
  await room.screenshot({ path: 'test-results/room-daylight-open-v2.png' });
  await button(page, 'Curtain', 'Close').click();
  await expect(room).toHaveAttribute('data-curtain', 'CLOSED');
  await expect(page.locator('#history-list .history-entry').first()).toContainText('Successful');
  expect(errors).toEqual([]);
});

test('prediction is displayed before execution, and confirmation waits for the controller', async ({ page, request }) => {
  await predict(request, { intent: 'TurnOn', device: 'Fan', value: null });
  await ready(page);
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  await page.route('**/api/execute', async (route) => { await gate; await route.continue(); });
  await page.locator('#command-input').fill('Fan on bay nang.');
  await page.locator('#send-command').click();
  await expect(page.locator('#prediction')).toContainText('Intent: TurnOn');
  await expect(page.locator('#voice-label')).toHaveText('Adjusting your room…');
  await expect(page.locator('#execution-result')).toHaveText('Waiting for model understanding.');
  release();
  await expect(page.locator('#execution-result')).toHaveText('Bedroom fan has been switched on.');
  await expect(page.locator('#bedroom')).toHaveAttribute('data-fan', 'ON');
  await expect(page.locator('#transcript-heading')).toHaveText('Typed command');
});

test('recognized speech reaches the same model adapter and controller', async ({ page, request }) => {
  await predict(request, { intent: 'Open', device: 'Curtain' });
  await speechFixture(page, { text: 'Open the curtains' });
  await ready(page);
  await page.locator('#microphone').click();
  await expect(page.locator('#transcript')).toHaveText('Open the curtains');
  await expect(page.locator('#transcript-heading')).toHaveText('Speech recognition output');
  await expect(page.locator('#bedroom')).toHaveAttribute('data-curtain', 'OPEN');
  await expect(page.locator('#execution-result')).toHaveText('Bedroom curtains are open.');
  await expect(page.locator('#history-list .history-entry').first()).toContainText('Voice command');
});

for (const [behavior, message] of [
  [{ error: 'not-allowed' }, 'Microphone permission was denied'],
  [{ noSpeech: true }, 'No speech was detected'],
  [{ error: 'network' }, 'browser speech service could not connect'],
]) {
  test(`speech error: ${message}`, async ({ page }) => {
    await speechFixture(page, behavior);
    await ready(page);
    await page.locator('#microphone').click();
    await expect(page.locator('#execution-result')).toContainText(message);
    await expect(page.locator('#microphone')).toBeEnabled();
    await expect(page.locator('#command-input')).toBeEnabled();
  });
}

test('low confidence preserves the room and displays clarification', async ({ page, request }) => {
  await predict(request, { intent: 'TurnOn', device: 'Light', confidence: .2 });
  await ready(page);
  const before = await page.locator('#bedroom').getAttribute('data-light');
  await page.locator('#command-input').fill('Maybe do something');
  await page.locator('#send-command').click();
  await expect(page.locator('#execution-result')).toContainText('not confident');
  await expect(page.locator('#prediction')).toContainText('20% confidence');
  await expect(page.locator('#bedroom')).toHaveAttribute('data-light', before);
  await expect(page.locator('#history-list .history-entry').first()).toContainText('Not executed');
});

test('invalid inferred commands display controller errors without success', async ({ page, request }) => {
  await predict(request, { intent: 'SetTemp', device: 'AC', value: null });
  await ready(page);
  await page.locator('#command-input').fill('Set the temperature');
  await page.locator('#send-command').click();
  await expect(page.locator('#execution-result')).toContainText('whole-number temperature');
  await expect(page.locator('#execution-marker')).toHaveClass('step-number error');
  await expect(page.locator('#prediction')).toContainText('Intent: SetTemp');
});

test('room recovers from a backend failure', async ({ page }) => {
  await ready(page);
  await page.route('**/api/control', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Bedroom service is unavailable.', execution: { success: false } }) }));
  await button(page, 'Light', 'TurnOn').click();
  await expect(page.locator('#execution-result')).toHaveText('Bedroom service is unavailable.');
  await expect(button(page, 'Light', 'TurnOn')).toBeEnabled();
  await page.unroute('**/api/control');
  await button(page, 'Light', 'TurnOn').click();
  await expect(page.locator('#bedroom')).toHaveAttribute('data-light', 'ON');
});

test('missing-model notice and typed-command failure are explicit', async ({ page, request }) => {
  const state = await (await request.get('/api/state')).json();
  await page.route('**/api/health', async (route) => {
    const response = await route.fetch();
    const health = await response.json();
    health.model.ready = false;
    await route.fulfill({ json: health });
  });
  await page.route('**/api/interpret', (route) => route.fulfill({ status: 503, json: { ...state, error: 'model_not_configured', message: 'Trained model not connected.', execution: { success: false } } }));
  await ready(page);
  await expect(page.locator('#model-notice')).toContainText('Manual controls are ready');
  await page.locator('#command-input').fill('Turn on the fan');
  await page.locator('#send-command').click();
  await expect(page.locator('#execution-result')).toHaveText('Trained model not connected.');
  await expect(button(page, 'Light', 'TurnOn')).toBeEnabled();
});

test('desktop and mobile layouts fit, preserve keyboard controls, and respect reduced motion', async ({ page }) => {
  await ready(page);
  await expect(page.locator('.light-glow')).toHaveCSS('opacity', '1');
  await expect(page.locator('.curtain-left')).toHaveCSS('opacity', '0');
  await page.screenshot({ path: 'test-results/bedroom-desktop.png', fullPage: true });
  for (const width of [320, 390, 740, 900, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/bedroom-mobile.png', fullPage: true });
  await button(page, 'Light', 'TurnOn').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#bedroom')).toHaveAttribute('data-light', 'ON');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(page.locator('.fan-rotor')).toHaveCSS('animation-name', 'none');
});
