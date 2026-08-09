from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src/accessible_caption_studio/web/app.js"
STYLES = ROOT / "src/accessible_caption_studio/web/styles.css"

JS_MARKER = "// major-iterations: readability and finding fixes"
CSS_MARKER = "/* major-iterations: readability and finding fixes */"

JS = r'''
// major-iterations: readability and finding fixes
(() => {
  const baseRenderFindings = renderFindings;

  function colorChannels(hex) {
    const value = normalizedHex(hex, "#000000").slice(1);
    return [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16) / 255);
  }

  function relativeLuminance(hex) {
    const linear = colorChannels(hex).map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    );
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  }

  function captionContrastRatio(first, second) {
    const firstLuminance = relativeLuminance(first);
    const secondLuminance = relativeLuminance(second);
    const lighter = Math.max(firstLuminance, secondLuminance);
    const darker = Math.min(firstLuminance, secondLuminance);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function captionStyleReadabilityFindings() {
    if (!state.project) return [];
    const style = normalizeCaptionStyle(state.project.caption_style);
    const findings = [];
    const contrast = captionContrastRatio(style.text_color, style.background_color);
    if (style.background_opacity >= 0.65 && contrast < 4.5) {
      findings.push({
        code: "style_low_contrast",
        severity: "warning",
        message: `Caption text and background colors have ${contrast.toFixed(2)}:1 contrast when the background is opaque. Choose colors with at least 4.5:1 contrast for normal-size text.`,
      });
    }
    if (style.background_opacity < 0.55 && style.outline_size_percent < 0.1 && style.shadow_size_percent < 0.1) {
      findings.push({
        code: "style_weak_video_separation",
        severity: "warning",
        message: "The caption background is highly transparent and the text has little outline or shadow. Moving video may make the caption difficult to read.",
      });
    }
    if (style.font_size_percent < 5) {
      findings.push({
        code: "style_small_text",
        severity: "info",
        message: "Caption text is very small relative to the video frame. Preview the result at the intended viewing size or increase the caption size.",
      });
    }
    if (style.max_width_percent > 94) {
      findings.push({
        code: "style_edge_crowding",
        severity: "info",
        message: "Captions can extend very close to the video edge. Reduce maximum caption width to leave a safer visual margin.",
      });
    }
    return findings;
  }

  function findingFixLabel(finding) {
    if (!finding?.cue_id) return null;
    const cue = state.project?.cues.find((item) => item.id === finding.cue_id);
    if (!cue) return null;
    const index = state.project.cues.indexOf(cue);
    const previous = index > 0 ? state.project.cues[index - 1] : null;
    const next = index + 1 < state.project.cues.length ? state.project.cues[index + 1] : null;
    const duration = Number(state.project.media?.duration || 0);
    if (["reading_speed", "long_line", "line_count"].includes(finding.code)) return "Split caption";
    if (finding.code === "too_long") return "Limit to 7 seconds";
    if (finding.code === "outside_media" && duration > cue.start) return "Clamp to media";
    if (finding.code === "too_short") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target > cue.end && (!next || target <= next.start)) return "Extend to 1 second";
    }
    if (finding.code === "overlap" && previous && previous.end < cue.end) return "Resolve overlap";
    if (finding.code === "invalid_interval") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target > cue.start && (!next || target <= next.start)) return "Repair interval";
    }
    return null;
  }

  async function applyFindingFix(finding) {
    if (!state.project || !finding?.cue_id) return;
    const cue = state.project.cues.find((item) => item.id === finding.cue_id);
    if (!cue) return;
    const index = state.project.cues.indexOf(cue);
    const previous = index > 0 ? state.project.cues[index - 1] : null;
    const next = index + 1 < state.project.cues.length ? state.project.cues[index + 1] : null;
    const duration = Number(state.project.media?.duration || 0);

    if (["reading_speed", "long_line", "line_count"].includes(finding.code)) {
      splitCue(index);
      await validateProject();
      return;
    }

    remember();
    if (finding.code === "too_long") {
      cue.end = Math.min(duration || Infinity, cue.start + 7);
    } else if (finding.code === "outside_media" && duration > cue.start) {
      cue.end = duration;
    } else if (finding.code === "too_short") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target <= cue.end || (next && target > next.start)) return;
      cue.end = target;
    } else if (finding.code === "overlap" && previous && previous.end < cue.end) {
      cue.start = previous.end;
    } else if (finding.code === "invalid_interval") {
      const target = Math.min(duration || Infinity, cue.start + 1);
      if (target <= cue.start || (next && target > next.start)) return;
      cue.end = target;
    } else {
      return;
    }
    renderCues();
    await validateProject();
  }

  async function applyStyleFindingFix(code) {
    if (!state.project) return;
    const style = normalizeCaptionStyle(state.project.caption_style);
    if (code === "style_low_contrast") {
      state.project.caption_style = normalizeCaptionStyle(captionStylePresets.high_contrast);
    } else if (code === "style_weak_video_separation") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        background_opacity: Math.max(style.background_opacity, 0.78),
        outline_size_percent: Math.max(style.outline_size_percent, 0.16),
      });
    } else if (code === "style_small_text") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        font_size_percent: Math.max(style.font_size_percent, 7.5),
      });
    } else if (code === "style_edge_crowding") {
      state.project.caption_style = normalizeCaptionStyle({
        ...style,
        preset: "custom",
        max_width_percent: Math.min(style.max_width_percent, 88),
      });
    } else return;

    renderCaptionStyleControls();
    applyCaptionStyle();
    syncPlayback();
    storeCaptionStyle(state.project.id, state.project.caption_style);
    await saveProject();
    renderFindings();
    toast("Caption appearance updated.");
  }

  function styleFixLabel(code) {
    return ({
      style_low_contrast: "Use high-contrast preset",
      style_weak_video_separation: "Strengthen background",
      style_small_text: "Increase caption size",
      style_edge_crowding: "Restore safe width",
    })[code] || null;
  }

  function appendFixButton(item, label, handler) {
    if (!label || item.querySelector(".finding-fix")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "finding-fix";
    button.textContent = label;
    button.addEventListener("click", handler);
    item.append(button);
  }

  function rebuildFindingSummary(allFindings) {
    const overview = $("#findingOverview");
    overview.replaceChildren();
    $("#findingCount").textContent = `${allFindings.length} ${allFindings.length === 1 ? "finding" : "findings"}`;
    if (!allFindings.length) {
      overview.hidden = true;
      return;
    }
    overview.hidden = false;
    ["error", "warning", "info"].forEach((severity) => {
      const count = allFindings.filter((finding) => finding.severity === severity).length;
      if (!count) return;
      const summary = document.createElement("span");
      summary.className = `finding-summary ${severity}`;
      summary.textContent = `${count} ${severity}${count === 1 ? "" : "s"}`;
      overview.append(summary);
    });
  }

  renderFindings = function renderFindingsWithAppearanceChecks() {
    baseRenderFindings();
    if (!state.project) return;
    const list = $("#findingList");
    const severityOrder = { error: 0, warning: 1, info: 2 };
    const cueFindings = [...(state.project.findings || [])]
      .sort((left, right) => severityOrder[left.severity] - severityOrder[right.severity]);
    const renderedCueFindings = [...list.querySelectorAll(".finding")];
    renderedCueFindings.forEach((item, index) => {
      const finding = cueFindings[index];
      const label = findingFixLabel(finding);
      appendFixButton(item, label, () => applyFindingFix(finding));
    });

    const styleFindings = captionStyleReadabilityFindings();
    if (styleFindings.length) {
      list.querySelector(".success-note")?.remove();
      list.tabIndex = 0;
      styleFindings.forEach((finding) => {
        const item = document.createElement("div");
        item.className = `finding ${finding.severity} style-finding`;
        const severity = document.createElement("span");
        severity.className = "finding-severity";
        severity.textContent = `${finding.severity} · caption appearance`;
        const message = document.createElement("p");
        message.textContent = finding.message;
        item.append(severity, message);
        appendFixButton(item, styleFixLabel(finding.code), () => applyStyleFindingFix(finding.code));
        list.append(item);
      });
    }
    rebuildFindingSummary([...(state.project.findings || []), ...styleFindings]);
  };

  function scheduleAppearanceCheck() {
    requestAnimationFrame(() => {
      if (state.project && !workspaceView.hidden) renderFindings();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-caption-style]").forEach((control) => {
      control.addEventListener("input", scheduleAppearanceCheck);
      control.addEventListener("change", scheduleAppearanceCheck);
    });
    $("#captionStylePreset")?.addEventListener("change", scheduleAppearanceCheck);
    $("#resetCaptionStyle")?.addEventListener("click", scheduleAppearanceCheck);
  });
})();
'''

CSS = r'''
/* major-iterations: readability and finding fixes */
.finding-fix {
  display: inline-flex !important;
  align-items: center;
  min-height: 30px;
  margin-top: .55rem;
  padding: .34rem .55rem !important;
  border: 1px solid color-mix(in srgb, var(--blue) 38%, var(--line)) !important;
  border-radius: 7px;
  color: var(--blue-dark) !important;
  background: var(--control) !important;
  font-size: .74rem !important;
}
.finding-fix:hover { background: var(--sky) !important; border-color: var(--blue) !important; }
.style-finding { border-left-color: var(--blue); }
'''


def append_once(path: Path, marker: str, addition: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")


def main() -> None:
    append_once(APP_JS, JS_MARKER, JS)
    append_once(STYLES, CSS_MARKER, CSS)


if __name__ == "__main__":
    main()
