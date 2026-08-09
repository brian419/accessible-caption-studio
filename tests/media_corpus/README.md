# Generated media regression corpus

The regression suite generates tiny local media fixtures at test time instead of checking large binary videos into Git. It covers landscape and portrait geometry, low resolution, a one-frame 4K source, MOV, WebM, audio-only WAV, non-square pixels, and long filenames. `tests/test_media_geometry.py` separately covers sample-aspect-ratio and rotation logic and performs captioned MP4 geometry exports.
