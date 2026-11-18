"""Fast checks for the headless shorts pipeline (no GPU, no Studio, a few seconds).

    .venv\\Scripts\\python -m unittest discover tests -v

Tests that need generated working data (own sets/props in the headless cache, fonts/SFX in demo/episodes/build/_media)
skip with a hint when it is missing; `python scripts/shorts.py doctor` says how to build it.
"""
from __future__ import annotations

import contextlib
import io
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for p in ("mcp_server", "roblox/headless", "demo/episodes"):
    sys.path.insert(0, str(REPO / p))

import local_config as LC  # noqa: E402

HAVE_OWN = (LC.OWN / "props.json").exists() and (LC.OWN / "sets" / "maps").exists()
MEDIA = REPO / "demo" / "episodes" / "build" / "_media"
HAVE_FONTS = (MEDIA / "fonts").exists()


class LocalConfig(unittest.TestCase):
    def test_paths_resolve(self):
        self.assertTrue(LC.HEADLESS_CACHE.is_absolute())
        self.assertEqual(LC.OWN, LC.HEADLESS_CACHE / "own")

    def test_h264_args_shape(self):
        args = LC.h264_args(21)
        self.assertEqual(args[0], "-c:v")
        self.assertIn("-pix_fmt", args)


class Particles(unittest.TestCase):
    def test_every_kind_builds(self):
        import fx
        times = np.arange(0, 2, 1 / 30)
        for kind in fx.KINDS:
            with self.subTest(kind=kind):
                out = fx.particles(kind, np.array([0.0, 3.0, 0.0]), 0.2, 1.5, times, seed=1)
                self.assertTrue(out, kind)


@unittest.skipUnless(HAVE_OWN, "headless cache has no own sets/props: run scripts/shorts.py doctor")
class StoryCompile(unittest.TestCase):
    def test_all_stories_compile(self):
        import story_compile as SC
        stories = sorted((REPO / "demo" / "episodes" / "stories").glob("*.py"))
        self.assertTrue(stories)
        for st in stories:
            with self.subTest(story=st.stem), contextlib.redirect_stdout(io.StringIO()):
                src = SC.compile_story(SC.load(st), st.stem)
                ns: dict = {}
                exec(compile(src, st.name, "exec"), ns)       # the compiled episode is valid Python
                for key in ("LINES", "CAST", "BEATS"):
                    if key in ns:
                        self.assertTrue(ns[key], f"{st.stem}: empty {key}")
                self.assertGreater(len(ns.get("LINES", [])), 3)

    def test_catalog_lists_vocabulary(self):
        import story_compile as SC
        cat = SC.catalog()
        for word in ("ACTIONS", "FEELINGS", "PROPS", "SETS"):
            self.assertIn(word, cat)


@unittest.skipUnless(HAVE_FONTS, "no fonts in demo/episodes/build/_media/fonts: run scripts/shorts.py doctor")
class Signs(unittest.TestCase):
    def test_sign_texture(self):
        import fx
        with tempfile.TemporaryDirectory() as d:
            old = fx.TEX_OUT
            fx.TEX_OUT = Path(d)
            try:
                png = fx.sign_png("TEST SIGN: 42", "gold")
                self.assertTrue(Path(png).exists())
            finally:
                fx.TEX_OUT = old


class CompilerHelpers(unittest.TestCase):
    def test_yaw_dir_unit(self):
        import story_compile as SC
        for yaw in (0, 45, 90, 180, -90):
            x, z = SC._yaw_dir(yaw)
            self.assertAlmostEqual(math.hypot(x, z), 1.0, places=5)

    def test_speech_estimate_grows_with_text(self):
        import story_compile as SC
        self.assertLess(SC._est("one two three"), SC._est("one two three four five six seven eight nine ten"))


if __name__ == "__main__":
    unittest.main()
