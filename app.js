// LUCIFER — Frontend logic (mic via backend whisper STT, reliable)
// Served from same origin as backend (/app, /app.js) so CORS + mic permission work.

const API_BASE = "https://gone-verification-cinema-citizen.trycloudflare.com";  // backend tunnel (Vercel is static-only)

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");

let audioEl = new Audio();
let listening = false, busy = false, mediaRecorder = null, micStream = null, recTimer = null;

function setStatus(state) {
  dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}

// waveform (visual only)
const cv = $("wave"), cx = cv.getContext("2d");
function sizeCanvas() { cv.width = cv.clientWidth * devicePixelRatio; cv.height = cv.clientHeight * devicePixelRatio; }
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
    const y = mid + Math.sin(t * (active ? 18 : 5) + phase) * amp
    cx.lineTo(x, y);
  }
  cx.stroke();
  phase += active ? 0.25 : 0.06;
  requestAnimationFrame(() => drawWave(active));
}
drawWave(false);

function addLine(who, text) {
  if (hint) hint.remove();
  const p = document.createElement("p");
  p.className = who === "you" ? "you" : who === "err" ? "err" : "lu";
  p.textContent = (who === "you" ? "🧑 " : who === "err" ? "⚠️ " : "😈 ") + text;
  transcript.appendChild(p);
  transcript.scrollTop = transcript.scrollHeight;
}

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

// ---------- MIC: Web Speech (primary, accurate) + backend whisper (fallback) ----------
let recog = null;
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recog = new SR();
  recog.lang = "en-IN"; // Hinglish (Roman) — best for mixed Hindi+English
  recog.interimResults = true;
  recog.continuous = false;
  recog.onresult = (e) => {
    let txt = "";
    for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
    txt = txt.trim();
    if (txt) {
      let p = transcript.querySelector(".you.interim");
      if (!p) { p = document.createElement("p"); p.className = "you interim"; transcript.appendChild(p); }
      p.textContent = "🧑 " + txt;
      transcript.scrollTop = transcript.scrollHeight;
      if (e.results[0].isFinal) { recog._gotFinal = true; p.remove(); askLucifer(txt); stopListen(); }
    }
  };
  recog.onerror = (ev) => {
    const msg = ev && ev.error ? ev.error : "unknown";
    if (msg === "not-allowed" || msg === "service-not-allowed") {
      if (hint) hint.textContent = "❌ Mic blocked. Allow mic & retry, or TYPE.";
    } else if (msg !== "no-speech" && msg !== "aborted") {
      startBackendSTT(); // fallback to whisper on any real error
    }
    stopListen();
  };
  recog.onend = () => {
    // Web Speech ended without delivering a final result (common on mobile) → whisper
    if (listening && !busy && !recog._gotFinal) startBackendSTT();
    else if (listening) stopListen();
  };
  return true;
}

async function startListen() {
  if (busy || listening) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  hint.textContent = "🎙️ Sun raha hoon… bol bc (8s auto-stop)";
  // Try Web Speech first (fast on Chrome). If it errors or ends with no result,
  // the onerror/onend handlers below fall back to backend whisper.
  if (recog) {
    try { recog.start(); return; } catch (_) {}
  }
  startBackendSTT();
}

// Whisper fallback (Firefox/Safari where Web Speech unsupported) — uses real mimeType
async function startBackendSTT() {
  if (busy || listening) return;
  listening = true; orb.classList.add("listening"); micBtn.classList.add("hold");
  hint.textContent = "🎙️ Recording… (whisper) bol bc";
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { listening = false; orb.classList.remove("listening"); micBtn.classList.remove("hold"); if (hint) hint.textContent = "❌ Mic denied. Use TYPE."; return; }
  let mr;
  try { mr = new MediaRecorder(stream); } catch (e) { stream.getTracks().forEach(t=>t.stop()); if (hint) hint.textContent = "❌ MediaRecorder unsupported."; resetMic(); return; }
  mediaRecorder = mr; micStream = stream;
  const chunks = [];
  mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  mr.onstop = async () => {
    if (micStream) { micStream.getTracks().forEach(t=>t.stop()); micStream = null; }
    const mime = mr.mimeType || "audio/webm";
    const blob = new Blob(chunks, { type: mime });
    if (!blob.size) { resetMic(); return; }
    busy = true; setStatus("busy"); orb.classList.add("speaking");
    hint.textContent = "🧠 Soch raha hoon…";
    try {
      const fd = new FormData(); fd.append("audio", blob, "speech");
      const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
      if (!r.ok) throw new Error("voice failed " + r.status);
      const d = await r.json();
      if (d.text && d.text.trim()) { addLine("you", d.text); addLine("lu", d.reply || ""); await speak(d.reply || ""); }
      else if (hint) hint.textContent = "🎤 Kuch sunai nhi — dobara bol bc.";
    } catch (e) { addLine("err", "⚠️ Voice process fail: " + e.message); }
    finally { busy = false; setStatus("on"); orb.classList.remove("speaking"); resetMic(); }
  };
  mr.start();
  recTimer = setTimeout(() => { if (mr.state === "recording") mr.stop(); }, 8000);
}

function stopListen() {
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
  if (recTimer) { clearTimeout(recTimer); recTimer = null; }
}
function resetMic() {
  listening = false; orb.classList.remove("listening"); micBtn.classList.remove("hold");
}

// ---------- events ----------
micBtn.addEventListener("click", () => { listening ? stopListen() : startListen(); });
textBtn.addEventListener("click", () => {
  typebox.hidden = !typebox.hidden;
  if (!typebox.hidden) textInput.focus();
});
sendBtn.addEventListener("click", () => {
  const v = textInput.value.trim();
  if (v) { askLucifer(v); textInput.value = ""; }
});
textInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendBtn.click(); });

// ---------- boot ----------
setupSpeech();
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
