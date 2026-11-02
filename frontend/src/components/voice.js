/* Voice in and out through the browser's own speech APIs: no key, no cost,
   nothing leaves the device for recognition on most browsers. Both are
   optional; the buttons only appear where the browser supports them. */

export const canListen = () =>
  typeof window !== "undefined" && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;

export function listen(lang, { onText, onEnd, onError }) {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new Rec();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = (e) => onText(Array.from(e.results).map((r) => r[0].transcript).join(""));
  rec.onerror = (e) => onError?.(e.error);
  rec.onend = () => onEnd?.();
  rec.start();
  return rec;
}

export function speak(text, lang, onEnd) {
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang;
  u.rate = 0.95;
  u.onend = onEnd;
  u.onerror = onEnd;
  window.speechSynthesis.speak(u);
}

export const stopSpeaking = () => window.speechSynthesis?.cancel();
