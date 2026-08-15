// LUCIFER — Frontend logic
// Talks to backend via Vercel serverless proxy at /api/* (HTTPS, no mixed-content).
// /api/* -> Vercel function -> VPS:8000 (server-side). Mic uses MediaRecorder
// (cross-platform: Chrome, Firefox, Edge, Safari, Android, iOS, PC, laptop).

// ===== CONFIG: backend via Vercel proxy (same-origin, no tunnel needed) =====
const API_BASE = "/api";
const sessId = (() => {
  // stable per-client session id for conversation memory across turns
  let s = localStorage.getItem("lucifer_sid");
  if (!s) { s = "w-" + Math.random().toString(36).slice(2, 12); localStorage.setItem("lucifer_sid", s); }
  return s;
})();
const VOICE_URL = API_BASE + "/voice?sid=" + sessId;
const CHAT_URL = API_BASE + "/chat/stream?sid=" + sessId;
// ============================================================================

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");

let audioEl = new Audio();
audioEl.setAttribute("playsinline", "");
audioEl.setAttribute("webkit-playsinline", "");
audioEl.preload = "auto";
let listening = false, busy = false, conversationOn = false;
let mediaStream = null, mediaRecorder = null, audioChunks = [];
// VAD (Voice Activity Detection) — auto-send when user stops talking
let audioCtx = null, analyser = null, vadInterval = null;
let silenceStart = 0;
const SILENCE_LIMIT = 1800;   // ms of silence → auto-send
const VAD_THRESHOLD = 0.01;   // volume threshold for "silence"

// ---------- audio unlock (mobile autoplay policy) ----------
let audioUnlocked = false;
function unlockAudio() {
  if (audioUnlocked) return;
  audioUnlocked = true;
  try { audioEl.play().then(() => audioEl.pause()).catch(() => {}); } catch (_) {}
}
document.addEventListener("pointerdown", unlockAudio, { once: true });
document.addEventListener("keydown", unlockAudio, { once: true });

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
  p.className = who === "you" ? "you" : (who === "err" ? "err" : "lu");
  p.textContent = (who === "you" ? "🧑 " : who === "err" ? "⚠️ " : "😈 ") + text;
  transcript.appendChild(p);
  transcript.scrollTop = transcript.scrollHeight;
}

// ---------- backend calls ----------
async function askLucifer(text) {
  if (!text || busy) return;
  busy = true; setStatus("busy"); orb.classList.add("speaking");
  addLine("you", text);
  try {
    const r = await fetch(CHAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("chat failed");
    const reply = (await r.text()).trim();
    if (!reply) throw new Error("empty reply");
    addLine("lu", reply);
    await speak(reply);
  } catch (e) {
    addLine("err", "Connection error — backend down?");
  } finally {
    busy = false; setStatus("on"); orb.classList.remove("speaking");
  }
}

async function speak(text) {
  // Pause mic during playback to prevent the assistant echoing its own voice
  // (acoustic feedback loop). Resume listening only after audio ends.
  const wasConversation = conversationOn;
  if (listening) stopListen();
  try {
    const r = await fetch(API_BASE + "/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("tts failed");
    const blob = await r.blob();
    if (!blob.size) throw new Error("empty audio");
    const url = URL.createObjectURL(blob);
    audioEl.src = url;
    audioEl.type = blob.type && blob.type !== "application/json" ? blob.type : "";
    await audioEl.play();
    await new Promise((res) => {
      audioEl.onended = res;
      setTimeout(res, 30000);
    });
  } catch (e) {
    console.warn("TTS failed, skipping audio", e);
  } finally {
    // Resume listening only if conversation was on BEFORE we stopped for playback
    if (wasConversation && !busy && !listening) startListen();
  }
}

// ---------- voice input (MediaRecorder, cross-platform) ----------
// ONE-TAP TOGGLE. We use the POINTER EVENT (pointerup) instead of click/touchstart.
// Why:
//   1) Using `touchstart`+preventDefault kills the synthesized click on mobile
//      (iOS/Android) so the orb tap did nothing — that was the "tap doesn't work"
//      bug. pointerup fires exactly once per tap on every device.
//   2) A single unified handler for mouse/touch/pen avoids the double-fire you
//      get when you bind both touch and click on mobile.
// CSS ships `touch-action: manipulation` so there is no 300ms delay / zoom.
function hasMediaSupport() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && typeof MediaRecorder !== "undefined");
}

function pickMimeType() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  for (const m of types) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

async function startListen() {
  if (listening || busy) return;
  if (!hasMediaSupport()) {
    alert("Mic not supported on this browser — use TYPE.");
    return;
  }
  try {
    // Force-unlock audio context BEFORE requesting mic — mobile Chrome/iOS
    // blocks getUserMedia if audio context is locked by autoplay policy.
    if (typeof AudioContext !== "undefined" && !audioUnlocked) {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        if (ctx.state === "suspended") {
          await ctx.resume();
        }
        audioUnlocked = true;
      } catch (_) {}
    }
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    let msg = "Mic permission denied — allow mic and retry, or use TYPE.";
    if (e.name === "NotAllowedError") msg = "🔇 Mic permission BLOCKED. Tap allow when browser asks, then retry.";
    if (e.name === "NotFoundError") msg = "🎤 No microphone found on this device.";
    if (e.name === "NotReadableError") msg = "⚠️ Mic in use by another app (close other tabs/apps).";
    addLine("err", msg);
    return;
  }
  listening = true;
  conversationOn = true;
  orb.classList.add("listening");
  orb.setAttribute("aria-pressed", "true");
  const mime = pickMimeType();
  try {
    mediaRecorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime })
                         : new MediaRecorder(mediaStream);
  } catch (e) {
    addLine("err", "Recorder init failed on this browser — use TYPE.");
    stopListen();
    return;
  }
  audioChunks = [];
  mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) audioChunks.push(e.data); };
  mediaRecorder.onstop = async () => {
    stopVAD();
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    stopMicTracks();
    if (blob.size < 500) {
      if (conversationOn && !busy && !listening) startListen();
      return;
    }
    const fd = new FormData();
    fd.append("audio", blob, "voice.webm");
    try {
      const r = await fetch(VOICE_URL, { method: "POST", body: fd });
      if (!r.ok) throw new Error("voice failed " + r.status);
      const j = await r.json();
      if (j.text) addLine("you", j.text);
      if (j.reply) {
        addLine("lu", j.reply);
        await speak(j.reply);
      } else if (conversationOn && !busy && !listening) {
        startListen();
      }
    } catch (e) {
      addLine("err", "Voice send failed — backend down?");
      if (conversationOn && !busy && !listening) startListen();
    }
  };
  mediaRecorder.start();
  // Start VAD — detect silence → auto-send
  startVAD();
}

function startVAD() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    const src = audioCtx.createMediaStreamSource(mediaStream);
    src.connect(analyser);
    const buf = new Uint8Array(analyser.frequencyBinCount);
    silenceStart = Date.now();
    vadInterval = setInterval(() => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
      const rms = Math.sqrt(sum / buf.length);
      if (rms > VAD_THRESHOLD) { silenceStart = Date.now(); }
      else if (Date.now() - silenceStart > SILENCE_LIMIT && mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
    }, 200);
  } catch (_) {}
}

function stopVAD() {
  if (vadInterval) { clearInterval(vadInterval); vadInterval = null; }
  try { if (audioCtx) audioCtx.close(); } catch (_) {}
  audioCtx = null; analyser = null;
}

function stopMicTracks() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
}

function stopListen() {
  if (!listening && !conversationOn) return;
  listening = false;
  conversationOn = false;
  orb.classList.remove("listening");
  orb.setAttribute("aria-pressed", "false");
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    try { mediaRecorder.stop(); } catch (_) {}
  } else {
    stopMicTracks();
  }
}

// ---------- orb tap: TOGGLE conversation on/off ----------
// Continuous voice mode (ChatGPT/Gemini style):
//   TAP ONCE → start listening → speak → auto-send on silence → reply → auto-resume
//   TAP AGAIN → end conversation (stop listening + stop reply audio)
// Using pointerdown (not pointerup) so first tap itself activates
orb.addEventListener("pointerdown", (e) => {
  unlockAudio();
  if (busy) return;
  if (listening || conversationOn) {
    // End conversation: stop recording + audio playback
    stopListen();
    try { audioEl.pause(); } catch (_) {}
  } else {
    // Start conversation
    startListen();
  }
});

// ---------- events ----------
const _micBtn = $("micBtn");
if (_micBtn) _micBtn.addEventListener("click", () => {
  if (!hasMediaSupport()) { alert("Mic not supported on this browser — use TYPE."); return; }
  listening ? stopListen() : startListen();
});
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
// keyboard accessibility for the orb
orb.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); orb.dispatchEvent(new PointerEvent("pointerup")); }
});

// ---------- boot ----------
if (!hasMediaSupport()) {
  micBtn.title = "Mic not supported — use TYPE";
}
// health check
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
/* deploy: 1786820146 */
