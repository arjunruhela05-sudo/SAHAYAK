/**
 * Voice guide
 * ===========
 *
 * Spoken prompts (speech synthesis) + spoken commands (speech
 * recognition) so an assessment can be completed hands-free:
 *
 *   app  → "Speak now." / "Proceed?" / "Say 'I am done' when finished."
 *   user → "start", "I am done", "proceed", "submit", "record again" …
 *
 * English, Hindi and Hinglish command phrases are recognised.  While
 * the person is recording their statement only a small set of explicit
 * "stop" phrases is accepted, so ordinary words in the statement never
 * trigger a command by accident.
 *
 * Uses the Web Speech API (Chrome / Edge).  Everything degrades to a
 * no-op with `supported === false` elsewhere.
 */

const SR = typeof window !== "undefined" ? window.SpeechRecognition || window.webkitSpeechRecognition : null;
const TTS = typeof window !== "undefined" ? window.speechSynthesis : null;

export const voiceSupport = {
  recognition: Boolean(SR),
  synthesis: Boolean(TTS),
};

/* ------------------------------------------------------------------ */
/* command grammar                                                     */
/* ------------------------------------------------------------------ */

const norm = (s) =>
  String(s || "")
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

/**
 * Intent → phrases.  Order matters: longer / more specific phrases are
 * matched first.  Phrases are matched as whole words inside the heard
 * text so "I am done now" still matches "i am done".
 */
export const COMMANDS = {
  stop: [
    "stop recording", "stop the recording", "i am done", "im done", "i have finished", "i am finished",
    "thats all", "that is all", "finished", "done",
    "recording band karo", "record band karo", "band karo", "bas ho gaya", "ho gaya", "bas itna hi", "ruk jao", "ruko", "bas",
    "रिकॉर्डिंग बंद करो", "बंद करो", "बस हो गया", "हो गया", "रुको", "बस",
  ],
  start: [
    "start recording", "begin recording", "start the recording", "start", "begin", "record now", "record", "i am ready", "ready",
    "recording shuru karo", "shuru karo", "record karo", "shuru", "chalu karo", "main taiyar hoon", "taiyar",
    "रिकॉर्डिंग शुरू करो", "शुरू करो", "शुरू", "चालू करो", "तैयार",
  ],
  submit: [
    "submit", "submit it", "send it", "send", "upload", "analyze", "analyse", "analyze it", "confirm",
    "bhej do", "bhejo", "jama karo", "submit karo", "bhej dijiye",
    "भेज दो", "भेजो", "जमा करो", "सबमिट",
  ],
  discard: [
    "record again", "start again", "try again", "discard", "delete it", "delete", "retry", "redo",
    "dobara", "phir se", "fir se", "dobara record karo", "hata do",
    "दोबारा", "फिर से", "हटा दो",
  ],
  consent: [
    "i consent", "i agree", "i understand and consent", "yes i consent", "yes i agree", "agree", "consent",
    "main sehmat hoon", "main sahmat hoon", "mujhe manzoor hai", "haan manzoor hai", "sehmat", "manzoor",
    "मैं सहमत हूँ", "मैं सहमत हूं", "मुझे मंज़ूर है", "सहमत", "मंज़ूर",
  ],
  next: [
    "proceed", "next step", "next", "continue", "go ahead", "move on", "go on",
    "aage badho", "aage badhiye", "aage", "agla", "chalo", "jari rakho", "aage chalo",
    "आगे बढ़ो", "आगे", "अगला", "चलो", "जारी रखो",
  ],
  back: [
    "go back", "previous step", "previous", "back",
    "peeche", "wapas", "pichla", "peeche jao",
    "पीछे", "वापस", "पिछला",
  ],
  text: ["type it", "type", "text statement", "text", "narrative", "likhna hai", "likh kar", "लिखना है"],
  voice: ["voice statement", "voice recording", "voice", "audio", "awaaz", "awaz", "bol kar", "आवाज़"],
  video: ["video statement", "video recording", "video", "camera", "वीडियो"],
  dictate: [
    "start dictation", "dictate", "take dictation", "write what i say", "type what i say",
    "bolkar likho", "bol kar likho", "likho", "बोलकर लिखो", "लिखो",
  ],
  stopDictate: ["stop dictation", "stop typing", "stop writing", "likhna band karo", "लिखना बंद करो"],
  clear: ["clear text", "clear the text", "clear", "erase", "saaf karo", "mita do", "साफ़ करो", "मिटा दो"],
  repeat: ["repeat", "say again", "say that again", "pardon", "dobara bolo", "phir se bolo", "दोबारा बोलो", "फिर से बोलो"],
  help: ["help", "what can i say", "commands", "options", "madad", "kya bol sakta hoon", "kya bol sakti hoon", "मदद"],
  stopGuide: ["stop voice mode", "turn off voice", "voice off", "stop listening", "voice mode band karo", "सुनना बंद करो"],
};

/** Only these intents are honoured while the statement is being recorded. */
export const RECORDING_INTENTS = ["stop", "stopGuide"];

const phraseMatches = (heard, phrase) => {
  const p = norm(phrase);
  if (!p) return false;
  if (heard === p) return true;
  return new RegExp(`(^|\\s)${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\s|$)`, "u").test(heard);
};

/**
 * Map a transcript to an intent.  Returns `{ intent, phrase }` or null.
 * `allowed` restricts the intents that may fire (e.g. while recording).
 */
export function parseCommand(transcript, allowed = null) {
  const heard = norm(transcript);
  if (!heard) return null;
  const intents = allowed || Object.keys(COMMANDS);
  // longest phrase wins across all intents
  let best = null;
  for (const intent of intents) {
    for (const phrase of COMMANDS[intent] || []) {
      if (phraseMatches(heard, phrase)) {
        const len = norm(phrase).length;
        if (!best || len > best.len) best = { intent, phrase, len };
      }
    }
  }
  if (!best) return null;
  // very short generic words ("done", "bas", "back") need the heard text
  // to be short too, otherwise they fire inside normal sentences.
  if (best.len <= 4 && heard.split(" ").length > 3) return null;
  return { intent: best.intent, phrase: best.phrase };
}

/* ------------------------------------------------------------------ */
/* spoken prompts                                                      */
/* ------------------------------------------------------------------ */

export const PROMPTS = {
  en: {
    welcome: "Voice guidance is on. I will read each step and you can answer by speaking. Say help at any time to hear the commands.",
    consent: "Step one, privacy and consent. Your statement may be analysed to support a human reviewer. It is not a diagnosis, and an authorised person always reviews it. If you agree, say: I consent.",
    consented: "Thank you. Consent recorded. Say proceed to continue.",
    details: "Step two, case details. Say proceed to continue, or back to return.",
    narrative: "Step three, your statement. You can type it, or say start dictation to speak and I will write it down. Say voice or video if you would rather record yourself. Say analyze when you are finished.",
    dictationOn: "I am listening. Speak your statement now. Say stop dictation when you have finished.",
    dictationOff: "Dictation stopped.",
    voice: "Voice statement. When you are ready, say start. I will then say speak now. Describe what happened in your own words, and when you have finished, say: I am done.",
    video: "Video statement. Please look at the camera. When you are ready, say start. I will then say speak now. When you have finished, say: I am done.",
    speakNow: "Speak now.",
    recorded: "Thank you. Say submit to send your statement, record again to start over, or proceed to continue.",
    submitting: "Sending your statement now. Please wait.",
    submitted: "Your statement has been submitted. Thank you. A human responder will review it.",
    needConsent: "Please give consent first by saying: I consent.",
    needNarrative: "I have not heard or received a statement yet.",
    help: "You can say: I consent, proceed, back, start, I am done, submit, record again, start dictation, voice, video, or help.",
    notUnderstood: "Sorry, I did not catch a command. Say help to hear what you can say.",
    off: "Voice guidance is off.",
    error: "Something went wrong. Please try again or use the buttons.",
    listening: "Listening…",
  },
  hi: {
    welcome: "आवाज़ मार्गदर्शन चालू है। मैं हर चरण पढ़ूँगा और आप बोलकर जवाब दे सकते हैं। किसी भी समय मदद कहें।",
    consent: "चरण एक, गोपनीयता और सहमति। आपके बयान का विश्लेषण एक मानव समीक्षक की सहायता के लिए किया जा सकता है। यह कोई निदान नहीं है, और एक अधिकृत व्यक्ति हमेशा इसकी समीक्षा करता है। यदि आप सहमत हैं, तो कहें: मैं सहमत हूँ।",
    consented: "धन्यवाद। सहमति दर्ज हो गई। जारी रखने के लिए आगे बढ़ो कहें।",
    details: "चरण दो, केस विवरण। जारी रखने के लिए आगे बढ़ो कहें, या वापस कहें।",
    narrative: "चरण तीन, आपका बयान। आप इसे टाइप कर सकते हैं, या बोलकर लिखो कहें और मैं लिख लूँगा। यदि आप रिकॉर्ड करना चाहते हैं तो आवाज़ या वीडियो कहें। पूरा होने पर सबमिट कहें।",
    dictationOn: "मैं सुन रहा हूँ। अब अपना बयान बोलें। पूरा होने पर लिखना बंद करो कहें।",
    dictationOff: "लिखना बंद हो गया।",
    voice: "आवाज़ का बयान। जब आप तैयार हों, शुरू करो कहें। फिर मैं कहूँगा, अब बोलिए। अपने शब्दों में बताइए क्या हुआ, और पूरा होने पर कहें: हो गया।",
    video: "वीडियो बयान। कृपया कैमरे की ओर देखें। जब आप तैयार हों, शुरू करो कहें। फिर मैं कहूँगा, अब बोलिए। पूरा होने पर कहें: हो गया।",
    speakNow: "अब बोलिए।",
    recorded: "धन्यवाद। भेजने के लिए भेज दो कहें, दोबारा रिकॉर्ड करने के लिए दोबारा कहें, या आगे बढ़ो कहें।",
    submitting: "आपका बयान भेजा जा रहा है। कृपया प्रतीक्षा करें।",
    submitted: "आपका बयान भेज दिया गया है। धन्यवाद। एक मानव समीक्षक इसकी समीक्षा करेगा।",
    needConsent: "कृपया पहले सहमति दें, कहें: मैं सहमत हूँ।",
    needNarrative: "मुझे अभी तक कोई बयान नहीं मिला है।",
    help: "आप कह सकते हैं: मैं सहमत हूँ, आगे बढ़ो, वापस, शुरू करो, हो गया, भेज दो, दोबारा, बोलकर लिखो, आवाज़, वीडियो, या मदद।",
    notUnderstood: "माफ़ कीजिए, मुझे कोई आदेश समझ नहीं आया। मदद कहें।",
    off: "आवाज़ मार्गदर्शन बंद है।",
    error: "कुछ गलत हो गया। कृपया फिर से कोशिश करें या बटन का उपयोग करें।",
    listening: "सुन रहा हूँ…",
  },
};

export const GUIDE_LANGS = [
  { code: "en-IN", label: "English (India)", prompts: "en" },
  { code: "en-US", label: "English (US)", prompts: "en" },
  { code: "hi-IN", label: "हिन्दी / Hinglish", prompts: "hi" },
];

/* ------------------------------------------------------------------ */
/* guide                                                               */
/* ------------------------------------------------------------------ */

/**
 * createVoiceGuide({ lang, onCommand, onTranscript, onStatus })
 *
 *  - speak(text, { interrupt })   : speak a prompt; recognition pauses meanwhile
 *  - say(key)                     : speak a canned prompt in the current language
 *  - listen() / pause()           : start / stop recognition
 *  - setMode("commands"|"recording"|"dictation")
 *  - setLang(code)
 *  - destroy()
 */
export function createVoiceGuide({ lang = "en-IN", onCommand, onTranscript, onStatus, onDictation } = {}) {
  let recognition = null;
  let wantListening = false;
  let speaking = false;
  let mode = "commands";
  let currentLang = lang;
  let lastPrompt = "";
  let restartTimer = null;
  let destroyed = false;

  const promptsFor = () => PROMPTS[(GUIDE_LANGS.find((l) => l.code === currentLang) || GUIDE_LANGS[0]).prompts] || PROMPTS.en;
  const status = (state, detail) => onStatus?.({ state, detail, mode, speaking, listening: wantListening });

  function pickVoice() {
    if (!TTS) return null;
    const voices = TTS.getVoices() || [];
    const exact = voices.find((v) => v.lang?.toLowerCase() === currentLang.toLowerCase());
    if (exact) return exact;
    const base = currentLang.split("-")[0].toLowerCase();
    return voices.find((v) => v.lang?.toLowerCase().startsWith(base)) || null;
  }

  function speak(text, { interrupt = true } = {}) {
    return new Promise((resolve) => {
      if (!TTS || !text || destroyed) return resolve();
      lastPrompt = text;
      if (interrupt) TTS.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = currentLang;
      const voice = pickVoice();
      if (voice) utter.voice = voice;
      utter.rate = 0.95;
      const finish = () => {
        speaking = false;
        status("spoke", text);
        // Small gap so the microphone does not pick up the tail of the prompt.
        setTimeout(() => {
          if (wantListening) startRecognition();
          resolve();
        }, 250);
      };
      utter.onend = finish;
      utter.onerror = finish;
      speaking = true;
      // Never listen to our own voice.
      stopRecognition(false);
      status("speaking", text);
      TTS.speak(utter);
    });
  }

  const say = (key, opts) => speak(promptsFor()[key] || key, opts);

  function handleResult(event) {
    let finalText = "";
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const res = event.results[i];
      if (res.isFinal) finalText += `${res[0].transcript} `;
      else interim += `${res[0].transcript} `;
    }
    if (interim) onTranscript?.({ text: interim.trim(), final: false, mode });
    if (!finalText.trim()) return;
    const text = finalText.trim();
    onTranscript?.({ text, final: true, mode });

    if (mode === "dictation") {
      const cmd = parseCommand(text, ["stopDictate", "stopGuide", "clear"]);
      if (cmd) onCommand?.(cmd, text);
      else onDictation?.(text);
      return;
    }
    const allowed = mode === "recording" ? RECORDING_INTENTS : null;
    const cmd = parseCommand(text, allowed);
    if (cmd) onCommand?.(cmd, text);
    else if (mode === "commands") onCommand?.({ intent: "unknown", phrase: "" }, text);
  }

  function startRecognition() {
    if (!SR || destroyed || speaking || recognition) return;
    try {
      const rec = new SR();
      rec.lang = currentLang;
      rec.continuous = true;
      rec.interimResults = mode === "dictation";
      rec.maxAlternatives = 1;
      rec.onresult = handleResult;
      rec.onerror = (e) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          wantListening = false;
          status("error", "Microphone permission for voice commands was denied.");
        } else if (e.error !== "no-speech" && e.error !== "aborted") {
          status("error", e.error);
        }
      };
      rec.onend = () => {
        recognition = null;
        if (wantListening && !speaking && !destroyed) {
          clearTimeout(restartTimer);
          restartTimer = setTimeout(startRecognition, 300);
        } else status("idle");
      };
      rec.start();
      recognition = rec;
      status("listening");
    } catch (err) {
      recognition = null;
      status("error", String(err?.message || err));
    }
  }

  function stopRecognition(clearWant = true) {
    if (clearWant) wantListening = false;
    clearTimeout(restartTimer);
    if (recognition) {
      const rec = recognition;
      recognition = null;
      rec.onend = null;
      try { rec.stop(); } catch { /* ignore */ }
    }
    if (clearWant) status("idle");
  }

  return {
    supported: Boolean(SR) && Boolean(TTS),
    speak,
    say,
    repeat: () => speak(lastPrompt),
    listen() {
      wantListening = true;
      if (!speaking) startRecognition();
    },
    pause() {
      stopRecognition(true);
    },
    setMode(next) {
      if (mode === next) return;
      mode = next;
      // interimResults differs per mode → restart the recogniser
      if (wantListening && !speaking) {
        stopRecognition(false);
        wantListening = true;
        startRecognition();
      }
      status("mode", next);
    },
    getMode: () => mode,
    setLang(code) {
      currentLang = code;
      if (wantListening && !speaking) {
        stopRecognition(false);
        wantListening = true;
        startRecognition();
      }
    },
    prompts: promptsFor,
    destroy() {
      destroyed = true;
      stopRecognition(true);
      try { TTS?.cancel(); } catch { /* ignore */ }
    },
  };
}
