// LUCIFER — Frontend logic (orb = mic, real-time conversation)
// Backend via Vercel serverless proxy /api/* -> VPS:8000.
//
// CROSS-PLATFORM VOICE (Chrome / Firefox / Android / iOS / PC / laptop):
//   We use the MediaRecorder API + getUserMedia to capture mic audio and
//   send it to the backend /voice endpoint (faster-whisper STT). This works
//   UNIFORMLY on every modern browser. We deliberately do NOT use the Web
//   Speech API — it is Chrome/Android-only and behaves differently (or is
//   absent) on Firefox and iOS Safari, which broke cross-platform parity.
//
// UX: TAP the ORB to start listening, TAP again to stop. After Lucifer
//   replies it auto-resumes listening (hands-free loop) until you tap to
//   stop or say a stop word.
// Output voice: Sarvam shubh (backend, via /tts) played through <audio>.

const API_BASE = "/api";

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");
const micEmoji = document.querySelector(".mic-emoji");

let audioEl = new Audio();
let listening = false, busy = false, conversationOn = false;
let mediaRecorder = null, mediaChunks = [], mediaStream = null;
let _speakResumePending = false;

// ---------- status ----------
function setStatus(state) {
  dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}
function setHint(msg) { if (hint) hint.textContent = msg; }

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
  if (/^(band kar|stop|ruk|chup|bas|enough|quit|exit)\b/i.test(text.toLowerCase())) {
    conversationOn = false;
    addLine("lu", "Theek hai, band kar raha hoon. Dobara tap karna baat karne ke liye.");
    return;
  }
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
// While TTS plays, the mic MUST be paused so Lucifer doesn't hear its own
// voice and loop (acoustic feedback). Pause before playback, resume after.
async function speak(text) {
  const wasListening = listening || (mediaRecorder && mediaRecorder.state === "recording");
  if (wasListening) pauseListenForPlayback();
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
    await new Promise((res) => {
      audioEl.onended = res;
      setTimeout(res, 30000);
    });
  } catch (e) {
    console.warn("TTS failed, skipping audio", e);
  } finally {
    if (_speakResumePending) {
      setTimeout(() => {
        _speakResumePending = false;
        if (conversationOn && !busy && !listening) startListen();
      }, 350);
    }
  }
}

function pauseListenForPlayback() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    try { mediaRecorder.stop(); } catch (_) {}
  }
  listening = false;
  orb.classList.remove("listening");
  if (micEmoji) micEmoji.textContent = "🎙️";
  _speakResumePending = conversationOn;
}

// ---------- VOICE: unified MediaRecorder (all browsers) ----------
function hasMic() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && typeof MediaRecorder !== "undefined");
}

// Pick a mimeType the current browser actually supports.
function pickMime() {
  const candidates = [
    "audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus",
  ];
  for (const m of candidates) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m;
  }
  return ""; // let the browser choose
}

async function startRecorder() {
  if (!hasMic()) {
    addLine("err", "Mic not supported on this browser — use TYPE mode.");
    stopListen();
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    addLine("err", "Mic permission denied. Allow mic access, or use TYPE mode.");
    stopListen();
    return;
  }
  const mime = pickMime();
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
  mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size) mediaChunks.push(e.data); };
  mediaRecorder.onstop = async () => {
    const blob = new Blob(mediaChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    // Release mic immediately so the next tap can grab it again.
    if (mediaStream) { mediaStream.getTracks().forEach((t) => t.stop()); mediaStream = null; }
    if (blob.size < 800) { // silence / too short
      addLine("err", "Couldn't hear clearly — try again.");
      busy = false; setStatus("on"); orb.classList.remove("speaking");
      autoResume();
      return;
    }
    busy = true; setStatus("busy"); orb.classList.add("speaking");
    addLine("you", "🎤 …");
    try {
      const fd = new FormData();
      fd.append("audio", blob, "voice.webm");
      const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
      if (!r.ok) throw new Error("voice failed " + r.status);
      const data = await r.json();
      const text = (data.text || "").trim();
      if (text) {
        addLine("you", text);
        const reply = (data.reply || "").trim();
        if (reply) {
          addLine("lu", reply);
          await speak(reply);
          autoResume();
          return;
        }
      } else {
        addLine("err", "Couldn't hear clearly — try again.");
      }
      autoResume();
    } catch (e) {
      addLine("err", "Voice backend error — try TYPE mode. (" + e.message + ")");
    } finally {
      busy = false; setStatus("on"); orb.classList.remove("speaking");
    }
  };
  mediaRecorder.start();
}

// ---------- start / stop (orb tap = toggle) ----------
function startListen() {
  if (busy && !listening) return;
  listening = true;
  conversationOn = true;
  orb.classList.add("listening");
  if (micEmoji) micEmoji.textContent = "🎙️";
  setHint("Sun raha hoon… bol lo (dobara tap = band)");
  startRecorder();
}

function stopListen() {
  listening = false;
  conversationOn = false;
  orb.classList.remove("listening");
  if (micEmoji) micEmoji.textContent = "🎙️";
  try { if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop(); } catch (_) {}
}

// After a reply finishes, auto-resume listening (hands-free loop).
function autoResume() {
  if (conversationOn && !busy && !listening && !_speakResumePending) {
    startListen();
  }
}

async function askLuciferLoop(text) {
  await askLucifer(text);
  autoResume();
}

// ---------- orb = mic button (ONE TAP TOGGLE, all platforms) ----------
function toggleOrb() {
  listening ? stopListen() : startListen();
}
orb.addEventListener("click", toggleOrb);
orb.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleOrb(); }
});
// Prevent the ghost touchstart->click double fire on Android/iOS from toggling
// twice. We swallow touchstart (it would otherwise also emit a click) and rely
// solely on the click event for a clean single-toggle on mobile.
orb.addEventListener("touchstart", (e) => { e.preventDefault(); }, { passive: false });

// ---------- text mode ----------
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
  if (!hasMic()) {
    orb.title = "Mic not supported — use TYPE";
  } else {
    orb.title = "Tap orb to talk (Hinglish / Hindi)";
  }
  fetch(API_BASE + "/health")
    .then((r) => r.json())
    .then(() => setStatus("on"))
    .catch(() => setStatus("off"));
}
boot();
