# Generated media regression corpus

The regression suite generates tiny local media fixtures at test time instead of checking large binary videos into Git. It covers landscape and portrait/mobile geometry, low resolution, a one-frame 4K source, 24/25/30/60 fps inputs, MOV, WebM, audio-only WAV, and long filenames. `tests/test_media_geometry.py` separately covers sample-aspect-ratio and rotation metadata logic and performs captioned MP4 geometry exports, including portrait and non-square-pixel normalization.
