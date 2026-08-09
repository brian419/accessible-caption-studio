from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "src/accessible_caption_studio/web/final_batch.js"
TEST = ROOT / "tests/browser/test_browser_ui.py"

js = JS.read_text()
replacements = {
    '      .caption-track-bar { display:grid; gap:.65rem; margin:.05rem 0 .85rem; padding:.72rem 0 .8rem; border-top:1px solid var(--soft-line); border-bottom:1px solid var(--soft-line); background:transparent; }':
    '      .caption-track-bar { display:grid; gap:1rem; margin:0 0 .85rem; padding:1rem 1rem 1.05rem; border-top:0; border-bottom:1px solid var(--soft-line); background:transparent; }',
    '      .caption-track-heading > div { min-width:0; display:flex; flex-wrap:wrap; align-items:baseline; gap:.4rem .65rem; }':
    '      .caption-track-heading > div { min-width:0; display:grid; gap:.18rem; }',
    '      .caption-track-description { color:var(--muted); font-size:.72rem; line-height:1.4; }':
    '      .caption-track-description { color:var(--muted); font-size:.74rem; line-height:1.45; }',
    '      .caption-track-controls { min-width:0; display:grid; grid-template-columns:minmax(230px,.9fr) minmax(270px,1.1fr); gap:.75rem; align-items:end; }':
    '      .caption-track-controls { min-width:0; display:grid; grid-template-columns:1fr; gap:1rem; align-items:stretch; }',
    '      .caption-track-current { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:.5rem; }':
    '      .caption-track-current { min-width:0; display:grid; grid-template-columns:minmax(240px,320px) auto; align-items:end; justify-content:start; gap:.75rem; }',
    '      .caption-track-create { min-width:0; display:grid; gap:.28rem; }':
    '      .caption-track-create { min-width:0; display:grid; gap:.38rem; max-width:560px; }',
    '      .caption-track-field { display:grid; gap:.28rem; min-width:0; font-size:.72rem; font-weight:800; color:var(--muted); }':
    '      .caption-track-field { display:grid; gap:.38rem; min-width:0; font-size:.72rem; font-weight:800; color:var(--muted); }',
    '      .caption-track-status { display:inline-flex; align-items:center; align-self:end; min-height:30px; padding:.3rem .55rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }':
    '      .caption-track-status { display:inline-flex; align-items:center; align-self:end; justify-self:start; min-height:34px; padding:.35rem .65rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }',
    '      .caption-track-add { min-width:0; display:grid; grid-template-columns:minmax(170px,1fr) auto; gap:.4rem; align-items:end; }':
    '      .caption-track-add { min-width:0; display:grid; grid-template-columns:minmax(260px,1fr) auto; gap:.55rem; align-items:end; }',
    '      .caption-track-actions { display:flex; flex-wrap:wrap; align-items:center; gap:.4rem; min-width:0; }':
    '      .caption-track-actions { display:grid; grid-template-columns:repeat(3,max-content); align-items:center; justify-content:start; gap:.45rem .5rem; min-width:0; }',
    '      .caption-track-actions-label { margin-right:.1rem; color:var(--muted); font-size:.68rem; font-weight:850; }':
    '      .caption-track-actions-label { grid-column:1 / -1; margin:0 0 .05rem; color:var(--muted); font-size:.68rem; font-weight:850; }',
    '      @media (max-width:760px) {\n        .caption-track-controls { grid-template-columns:1fr; align-items:stretch; }\n        .caption-track-current { grid-template-columns:minmax(0,1fr) auto; }\n        .caption-track-actions { align-items:flex-start; }\n      }':
    '      @media (max-width:680px) {\n        .caption-track-bar { padding:.9rem .85rem 1rem; }\n        .caption-track-current { grid-template-columns:1fr; align-items:stretch; gap:.45rem; }\n        .caption-track-status { align-self:start; }\n        .caption-track-create { max-width:none; }\n        .caption-track-actions { grid-template-columns:repeat(2,max-content); }\n      }',
    '      @media (max-width:480px) {\n        .caption-track-current { grid-template-columns:1fr; align-items:stretch; }\n        .caption-track-status { justify-self:start; }\n        .caption-track-add { grid-template-columns:1fr; }\n        .caption-track-add button { width:100%; }\n        .caption-track-actions { align-items:stretch; }\n        .caption-track-actions-label { flex-basis:100%; }\n      }':
    '      @media (max-width:480px) {\n        .caption-track-add { grid-template-columns:1fr; }\n        .caption-track-add button { width:100%; }\n        .caption-track-actions { grid-template-columns:1fr; align-items:stretch; }\n        .caption-track-actions button { width:100%; }\n        .caption-track-actions-label { grid-column:1; }\n      }',
}

for old, new in replacements.items():
    if old not in js:
        raise SystemExit(f"Expected final_batch.js fragment not found:\n{old}")
    js = js.replace(old, new, 1)
JS.write_text(js)

test = TEST.read_text()
old_field = '            currentTop: Math.round(current.top),'
new_field = '            currentBottom: Math.round(current.bottom),'
old_assert = '    assert abs(desktop["currentTop"] - desktop["createTop"]) <= 2'
new_assert = '    assert desktop["createTop"] >= desktop["currentBottom"] + 8'
for old, new in ((old_field, new_field), (old_assert, new_assert)):
    if old not in test:
        raise SystemExit(f"Expected browser-test fragment not found:\n{old}")
    test = test.replace(old, new, 1)
TEST.write_text(test)
