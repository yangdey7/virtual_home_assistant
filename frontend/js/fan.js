// Visual inertia is independent of the controller's authoritative ON/OFF state.
export class FanMotion {
  constructor(rotor, room, onMotionChange) {
    this.rotor = rotor;
    this.room = room;
    this.onMotionChange = onMotionChange;
    this.angle = 0;
    this.velocity = 0;
    this.target = 0;
    this.frame = null;
    this.transition = null;
    this.on = false;
    this.level = 1;
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    this.tick = this.tick.bind(this);
    this.preferenceChanged = () => this.setState(this.on, this.level, true);
    this.reducedMotion.addEventListener('change', this.preferenceChanged);
    window.addEventListener('pagehide', () => this.dispose(), { once: true });
  }

  setMotion(motion) {
    if (this.room.dataset.fanMotion === motion) return;
    this.room.dataset.fanMotion = motion;
    this.onMotionChange(motion);
  }

  setState(on, level, force = false) {
    this.on = on;
    this.level = level;
    const target = on ? 200 * (2 ** (level - 1)) : 0;
    if (this.reducedMotion.matches) {
      this.cancel();
      this.velocity = 0;
      this.target = 0;
      this.setMotion(on ? 'running' : 'stopped');
      return;
    }
    // Polls and unrelated device actions must not restart a deceleration.
    if (!force && target === this.target) {
      if (target === 0 && this.frame === null) this.setMotion('stopped');
      return;
    }
    this.target = target;
    if (target === 0 && this.velocity === 0) {
      this.cancel();
      this.setMotion('stopped');
      return;
    }
    const now = performance.now();
    this.transition = {
      start: now,
      from: this.velocity,
      to: target,
      // Higher speeds retain more momentum; stopping takes about 3–5 seconds.
      duration: target === 0 ? 3200 + this.velocity * 2 : this.velocity === 0 ? 900 : 650,
    };
    this.setMotion(target === 0 ? 'slowing' : 'running');
    if (this.frame === null) {
      this.lastFrame = now;
      this.frame = requestAnimationFrame(this.tick);
    }
  }

  tick(now) {
    const elapsed = Math.max(0, Math.min(now - this.lastFrame, 64)) / 1000;
    this.lastFrame = now;
    const previousVelocity = this.velocity;
    if (this.transition) {
      const progress = Math.min(1, (now - this.transition.start) / this.transition.duration);
      const eased = progress * progress * (3 - 2 * progress);
      this.velocity = this.transition.from + (this.transition.to - this.transition.from) * eased;
      if (progress >= 1) {
        this.velocity = this.transition.to;
        this.transition = null;
      }
    }
    this.angle = (this.angle + (previousVelocity + this.velocity) * .5 * elapsed) % 360;
    this.rotor.style.transform = `rotate(${this.angle}deg)`;
    if (this.velocity === 0 && !this.transition) {
      this.frame = null;
      this.setMotion('stopped');
      return;
    }
    this.frame = requestAnimationFrame(this.tick);
  }

  cancel() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.transition = null;
  }

  dispose() {
    this.cancel();
    this.reducedMotion.removeEventListener('change', this.preferenceChanged);
  }
}
