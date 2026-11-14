"""Generate background music with Meta MusicGen (CC-BY-NC weights) on CPU. Run inside the WSL venv."""
import sys, time
import numpy as np, scipy.io.wavfile, torch
from transformers import AutoProcessor, MusicgenForConditionalGeneration

MODEL = "facebook/musicgen-small"
TRACKS = {
    "music_A": "warm minimal electronic groove, soft plucked synths and light percussion, building to a bright uplifting chorus, 115 bpm, modern tech product video",
    "music_B": "punchy minimal electronic beat, crisp drums, playful bouncy bass, confident and energetic, 120 bpm, modern",
    "music_C": "low tense minimal synth pulse with ticking hi-hats, slowly building into a warm hopeful synth resolution, 100 bpm, cinematic tech",
}
out_dir = sys.argv[1]
only = set(sys.argv[2:])
torch.manual_seed(7)
proc = AutoProcessor.from_pretrained(MODEL)
model = MusicgenForConditionalGeneration.from_pretrained(MODEL)
sr = model.config.audio_encoder.sampling_rate
for name, prompt in TRACKS.items():
    if only and name not in only: continue
    t = time.time()
    inputs = proc(text=[prompt], padding=True, return_tensors="pt")
    with torch.no_grad():
        audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=1500)  # ~30 s at 50 tokens/s
    a = audio[0, 0].numpy()
    a = a / (np.abs(a).max() + 1e-9) * 0.89
    scipy.io.wavfile.write(f"{out_dir}/{name}.wav", sr, (a * 32767).astype(np.int16))
    print(f"{name}: {len(a)/sr:.1f}s in {time.time()-t:.0f}s", flush=True)
