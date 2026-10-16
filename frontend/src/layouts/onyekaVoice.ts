import { API_BASE, api, authFetch, unwrap } from "../api/client";
import { ApiError, type Problem } from "../api/errors";
import type { components } from "../api/schema";

export type VoiceReply = components["schemas"]["TkAdvisorReply"];

/** Recording formats in order of preference; the first the browser can make is used. */
const FORMATS = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const MAX_MS = 90_000; // a long question, well inside the 4 MB the server takes
const QUIET_AFTER_SPEECH_MS = 900; // this much quiet after speaking ends the turn
const NO_SPEECH_MS = 8_000; // give up if nothing is said at all
const TICK_MS = 100;

export function voiceSupported(): boolean {
  return typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

function pickFormat(): string {
  return FORMATS.find((f) => window.MediaRecorder.isTypeSupported?.(f)) ?? "";
}

export type RecordingEnd = "finished" | "silent" | "cancelled";

export interface Recording {
  /** Stops and keeps what was said. */
  finish: () => void;
  /** Stops and throws the recording away. */
  cancel: () => void;
  /** Resolves when recording stops: the audio, or null if it was cancelled or nothing was said. */
  done: Promise<{ blob: Blob | null; end: RecordingEnd }>;
}

/**
 * Records from the microphone until the speaker pauses, the time runs out, or `finish` is called.
 * `onLevel` gets a 0 to 1 loudness for a meter. Throws if the microphone cannot be opened.
 */
export async function record(onLevel?: (level: number) => void): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const format = pickFormat();
  const recorder = new MediaRecorder(stream, format ? { mimeType: format } : undefined);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size) chunks.push(event.data);
  };

  const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  const context = AudioCtx ? new AudioCtx() : null;
  const analyser = context?.createAnalyser();
  if (context && analyser) {
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
  }
  const samples = new Float32Array(analyser?.fftSize ?? 0);

  let end: RecordingEnd = "finished";
  let heard = false;
  let quietSince = 0;
  let floor = 0;
  const started = performance.now();

  const stopAll = () => {
    window.clearInterval(timer);
    if (recorder.state !== "inactive") recorder.stop();
    stream.getTracks().forEach((t) => t.stop());
    void context?.close().catch(() => undefined);
  };

  const timer = window.setInterval(() => {
    const now = performance.now();
    if (analyser) {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += s * s;
      const rms = Math.sqrt(sum / samples.length);
      if (now - started < 400) floor = Math.max(floor, rms); // the room's own noise
      const threshold = Math.max(0.02, floor * 2.5);
      onLevel?.(Math.min(1, rms / 0.2));
      if (rms > threshold) {
        heard = true;
        quietSince = 0;
      } else if (heard) {
        quietSince ||= now;
        if (now - quietSince > QUIET_AFTER_SPEECH_MS) stopAll();
      }
      if (!heard && now - started > NO_SPEECH_MS) {
        end = "silent";
        stopAll();
      }
    }
    if (now - started > MAX_MS) stopAll();
  }, TICK_MS);

  const done = new Promise<{ blob: Blob | null; end: RecordingEnd }>((resolve) => {
    recorder.onstop = () => {
      const kept = end === "finished" && chunks.length > 0;
      resolve({ blob: kept ? new Blob(chunks, { type: recorder.mimeType || format || "audio/webm" }) : null, end });
    };
  });
  recorder.start(250);
  return {
    finish: () => stopAll(),
    cancel: () => {
      end = "cancelled";
      stopAll();
    },
    done,
  };
}

async function problemOf(response: Response): Promise<ApiError> {
  let problem: Problem = { status: response.status, detail: response.statusText };
  try {
    problem = (await response.json()) as Problem;
  } catch {
    /* not JSON: keep the status text */
  }
  return new ApiError(response.status, problem);
}

/**
 * One spoken turn in a single request: the server turns the recording into words, asks Onyeka and
 * answers with the reply and, when it is ready, where to stream it read aloud.
 */
export async function voiceTurn(blob: Blob): Promise<VoiceReply> {
  const form = new FormData();
  const extension = blob.type.includes("mp4") ? "mp4" : blob.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", blob, `speech.${extension}`);
  const response = await authFetch(new Request(new URL(`${API_BASE}/api/v1/toolkit/advisor/voice`, window.location.origin), { method: "POST", body: form }));
  if (!response.ok) throw await problemOf(response);
  return (await response.json()) as VoiceReply;
}

/** Where to stream one of Onyeka's answers from. */
export async function speechUrl(messageId: string): Promise<string> {
  const link = await unwrap(api.POST("/api/v1/toolkit/advisor/messages/{message_id}/speech", { params: { path: { message_id: messageId } } }));
  return link.url;
}

/** A short silent sound. Playing it while the member taps unlocks audio for later replies. */
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

/** One audio element for all of Onyeka's speech, so a browser that needs a tap first only needs one. */
export class Speaker {
  private el: HTMLAudioElement | null = null;
  private unlocked = false;

  private element(): HTMLAudioElement {
    this.el ??= new Audio();
    return this.el;
  }

  /** Call from a tap or click. */
  unlock(): void {
    if (this.unlocked) return;
    this.unlocked = true;
    const el = this.element();
    el.src = SILENCE;
    void el.play().catch(() => undefined);
  }

  /**
   * Plays an answer from its streaming address; sound starts as soon as the first of it arrives.
   * Resolves when it ends or is stopped.
   */
  async play(url: string, signal?: AbortSignal): Promise<void> {
    if (signal?.aborted) return;
    this.stop();
    const el = this.element();
    el.src = new URL(API_BASE + url, window.location.origin).toString();
    await new Promise<void>((resolve, reject) => {
      const finish = () => {
        el.onended = null;
        el.onpause = null;
        el.onerror = null;
        resolve();
      };
      el.onended = finish;
      el.onpause = finish;
      el.onerror = () => reject(new Error("Onyeka's voice could not be played. Please try again."));
      signal?.addEventListener("abort", () => el.pause(), { once: true });
      el.play().catch(reject);
    });
  }

  stop(): void {
    if (this.el && !this.el.paused) this.el.pause();
  }
}
