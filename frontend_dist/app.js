const $ = (id) => document.getElementById(id);
const labels = { draft: "草稿", ready: "待执行", running: "执行中", needs_review: "待人工复核", completed: "已完成", ready_for_material: "待接入素材", ready_for_validation: "待技术验证", active: "已启用" };
const libraryMeta = {
  person: { title: "人物库", action: "新建人物", description: "管理需在媒资中召回和复核的具体人物；人物条目须有清晰、可用的本地参考素材。", idHint: "person.example", classificationHint: "例如：影视演员", columns: ["人物", "分类", "别名", "参考素材", "状态", "审核说明"] },
  text: { title: "文本规则库", action: "新建文本规则", description: "管理 OCR、ASR 的审核词、词组与变体规则。词表种子必须经分类和确认条件治理后才能启用。", idHint: "text.rule", classificationHint: "例如：语义类别", columns: ["规则名称", "分类", "别名 / 变体", "召回通道", "状态", "审核说明"] },
  content: { title: "场景与行为库", action: "新建内容对象", description: "管理需从画面、文字与语音中召回的场景、物体和行为；模型结果只作为候选证据。", idHint: "content.object", classificationHint: "例如：场景规则", columns: ["内容对象", "分类", "别名 / 标签", "证据通道", "状态", "审核说明"] },
};
let allItems = [];
let activeCategory = "person";
const esc = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));

function setView(view, category = activeCategory) {
  activeCategory = category;
  document.querySelectorAll(".view").forEach((node) => node.classList.toggle("active", node.id === `${view}-view`));
  document.querySelectorAll(".nav-item").forEach((node) => node.classList.toggle("active", node.dataset.view === view && (!node.dataset.category || node.dataset.category === category)));
  const title = view === "library" ? libraryMeta[category].title : view === "analysis" ? "技术验证" : "审核总览";
  $("breadcrumb").textContent = view === "library" ? `审核对象库 / ${title}` : `审核工作台 / ${title}`;
  $("page-title").textContent = title;
  if (view === "library") renderLibrary();
}

function renderSummary(overview) {
  const counts = overview.library_counts;
  $("person-count").textContent = counts.person;
  $("text-count").textContent = counts.text;
  $("content-count").textContent = counts.content;
  $("summary-grid").innerHTML = [["审核任务", overview.task_count, overview.task_count ? "任务数据已保存" : "创建首个审核任务"], ["人物库", counts.person, "人物及参考素材"], ["文本规则库", counts.text, "OCR / ASR 规则"], ["场景与行为库", counts.content, "内容召回策略"]].map(([name, count, note]) => `<article class="summary-card"><span>${name}</span><b>${count}</b><small>${note}</small></article>`).join("");
}

function renderTasks(tasks) {
  $("task-list").innerHTML = tasks.length ? `<div class="task-table">${tasks.map((task) => `<article><div><strong>${esc(task.name)}</strong><code>${esc(task.asset_path)}</code></div><div><span class="muted">关联对象</span><p>${task.object_ids.length ? task.object_ids.map(esc).join(" · ") : "未关联对象"}</p></div><div><span class="status-badge ${esc(task.status)}">${labels[task.status]}</span><small>人脸：已接入；其余通道待配置</small></div></article>`).join("")}</div>` : `<div class="empty-library"><h3>还没有审核任务</h3><p>先创建任务并关联视频与审核对象，系统才会开始产生真实的作业状态。</p><button class="primary" type="button" data-create-task>创建审核任务</button></div>`;
}

function taskOptions() { $("task-objects").innerHTML = allItems.map((item) => `<option value="${esc(item.item_id)}">${esc(item.name)} · ${libraryMeta[item.category].title}</option>`).join(""); }
function openTaskDialog() { $("task-error").classList.add("hidden"); $("task-form").reset(); taskOptions(); $("task-dialog").showModal(); }
async function submitTask(event) {
  event.preventDefault();
  const submit=event.submitter;
  if(submit?.disabled)return;
  const objectIds = [...$("task-person-options").querySelectorAll('input:checked')].map(input=>input.value);
  if(!objectIds.length||!$('task-asset-path').value.trim()){$('task-error').textContent='请选择一部媒资和至少一位需要核查的人物。';$('task-error').classList.remove('hidden');return;}
  if(submit)submit.disabled=true;
  try {
  const response = await fetch(editingTaskId?`/api/review-tasks/${editingTaskId}/scope`:"/api/review-tasks", { method: editingTaskId?'PUT':"POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: $("task-name-input").value.trim(), asset_path: $("task-asset-path").value.trim(), object_ids: objectIds, purpose:activePurpose, capabilities:['face'] }) });
  if (!response.ok) { const body = await response.json(); $("task-error").textContent = body.detail || "无法创建任务"; $("task-error").classList.remove("hidden"); return; }
  const task=await response.json();
  if(editingTaskId){$("task-dialog").close();await loadApp();await openReview(task.task_id);return;}
  const started=await fetch(`/api/review-tasks/${task.task_id}/run`,{method:'POST'});
  $("task-dialog").close(); await loadApp(); await openReview(task.task_id);
  if(!started.ok){const error=await started.json();$('review-error').textContent=error.detail||'任务已保存，请稍后从任务列表开始检查。';}
  } catch(error){$('task-error').textContent='请求未完成，请先关闭窗口并检查任务列表，避免重复提交。';$('task-error').classList.remove('hidden');}
  finally{if(submit)submit.disabled=false;}
}

function filteredItems() {
  const query = $("library-search").value.trim().toLowerCase();
  const state = $("library-status-filter").value;
  const classification = $("library-classification-filter").value;
  return allItems.filter((item) => item.category === activeCategory && (state === "all" || item.status === state) && (classification === "all" || item.classification === classification) && (!query || [item.name, item.item_id, item.classification, ...item.aliases].join(" ").toLowerCase().includes(query)));
}
function renderLibrary() {
  const meta = libraryMeta[activeCategory];
  $("library-title").textContent = meta.title; $("library-description").textContent = meta.description; $("library-create").textContent = meta.action;
  $("library-table-head").innerHTML = `<tr>${meta.columns.map((column) => `<th>${column}</th>`).join("")}</tr>`;
  const filter = $("library-classification-filter"); const selection = filter.value;
  const classes = [...new Set(allItems.filter((item) => item.category === activeCategory).map((item) => item.classification || "未分类"))];
  filter.innerHTML = `<option value="all">全部分类</option>${classes.map((value) => `<option value="${esc(value)}">${esc(value)}</option>`).join("")}`; filter.value = classes.includes(selection) ? selection : "all";
  const items = filteredItems(); $("library-result-count").textContent = `共 ${items.length} 条`;
  $("library-table-body").innerHTML = items.map((item) => { const material = item.category === "person" ? `<button class="link-button" data-materials-id="${esc(item.item_id)}" type="button">${item.materials?.length || 0} 份素材</button>` : "<span class=\"muted\">待接入</span>"; return `<tr><td><strong>${esc(item.name)}</strong><code>${esc(item.item_id)}</code></td><td><span class="classification">${esc(item.classification)}</span></td><td>${item.aliases.length ? item.aliases.map((alias) => `<span class="token">${esc(alias)}</span>`).join("") : "<span class=\"muted\">暂无别名</span>"}</td><td>${material}</td><td><span class="status-badge ${esc(item.status)}">${labels[item.status]}</span></td><td class="definition">${esc(item.definition)}</td></tr>`; }).join("");
  $('library-table-head').querySelector('tr').insertAdjacentHTML('beforeend','<th>操作</th>');
  [...$('library-table-body').querySelectorAll('tr')].forEach((row,index)=>row.insertAdjacentHTML('beforeend',`<td><button class="quiet" data-edit-object="${esc(items[index].item_id)}">编辑</button></td>`));
  $("library-empty").classList.toggle("hidden", items.length !== 0);
}
let editingLibraryId=null;
function openLibraryDialog() { editingLibraryId=null; $("item-id").disabled=false; $("item-category").disabled=false; const meta = libraryMeta[activeCategory]; $("library-error").classList.add("hidden"); $("library-form").reset(); $("item-category").value = activeCategory; $("item-id").placeholder = meta.idHint; $("item-classification").placeholder = meta.classificationHint; $("dialog-title").textContent = meta.action; $("library-dialog").showModal(); }
async function submitLibrary(event) {
  event.preventDefault(); const payload = { item_id: editingLibraryId || `${$('item-category').value}.${crypto.randomUUID()}`, category: $("item-category").value, classification: $("item-classification").value.trim(), name: $("item-name").value.trim(), aliases: $("item-aliases").value.split(",").map((value) => value.trim()).filter(Boolean), definition: $("item-definition").value.trim(), status: $("item-status").value };
  const response = await fetch(editingLibraryId?`/api/library-items/${encodeURIComponent(editingLibraryId)}`:"/api/library-items", { method: editingLibraryId?"PUT":"POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); if (!response.ok) { const body = await response.json(); $("library-error").textContent = body.detail || "无法保存条目"; $("library-error").classList.remove("hidden"); return; } $("library-dialog").close(); await loadApp(); renderLibrary();
}
async function showMaterials(itemId) { const item = allItems.find((candidate) => candidate.item_id === itemId); if (!item) return; $("material-dialog-title").textContent = `${item.name} · 参考素材`; $("material-list").innerHTML = "<p class=\"muted\">正在加载…</p>"; $("material-dialog").showModal(); const materials = await fetch(`/api/library-items/${encodeURIComponent(itemId)}/materials`).then((response) => response.json()); $("material-list").innerHTML = materials.length ? materials.map((material) => { const preview = material.kind === "reference_image" ? `<img src="${esc(material.local_uri)}" alt="${esc(material.title)}"/>` : "<div class=\"material-video\">本地视频素材</div>"; return `<article class="material-card">${preview}<div><h3>${esc(material.title)}</h3><span class="status-badge ready_for_validation">待技术验证</span><p>${esc(material.quality_note)}</p></div></article>`; }).join("") : "<p class=\"muted\">暂无参考素材。</p>"; }
function renderJob(job) { const node = $("job-result"); if (job.status === "failed") { node.className = "job-result error"; node.textContent = job.error || "任务失败"; return; } if (job.status !== "completed") { node.className = "job-result empty"; node.innerHTML = `<p>${job.status === "running" ? "正在分析" : "已提交"}</p>`; return; } node.className = "job-result"; node.innerHTML = `<p>完成：${job.events.length} 组候选证据。结果仅作人工复核线索。</p>`; }
async function poll(jobId) { const job = await fetch(`/api/jobs/${jobId}`).then((response) => response.json()); renderJob(job); if (["queued", "running"].includes(job.status)) setTimeout(() => poll(jobId), 700); else $("submit").disabled = false; }
async function loadApp() { const [overview, items, settings] = await Promise.all([fetch("/api/overview").then((r) => r.json()), fetch("/api/library-items").then((r) => r.json()), fetch("/api/settings").then((r) => r.json())]); allItems = items; $("person").value = settings.person_name || ""; $("video-path").value = settings.video_path || ""; $("reference-path").value = settings.reference_image_path || ""; renderSummary(overview); renderTasks(overview.tasks); renderLibrary(); }
document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view, button.dataset.category || activeCategory)));
$("new-task").addEventListener("click", openTaskDialog); $("dashboard-create").addEventListener("click", openTaskDialog); $("close-task").addEventListener("click", () => $("task-dialog").close()); $("task-form").addEventListener("submit", submitTask); $("library-create").addEventListener("click", openLibraryDialog); $("close-library").addEventListener("click", () => $("library-dialog").close()); $("library-form").addEventListener("submit", submitLibrary); $("library-search").addEventListener("input", renderLibrary); $("library-classification-filter").addEventListener("change", renderLibrary); $("library-status-filter").addEventListener("change", renderLibrary); $("library-table-body").addEventListener("click", (event) => { const button = event.target.closest("[data-materials-id]"); if (button) showMaterials(button.dataset.materialsId); }); $("close-materials").addEventListener("click", () => $("material-dialog").close()); $("task-list").addEventListener("click", (event) => { if (event.target.matches("[data-create-task]")) openTaskDialog(); });
$("job-form").addEventListener("submit", async (event) => { event.preventDefault(); $("submit").disabled = true; const response = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ video_path: $("video-path").value, reference_image_path: $("reference-path").value, person_name: $("person").value, run_async: true }) }); const data = await response.json(); if (!response.ok) { renderJob({ status: "failed", error: data.detail }); $("submit").disabled = false; return; } renderJob(data); poll(data.job_id); });
loadApp().catch((error) => { $("task-list").textContent = `加载失败：${error.message}`; });
