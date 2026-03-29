/**
 * Procedural background music — warm, layered pixel-town ambiance.
 *
 * Structure: A-B-A-C pattern with intro. Each section has distinct character.
 *   Intro: gentle rising arpeggios
 *   A: Main theme — warm melody + walking bass + pad chords
 *   B: Bridge — lighter, higher register, call-and-response
 *   C: Variation — minor-tinged, slightly wistful, returns to major
 *
 * Layers: bass (triangle), pad chords (sine), melody (triangle),
 *         arpeggio (square), percussion (noise bursts), sparkles (sine)
 */

// ── Note frequencies ──
const NOTE: Record<string, number> = {
  C3: 130.81, D3: 146.83, E3: 164.81, F3: 174.61, G3: 196.00, A3: 220.00, B3: 246.94,
  C4: 261.63, D4: 293.66, E4: 329.63, F4: 349.23, G4: 392.00, A4: 440.00, B4: 493.88,
  C5: 523.25, D5: 587.33, E5: 659.25, F5: 698.46, G5: 783.99, A5: 880.00, B5: 987.77,
  C6: 1046.50, D6: 1174.66, E6: 1318.51,
};

// ── Chord definitions ──
type Chord = { bass: string; notes: string[]; color: string };

const SECTION_A: Chord[] = [
  { bass: "C3", notes: ["E4", "G4", "C5"], color: "C4" },
  { bass: "G3", notes: ["B4", "D5", "G5"], color: "G4" },
  { bass: "A3", notes: ["C5", "E5", "A5"], color: "A4" },
  { bass: "F3", notes: ["A4", "C5", "F5"], color: "F4" },
  { bass: "C3", notes: ["E4", "G4", "C5"], color: "C4" },
  { bass: "E3", notes: ["G4", "B4", "E5"], color: "E4" },
  { bass: "F3", notes: ["A4", "C5", "F5"], color: "F4" },
  { bass: "G3", notes: ["B4", "D5", "G5"], color: "G4" },
];

const SECTION_B: Chord[] = [
  { bass: "A3", notes: ["C5", "E5"], color: "A4" },
  { bass: "F3", notes: ["A4", "C5"], color: "F4" },
  { bass: "G3", notes: ["B4", "D5"], color: "G4" },
  { bass: "C3", notes: ["E4", "G4"], color: "C4" },
  { bass: "D3", notes: ["F4", "A4"], color: "D4" },
  { bass: "G3", notes: ["B4", "D5"], color: "G4" },
  { bass: "A3", notes: ["C5", "E5"], color: "A4" },
  { bass: "C3", notes: ["E4", "G4", "C5"], color: "C4" },
];

const SECTION_C: Chord[] = [
  { bass: "A3", notes: ["C5", "E5", "A5"], color: "A4" },
  { bass: "E3", notes: ["G4", "B4", "E5"], color: "E4" },
  { bass: "F3", notes: ["A4", "C5"], color: "F4" },
  { bass: "C3", notes: ["E4", "G4", "C5"], color: "C4" },
  { bass: "D3", notes: ["F4", "A4", "D5"], color: "D4" },
  { bass: "A3", notes: ["C5", "E5"], color: "A4" },
  { bass: "G3", notes: ["B4", "D5", "G5"], color: "G4" },
  { bass: "C3", notes: ["E4", "G4", "C5"], color: "C4" },
];

// Melody patterns per section (scale degree offsets from chord root, -1 = rest)
const MELODY_A = [
  [0, -1, 2, 4, -1, 3, 2, -1],
  [4, 3, 2, -1, 0, -1, 2, 3],
  [2, -1, 4, -1, 3, 2, 0, -1],
  [0, 2, -1, 4, -1, 2, 3, 4],
  [5, -1, 4, 3, -1, 2, -1, 0],
  [2, 3, 4, -1, 5, -1, 4, 3],
  [0, -1, 2, -1, 4, 3, 2, -1],
  [4, 3, 2, 0, -1, -1, 2, -1],
];

const MELODY_B = [
  [5, 4, -1, 3, -1, 2, 4, -1],
  [3, -1, 2, -1, 4, -1, 3, 2],
  [0, 2, 3, -1, 4, -1, 5, -1],
  [4, -1, 3, 2, -1, 0, -1, 2],
  [3, 4, -1, 5, -1, 4, 3, -1],
  [2, -1, 0, -1, 2, 3, -1, 4],
  [5, 4, 3, -1, 2, -1, 0, -1],
  [0, -1, 2, -1, 4, -1, -1, -1],
];

// Pentatonic scale for melody resolution
const PENTA = ["C", "D", "E", "G", "A", "C+", "D+", "E+"];
function melodyFreq(degree: number, octaveBase: number): number {
  const notes = PENTA;
  const idx = Math.max(0, Math.min(degree, notes.length - 1));
  const n = notes[idx];
  const oct = n.includes("+") ? octaveBase + 1 : octaveBase;
  const name = n.replace("+", "") + oct;
  return NOTE[name] ?? 440;
}

// ── Audio engine ──
let ctx: AudioContext | null = null;
let masterGain: GainNode | null = null;
let playing = false;
let loopTimer: number | null = null;
let phraseCount = 0;

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

function playNote(
  freq: number, start: number, dur: number, vol: number,
  type: OscillatorType, attack = 0.02, release = 0.4,
): void {
  const c = ensureContext();
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;

  const sustain = dur * (1 - release);
  gain.gain.setValueAtTime(0, start);
  gain.gain.linearRampToValueAtTime(vol, start + attack);
  gain.gain.setValueAtTime(vol, start + Math.max(attack, sustain));
  gain.gain.linearRampToValueAtTime(0, start + dur);

  osc.connect(gain);
  gain.connect(masterGain!);
  osc.start(start);
  osc.stop(start + dur + 0.05);
}

/** Soft pad chord (layered detuned sines). */
function playPad(freqs: number[], start: number, dur: number, vol: number): void {
  for (const f of freqs) {
    playNote(f, start, dur, vol * 0.4, "sine", 0.15, 0.6);
    playNote(f * 1.002, start, dur, vol * 0.2, "sine", 0.2, 0.6); // slight detune
  }
}

/** Percussive hi-hat-like noise burst. */
function playHat(start: number, vol: number): void {
  const c = ensureContext();
  const bufferSize = c.sampleRate * 0.04;
  const buffer = c.createBuffer(1, bufferSize, c.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
  }
  const source = c.createBufferSource();
  source.buffer = buffer;

  // High-pass filter for hat sound
  const filter = c.createBiquadFilter();
  filter.type = "highpass";
  filter.frequency.value = 8000;

  const gain = c.createGain();
  gain.gain.setValueAtTime(vol, start);
  gain.gain.linearRampToValueAtTime(0, start + 0.04);

  source.connect(filter);
  filter.connect(gain);
  gain.connect(masterGain!);
  source.start(start);
}

/** Soft kick drum. */
function playKick(start: number, vol: number): void {
  const c = ensureContext();
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(150, start);
  osc.frequency.exponentialRampToValueAtTime(40, start + 0.1);
  gain.gain.setValueAtTime(vol, start);
  gain.gain.linearRampToValueAtTime(0, start + 0.15);
  osc.connect(gain);
  gain.connect(masterGain!);
  osc.start(start);
  osc.stop(start + 0.2);
}

// ── Phrase scheduling ──

function scheduleSection(
  chords: Chord[], melodies: number[][], startTime: number,
  tempo: number, withDrums: boolean, intensity: number,
): number {
  const beat = 60 / tempo;
  const eighthNote = beat / 2;
  let t = startTime;

  for (let bar = 0; bar < chords.length; bar++) {
    const ch = chords[bar];
    const bassFreq = NOTE[ch.bass];
    const chordFreqs = ch.notes.map((n) => NOTE[n]);
    const melody = melodies[bar % melodies.length];

    // ── Bass: walking pattern ──
    playNote(bassFreq, t, beat * 1.5, 0.14 * intensity, "triangle", 0.01, 0.3);
    // Bass walks to 5th on beat 3
    const bass5th = bassFreq * 1.5;
    playNote(bass5th, t + beat * 2, beat * 1.2, 0.10 * intensity, "triangle", 0.01, 0.3);
    // Passing tone on beat 4
    if (rand() > 0.4) {
      const passing = bassFreq * (rand() > 0.5 ? 1.25 : 1.33);
      playNote(passing, t + beat * 3, beat * 0.8, 0.06 * intensity, "triangle", 0.01, 0.3);
    }

    // ── Pad chords: sustain over bar ──
    playPad(chordFreqs, t, beat * 3.8, 0.06 * intensity);

    // ── Arpeggio: eighth-note pattern ──
    for (let i = 0; i < 8; i++) {
      const arpNote = chordFreqs[i % chordFreqs.length];
      const arpVol = 0.04 * intensity * (i % 2 === 0 ? 1 : 0.6);
      if (rand() > 0.15) {
        playNote(arpNote, t + i * eighthNote, eighthNote * 0.7, arpVol, "square", 0.005, 0.5);
      }
    }

    // ── Melody ──
    for (let i = 0; i < melody.length; i++) {
      if (melody[i] < 0) continue;
      const freq = melodyFreq(melody[i], 5);
      const dur = eighthNote * (1.2 + rand() * 0.5);
      const vol = 0.07 * intensity * (i % 4 === 0 ? 1 : 0.8);
      playNote(freq, t + i * eighthNote, dur, vol, "triangle", 0.01, 0.4);
    }

    // ── Percussion ──
    if (withDrums) {
      // Kick on 1 and 3
      playKick(t, 0.08 * intensity);
      playKick(t + beat * 2, 0.06 * intensity);
      // Hat on eighth notes, accented on beats
      for (let i = 0; i < 8; i++) {
        const hatVol = i % 2 === 0 ? 0.03 : 0.015;
        if (rand() > 0.1) playHat(t + i * eighthNote, hatVol * intensity);
      }
    }

    // ── Sparkles (occasional high notes) ──
    if (rand() > 0.6) {
      const sparkle = chordFreqs[chordFreqs.length - 1] * 2;
      playNote(sparkle, t + beat * (1 + rand() * 2), beat * 0.3, 0.02 * intensity, "sine", 0.01, 0.8);
    }

    t += beat * 4; // 4 beats per bar
  }
  return t;
}

function scheduleIntro(startTime: number, tempo: number): number {
  const beat = 60 / tempo;
  const eighth = beat / 2;
  let t = startTime;

  // Gentle rising arpeggio over 4 bars
  const introNotes = [
    ["C4", "E4", "G4", "C5"],
    ["G4", "B4", "D5", "G5"],
    ["A4", "C5", "E5", "A5"],
    ["F4", "A4", "C5", "E5", "G5", "C6"],
  ];

  for (let bar = 0; bar < introNotes.length; bar++) {
    const notes = introNotes[bar];
    const vol = 0.03 + bar * 0.015;
    for (let i = 0; i < notes.length; i++) {
      const freq = NOTE[notes[i]];
      playNote(freq, t + i * eighth * 1.5, beat * 2, vol, "sine", 0.05, 0.7);
    }
    t += beat * 4;
  }
  return t;
}

function scheduleFullSong(startTime: number): number {
  const tempo = 108; // BPM — lively but not hectic
  let t = startTime;

  // Vary structure based on phrase count for less repetition
  const section = phraseCount % 4;
  phraseCount++;

  if (section === 0) {
    // Intro + A
    t = scheduleIntro(t, tempo);
    t = scheduleSection(SECTION_A, MELODY_A, t, tempo, true, 0.85);
  } else if (section === 1) {
    // B section — lighter
    t = scheduleSection(SECTION_B, MELODY_B, t, tempo, false, 0.7);
    t = scheduleSection(SECTION_A, MELODY_A, t, tempo, true, 0.9);
  } else if (section === 2) {
    // A with full energy
    t = scheduleSection(SECTION_A, MELODY_A, t, tempo, true, 1.0);
    t = scheduleSection(SECTION_C, MELODY_B, t, tempo, true, 0.8);
  } else {
    // C variation → resolve back to A
    t = scheduleSection(SECTION_C, MELODY_B, t, tempo, false, 0.7);
    t = scheduleSection(SECTION_A, MELODY_A, t, tempo, true, 0.85);
  }

  return t;
}

// ── Public API ──

export function startMusic(): void {
  if (playing) return;
  playing = true;
  rngState = 42;
  phraseCount = 0;

  const c = ensureContext();
  if (c.state === "suspended") c.resume();

  let nextStart = c.currentTime + 0.1;

  function scheduleNext() {
    if (!playing) return;
    nextStart = scheduleFullSong(nextStart);
    const delay = (nextStart - ctx!.currentTime - 2) * 1000;
    loopTimer = window.setTimeout(scheduleNext, Math.max(200, delay));
  }

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
