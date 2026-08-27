(
// XYPI v11: /xypi/corner, agentName, soundName, normalizedY, normalizedX, streetDuration

SynthDef(\xypiKick, { |out=0, y=0.5, x=0.5, dur=0.5, amp=0.35|
    var base = y.clip(0, 1).linexp(0, 1, 36, 85);
    var rel = dur.clip(0.05, 1.2);
    var fenv = EnvGen.kr(Env([base * x.linlin(0, 1, 3, 8), base], [0.025], \exp));
    var env = EnvGen.kr(Env.perc(0.001, rel), doneAction: 2);
    var click = HPF.ar(WhiteNoise.ar(0.12), x.linexp(0, 1, 1500, 7000)) * EnvGen.kr(Env.perc(0.001, 0.025));
    Out.ar(out, Pan2.ar((SinOsc.ar(fenv) * env + click) * amp));
}).add;

SynthDef(\xypiSnare, { |out=0, y=0.5, x=0.5, dur=0.5, amp=0.23|
    var rel = dur.clip(0.04, 1.5);
    var bodyFreq = y.clip(0, 1).linexp(0, 1, 120, 330);
    var noise = BPF.ar(WhiteNoise.ar, x.linexp(0, 1, 900, 6500), 0.55);
    var body = SinOsc.ar(bodyFreq) * (1 - x.clip(0, 1)) * 0.7;
    var env = EnvGen.kr(Env.perc(0.002, rel), doneAction: 2);
    Out.ar(out, Pan2.ar((noise * 0.75 + body) * env * amp, x.linlin(0, 1, -0.25, 0.25)));
}).add;

SynthDef(\xypiHH, { |out=0, y=0.5, x=0.5, dur=0.2, amp=0.13|
    var rel = dur.clip(0.015, 0.8);
    var cutoff = y.clip(0, 1).linexp(0, 1, 3500, 13000);
    var noise = HPF.ar(WhiteNoise.ar, cutoff);
    var metallic = HPF.ar(Pulse.ar([5100, 6300, 7900] * x.linlin(0, 1, 0.85, 1.25), 0.45).sum * 0.04, cutoff);
    var env = EnvGen.kr(Env.perc(0.001, rel), doneAction: 2);
    Out.ar(out, Pan2.ar((noise + metallic) * env * amp, x.linlin(0, 1, -0.8, 0.8)));
}).add;

SynthDef(\xypiSine, { |out=0, y=0.5, x=0.5, dur=0.5, amp=0.15|
    var freq = y.clip(0, 1).linexp(0, 1, 80, 1800);
    var rel = dur.clip(0.03, 8.0);
    var sig = SinOsc.ar(freq) + SinOsc.ar(freq * 2, 0, x.clip(0, 1) * 0.22);
    var env = EnvGen.kr(Env.perc(0.005, rel), doneAction: 2);
    Out.ar(out, Pan2.ar(sig * env * amp, x.linlin(0, 1, -0.75, 0.75)));
}).add;

SynthDef(\xypiBass, { |out=0, y=0.5, x=0.5, dur=0.5, amp=0.18|
    var freq = y.clip(0, 1).linexp(0, 1, 32, 180);
    var rel = dur.clip(0.05, 8.0);
    var osc = VarSaw.ar(freq * [1, 1.003], width: x.linlin(0, 1, 0.08, 0.92)).sum * 0.45;
    var cutoff = x.clip(0, 1).linexp(0, 1, freq * 1.7, 3500);
    var env = EnvGen.kr(Env.perc(0.005, rel), doneAction: 2);
    Out.ar(out, Pan2.ar(LPF.ar(osc, cutoff) * env * amp));
}).add;

SynthDef(\xypiHarmonic, { |out=0, y=0.5, x=0.5, dur=0.5, amp=0.12|
    var root = y.clip(0, 1).linexp(0, 1, 70, 700);
    var rel = dur.clip(0.05, 10.0);
    var det = x.linlin(0, 1, 0.998, 1.006);
    var sig = SinOsc.ar([root, root * 1.5 * det, root * 2 / det], 0, [1, 0.72, 0.52]).sum;
    var env = EnvGen.kr(Env.perc(0.01, rel), doneAction: 2);
    Out.ar(out, Splay.ar(sig * env * amp, spread: x.clip(0, 1)));
}).add;

OSCdef(\xypiCorner, { |msg|
    var agent = msg[1].asString;
    var sound = msg[2].asString.asSymbol;
    var y = msg[3].asFloat;
    var x = msg[4].asFloat;
    var dur = msg[5].asFloat;
    var synth = switch(sound,
        \kick, { \xypiKick },
        \snare, { \xypiSnare },
        \hh, { \xypiHH },
        \sine, { \xypiSine },
        \bass, { \xypiBass },
        \harmonic, { \xypiHarmonic },
        { \xypiSine }
    );
    [\corner, agent, \sound, sound, \pitchY, y, \timbreX, x, \duration, dur].postln;
    Synth(synth, [\y, y, \x, x, \dur, dur]);
}, '/xypi/corner');
)
