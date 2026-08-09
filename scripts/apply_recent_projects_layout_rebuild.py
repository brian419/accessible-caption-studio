from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "src/accessible_caption_studio/web/final_batch.js"
text = path.read_text()

old = '''      .project-thumbnail { width:88px; height:56px; object-fit:cover; border-radius:8px; border:1px solid var(--line); background:var(--wash); grid-column:1; grid-row:1 / span 2; margin-top:.08rem; }
      .project-card .project-open:has(.project-thumbnail) { display:grid; grid-template-columns:88px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.85rem; row-gap:.08rem; align-items:start; }
      .project-card .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-card .project-open:has(.project-thumbnail) strong { grid-column:2; grid-row:1; min-width:0; margin:.05rem 0 .22rem; line-height:1.25; }
      .project-card .project-open:has(.project-thumbnail) > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; }
      .project-view-select { min-width:132px; }
      .project-grid.project-grid-compact { grid-template-columns:1fr; gap:.55rem; }
      .project-grid-compact .project-card { min-height:0; display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:.75rem; padding:.72rem .8rem; }
      .project-grid-compact .project-card:hover { transform:none; }
      .project-grid-compact .project-open { min-width:0; display:grid; grid-template-columns:40px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.7rem; row-gap:.08rem; align-items:center; }
      .project-grid-compact .project-open .project-type { grid-column:1; grid-row:1 / span 2; }
      .project-grid-compact .project-open strong { grid-column:2; grid-row:1; min-width:0; margin:0 0 .16rem; font-size:.92rem; line-height:1.25; }
      .project-grid-compact .project-open > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; }
      .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:64px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.7rem; }
      .project-grid-compact .project-open:has(.project-thumbnail) .project-thumbnail { width:64px; height:40px; grid-column:1; grid-row:1 / span 2; margin:0; }
      .project-grid-compact .project-card-actions { align-self:center; display:flex; gap:.35rem; margin:0; padding:0; border-top:0; }
      .project-grid-compact .project-action { min-height:30px; padding:.3rem .5rem; }
'''

new = '''      .project-view-select { min-width:118px; }
      .project-grid:not(.project-grid-compact) { grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:.9rem; align-items:start; }
      .project-grid:not(.project-grid-compact) .project-card { min-height:0; overflow:hidden; padding:0; display:flex; flex-direction:column; }
      .project-grid:not(.project-grid-compact) .project-open { display:flex !important; flex-direction:column; align-items:stretch; width:100%; min-width:0; padding:0 !important; }
      .project-grid:not(.project-grid-compact) .project-thumbnail { order:-2; width:100%; height:112px; object-fit:cover; display:block; margin:0; border:0; border-bottom:1px solid var(--soft-line); border-radius:0; background:var(--wash); }
      .project-grid:not(.project-grid-compact) .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-grid:not(.project-grid-compact) .project-open:not(:has(.project-thumbnail)) .project-type { margin:.9rem .9rem .05rem; }
      .project-grid:not(.project-grid-compact) .project-open > strong { width:100%; max-width:none; margin:0; padding:.8rem .9rem .22rem; font-size:.96rem; line-height:1.3; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }
      .project-grid:not(.project-grid-compact) .project-open > span:not(.project-type):not(.project-job-status) { width:100%; padding:0 .9rem .75rem; }
      .project-grid:not(.project-grid-compact) .project-job-status { margin:.05rem .9rem .75rem; }
      .project-grid:not(.project-grid-compact) .project-card-actions { margin:auto .9rem .85rem; padding-top:.7rem; }
      .project-grid:not(.project-grid-compact) .project-favorite { top:.55rem; right:.55rem; background:color-mix(in srgb,var(--paper) 86%,transparent); box-shadow:0 2px 8px rgba(20,35,70,.14); -webkit-backdrop-filter:blur(8px); backdrop-filter:blur(8px); }

      .project-grid.project-grid-compact { grid-template-columns:1fr; gap:.48rem; }
      .project-grid-compact .project-card { min-height:0; overflow:visible; display:grid; grid-template-columns:minmax(0,1fr) auto 34px; align-items:center; gap:.7rem; padding:.68rem .75rem; }
      .project-grid-compact .project-card:hover { transform:none; }
      .project-grid-compact .project-open { min-width:0; display:grid !important; grid-template-columns:44px minmax(0,1fr); grid-template-rows:auto auto; column-gap:.72rem; row-gap:.08rem; align-items:center; padding:0 !important; }
      .project-grid-compact .project-open .project-type { grid-column:1; grid-row:1 / span 2; width:40px; height:40px; margin:0; }
      .project-grid-compact .project-thumbnail { width:72px; height:44px; object-fit:cover; border-radius:7px; border:1px solid var(--line); background:var(--wash); grid-column:1; grid-row:1 / span 2; margin:0; }
      .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:72px minmax(0,1fr); }
      .project-grid-compact .project-open:has(.project-thumbnail) .project-type { display:none !important; }
      .project-grid-compact .project-open > strong { grid-column:2; grid-row:1; min-width:0; max-width:none; margin:0; padding:0; font-size:.9rem; line-height:1.25; white-space:normal; overflow-wrap:anywhere; word-break:break-word; }
      .project-grid-compact .project-open > span:not(.project-type):not(.project-job-status) { grid-column:2; grid-row:2; min-width:0; padding:0; }
      .project-grid-compact .project-job-status { grid-column:2; margin:.18rem 0 0; }
      .project-grid-compact .project-card-actions { grid-column:2; align-self:center; display:flex; gap:.35rem; margin:0; padding:0; border-top:0; }
      .project-grid-compact .project-action { min-height:30px; padding:.3rem .5rem; }
      .project-grid-compact .project-favorite { position:static; grid-column:3; justify-self:end; width:32px; height:32px; }
'''

if old not in text:
    raise SystemExit("Expected Recent Projects layout block was not found")
text = text.replace(old, new, 1)
text = text.replace('<option value="default">Default cards</option>', '<option value="default">Cards</option>', 1)

old_mobile = '''        .project-card .project-open:has(.project-thumbnail) { grid-template-columns:64px minmax(0,1fr); }
        .project-thumbnail { width:64px; height:42px; }
        .project-view-select { grid-column:1 / -1; min-width:0; }
        .project-grid-compact .project-card { grid-template-columns:1fr; align-items:stretch; }
        .project-grid-compact .project-card-actions { padding-top:.55rem; border-top:1px solid var(--soft-line); }
'''
new_mobile = '''        .project-view-select { grid-column:1 / -1; min-width:0; }
        .project-grid:not(.project-grid-compact) .project-thumbnail { height:104px; }
        .project-grid-compact .project-card { grid-template-columns:minmax(0,1fr) 34px; align-items:start; }
        .project-grid-compact .project-open { grid-column:1 / -1; grid-row:1; padding-right:2.55rem !important; }
        .project-grid-compact .project-open:has(.project-thumbnail) { grid-template-columns:58px minmax(0,1fr); }
        .project-grid-compact .project-thumbnail { width:58px; height:38px; }
        .project-grid-compact .project-card-actions { grid-column:1 / -1; grid-row:2; padding-top:.55rem; border-top:1px solid var(--soft-line); }
        .project-grid-compact .project-favorite { grid-column:2; grid-row:1; z-index:2; }
'''
if old_mobile not in text:
    raise SystemExit("Expected Recent Projects mobile layout block was not found")
text = text.replace(old_mobile, new_mobile, 1)
path.write_text(text)
