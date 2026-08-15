// LUCIFER — Frontend logic (cross-platform voice: Android / iOS / PC)
// Talks to backend via Vercel serverless proxy at /api/* (HTTPS, VPS-direct).
// /api/* -> Vercel function -> VPS:8000.
//
// VOICE INPUT STRATEGY (max compatibility):
//   1) Web Speech API (SpeechRecognition) if available — best on Chrome/Edge.
//   2) MediaRecorder fallback — records raw audio, sends to /voice (faster-whisper).
//      Works on Firefox, Safari, iOS, any browser with getUserMedia.
// VOICE OUTPUT: always Edge TTS (played via <audio>, works everywhere).

const API_BASE = "/api";

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");

let audioEl = new Audio();
let recog = null, listening = false, busy = false;
let mediaRecorder = null, mediaChunks = [], mediaStream = null;
let usingFallback = false;

// ---------- status ----------
function setStatus(state) {
  dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}

// ---------- waveform ----------
const cv = $("wave"), cx = cv.getContext("2d");
function sizeCanvas() {
  cv.width = cv.clientWidth * devicePixelRatio;
  cv.height = cv.clientHeight * devicePixelRatio;
}
window.addEventListener("resize", sizeCanvas); sizeCanvas();
let phase = 0;
function drawWave(active) {
  cx.clearRect(0, 0, cv.width, cv.height);
  const w = cv.width, h = cv.height, mid = h / 2;
  cx.lineWidth = 2 * devicePixelRatio;
  cx.strokeStyle = active ? "#00e5ff" : "#7b2dff";
  cx.shadowBlur = 16; cx.shadowColor = cx.strokeStyle;
  cx.beginPath();
  for (let x = 0; x <= w; x += 4) {
    const t = x / w;
    const amp = active ? (Math.sin(t * 12 + phase) * 0.5 + 0.5) * (h * 0.32) : (Math.sin(t * 6 + phase) * 0.5 + 0.5) * (h * 0.06);
    const y = mid + Math.sin(t * (active ? 18 : 5) + phase) * amp;
    x === 0 ? cx.moveTo(x, y) : cx.lineTo(x, y);
  }
  cx.stroke();
  phase += active ? 0.25 : 0.06;
  requestAnimationFrame(() => drawWave(active));
}
drawWave(false);

// ---------- transcript ----------
function addLine(who, text) {
  if (hint) { hint.remove(); }
  const p = document.createElement("p");
  p.className = who === "you" ? "you" : who === "err" ? "err" : "lu";
  p.textContent = (who === "you" ? "🧑 " : who === "lu" ? "😈 " : "⚠️ ") + text;
  transcript.appendChild(p);
  transcript.scrollTop = transcript.scrollHeight;
}

// ---------- backend calls ----------
async function askLucifer(text) {
  if (!text || busy) return;
  busy = true; setStatus("busy"); orb.classList.add("speaking");
  addLine("you", text);
  try {
    const r = await fetch(API_BASE + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("chat failed");
    const reply = await r.text();
    addLine("lu", reply.trim());
    await speak(reply.trim());
  } catch (e) {
    addLine("err", "Connection error — backend down?");
  } finally {
    busy = false; setStatus("on"); orb.classList.remove("speaking");
  }
}

async function speak(text) {
  try {
    const r = await fetch(API_BASE + "/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("tts failed");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    audioEl.src = url;
    await audioEl.play();
  } catch (e) {
    console.warn("TTS failed, skipping audio", e);
  }
}

// ---------- VOICE INPUT: Web Speech API (primary) ----------
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  try {
    recog = new SR();
    recog.lang = "hi-IN"; // Hinglish — English words pass through
    recog.interimResults = false;
    recog.continuous = false;
    recog.onresult = (e) => {
      const txt = e.results[0][0].transcript.trim();
      if (txt) askLucifer(txt);
    };
    recog.onerror = (ev) => {
      // no-speech / network / denied — fall through to stop; message shown by stopListen
      console.warn("SpeechRecognition error:", ev.error);
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        addLine("err", "Mic blocked. Allow mic permission in site settings, then retry.");
      }
      stopListen();
    };
    recog.onend = () => {
      // Auto-restart if user is still holding (no-speech timeout on some browsers)
      if (listening && !busy && !usingFallback) {
        try { recog.start(); } catch (_) {}
      } else {
        stopListen();
      }
    };
    return true;
  } catch (_) {
    return false;
  }
}

// ---------- VOICE INPUT: MediaRecorder fallback (Firefox / Safari / iOS) ----------
async function setupFallback() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return false;
  if (typeof MediaRecorder === "undefined") return false;
  return true;
}

async function startFallback() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm"
               : MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4"
               : "";
    mediaRecorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime })
                         : new MediaRecorder(mediaStream);
    mediaChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) mediaChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      stopListen();
      // Send to backend /voice as multipart form (matches UploadFile field "audio")
      const fd = new FormData();
      fd.append("audio", blob, "voice.webm");
      busy = true; setStatus("busy"); orb.classList.add("speaking");
      addLine("you", "🎤 …");
      try {
        const r = await fetch(API_BASE + "/voice", {
          method: "POST",
          body: fd, // no Content-Type header — browser sets multipart boundary
        });
        if (!r.ok) throw new Error("voice failed");
        const data = await r.json();
        const text = data.text || "";
        if (text.trim()) {
          addLine("you", text);
          const reply = data.reply || "";
          if (reply) {
            addLine("lu", reply.trim());
            await speak(reply.trim());
          }
        } else {
          addLine("err", "Couldn't hear clearly — try again.");
        }
      } catch (e) {
        addLine("err", "Voice backend error — try TYPE mode.");
      } finally {
        busy = false; setStatus("on"); orb.classList.remove("speaking");
        if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
      }
    };
    mediaRecorder.start();
    return true;
  } catch (e) {
    console.warn("Fallback mic failed:", e);
    addLine("err", "Mic access denied. Allow mic permission, or use TYPE.");
    return false;
  }
}

// ---------- start / stop listening ----------
function startListen() {
  if (busy) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  if (recog && !usingFallback) {
    try { recog.start(); return; } catch (_) {}
  }
  // fallback path
  usingFallback = true;
  startFallback();
}

function stopListen() {
  listening = false;
  usingFallback = false;
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  try { if (recog) recog.stop(); } catch (_) {}
  try { if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop(); } catch (_) {}
}

// ---------- events (PC click + mobile tap) ----------
micBtn.addEventListener("click", () => {
  listening ? stopListen() : startListen();
});

// Hold-to-talk on touch devices (press = listen, release = stop)
let holdTimer = null;
micBtn.addEventListener("touchstart", (e) => {
  e.preventDefault();
  if (!listening) startListen();
}, { passive: false });
micBtn.addEventListener("touchend", (e) => {
  e.preventDefault();
  if (listening) stopListen();
}, { passive: false });

textBtn.addEventListener("click", () => {
  typebox.hidden = !typebox.hidden;
  if (!typebox.hidden) textInput.focus();
});
sendBtn.addEventListener("click", () => {
  const v = textInput.value.trim();
  if (v) { askLucifer(v); textInput.value = ""; }
});
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

// ---------- boot ----------
async function boot() {
  const hasSpeech = setupSpeech();
  const hasFallback = await setupFallback();
  if (!hasSpeech && !hasFallback) {
    micBtn.title = "Mic not supported — use TYPE";
    micBtn.disabled = true;
  } else if (!hasSpeech) {
    micBtn.title = "Using recorder fallback (tap & hold to talk)";
  } else {
    micBtn.title = "Tap to talk (Hinglish / Hindi)";
  }
  // health check
  fetch(API_BASE + "/health")
    .then((r) => r.json())
    .then(() => setStatus("on"))
    .catch(() => setStatus("off"));
}
boot();
