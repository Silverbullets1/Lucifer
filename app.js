// LUCIFER — Frontend logic (cross-platform voice: Android / iOS / PC)
// Backend via Vercel serverless proxy /api/* -> VPS:8000.
//
// VOICE INPUT (priority order):
//   1) Web Speech API (SpeechRecognition) — Chrome/Edge/Android Chrome (best, Hindi STT)
//   2) MediaRecorder fallback — Firefox/Safari/iOS (raw audio -> /voice -> faster-whisper)
// VOICE OUTPUT: always Edge TTS (<audio> playback, universal).

const API_BASE = "/api";

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");
const micEmoji = document.querySelector(".mic-emoji");

let audioEl = new Audio();
let recog = null, listening = false, busy = false;
let mediaRecorder = null, mediaChunks = [], mediaStream = null;
let usingFallback = false;
let mode = "none"; // "speech" | "recorder" | "none"

// ---------- status ----------
function setStatus(state) {
  dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}
function setHint(msg) {
  if (hint) hint.textContent = msg;
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

// ---------- backend: text chat ----------
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

// ---------- backend: TTS ----------
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

// ---------- VOICE: Web Speech API (primary) ----------
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  try {
    recog = new SR();
    recog.lang = "hi-IN";
    recog.interimResults = false;
    recog.continuous = false;
    recog.onresult = (e) => {
      const txt = e.results[0][0].transcript.trim();
      if (txt) { mode = "speech"; askLucifer(txt); }
    };
    recog.onerror = (ev) => {
      console.warn("SpeechRecognition error:", ev.error);
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        addLine("err", "Mic blocked by browser. Allow mic access in site settings, then retry.");
        stopListen();
      }
      // other errors (no-speech/network/aborted) -> let onend handle restart
    };
    recog.onend = () => {
      if (listening && !busy && mode === "speech") {
        try { recog.start(); } catch (_) {} // auto-restart on no-speech
      } else {
        stopListen();
      }
    };
    return true;
  } catch (_) {
    return false;
  }
}

// ---------- VOICE: MediaRecorder fallback (Firefox/Safari/iOS) ----------
function hasGetUserMedia() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

async function startFallback() {
  if (!hasGetUserMedia() || typeof MediaRecorder === "undefined") {
    addLine("err", "Mic not supported on this browser — use TYPE mode.");
    stopListen();
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    addLine("err", "Mic permission denied. Allow mic, or use TYPE mode.");
    stopListen();
    return;
  }
  const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm"
             : MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4"
             : "";
  try {
    mediaRecorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime })
                         : new MediaRecorder(mediaStream);
  } catch (e) {
    addLine("err", "Recorder init failed — use TYPE mode.");
    mediaStream.getTracks().forEach((t) => t.stop());
    stopListen();
    return;
  }
  mediaChunks = [];
  let stopped = false;
  mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) mediaChunks.push(e.data); };
  mediaRecorder.onstop = async () => {
    if (stopped) return;
    stopped = true;
    const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    const fd = new FormData();
    fd.append("audio", blob, "voice.webm");
    busy = true; setStatus("busy"); orb.classList.add("speaking");
    addLine("you", "🎤 …");
    try {
      const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
      if (!r.ok) throw new Error("voice failed " + r.status);
      const data = await r.json();
      const text = data.text || "";
      if (text.trim()) {
        addLine("you", text);
        const reply = data.reply || "";
        if (reply) { addLine("lu", reply.trim()); await speak(reply.trim()); }
      } else {
        addLine("err", "Couldn't hear clearly — try again.");
      }
    } catch (e) {
      addLine("err", "Voice backend error — try TYPE mode. (" + e.message + ")");
    } finally {
      busy = false; setStatus("on"); orb.classList.remove("speaking");
      if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
    }
  };
  mediaRecorder.start();
}

// ---------- start / stop ----------
function startListen() {
  if (busy) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  if (micEmoji) micEmoji.textContent = "🎙️";
  // Prefer Web Speech if available
  if (recog && !usingFallback) {
    mode = "speech";
    try { recog.start(); setHint("Listening… (speak now)"); return; }
    catch (_) { /* fall through to recorder */ }
  }
  // Fallback to MediaRecorder
  usingFallback = true;
  mode = "recorder";
  setHint("Recording… (tap again to stop)");
  startFallback();
}

function stopListen() {
  listening = false;
  usingFallback = false;
  mode = "none";
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  if (micEmoji) micEmoji.textContent = "🎙️";
  try { if (recog) recog.stop(); } catch (_) {}
  try { if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop(); } catch (_) {}
}

// ---------- events ----------
micBtn.addEventListener("click", () => {
  listening ? stopListen() : startListen();
});
// Mobile: tap-and-hold to talk
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
  const hasRecorder = hasGetUserMedia() && typeof MediaRecorder !== "undefined";
  if (!hasSpeech && !hasRecorder) {
    micBtn.title = "Mic not supported — use TYPE";
  } else if (!hasSpeech) {
    micBtn.title = "Recorder mode (tap & hold to talk)";
  } else {
    micBtn.title = "Tap to talk (Hinglish / Hindi)";
  }
  fetch(API_BASE + "/health")
    .then((r) => r.json())
    .then(() => setStatus("on"))
    .catch(() => setStatus("off"));
}
boot();
