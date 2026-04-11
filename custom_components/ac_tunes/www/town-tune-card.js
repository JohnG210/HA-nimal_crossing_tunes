/**
 * Town Tune Card for Animal Crossing Tunes
 *
 * A custom Lovelace card that reproduces the AC Music Extension's
 * town tune editor with a musical staff display, vertical sliders,
 * and colored note labels.
 *
 * Config:
 *   type: custom:town-tune-card
 *   entity: switch.auto_play   (optional, defaults to this)
 */

const PITCHES = [
  "z", "-",
  "g", "a", "b", "c", "d", "e", "f",
  "G", "A", "B", "C", "D", "E", "F",
];

// Display labels — lower octave gets subscript, upper gets superscript (handled in rendering)
const PITCH_LABELS = {
  z: "♩", "-": "–",
  g: "G", a: "A", b: "B", c: "C", d: "D", e: "E", f: "F",
  G: "G", A: "A", B: "B", C: "C", D: "D", E: "E", F: "F",
};

const PITCH_COLORS = [
  "#9E9EBB", "#C8A0C8",
  "#52D3FE", "#12FEE0", "#53FD8A", "#79FC4E", "#A8FD35", "#D0FE47", "#E4FD39",
  "#F9FE2E", "#FEFA43", "#FEF03F", "#FCD03A", "#FCB141", "#FE912E", "#FE7929",
];

// Softer versions for the staff note dots
const PITCH_COLORS_SOFT = [
  "#B0B0CC", "#D4B0D4",
  "#7FDDFE", "#5FFEE8", "#80FEA8", "#99FD78", "#BCFE6A", "#DCFE78", "#EAFE6C",
  "#FBFE6A", "#FEFB74", "#FEF470", "#FDD86C", "#FDC472", "#FEA96A", "#FE9468",
];

// Frequencies for Web Audio preview (matches town_tune.py)
const PITCH_FREQ = {
  z: 0, "-": 0,
  g: 196.00, a: 220.00, b: 246.94, c: 261.63, d: 293.66, e: 329.63, f: 349.23,
  G: 392.00, A: 440.00, B: 493.88, C: 523.25, D: 587.33, E: 659.25, F: 698.46,
};

const DEFAULT_TUNE = ["C","C","C","E","D","D","D","F","E","E","D","D","C","-","z","z"];

// Staff row labels — bottom to top (index 0 = bottom of staff)
const STAFF_NOTES = ["g","a","b","c","d","e","f","G","A","B","C","D","E","F"];
const STAFF_LABELS = ["G₃","A₃","B₃","C₄","D₄","E₄","F₄","G₄","A₄","B₄","C₅","D₅","E₅","F₅"];

class TownTuneCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tune = [...DEFAULT_TUNE];
    this._playing = false;
    this._audioCtx = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) return;

    // Sync tune from entity attribute whenever it changes
    const entity = this._config.entity || "switch.auto_play";
    const state = hass.states[entity];
    if (state && state.attributes.town_tune) {
      const incoming = JSON.stringify(state.attributes.town_tune);
      if (incoming !== this._lastKnownTune) {
        this._lastKnownTune = incoming;
        this._tune = [...state.attributes.town_tune];
        this._updateAllSliders();
        this._updateStaff();
      }
    }
  }

  setConfig(config) {
    this._config = config;
    this._render();
    this._initialized = true;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${this._getStyles()}</style>
      <div class="card">
        <div class="header">
          <img class="leaf-icon" src="/local/ac_tunes/leaf.png" alt="">
          <div>
            <div class="title">Town Tune Editor</div>
            <div class="subtitle">Compose a 16-note melody played at the top of each hour</div>
          </div>
        </div>

        <div class="staff-container">
          <div class="staff-labels" id="staff-labels"></div>
          <div class="staff-grid" id="staff-grid"></div>
        </div>

        <div class="editor-section">
          <div class="measure" id="measure1"></div>
          <div class="measure-divider">
            <div class="bar-line"></div>
          </div>
          <div class="measure" id="measure2"></div>
        </div>

        <div class="controls">
          <button class="btn btn-icon" id="btn-play" title="Play">
            <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>
            Play
          </button>
          <button class="btn" id="btn-reset">Reset</button>
          <button class="btn" id="btn-random">Randomize</button>
          <button class="btn btn-primary" id="btn-save">
            <svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg>
            Save
          </button>
        </div>
        <div class="save-status" id="save-status"></div>
      </div>
    `;

    this._buildStaff();
    this._buildEditor();
    this._updateAllSliders();
    this._updateStaff();

    this.shadowRoot.getElementById("btn-play").addEventListener("click", () => this._playTune());
    this.shadowRoot.getElementById("btn-reset").addEventListener("click", () => this._resetTune());
    this.shadowRoot.getElementById("btn-random").addEventListener("click", () => this._randomizeTune());
    this.shadowRoot.getElementById("btn-save").addEventListener("click", () => this._saveTune());
  }

  _getStyles() {
    return `
      :host { display: block; }

      .card {
        padding: 16px;
        background: var(--ha-card-background, var(--card-background-color, white));
        border-radius: var(--ha-card-border-radius, 12px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
        overflow: hidden;
      }

      /* Header */
      .header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
      }
      .leaf-icon {
        width: 40px;
        height: 40px;
        border-radius: 8px;
      }
      .title {
        font-size: 18px;
        font-weight: 600;
        color: var(--primary-text-color);
        line-height: 1.2;
      }
      .subtitle {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      /* Staff display */
      .staff-container {
        display: flex;
        gap: 4px;
        margin-bottom: 16px;
        overflow-x: auto;
      }
      .staff-labels {
        display: flex;
        flex-direction: column-reverse;
        gap: 0;
        padding-top: 1px;
      }
      .staff-label {
        height: 16px;
        line-height: 16px;
        font-size: 9px;
        color: var(--secondary-text-color);
        text-align: right;
        padding-right: 4px;
        white-space: nowrap;
        font-family: monospace;
      }
      .staff-grid {
        flex: 1;
        position: relative;
        min-height: ${STAFF_NOTES.length * 16}px;
      }
      .staff-row {
        position: absolute;
        left: 0;
        right: 0;
        height: 16px;
        border-bottom: 1px solid var(--divider-color, rgba(0,0,0,.08));
        box-sizing: border-box;
      }
      .staff-row:nth-child(7) {
        border-bottom: 2px solid var(--divider-color, rgba(0,0,0,.15));
      }
      .staff-row.line {
        border-bottom-color: var(--divider-color, rgba(0,0,0,.18));
      }
      .staff-col-marker {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 1px;
        background: var(--divider-color, rgba(0,0,0,.05));
      }
      .staff-bar-line {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 2px;
        background: var(--divider-color, rgba(0,0,0,.2));
      }
      .note-dot {
        position: absolute;
        width: 20px;
        height: 14px;
        border-radius: 50%;
        transform: translate(-50%, 1px);
        transition: all 0.15s ease;
        border: 2px solid rgba(0,0,0,.15);
        box-sizing: border-box;
      }
      .note-dot.rest-dot, .note-dot.sustain-dot {
        width: 16px;
        height: 16px;
        border-radius: 4px;
        opacity: 0.5;
        border-style: dashed;
        transform: translate(-50%, 0);
      }
      .note-dot.flash-dot {
        transform: translate(-50%, 1px) scale(1.4);
        box-shadow: 0 0 8px rgba(255,255,255,.8);
      }
      .note-text {
        position: absolute;
        transform: translate(-50%, 0);
        font-size: 8px;
        font-weight: 700;
        color: rgba(0,0,0,.5);
        text-align: center;
        pointer-events: none;
        width: 20px;
        line-height: 14px;
      }

      /* Editor sliders */
      .editor-section {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        gap: 0;
        margin-bottom: 4px;
        flex-wrap: wrap;
      }
      .measure {
        display: flex;
        gap: 2px;
        flex: 1;
        justify-content: center;
      }
      .measure-divider {
        display: flex;
        align-items: center;
        padding: 0 4px;
      }
      .bar-line {
        width: 2px;
        height: 100px;
        background: var(--divider-color, #ccc);
        border-radius: 1px;
      }

      .pitch {
        display: flex;
        flex-direction: column;
        align-items: center;
        width: calc((100% - 16px) / 8);
        min-width: 24px;
        max-width: 36px;
      }
      .pitch-name {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 2px solid transparent;
        text-align: center;
        line-height: 28px;
        font-size: 12px;
        font-weight: 700;
        cursor: default;
        transition: transform 0.12s, border-color 0.12s;
        color: #333;
        user-select: none;
        margin-bottom: 2px;
      }
      .pitch-name.flash {
        transform: scale(1.3) rotate(8deg);
        border-color: #fff !important;
        box-shadow: 0 0 8px rgba(255,255,255,.6);
      }
      .pitch-name.flash-sustain {
        transform: scale(1.15) translateX(-2px) rotate(-12deg);
        border-color: #fff !important;
      }
      .octave-label {
        font-size: 8px;
        color: var(--secondary-text-color);
        height: 10px;
        line-height: 10px;
        margin-bottom: 2px;
      }

      .slider-wrap {
        height: 70px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .pitch-slider {
        -webkit-appearance: none;
        appearance: none;
        writing-mode: vertical-lr;
        direction: rtl;
        width: 3px;
        height: 62px;
        background: var(--divider-color, #ddd);
        border-radius: 2px;
        outline: none;
      }
      .pitch-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 16px;
        height: 16px;
        background: var(--primary-color, #03a9f4);
        border-radius: 50%;
        cursor: pointer;
        border: 2px solid rgba(255,255,255,.8);
        box-shadow: 0 1px 3px rgba(0,0,0,.3);
      }
      .pitch-slider::-moz-range-thumb {
        width: 16px;
        height: 16px;
        background: var(--primary-color, #03a9f4);
        border-radius: 50%;
        cursor: pointer;
        border: 2px solid rgba(255,255,255,.8);
        box-shadow: 0 1px 3px rgba(0,0,0,.3);
      }

      /* Controls */
      .controls {
        display: flex;
        justify-content: center;
        gap: 8px;
        margin-top: 12px;
        flex-wrap: wrap;
      }
      .btn {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 8px 14px;
        border-radius: 20px;
        border: 1px solid var(--divider-color, #ddd);
        background: var(--card-background-color, white);
        color: var(--primary-text-color);
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
        transition: background 0.15s, transform 0.1s;
      }
      .btn:hover { background: var(--secondary-background-color, #f0f0f0); }
      .btn:active { transform: scale(0.97); }
      .btn:disabled { opacity: 0.5; cursor: default; transform: none; }
      .btn-primary {
        background: #7fbb5e;
        color: white;
        border-color: #6aa34d;
      }
      .btn-primary:hover { background: #6fad4e; }
      .save-status {
        font-size: 12px;
        color: var(--secondary-text-color);
        text-align: center;
        margin-top: 6px;
        min-height: 16px;
      }
    `;
  }

  _buildStaff() {
    const labels = this.shadowRoot.getElementById("staff-labels");
    const grid = this.shadowRoot.getElementById("staff-grid");

    // Row labels (pitch names on the left)
    for (let r = 0; r < STAFF_NOTES.length; r++) {
      const lbl = document.createElement("div");
      lbl.className = "staff-label";
      lbl.textContent = STAFF_LABELS[r];
      labels.appendChild(lbl);
    }

    // Horizontal staff lines and column guides
    const totalH = STAFF_NOTES.length * 16;
    for (let r = 0; r < STAFF_NOTES.length; r++) {
      const row = document.createElement("div");
      row.className = "staff-row";
      // Lines on C and E positions for visual reference (like treble clef lines)
      if (["c","e","G","B","D"].includes(STAFF_NOTES[r])) {
        row.classList.add("line");
      }
      row.style.bottom = `${r * 16}px`;
      grid.appendChild(row);
    }

    // Column guides + bar line at measure boundary
    const colWidth = 100 / 16;
    for (let c = 0; c < 16; c++) {
      if (c === 8) {
        const bar = document.createElement("div");
        bar.className = "staff-bar-line";
        bar.style.left = `${c * colWidth}%`;
        grid.appendChild(bar);
      }
    }
  }

  _updateStaff() {
    const grid = this.shadowRoot.getElementById("staff-grid");
    if (!grid) return;

    // Remove old dots
    grid.querySelectorAll(".note-dot, .note-text").forEach(el => el.remove());

    const colWidth = 100 / 16;

    for (let i = 0; i < 16; i++) {
      const note = this._tune[i];
      const pitchIdx = PITCHES.indexOf(note);
      const staffIdx = STAFF_NOTES.indexOf(note);
      const x = (i + 0.5) * colWidth;

      const dot = document.createElement("div");
      dot.className = "note-dot";
      dot.id = `dot-${i}`;

      if (staffIdx >= 0) {
        // Real note — position on staff
        const y = (STAFF_NOTES.length - 1 - staffIdx) * 16;
        dot.style.left = `${x}%`;
        dot.style.top = `${y}px`;
        dot.style.background = PITCH_COLORS[pitchIdx];
      } else {
        // Rest or sustain — show at bottom
        dot.style.left = `${x}%`;
        dot.style.top = `${(STAFF_NOTES.length - 1) * 16}px`;
        dot.style.background = PITCH_COLORS[pitchIdx] || "#aaa";
        dot.classList.add(note === "-" ? "sustain-dot" : "rest-dot");
      }
      grid.appendChild(dot);

      // Small label inside dot
      const txt = document.createElement("div");
      txt.className = "note-text";
      txt.id = `dot-text-${i}`;
      txt.style.left = `${x}%`;
      txt.style.top = dot.style.top;
      txt.textContent = note === "z" ? "R" : note === "-" ? "–" : "";
      grid.appendChild(txt);
    }
  }

  _buildEditor() {
    const m1 = this.shadowRoot.getElementById("measure1");
    const m2 = this.shadowRoot.getElementById("measure2");
    for (let i = 0; i < 16; i++) {
      const target = i < 8 ? m1 : m2;
      target.appendChild(this._createPitchControl(i));
    }
  }

  _createPitchControl(index) {
    const pitch = document.createElement("div");
    pitch.className = "pitch";

    const name = document.createElement("div");
    name.className = "pitch-name";
    name.id = `name-${index}`;

    const octave = document.createElement("div");
    octave.className = "octave-label";
    octave.id = `octave-${index}`;

    const sliderWrap = document.createElement("div");
    sliderWrap.className = "slider-wrap";

    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "pitch-slider";
    slider.id = `slider-${index}`;
    slider.min = 0;
    slider.max = PITCHES.length - 1;
    slider.step = 1;
    slider.value = PITCHES.indexOf(this._tune[index]);

    slider.addEventListener("input", () => {
      const val = PITCHES[slider.value];
      this._tune[index] = val;
      this._updateNote(index);
      this._updateStaff();
      this._previewNote(val);
    });

    sliderWrap.appendChild(slider);
    pitch.appendChild(name);
    pitch.appendChild(octave);
    pitch.appendChild(sliderWrap);

    return pitch;
  }

  _updateNote(index) {
    const note = this._tune[index];
    const pitchIdx = PITCHES.indexOf(note);
    const name = this.shadowRoot.getElementById(`name-${index}`);
    const octave = this.shadowRoot.getElementById(`octave-${index}`);
    if (!name) return;

    name.textContent = PITCH_LABELS[note] || note;
    name.style.background = PITCH_COLORS[pitchIdx] || "#eee";

    if (note === "z" || note === "-") {
      octave.textContent = note === "z" ? "rest" : "hold";
    } else if (note === note.toLowerCase()) {
      octave.textContent = "low";
    } else {
      octave.textContent = "high";
    }
  }

  _updateAllSliders() {
    for (let i = 0; i < 16; i++) {
      const slider = this.shadowRoot.getElementById(`slider-${i}`);
      if (slider) {
        slider.value = PITCHES.indexOf(this._tune[i]);
        this._updateNote(i);
      }
    }
  }

  _previewNote(note) {
    const freq = PITCH_FREQ[note];
    if (!freq) return;
    if (!this._audioCtx) {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    this._playBell(this._audioCtx, freq);
  }

  async _playTune() {
    if (this._playing) return;
    this._playing = true;

    const playBtn = this.shadowRoot.getElementById("btn-play");
    playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg> Playing...';
    playBtn.disabled = true;

    if (!this._audioCtx) {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    const noteMs = 300;
    let lastFreq = 0;

    for (let i = 0; i < 16; i++) {
      if (!this._playing) break;
      const note = this._tune[i];

      // Flash the note label
      const name = this.shadowRoot.getElementById(`name-${i}`);
      if (name) {
        name.classList.add(note === "-" ? "flash-sustain" : "flash");
        setTimeout(() => name.classList.remove("flash", "flash-sustain"), noteMs * 0.8);
      }

      // Flash the staff dot
      const dot = this.shadowRoot.getElementById(`dot-${i}`);
      if (dot) {
        dot.classList.add("flash-dot");
        setTimeout(() => dot.classList.remove("flash-dot"), noteMs * 0.8);
      }

      const freq = PITCH_FREQ[note];
      if (freq > 0) {
        // Count how many sustain slots follow this note
        let beats = 1;
        for (let j = i + 1; j < 16 && this._tune[j] === "-"; j++) beats++;
        lastFreq = freq;
        this._playBell(this._audioCtx, freq, beats);
      } else if (note === "-") {
        // sustain — bell is already ringing from the original note
      } else {
        lastFreq = 0;
      }

      await new Promise(r => setTimeout(r, noteMs));
    }

    playBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M8 5v14l11-7z"/></svg> Play';
    playBtn.disabled = false;
    this._playing = false;
  }

  _playBell(ctx, freq, beats = 1) {
    const now = ctx.currentTime;
    const partials = [
      [1.0, 0.45, 4.0],
      [2.0, 0.25, 5.5],
      [3.0, 0.12, 7.0],
      [4.0, 0.08, 9.0],
      [5.92, 0.05, 12.0],
    ];
    // Bell strike (always the same sharp attack)
    for (const [ratio, amp, decay] of partials) {
      const ringTime = 1.0 / decay + 0.1;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq * ratio;
      gain.gain.setValueAtTime(amp * 0.4, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + ringTime);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + ringTime + 0.05);
    }
    // Sustained tone for held notes — gentle pad under the bell
    if (beats > 1) {
      const holdDur = beats * 0.3;
      const fadeOut = 0.08;
      const sus = ctx.createOscillator();
      const sus2 = ctx.createOscillator();
      const g = ctx.createGain();
      sus.type = "sine";
      sus.frequency.value = freq;
      sus2.type = "sine";
      sus2.frequency.value = freq * 2;
      sus.connect(g);
      sus2.connect(g);
      g.connect(ctx.destination);
      // Fade in gently after the bell attack, hold, then fade out
      g.gain.setValueAtTime(0.001, now);
      g.gain.linearRampToValueAtTime(0.12, now + 0.05);
      g.gain.setValueAtTime(0.12, now + holdDur - fadeOut);
      g.gain.linearRampToValueAtTime(0.001, now + holdDur);
      sus.start(now);
      sus2.start(now);
      sus.stop(now + holdDur + 0.01);
      sus2.stop(now + holdDur + 0.01);
    }
  }

  _resetTune() {
    this._tune = [...DEFAULT_TUNE];
    this._updateAllSliders();
    this._updateStaff();
    this._setStatus("");
  }

  _randomizeTune() {
    for (let i = 0; i < 16; i++) {
      const idx = 2 + Math.floor(Math.random() * (PITCHES.length - 2));
      this._tune[i] = PITCHES[idx];
    }
    this._updateAllSliders();
    this._updateStaff();
    this._setStatus("");
  }

  async _saveTune() {
    if (!this._hass) return;
    const btn = this.shadowRoot.getElementById("btn-save");
    btn.innerHTML = "Saving...";
    btn.disabled = true;

    try {
      await this._hass.callService("ac_tunes", "set_town_tune", {
        notes: [...this._tune],
      });
      this._setStatus("Saved!");
      btn.innerHTML = "Saved! ✓";
      setTimeout(() => {
        btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save';
        btn.disabled = false;
      }, 2000);
    } catch (e) {
      this._setStatus("Error: " + e.message);
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg> Save';
      btn.disabled = false;
    }
  }

  _setStatus(msg) {
    const el = this.shadowRoot.getElementById("save-status");
    if (el) el.textContent = msg;
  }

  getCardSize() {
    return 7;
  }

  static getStubConfig() {
    return { entity: "switch.auto_play" };
  }
}

customElements.define("town-tune-card", TownTuneCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "town-tune-card",
  name: "Town Tune Editor",
  description: "Animal Crossing town tune composer with staff display and sliders",
});
