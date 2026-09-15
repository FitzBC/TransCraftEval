const $ = (id) => document.getElementById(id);
const stateLabels = { queued: "排队中", running: "逐帧分析中", completed: "分析完成", failed: "任务失败" };
const fmt = (seconds) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

fetch("/api/settings").then((r) => r.json()).then((s) => {
  $("video-path").value = s.video_path || "";
  $("reference-path").value = s.reference_image_path || "";
  $("person").value = s.person_name || "测试人物";
});

function render(job) {
  $("status").className = `status ${job.status}`;
  $("status").textContent = `● ${stateLabels[job.status]}`;
  $("progress").classList.toggle("hidden", !["queued", "running"].includes(job.status));
  $("progress-label").textContent = `${Math.round(job.progress * 100)}%`;
  $("progress-bar").style.width = `${job.progress * 100}%`;
  if (job.status === "failed") {
    $("result-title").textContent = "任务失败";
    $("result-body").className = "error";
    $("result-body").textContent = job.error || "未知错误";
    return;
  }
  if (job.status !== "completed") {
    $("result-title").textContent = "正在扫描视频";
    $("result-body").className = "empty";
    $("result-body").innerHTML = "⌾<span>逐帧扫描中，约需一分钟，请保持页面打开。</span>";
    return;
  }
  $("result-title").textContent = "发现人物出现线索";
  const confirmed = job.events.filter((event) => event.decision === "confirmed").length;
  const cards = job.events.map((event, index) => `
    <article class="event">
      <img src="${event.evidence_image}" alt="证据帧" />
      <div class="event-info"><div><em class="${event.decision}">${event.decision === "confirmed" ? "自动确认" : "建议复核"}</em><small>线索 ${String(index + 1).padStart(2, "0")}</small><h3>${event.person_name}</h3></div>
      <dl><div><dt>时间段</dt><dd>${fmt(event.start_seconds)}–${fmt(event.end_seconds)}</dd></div><div><dt>最高分</dt><dd>${event.best_score.toFixed(3)}</dd></div><div><dt>支持帧</dt><dd>${event.support_frames ?? "—"}</dd></div></dl></div>
    </article>`).join("");
  $("result-body").className = "results";
  $("result-body").innerHTML = `<div class="metrics"><div>✓<span>自动确认</span><b>${confirmed}</b></div><div>✦<span>待人工复核</span><b>${job.events.length - confirmed}</b></div><div>◴<span>扫描完成</span><b>100%</b></div></div>${cards || '<div class="empty"><span>未发现超过复核阈值的线索。</span></div>'}<p class="note">◷ 相似分数不是概率。本演示阈值仅根据当前片段初步标定；低分线索保留人工复核，以降低跨年龄照片造成的漏检。</p>`;
}

async function poll(jobId) {
  const job = await fetch(`/api/jobs/${jobId}`).then((r) => r.json());
  render(job);
  if (["queued", "running"].includes(job.status)) window.setTimeout(() => poll(jobId), 700);
  else $("submit").disabled = false;
}

$("job-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("submit").disabled = true;
  const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_path: $("video-path").value, reference_image_path: $("reference-path").value, person_name: $("person").value, run_async: true }) });
  const data = await response.json();
  if (!response.ok) { render({ status: "failed", progress: 0, error: data.detail }); $("submit").disabled = false; return; }
  render({ ...data, progress: 0, events: [] }); poll(data.job_id);
});
