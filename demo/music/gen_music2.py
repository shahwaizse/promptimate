"""Upbeat candidates for the launch film (MusicGen-small, CC-BY-NC weights). ~30 s first pass, then extended by
continuation (conditioned on the last 10 s) so the track runs ~50 s without a loop seam."""
import sys, time
import numpy as np, scipy.io.wavfile, torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

MODEL = "facebook/musicgen-small"
CANDIDATES = {
    "upbeat_1_playful":  "upbeat playful electronic pop, bouncy bass, bright plucky synths, claps and snappy drums, happy and fun, 118 bpm, product demo music",
    "upbeat_2_funky":    "fun funky groove, slap bass, tight drums, bright electric piano stabs, cheerful and confident, 112 bpm, tech commercial",
    "upbeat_3_indie":    "feel-good indie electronic, warm synths, upbeat four-on-the-floor beat, uplifting and optimistic, 120 bpm, happy advertisement",
    "upbeat_4_chiptune": "cheerful video game inspired electronic music, chiptune lead melody over modern drums, playful and energetic, 124 bpm",
}
out_dir = sys.argv[1]
torch.manual_seed(11)
proc = AutoProcessor.from_pretrained(MODEL)
model = MusicgenForConditionalGeneration.from_pretrained(MODEL)
sr = model.config.audio_encoder.sampling_rate
for name, prompt in CANDIDATES.items():
    t = time.time()
    inputs = proc(text=[prompt], padding=True, return_tensors="pt")
    with torch.no_grad():
        first = model.generate(**inputs, do_sample=True, guidance_scale=3.5, max_new_tokens=1500)[0, 0].numpy()
        tail = first[-10 * sr:]
        cont_in = proc(audio=tail, sampling_rate=sr, text=[prompt], padding=True, return_tensors="pt")
        cont = model.generate(**cont_in, do_sample=True, guidance_scale=3.5, max_new_tokens=1000)[0, 0].numpy()
    # cont starts with the 10 s prompt audio; append only the new part
    a = np.concatenate([first, cont[len(tail):]])
    a = a / (np.abs(a).max() + 1e-9) * 0.89
    scipy.io.wavfile.write(f"{out_dir}/{name}.wav", sr, (a * 32767).astype(np.int16))
    print(f"{name}: {len(a)/sr:.1f}s in {time.time()-t:.0f}s", flush=True)
