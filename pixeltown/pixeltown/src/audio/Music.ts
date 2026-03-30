/**
 * Procedural background music — multiple tracks that cycle automatically.
 *
 * Track 1: "Morning Dew" — warm C major, gentle walking bass, pentatonic melody
 * Track 2: "Starlit Path" — dreamy G major, arpeggiated pads, floating melody
 * Track 3: "Market Day" — upbeat F major, bouncy rhythm, cheerful
 * Track 4: "Twilight Garden" — mellow A minor → major, wistful, contemplative
 *
 * Each track plays for ~30-45 seconds, then crossfades to the next.
 */

// ── Note frequencies ──
const N: Record<string, number> = {
  C2: 65.41, D2: 73.42, E2: 82.41, F2: 87.31, G2: 98.00, A2: 110.00, B2: 123.47,
  C3: 130.81, D3: 146.83, E3: 164.81, F3: 174.61, G3: 196.00, A3: 220.00, B3: 246.94,
  C4: 261.63, D4: 293.66, E4: 329.63, F4: 349.23, G4: 392.00, A4: 440.00, B4: 493.88,
  C5: 523.25, D5: 587.33, E5: 659.25, F5: 698.46, G5: 783.99, A5: 880.00, B5: 987.77,
  C6: 1046.50, D6: 1174.66, E6: 1318.51,
  // Flats/sharps
  Eb3: 155.56, Bb3: 233.08, Ab3: 207.65,
  Eb4: 311.13, Bb4: 466.16, Ab4: 415.30,
  Eb5: 622.25, Bb5: 932.33, Ab5: 830.61,
  Fs4: 369.99, Fs5: 739.99,
};

type Chord = { bass: string; pads: string[]; };

// ── Track definitions ──

interface Track {
  name: string;
  tempo: number;
  chords: Chord[];
  melody: number[][]; // scale degrees per bar, -1 = rest
  scale: string[];    // note names for melody scale
  melodyOctave: number;
  style: "gentle" | "dreamy" | "bouncy" | "wistful";
}

const TRACKS: Track[] = [
  {
    name: "Morning Dew",
    tempo: 104,
    chords: [
      { bass: "C3", pads: ["E4", "G4", "C5"] },
      { bass: "G3", pads: ["B4", "D5", "G5"] },
      { bass: "A3", pads: ["C5", "E5", "A5"] },
      { bass: "F3", pads: ["A4", "C5", "F5"] },
      { bass: "C3", pads: ["E4", "G4", "C5"] },
      { bass: "E3", pads: ["G4", "B4", "E5"] },
      { bass: "F3", pads: ["A4", "C5", "F5"] },
      { bass: "G3", pads: ["B4", "D5", "G5"] },
    ],
    melody: [
      [0, -1, 2, 4, -1, 3, 2, -1],
      [4, 3, 2, -1, 0, -1, 2, 3],
      [2, -1, 4, -1, 5, 4, 3, -1],
      [0, 2, -1, 4, -1, 2, 3, 4],
      [5, -1, 4, 3, -1, 2, -1, 0],
      [2, 3, 4, -1, 5, -1, 4, 3],
      [0, -1, 2, -1, 4, 3, 2, -1],
      [4, 3, 2, 0, -1, -1, -1, -1],
    ],
    scale: ["C", "D", "E", "G", "A", "C+", "D+", "E+"],
    melodyOctave: 5,
    style: "gentle",
  },
  {
    name: "Starlit Path",
    tempo: 88,
    chords: [
      { bass: "G3", pads: ["B4", "D5"] },
      { bass: "E3", pads: ["G4", "B4", "E5"] },
      { bass: "C3", pads: ["E4", "G4", "C5"] },
      { bass: "D3", pads: ["Fs4", "A4", "D5"] },
      { bass: "G3", pads: ["B4", "D5", "G5"] },
      { bass: "E3", pads: ["G4", "B4"] },
      { bass: "A3", pads: ["C5", "E5"] },
      { bass: "D3", pads: ["Fs4", "A4", "D5"] },
    ],
    melody: [
      [4, -1, -1, 3, -1, 2, -1, -1],
      [1, -1, 3, -1, -1, 4, -1, 5],
      [-1, 3, -1, 2, -1, -1, 0, -1],
      [2, -1, -1, 4, -1, 3, -1, -1],
      [5, -1, 4, -1, -1, 3, -1, 2],
      [-1, -1, 1, -1, 3, -1, -1, 4],
      [3, -1, -1, 2, -1, 0, -1, -1],
      [-1, 2, -1, -1, 4, -1, -1, -1],
    ],
    scale: ["G", "A", "B", "D", "E", "G+", "A+", "B+"],
    melodyOctave: 5,
    style: "dreamy",
  },
  {
    name: "Market Day",
    tempo: 126,
    chords: [
      { bass: "F3", pads: ["A4", "C5", "F5"] },
      { bass: "C3", pads: ["E4", "G4", "C5"] },
      { bass: "G3", pads: ["B4", "D5"] },
      { bass: "F3", pads: ["A4", "C5"] },
      { bass: "Bb3", pads: ["D4", "F4", "Bb4"] },
      { bass: "F3", pads: ["A4", "C5", "F5"] },
      { bass: "C3", pads: ["E4", "G4", "C5"] },
      { bass: "G3", pads: ["B4", "D5", "G5"] },
    ],
    melody: [
      [0, 2, 3, 4, 3, 2, 0, 2],
      [4, 3, 2, 0, 2, 4, 5, -1],
      [3, 4, 5, -1, 4, 3, 2, 0],
      [2, -1, 0, 2, 3, 4, -1, 3],
      [5, 4, 3, 2, 0, -1, 2, 3],
      [0, 2, 4, 5, 4, 2, 0, -1],
      [3, -1, 4, 3, 2, 0, 2, 4],
      [5, 4, 3, 2, 0, -1, -1, -1],
    ],
    scale: ["F", "G", "A", "C", "D", "F+", "G+", "A+"],
    melodyOctave: 5,
    style: "bouncy",
  },
  {
    name: "Twilight Garden",
    tempo: 96,
    chords: [
      { bass: "A3", pads: ["C5", "E5"] },
      { bass: "F3", pads: ["A4", "C5", "F5"] },
      { bass: "D3", pads: ["F4", "A4", "D5"] },
      { bass: "E3", pads: ["G4", "B4", "E5"] },
      { bass: "A3", pads: ["C5", "E5", "A5"] },
      { bass: "D3", pads: ["F4", "A4"] },
      { bass: "G3", pads: ["B4", "D5", "G5"] },
      { bass: "C3", pads: ["E4", "G4", "C5"] },
    ],
    melody: [
      [0, -1, 2, 3, -1, -1, 4, -1],
      [3, 2, -1, 0, -1, 2, -1, 3],
      [-1, 4, -1, 3, 2, -1, 0, -1],
      [2, -1, 3, -1, 4, -1, -1, 5],
      [4, -1, -1, 3, -1, 2, 0, -1],
      [-1, 2, 3, -1, 4, -1, 5, -1],
      [3, -1, 2, -1, 0, -1, -1, 2],
      [0, -1, -1, -1, -1, -1, -1, -1],
    ],
    scale: ["A", "B", "C", "D", "E", "A+", "B+", "C+"],
    melodyOctave: 4,
    style: "wistful",
  },
];

// ── Audio engine ──

let ctx: AudioContext | null = null;
let masterGain: GainNode | null = null;
let playing = false;
let loopTimer: number | null = null;
let currentTrackIdx = 0;

let rngState = 42;
function rand(): number {
  rngState = (rngState * 1664525 + 1013904223) & 0x7fffffff;
  return rngState / 0x7fffffff;
}

function ensureContext(): AudioContext {
  if (!ctx) {
    ctx = new AudioContext();
    masterGain = ctx.createGain();
    masterGain.gain.value = 0.12;
    masterGain.connect(ctx.destination);
  }
  return ctx;
}

function noteFreq(name: string, octaveOffset: number): number {
  const clean = name.replace("+", "");
  const oct = name.includes("+") ? octaveOffset + 1 : octaveOffset;
  return N[clean + oct] ?? N[clean + "4"] ?? 440;
}

function playNote(
  freq: number, start: number, dur: number, vol: number,
  type: OscillatorType, attack = 0.02, releaseFrac = 0.4,
): void {
  const c = ensureContext();
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;

  const sustain = dur * (1 - releaseFrac);
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(vol, start + attack);
  gain.gain.setValueAtTime(vol, start + Math.max(attack, sustain));
  gain.gain.linearRampToValueAtTime(0, start + dur);

  osc.connect(gain);
  gain.connect(masterGain!);
  osc.start(start);
  osc.stop(start + dur + 0.05);
}

function playPad(freqs: number[], start: number, dur: number, vol: number): void {
  for (const f of freqs) {
    playNote(f, start, dur, vol * 0.4, "sine", 0.15, 0.6);
    playNote(f * 1.003, start, dur, vol * 0.2, "sine", 0.2, 0.6);
  }
}

function playHat(start: number, vol: number): void {
  const c = ensureContext();
  const buf = c.createBuffer(1, c.sampleRate * 0.03, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
  const src = c.createBufferSource();
  src.buffer = buf;
  const flt = c.createBiquadFilter();
  flt.type = "highpass";
  flt.frequency.value = 8000;
  const g = c.createGain();
  g.gain.setValueAtTime(vol, start);
  g.gain.linearRampToValueAtTime(0, start + 0.03);
  src.connect(flt);
  flt.connect(g);
  g.connect(masterGain!);
  src.start(start);
}

function playKick(start: number, vol: number): void {
  const c = ensureContext();
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(150, start);
  osc.frequency.exponentialRampToValueAtTime(40, start + 0.1);
  g.gain.setValueAtTime(vol, start);
  g.gain.linearRampToValueAtTime(0, start + 0.15);
  osc.connect(g);
  g.connect(masterGain!);
  osc.start(start);
  osc.stop(start + 0.2);
}

// ── Track rendering ──

function renderTrack(track: Track, startTime: number): number {
  const beat = 60 / track.tempo;
  const eighth = beat / 2;
  let t = startTime;

  // Repeat chord progression enough times for ~2 minutes
  const barDuration = beat * 4;
  const targetDuration = 120; // seconds
  const barsNeeded = Math.ceil(targetDuration / barDuration);
  const fadeInBars = 2;

  for (let bar = 0; bar < barsNeeded; bar++) {
    const ch = track.chords[bar % track.chords.length];
    const bassFreq = N[ch.bass] ?? 130;
    const padFreqs = ch.pads.map((n) => N[n] ?? 440);
    const melody = track.melody[bar % track.melody.length];
    const intensity = Math.min(1, (bar + 1) / fadeInBars);

    // ── Style-specific patterns ──
    if (track.style === "gentle" || track.style === "wistful") {
      // Walking bass
      playNote(bassFreq, t, beat * 1.5, 0.13 * intensity, "triangle", 0.01, 0.3);
      const bass5 = bassFreq * 1.5;
      playNote(bass5, t + beat * 2, beat * 1.2, 0.09 * intensity, "triangle", 0.01, 0.3);
      if (rand() > 0.4) {
        playNote(bassFreq * (rand() > 0.5 ? 1.25 : 1.33), t + beat * 3, beat * 0.8, 0.06 * intensity, "triangle", 0.01, 0.3);
      }

      // Pad
      playPad(padFreqs, t, beat * 3.8, 0.06 * intensity);

      // Arpeggio
      for (let i = 0; i < 8; i++) {
        if (rand() > 0.2) {
          const arpF = padFreqs[i % padFreqs.length];
          playNote(arpF, t + i * eighth, eighth * 0.7, 0.035 * intensity * (i % 2 === 0 ? 1 : 0.6), "square", 0.005, 0.5);
        }
      }

      // Light percussion
      if (bar >= fadeInBars) {
        playKick(t, 0.06 * intensity);
        playKick(t + beat * 2, 0.04 * intensity);
        for (let i = 0; i < 8; i++) {
          if (rand() > 0.2) playHat(t + i * eighth, (i % 2 === 0 ? 0.025 : 0.012) * intensity);
        }
      }
    } else if (track.style === "dreamy") {
      // Sustained bass
      playNote(bassFreq, t, beat * 3.5, 0.10 * intensity, "sine", 0.05, 0.5);

      // Long lush pads
      playPad(padFreqs, t, beat * 4, 0.08 * intensity);

      // Sparse shimmering arpeggio
      for (let i = 0; i < 8; i++) {
        if (rand() > 0.45) {
          const arpF = padFreqs[i % padFreqs.length] * (rand() > 0.5 ? 1 : 2);
          playNote(arpF, t + i * eighth, eighth * 1.5, 0.025 * intensity, "sine", 0.02, 0.7);
        }
      }

      // No drums, just occasional sparkle
      if (rand() > 0.5) {
        const sparkle = padFreqs[padFreqs.length - 1] * 2;
        playNote(sparkle, t + beat * (1 + rand() * 2), beat * 0.5, 0.015 * intensity, "sine", 0.01, 0.8);
      }
    } else if (track.style === "bouncy") {
      // Punchy staccato bass
      playNote(bassFreq, t, beat * 0.4, 0.14 * intensity, "triangle", 0.005, 0.2);
      playNote(bassFreq, t + beat, beat * 0.3, 0.08 * intensity, "triangle", 0.005, 0.2);
      playNote(bassFreq * 1.5, t + beat * 2, beat * 0.4, 0.12 * intensity, "triangle", 0.005, 0.2);
      playNote(bassFreq, t + beat * 3, beat * 0.3, 0.08 * intensity, "triangle", 0.005, 0.2);

      // Short stab chords
      playPad(padFreqs, t, beat * 0.5, 0.05 * intensity);
      playPad(padFreqs, t + beat * 2, beat * 0.5, 0.05 * intensity);

      // Fast arpeggio
      for (let i = 0; i < 8; i++) {
        const arpF = padFreqs[i % padFreqs.length];
        playNote(arpF, t + i * eighth, eighth * 0.5, 0.04 * intensity * (i % 2 === 0 ? 1 : 0.7), "square", 0.003, 0.3);
      }

      // Full drums
      playKick(t, 0.08 * intensity);
      playKick(t + beat * 2, 0.07 * intensity);
      for (let i = 0; i < 8; i++) {
        playHat(t + i * eighth, (i % 2 === 0 ? 0.03 : 0.018) * intensity);
      }
      // Snare-like on 2 and 4
      if (bar >= 1) {
        playHat(t + beat, 0.05 * intensity);
        playHat(t + beat * 3, 0.05 * intensity);
      }
    }

    // ── Melody (all styles) ──
    for (let i = 0; i < melody.length; i++) {
      if (melody[i] < 0) continue;
      const freq = noteFreq(track.scale[melody[i] % track.scale.length], track.melodyOctave);
      const dur = eighth * (track.style === "dreamy" ? 2 : 1.2 + rand() * 0.4);
      const vol = 0.065 * intensity * (i % 4 === 0 ? 1 : 0.8);
      const type: OscillatorType = track.style === "dreamy" ? "sine" : "triangle";
      playNote(freq, t + i * eighth, dur, vol, type, 0.01, 0.4);
    }

    // Occasional high sparkle
    if (rand() > 0.65) {
      const sparkle = padFreqs[padFreqs.length - 1] * 2;
      playNote(sparkle, t + beat * (1 + rand() * 2), beat * 0.3, 0.018 * intensity, "sine", 0.01, 0.8);
    }

    t += beat * 4;
  }

  return t;
}

// ── Playback control ──

function scheduleNext(): void {
  if (!playing || !ctx) return;

  const track = TRACKS[currentTrackIdx];
  const endTime = renderTrack(track, ctx.currentTime + 0.1);

  // Move to next track
  currentTrackIdx = (currentTrackIdx + 1) % TRACKS.length;

  // Schedule next track before this one ends (small gap for natural transition)
  const delay = (endTime - ctx.currentTime - 1.5) * 1000;
  loopTimer = window.setTimeout(scheduleNext, Math.max(200, delay));
}

export function startMusic(): void {
  if (playing) return;
  playing = true;
  rngState = Math.floor(Math.random() * 10000); // different each session
  currentTrackIdx = Math.floor(Math.random() * TRACKS.length); // random start

  const c = ensureContext();
  if (c.state === "suspended") c.resume();

  scheduleNext();
}

export function stopMusic(): void {
  playing = false;
  if (loopTimer != null) {
    clearTimeout(loopTimer);
    loopTimer = null;
  }
  if (ctx) {
    ctx.close();
    ctx = null;
    masterGain = null;
  }
}

export function isPlaying(): boolean {
  return playing;
}

export function setVolume(vol: number): void {
  if (masterGain) {
    masterGain.gain.value = Math.max(0, Math.min(1, vol)) * 0.12;
  }
}
