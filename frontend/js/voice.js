import { api } from './api.js';

const SPEECH_ERRORS = {
  'not-allowed': 'Microphone permission was denied. Allow microphone access in your browser settings, or type your command.',
  'service-not-allowed': 'Your browser blocked its speech service. Try another supported browser or type your command.',
  'audio-capture': 'No microphone is available. Connect a microphone or type your command.',
  'no-speech': 'No speech was detected. Tap the microphone and try again.',
  network: 'The browser speech service could not connect. Check your connection or type your command.',
  'language-not-supported': 'This speech language is unavailable. Try English or type your command.',
};

export class VoiceController {
  constructor({ onState, onTranscript, onCommand, onError }) {
    Object.assign(this, { onState, onTranscript, onCommand, onError });
    this.active = false;
    this.mode = null;
    this.timer = null;
    this.stream = null;
    this.recorder = null;
    this.recognition = null;
  }

  configure(speech) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (speech?.ready && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
      this.mode = 'whisper';
      this.description = 'Local Whisper · English and code-mixed accuracy varies. Dzongkha support is not guaranteed.';
    } else if (Recognition) {
      this.mode = 'browser';
      this.Recognition = Recognition;
      this.description = 'Browser speech · may use an online service. English and code-mixed accuracy varies; full Dzongkha support is not available.';
    } else {
      this.mode = null;
      this.description = 'Speech input is unavailable in this browser. Type your command or use the manual controls.';
    }
    return Boolean(this.mode);
  }

  async toggle() {
    if (this.active) return this.stop();
    if (!this.mode) return;
    this.active = true;
    this.onState('listening', 'Speak now. Tap again to finish.');
    if (this.mode === 'whisper') await this.recordWhisper();
    else this.recordBrowser();
  }

  stop() {
    clearTimeout(this.timer);
    if (this.recorder?.state === 'recording') this.recorder.stop();
    else if (this.recognition) this.recognition.stop();
    else {
      this.active = false;
      this.onState('idle');
    }
  }

  recordBrowser() {
    const recognition = new this.Recognition();
    this.recognition = recognition;
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    let delivered = false;
    let failed = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((result) => result[0].transcript).join(' ').trim();
      this.onTranscript(transcript);
      if (Array.from(event.results).some((result) => result.isFinal) && !delivered) {
        delivered = true;
        clearTimeout(this.timer);
        this.active = false;
        this.onCommand(transcript);
      }
    };
    recognition.onerror = (event) => {
      failed = true;
      this.active = false;
      clearTimeout(this.timer);
      if (!delivered) this.onError(SPEECH_ERRORS[event.error] || 'Speech recognition failed. Please try again or type your command.');
    };
    recognition.onend = () => {
      this.active = false;
      this.recognition = null;
      clearTimeout(this.timer);
      if (!delivered && !failed) this.onError(SPEECH_ERRORS['no-speech']);
    };
    try {
      recognition.start();
      this.timer = setTimeout(() => recognition.stop(), 15000);
    } catch {
      this.active = false;
      this.recognition = null;
      this.onError('Could not start speech recognition. Please try again or type your command.');
    }
  }

  async recordWhisper() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.stream = stream;
      if (!this.active) {
        this.releaseMicrophone();
        return;
      }
      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      this.recorder = recorder;
      const chunks = [];
      let failed = false;
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => {
        failed = true;
        this.active = false;
        clearTimeout(this.timer);
        this.releaseMicrophone();
        this.onError('The microphone recording failed. Please try again or type your command.');
      };
      recorder.onstop = async () => {
        this.active = false;
        this.recorder = null;
        clearTimeout(this.timer);
        this.releaseMicrophone();
        if (failed) return;
        if (!chunks.length) return this.onError(SPEECH_ERRORS['no-speech']);
        this.onState('processing', 'Transcribing your recording with local Whisper…');
        const data = new FormData();
        data.append('audio', new Blob(chunks, { type: recorder.mimeType }), 'command.audio');
        try {
          const result = await api('/api/transcribe', { method: 'POST', body: data });
          this.onTranscript(result.text);
          await this.onCommand(result.text);
        } catch (error) {
          this.onError(error.message);
        }
      };
      recorder.start(250);
      this.timer = setTimeout(() => this.stop(), 15000);
    } catch (error) {
      this.active = false;
      this.releaseMicrophone();
      this.onError(error.name === 'NotAllowedError' ? SPEECH_ERRORS['not-allowed'] : error.name === 'NotFoundError' ? SPEECH_ERRORS['audio-capture'] : 'Could not access the microphone. Please try again or type your command.');
    }
  }

  releaseMicrophone() {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  dispose() {
    clearTimeout(this.timer);
    this.active = false;
    if (this.recognition) {
      this.recognition.onend = null;
      this.recognition.onerror = null;
      this.recognition.abort();
    }
    if (this.recorder) {
      this.recorder.onstop = null;
      if (this.recorder.state === 'recording') this.recorder.stop();
    }
    this.releaseMicrophone();
  }
}

