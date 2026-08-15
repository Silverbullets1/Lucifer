// LUCIFER — Frontend logic
// Talks to backend via Vercel serverless proxy at /api/* (HTTPS, no mixed-content).
// /api/* -> Vercel function -> VPS:8000 (server-side). Mic uses browser Web Speech.

// ===== CONFIG: backend via Vercel proxy (same-origin, no tunnel needed) =====
const API_BASE = "/api";
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
let recog = null, listening = false, busy = false;

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
  p.className = who === "you" ? "you" : "lu";
  p.textContent = (who === "you" ? "🧑 " : "😈 ") + text;
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
    const reply = (await r.text()).trim();
    if (!reply) throw new Error("empty reply");
    addLine("lu", reply);
    // speak with Sarvam (backend) voice
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
  const wasListening = listening;
  if (wasListening) stopListen();
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
    audioEl.type = "audio/mpeg";
    await audioEl.play();
    await new Promise((res) => {
      audioEl.onended = res;
      setTimeout(res, 30000);
    });
  } catch (e) {
    console.warn("TTS failed, skipping audio", e);
  } finally {
    // resume hands-free loop only if user hadn't toggled off during playback
    if (conversationOn && !busy && !listening) startListen();
  }
}

// ---------- voice input (Web Speech API) ----------
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recog = new SR();
  recog.lang = "en-IN"; // Hinglish (Roman Hindi+English) — best for Web Speech; hi-IN mangles Roman
  recog.interimResults = false;
  recog.continuous = false;
  recog.onresult = (e) => {
    const txt = e.results[0][0].transcript.trim();
    if (txt) askLucifer(txt);
  };
  recog.onerror = () => stopListen();
  recog.onend = () => { if (listening) stopListen(); };
  return true;
}

function startListen() {
  if (!recog || busy) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  try { recog.start(); } catch (_) {}
}
function stopListen() {
  listening = false;
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  try { recog && recog.stop(); } catch (_) {}
}

// ---------- events ----------
micBtn.addEventListener("click", () => {
  if (!recog) { alert("Mic speech not supported on this browser — use TYPE."); return; }
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

// ---------- boot ----------
const hasSpeech = setupSpeech();
if (!hasSpeech) {
  micBtn.title = "Mic not supported — use TYPE";
}
// health check
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
