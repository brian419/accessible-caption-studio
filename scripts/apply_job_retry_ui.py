from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "src/accessible_caption_studio/web/app.js"
STYLES = ROOT / "src/accessible_caption_studio/web/styles.css"

JS_MARKER = "// major-iterations: failed job retry"
CSS_MARKER = "/* major-iterations: failed job retry */"

JS = r'''
// major-iterations: failed job retry
(() => {
  const baseUpdateJobPanel = updateJobPanel;
  const retryableJobKinds = new Set(["analysis", "mp4-export", "transcript-repair", "speaker-reanalysis"]);

  function installJobRecoveryActions() {
    if ($("#jobRecoveryActions")) return;
    const panel = $("#jobPanel");
    if (!panel) return;
    const actions = document.createElement("div");
    actions.id = "jobRecoveryActions";
    actions.className = "job-recovery-actions";
    actions.hidden = true;

    const retry = document.createElement("button");
    retry.id = "retryJob";
    retry.type = "button";
    retry.className = "secondary";
    retry.textContent = "Retry";
    retry.addEventListener("click", retryFailedJob);

    const dismiss = document.createElement("button");
    dismiss.id = "dismissFailedJob";
    dismiss.type = "button";
    dismiss.className = "text-button";
    dismiss.textContent = "Dismiss";
    dismiss.addEventListener("click", dismissFailedJob);

    actions.append(retry, dismiss);
    panel.append(actions);
  }

  updateJobPanel = function updateJobPanelWithRecovery(job) {
    baseUpdateJobPanel(job);
    installJobRecoveryActions();
    const actions = $("#jobRecoveryActions");
    const retry = $("#retryJob");
    const failed = job?.state === "failed";
    actions.hidden = !failed;
    if (!failed) return;
    const retryable = retryableJobKinds.has(job.kind);
    retry.hidden = !retryable;
    if (retryable) {
      retry.textContent = job.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
    }
  };

  pollJob = async function pollJobWithFailureRecovery() {
    if (!state.activeJob || !state.activeJobProjectId) return;
    const trackedJobId = state.activeJob.id;
    const trackedProjectId = state.activeJobProjectId;
    const trackedProjectName = state.activeJobProjectName;
    try {
      const job = await api(`/api/projects/${trackedProjectId}/jobs/${trackedJobId}`);
      if (state.activeJob?.id !== trackedJobId || String(state.activeJobProjectId) !== String(trackedProjectId)) return;
      state.activeJob = job;
      updateJobPanel(job);
      if (activeJobStates.has(job.state)) {
        state.pollTimer = setTimeout(pollJob, 1100);
        return;
      }

      const viewingTrackedProject = !workspaceView.hidden
        && String(state.project?.id) === String(trackedProjectId);

      if (job.state === "completed") {
        const completedProject = await api(`/api/projects/${trackedProjectId}`);
        if (viewingTrackedProject) {
          state.project = completedProject;
          renderProject();
          if (job.kind === "mp4-export") {
            const artifact = state.project.exports.find((item) => item.format === "mp4");
            if (artifact) showExportComplete(artifact);
          } else if (job.kind === "overlap-analysis" && job.result) {
            showOverlapProposal(job.result);
          } else if (job.kind === "speaker-reanalysis" && job.result) {
            showSpeakerProposal(job.result, job.id);
          } else if (job.kind === "transcript-repair" && job.result) {
            showTranscriptProposal(job.result, job.id);
          } else {
            toast("Automatic captions are ready.");
          }
        } else {
          if (!homeView.hidden) await loadProjects();
          toast(`${trackedProjectName} finished processing.`);
        }
        clearFinishedJobSoon(job.id);
        return;
      }

      if (job.state === "failed") {
        const message = job.error || job.message || `${trackedProjectName} could not be processed.`;
        toast(message, "error");
        $("#jobPanel").hidden = false;
        updateJobPanel(job);
        if (!retryableJobKinds.has(job.kind)) {
          $("#jobMessage").textContent = `${message} Restart this operation from its original project control.`;
        }
        syncActiveJobIndicators();
        return;
      }

      if (job.state === "cancelled") {
        toast(`Processing cancelled for ${trackedProjectName}. Saved work was not changed.`);
        clearFinishedJobSoon(job.id);
      }
    } catch (error) {
      toast(error.message, "error");
    }
  };

  function clearFinishedJobSoon(jobId) {
    setTimeout(() => {
      if (state.activeJob?.id !== jobId) return;
      clearTrackedJob();
    }, 1800);
  }

  function clearTrackedJob() {
    clearTimeout(state.pollTimer);
    $("#jobPanel").hidden = true;
    state.activeJob = null;
    state.activeJobProjectId = null;
    state.activeJobProjectName = "";
    syncActiveJobIndicators();
  }

  function dismissFailedJob() {
    if (state.activeJob?.state !== "failed") return;
    clearTrackedJob();
  }

  async function retryFailedJob() {
    if (state.activeJob?.state !== "failed" || !state.activeJobProjectId) return;
    const failedJob = state.activeJob;
    const projectId = state.activeJobProjectId;
    const retryButton = $("#retryJob");
    retryButton.disabled = true;
    retryButton.textContent = "Starting…";
    try {
      const project = await api(`/api/projects/${projectId}`);
      let job;
      if (failedJob.kind === "analysis") {
        job = await api(`/api/projects/${projectId}/analyze`, { method: "POST" });
      } else if (failedJob.kind === "mp4-export") {
        job = await api(`/api/projects/${projectId}/exports/mp4`, { method: "POST" });
      } else if (failedJob.kind === "transcript-repair") {
        job = await api(`/api/projects/${projectId}/repair-transcript`, { method: "POST" });
      } else if (failedJob.kind === "speaker-reanalysis") {
        job = await api(`/api/projects/${projectId}/reanalyze-speakers`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ expected_speaker_count: project.expected_speaker_count ?? null }),
        });
      } else {
        toast("This operation needs its original inputs and must be restarted from the project.", "error");
        return;
      }
      monitorJob(job, projectId, project.name);
      toast(`Retry started for ${project.name}.`);
    } catch (error) {
      toast(error.message, "error");
      updateJobPanel(failedJob);
    } finally {
      retryButton.disabled = false;
      if (state.activeJob?.state === "failed") {
        retryButton.textContent = state.activeJob.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", installJobRecoveryActions);
})();
'''

CSS = r'''
/* major-iterations: failed job retry */
.job-recovery-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: .45rem;
  grid-column: 1 / -1;
  padding-top: .55rem;
  border-top: 1px solid color-mix(in srgb, var(--blue) 22%, var(--line));
}
.job-recovery-actions .secondary,
.job-recovery-actions .text-button { min-height: 34px; padding: .4rem .65rem; font-size: .76rem; }
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
