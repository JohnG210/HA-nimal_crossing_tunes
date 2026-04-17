/**
 * Animal Crossing Clock Card for HA-nimal Crossing Tunes
 *
 * A custom Lovelace card styled after the DSiWare Animal Crossing Clock app.
 * Supports analog and digital modes with a dynamic sky background that
 * changes based on time of day, weather icons, and now-playing info.
 *
 * Config:
 *   type: custom:ac-clock-card
 *   entity: switch.ac_tunes_auto_play   (required)
 *   mode: analog         # "analog" or "digital" (default: analog)
 *   time_format: 12      # 12 or 24 (default: 12)
 *   show_weather: true    # show weather icon (default: true)
 *   show_now_playing: true # show game/track info (default: true)
 */

const GAME_DISPLAY_NAMES = {
  "animal-crossing": "Animal Crossing",
  "wild-world": "Wild World",
  "city-folk": "City Folk",
  "new-leaf": "New Leaf",
  "new-horizons": "New Horizons",
};

const WEATHER_LABELS = {
  sunny: "Sunny",
  raining: "Rainy",
  snowing: "Snowy",
};

// Sky color stops: [hour, topColor, bottomColor]
const SKY_GRADIENTS = [
  { hour: 0, top: "#0a1128", bottom: "#1b2845" },   // midnight
  { hour: 5, top: "#1b2845", bottom: "#2a4066" },   // pre-dawn
  { hour: 6, top: "#3d5a80", bottom: "#e09f7d" },   // dawn
  { hour: 7, top: "#5c9ead", bottom: "#f0c987" },   // sunrise
  { hour: 8, top: "#87ceeb", bottom: "#b5e5f5" },   // morning
  { hour: 12, top: "#5bb5e8", bottom: "#87ceeb" },  // noon
  { hour: 16, top: "#6baed6", bottom: "#c4b896" },  // afternoon
  { hour: 18, top: "#c06040", bottom: "#e8a87c" },  // sunset
  { hour: 19, top: "#6e3a5f", bottom: "#c06060" },  // dusk
  { hour: 20, top: "#1f2d50", bottom: "#3d2b56" },  // evening
  { hour: 22, top: "#0f1b33", bottom: "#1b2845" },  // night
];

function lerpColor(a, b, t) {
  const ar = parseInt(a.slice(1, 3), 16),
    ag = parseInt(a.slice(3, 5), 16),
    ab = parseInt(a.slice(5, 7), 16);
  const br = parseInt(b.slice(1, 3), 16),
    bg = parseInt(b.slice(3, 5), 16),
    bb = parseInt(b.slice(5, 7), 16);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bl = Math.round(ab + (bb - ab) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bl.toString(16).padStart(2, "0")}`;
}

function getSkyColors(now) {
  const h = now.getHours() + now.getMinutes() / 60;
  let prev = SKY_GRADIENTS[SKY_GRADIENTS.length - 1];
  let next = SKY_GRADIENTS[0];
  for (let i = 0; i < SKY_GRADIENTS.length; i++) {
    if (h >= SKY_GRADIENTS[i].hour) {
      prev = SKY_GRADIENTS[i];
      next = SKY_GRADIENTS[(i + 1) % SKY_GRADIENTS.length] || SKY_GRADIENTS[0];
    }
  }
  let range = next.hour - prev.hour;
  if (range <= 0) range += 24;
  let elapsed = h - prev.hour;
  if (elapsed < 0) elapsed += 24;
  const t = Math.min(1, Math.max(0, elapsed / range));
  return {
    top: lerpColor(prev.top, next.top, t),
    bottom: lerpColor(prev.bottom, next.bottom, t),
  };
}

// --- Weather SVG icons ---
function sunIcon() {
  return `<svg viewBox="0 0 64 64" width="48" height="48">
    <circle cx="32" cy="32" r="12" fill="#FFD93D" stroke="#F5A623" stroke-width="2"/>
    <g stroke="#FFD93D" stroke-width="3" stroke-linecap="round">
      <line x1="32" y1="6" x2="32" y2="14"/>
      <line x1="32" y1="50" x2="32" y2="58"/>
      <line x1="6" y1="32" x2="14" y2="32"/>
      <line x1="50" y1="32" x2="58" y2="32"/>
      <line x1="13.6" y1="13.6" x2="19.3" y2="19.3"/>
      <line x1="44.7" y1="44.7" x2="50.4" y2="50.4"/>
      <line x1="13.6" y1="50.4" x2="19.3" y2="44.7"/>
      <line x1="44.7" y1="19.3" x2="50.4" y2="13.6"/>
    </g>
  </svg>`;
}

function rainIcon() {
  return `<svg viewBox="0 0 64 64" width="48" height="48">
    <path d="M18 36 Q18 24 32 22 Q46 24 46 36 Z" fill="#B0C4DE" stroke="#8BA4C4" stroke-width="2"/>
    <line x1="22" y1="42" x2="20" y2="50" stroke="#5B9BD5" stroke-width="2.5" stroke-linecap="round" opacity="0.8"/>
    <line x1="32" y1="44" x2="30" y2="52" stroke="#5B9BD5" stroke-width="2.5" stroke-linecap="round" opacity="0.8"/>
    <line x1="42" y1="42" x2="40" y2="50" stroke="#5B9BD5" stroke-width="2.5" stroke-linecap="round" opacity="0.8"/>
    <line x1="27" y1="48" x2="25" y2="56" stroke="#5B9BD5" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
    <line x1="37" y1="48" x2="35" y2="56" stroke="#5B9BD5" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
  </svg>`;
}

function snowIcon() {
  return `<svg viewBox="0 0 64 64" width="48" height="48">
    <path d="M18 34 Q18 22 32 20 Q46 22 46 34 Z" fill="#D0DEE8" stroke="#A8B8C8" stroke-width="2"/>
    <circle cx="22" cy="44" r="2.5" fill="#fff" opacity="0.9"/>
    <circle cx="32" cy="42" r="2.5" fill="#fff" opacity="0.9"/>
    <circle cx="42" cy="44" r="2.5" fill="#fff" opacity="0.9"/>
    <circle cx="27" cy="50" r="2" fill="#fff" opacity="0.7"/>
    <circle cx="37" cy="52" r="2" fill="#fff" opacity="0.7"/>
    <circle cx="32" cy="56" r="2" fill="#fff" opacity="0.6"/>
  </svg>`;
}

function getWeatherIcon(weather) {
  if (weather === "raining") return rainIcon();
  if (weather === "snowing") return snowIcon();
  return sunIcon();
}

// --- Leaf SVG decoration ---
function leafSvg() {
  return `<svg viewBox="0 0 32 32" width="28" height="28" style="opacity:0.6">
    <path d="M16 4 C8 8 4 16 8 24 C10 20 14 16 16 14 C18 16 22 20 24 24 C28 16 24 8 16 4Z"
          fill="#4CAF50" stroke="#388E3C" stroke-width="1"/>
    <line x1="16" y1="14" x2="16" y2="28" stroke="#388E3C" stroke-width="1.5"/>
  </svg>`;
}

// ====================================================================
class ACClockCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._clockInterval = null;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity (e.g. switch.ac_tunes_auto_play)");
    }
    this._config = {
      entity: config.entity,
      mode: config.mode || "analog",
      time_format: config.time_format || 12,
      show_weather: config.show_weather !== false,
      show_now_playing: config.show_now_playing !== false,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._clockInterval = setInterval(() => this._updateClock(), 1000);
  }

  disconnectedCallback() {
    if (this._clockInterval) {
      clearInterval(this._clockInterval);
      this._clockInterval = null;
    }
  }

  _getState() {
    if (!this._hass) return null;
    const state = this._hass.states[this._config.entity];
    if (!state) return null;
    return {
      isPlaying: state.attributes.is_playing || false,
      currentGame: state.attributes.current_game || null,
      currentWeather: state.attributes.current_weather || null,
    };
  }

  _formatTime(date) {
    const h = date.getHours();
    const m = date.getMinutes();
    const s = date.getSeconds();
    const pad = (n) => String(n).padStart(2, "0");

    if (this._config.time_format === 24) {
      return { time: `${pad(h)}:${pad(m)}`, seconds: pad(s), ampm: "" };
    }
    const h12 = h % 12 || 12;
    const ampm = h < 12 ? "AM" : "PM";
    return { time: `${h12}:${pad(m)}`, seconds: pad(s), ampm };
  }

  _formatDate(date) {
    const days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${days[date.getDay()]}, ${months[date.getMonth()]} ${date.getDate()}`;
  }

  _render() {
    const state = this._getState();
    const now = new Date();
    const sky = getSkyColors(now);
    const isNight = now.getHours() >= 20 || now.getHours() < 6;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          width: 100%;
        }
        .ac-clock-container {
          position: relative;
          width: 100%;
          min-height: 380px;
          background: linear-gradient(180deg, ${sky.top} 0%, ${sky.bottom} 100%);
          border-radius: 16px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 24px 16px;
          box-sizing: border-box;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: ${isNight ? "#e8e0d0" : "#3e2c1c"};
          transition: background 60s linear;
        }

        /* Grass strip at the bottom */
        .grass {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 48px;
          background: linear-gradient(180deg, #5dad3a 0%, #4a9632 40%, #3d7a28 100%);
          border-top: 3px solid #6dc043;
        }
        .grass::before {
          content: "";
          position: absolute;
          top: -6px;
          left: 0;
          right: 0;
          height: 12px;
          background: repeating-linear-gradient(
            90deg,
            transparent 0px,
            transparent 8px,
            #6dc043 8px,
            #6dc043 10px
          );
          mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 12'%3E%3Cpath d='M0 12 Q5 0 10 12 Q15 0 20 12' fill='%23fff'/%3E%3C/svg%3E");
          mask-size: 20px 12px;
          -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 12'%3E%3Cpath d='M0 12 Q5 0 10 12 Q15 0 20 12' fill='%23fff'/%3E%3C/svg%3E");
          -webkit-mask-size: 20px 12px;
        }

        .leaf-decoration {
          position: absolute;
          top: 12px;
          left: 12px;
        }

        /* ── Analog clock ── */
        .analog-clock {
          position: relative;
          width: 220px;
          height: 220px;
          margin: 0 auto 16px;
          z-index: 1;
        }
        .clock-face {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          background: radial-gradient(circle, #faf5e8 60%, #f0e6cc 100%);
          border: 5px solid ${isNight ? "#8b7355" : "#6b4226"};
          box-shadow: 0 4px 16px rgba(0,0,0,0.25), inset 0 2px 8px rgba(0,0,0,0.08);
          position: relative;
        }
        .clock-face::after {
          content: "";
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 10px;
          height: 10px;
          background: #6b4226;
          border-radius: 50%;
          z-index: 10;
        }
        .hour-marker {
          position: absolute;
          width: 2px;
          height: 12px;
          background: #6b4226;
          left: 50%;
          top: 8px;
          transform-origin: 50% 102px;
          margin-left: -1px;
        }
        .hour-marker.major {
          width: 3px;
          height: 16px;
          margin-left: -1.5px;
          background: #4a2e14;
        }
        .hour-number {
          position: absolute;
          font-size: 16px;
          font-weight: 700;
          color: #5c3a1e;
          width: 24px;
          text-align: center;
        }
        .clock-hand {
          position: absolute;
          bottom: 50%;
          left: 50%;
          transform-origin: 50% 100%;
          border-radius: 3px;
        }
        .hand-hour {
          width: 6px;
          height: 60px;
          background: #4a2e14;
          margin-left: -3px;
          z-index: 6;
        }
        .hand-minute {
          width: 4px;
          height: 82px;
          background: #6b4226;
          margin-left: -2px;
          z-index: 7;
        }
        .hand-second {
          width: 2px;
          height: 90px;
          background: #c0392b;
          margin-left: -1px;
          z-index: 8;
        }

        /* ── Digital clock ── */
        .digital-clock {
          text-align: center;
          margin: 16px 0;
          z-index: 1;
        }
        .digital-time {
          font-size: 72px;
          font-weight: 700;
          letter-spacing: 2px;
          text-shadow: 0 3px 6px rgba(0,0,0,0.2);
          line-height: 1;
        }
        .digital-seconds {
          font-size: 28px;
          font-weight: 400;
          vertical-align: super;
          margin-left: 4px;
          opacity: 0.7;
        }
        .digital-ampm {
          font-size: 24px;
          font-weight: 600;
          margin-left: 8px;
          opacity: 0.8;
        }
        .digital-date {
          font-size: 18px;
          margin-top: 8px;
          opacity: 0.75;
          font-weight: 500;
        }

        /* ── Info area ── */
        .info-area {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          z-index: 1;
          margin-top: 8px;
        }
        .weather-icon {
          flex-shrink: 0;
        }
        .now-playing {
          background: rgba(255, 248, 230, 0.88);
          border: 2px solid #b8956a;
          border-radius: 12px;
          padding: 8px 16px;
          color: #5c3a1e;
          font-size: 14px;
          font-weight: 500;
          box-shadow: 0 2px 8px rgba(0,0,0,0.12);
          max-width: 260px;
          text-align: center;
        }
        .now-playing .game-name {
          font-weight: 700;
          font-size: 15px;
        }
        .now-playing .weather-label {
          font-size: 13px;
          opacity: 0.7;
          margin-top: 2px;
        }
        .not-playing {
          font-size: 14px;
          opacity: 0.6;
          font-style: italic;
          z-index: 1;
          margin-top: 8px;
        }
      </style>

      <div class="ac-clock-container" id="container">
        <div class="leaf-decoration">${leafSvg()}</div>

        ${this._config.mode === "digital" ? this._renderDigital(now) : this._renderAnalog(now)}

        ${this._renderInfo(state)}

        <div class="grass"></div>
      </div>
    `;
  }

  _renderAnalog(now) {
    const h = now.getHours() % 12;
    const m = now.getMinutes();
    const s = now.getSeconds();

    const hourDeg = (h + m / 60) * 30;
    const minuteDeg = (m + s / 60) * 6;
    const secondDeg = s * 6;

    // Hour markers
    let markers = "";
    for (let i = 0; i < 12; i++) {
      const cls = i % 3 === 0 ? "hour-marker major" : "hour-marker";
      markers += `<div class="${cls}" style="transform: rotate(${i * 30}deg)"></div>`;
    }

    // Hour numbers positioned around the face
    const numberPositions = [
      { n: 12, x: 98, y: 22 },
      { n: 1, x: 144, y: 32 },
      { n: 2, x: 172, y: 62 },
      { n: 3, x: 182, y: 98 },
      { n: 4, x: 172, y: 134 },
      { n: 5, x: 144, y: 164 },
      { n: 6, x: 98, y: 178 },
      { n: 7, x: 52, y: 164 },
      { n: 8, x: 24, y: 134 },
      { n: 9, x: 14, y: 98 },
      { n: 10, x: 24, y: 62 },
      { n: 11, x: 52, y: 32 },
    ];
    let numbers = "";
    for (const p of numberPositions) {
      numbers += `<div class="hour-number" style="left:${p.x}px;top:${p.y}px">${p.n}</div>`;
    }

    return `
      <div class="analog-clock">
        <div class="clock-face">
          ${markers}
          ${numbers}
          <div class="clock-hand hand-hour" id="hand-hour"
               style="transform: rotate(${hourDeg}deg)"></div>
          <div class="clock-hand hand-minute" id="hand-minute"
               style="transform: rotate(${minuteDeg}deg)"></div>
          <div class="clock-hand hand-second" id="hand-second"
               style="transform: rotate(${secondDeg}deg)"></div>
        </div>
      </div>
    `;
  }

  _renderDigital(now) {
    const { time, seconds, ampm } = this._formatTime(now);
    const dateStr = this._formatDate(now);

    return `
      <div class="digital-clock">
        <div class="digital-time" id="digital-time">
          ${time}<span class="digital-seconds" id="digital-seconds">${seconds}</span>
          ${ampm ? `<span class="digital-ampm" id="digital-ampm">${ampm}</span>` : ""}
        </div>
        <div class="digital-date" id="digital-date">${dateStr}</div>
      </div>
    `;
  }

  _renderInfo(state) {
    if (!state) return "";

    if (!state.isPlaying) {
      return `<div class="not-playing">Not playing</div>`;
    }

    const weatherHtml =
      this._config.show_weather && state.currentWeather
        ? `<div class="weather-icon">${getWeatherIcon(state.currentWeather)}</div>`
        : "";

    const gameName =
      GAME_DISPLAY_NAMES[state.currentGame] || state.currentGame || "Unknown";
    const weatherLabel =
      WEATHER_LABELS[state.currentWeather] || state.currentWeather || "";

    const nowPlayingHtml =
      this._config.show_now_playing && state.currentGame
        ? `<div class="now-playing">
             <div class="game-name">\u266a ${gameName}</div>
             ${weatherLabel ? `<div class="weather-label">${weatherLabel}</div>` : ""}
           </div>`
        : "";

    if (!weatherHtml && !nowPlayingHtml) return "";

    return `<div class="info-area">${weatherHtml}${nowPlayingHtml}</div>`;
  }

  _updateClock() {
    const now = new Date();

    if (this._config.mode === "analog") {
      const h = now.getHours() % 12;
      const m = now.getMinutes();
      const s = now.getSeconds();

      const hourHand = this.shadowRoot.getElementById("hand-hour");
      const minuteHand = this.shadowRoot.getElementById("hand-minute");
      const secondHand = this.shadowRoot.getElementById("hand-second");

      if (hourHand) hourHand.style.transform = `rotate(${(h + m / 60) * 30}deg)`;
      if (minuteHand) minuteHand.style.transform = `rotate(${(m + s / 60) * 6}deg)`;
      if (secondHand) secondHand.style.transform = `rotate(${s * 6}deg)`;
    } else {
      const { time, seconds, ampm } = this._formatTime(now);
      const timeEl = this.shadowRoot.getElementById("digital-time");
      const secEl = this.shadowRoot.getElementById("digital-seconds");
      const dateEl = this.shadowRoot.getElementById("digital-date");

      if (secEl) secEl.textContent = seconds;
      if (timeEl) {
        // Update just the main time text node
        const mainText = timeEl.childNodes[0];
        if (mainText && mainText.nodeType === Node.TEXT_NODE) {
          mainText.textContent = time;
        }
      }

      // Update date every minute
      if (now.getSeconds() === 0 && dateEl) {
        dateEl.textContent = this._formatDate(now);
      }
    }

    // Re-render sky gradient every 5 minutes
    if (now.getSeconds() === 0 && now.getMinutes() % 5 === 0) {
      const container = this.shadowRoot.getElementById("container");
      if (container) {
        const sky = getSkyColors(now);
        container.style.background = `linear-gradient(180deg, ${sky.top} 0%, ${sky.bottom} 100%)`;
      }
    }
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig() {
    return {
      entity: "switch.ac_tunes_auto_play",
      mode: "analog",
      time_format: 12,
    };
  }
}

customElements.define("ac-clock-card", ACClockCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ac-clock-card",
  name: "Animal Crossing Clock",
  description: "An AC-themed clock with weather and now-playing info.",
  preview: true,
});
