Object.assign(labels,{failed:'检查未完成',ready:'待检查',running:'系统检查中',needs_review:'待人工复核',completed:'审核已完成',ready_for_validation:'待确认',ready_for_material:'待添加照片'});
const verdictNames = {pending:'未处理', confirmed:'已确认出现', rejected:'已排除', uncertain:'留待复核'};
const taskName=t=>t.name.replace(/^端到端验证\s*·\s*/,'').replace(/^多人物验证\s*·\s*/,'抽检 · ').replace(/^演员召回验证\s*·\s*/,'').replace(/（1秒采样）/g,'');
let selectedTask = null, selectedEvent = null, taskTimer = null;
let workspaceMode='dashboard', cachedTasks=[], lastTasksMarkup='';
let activePurpose=new URLSearchParams(location.search).get('workspace')==='validation'?'validation':'production', editingTaskId=null, reviewBusy=false, navigationVersion=0;
$('workspace-purpose').value=activePurpose;
let mediaItems=[];
async function refreshMedia(){
  $('media-summary').textContent='正在读取本地媒资…';
  try{mediaItems=await reviewRequest('/api/local-media');renderMedia();}
  catch(error){$('media-summary').textContent=error.message;}
}
function renderMedia(){
  const query=$('media-search').value.trim();
  const rows=mediaItems.filter(m=>m.name.includes(query));
  $('media-summary').textContent=`共 ${rows.length} 个本地片段或视频`;
  $('media-grid').innerHTML=rows.map(m=>`<article class="media-card">${m.url?`<video controls preload="none" playsinline poster="${esc(m.poster||'')}" aria-label="预览${esc(m.name)}" src="${esc(m.url)}"></video>`:'<div class="media-placeholder">本地视频</div>'}<div><h2>${esc(m.name)}</h2><p>${m.duration_seconds?`${Math.round(m.duration_seconds)} 秒 · `:''}${(m.size_bytes/1048576).toFixed(1)} MB${m.source_start_seconds!==undefined?` · 原片约 ${timeLabel(m.source_start_seconds)}`:''}</p><small>${esc(m.selection_note||'本地文件，可创建人物检查任务')}</small><div class="media-actions">${m.task_id?`<button class="primary" data-media-review="${esc(m.task_id)}">查看待复核片段</button>`:''}<button class="quiet" data-media-create="${esc(m.path)}">新建检查任务</button></div></div></article>`).join('')||'<p>没有匹配的本地媒资。</p>';
}
$('media-search').oninput=renderMedia;
$('media-grid').addEventListener('play',event=>document.querySelectorAll('#media-grid video').forEach(v=>{if(v!==event.target)v.pause();}),true);
$('media-grid').onclick=async event=>{
  const review=event.target.closest('[data-media-review]'),create=event.target.closest('[data-media-create]');
  try{if(review)await openReview(review.dataset.mediaReview);if(create){await openTaskDialog();$('task-asset-path').value=create.dataset.mediaCreate;$('task-local-media').value=create.dataset.mediaCreate;$('task-name-input').value=mediaItems.find(m=>m.path===create.dataset.mediaCreate).name+' · 人物检查';}}
  catch(error){$('media-summary').textContent=error.message;}
};
let playbackVersion=0, previewQueue=Promise.resolve();
const previewCache=new Map();
function preparePreview(taskId,eventId){
  const key=`${taskId}/${eventId}`;
  if(previewCache.has(key))return previewCache.get(key);
  const pending=previewQueue.catch(()=>{}).then(async()=>{
    for(let attempt=0;attempt<8;attempt++){
      const response=await fetch(`/api/review-tasks/${taskId}/events/${eventId}/preview`,{method:'POST'});
      const data=await response.json();
      if(response.ok)return data;
      if(response.status!==409||attempt===7)throw new Error(data.detail||'片段暂时无法播放');
      await new Promise(resolve=>setTimeout(resolve,700));
    }
  });
  previewCache.set(key,pending);previewQueue=pending;
  pending.catch(()=>previewCache.delete(key));
  if(previewCache.size>30)previewCache.delete(previewCache.keys().next().value);
  return pending;
}
function visibleEvidence(){
  const filter=$('review-filter').value;
  return (selectedTask?.result?.events||[]).filter(e=>filter==='all'||(e.review_status||'pending')===filter);
}
async function playEvidence(){
  if(!selectedTask||!selectedEvent)return;
  const taskId=selectedTask.task_id,eventId=selectedEvent,version=++playbackVersion;
  const current=()=>version===playbackVersion&&selectedTask?.task_id===taskId&&selectedEvent===eventId;
  const video=$('review-video');
  video.hidden=false;video.poster=$('review-image').src;$('review-image').hidden=true;
  $('video-hint').hidden=false;$('video-hint').textContent='正在准备片段，首次打开需稍候…';
  $('show-video').textContent='准备中…';
  try{
    const preview=await preparePreview(taskId,eventId);if(!current())return;
    video.src=preview.url;
    $('video-hint').textContent=`当前媒资约 ${timeLabel(preview.start_seconds)} 起的短片段 · 默认静音，可在播放器开启声音`;
    try{await video.play();}catch(error){if(current())$('video-hint').textContent='片段已准备好，点击播放器即可播放。';}
    if(!current())return;
    const events=visibleEvidence(),next=events[events.findIndex(e=>e.event_id===eventId)+1];
    if(next)preparePreview(taskId,next.event_id).catch(()=>{});
  }catch(error){if(current()){video.hidden=true;$('review-image').hidden=false;$('video-hint').textContent=`${error.message}。已显示备用画面，可点击“重播片段”重试。`;}}
  finally{if(current())$('show-video').textContent='重播片段';}
}
labels.disabled='已停用'; labels.ready_for_validation='待验证';
document.querySelector('main.content').appendChild($('review-dialog'));
const originalSetView=setView;
setView=function(view,category=activeCategory) {
  if(reviewBusy)return;
  navigationVersion++;
  if(view!=='media')document.querySelectorAll('#media-grid video').forEach(v=>v.pause());
  document.body.classList.toggle('in-review',view==='review');
  if(view!=='review')history.replaceState(null,'',view==='library'?`#library/${category}`:`#${view}`);
  if(view!=='review') { $('review-video').pause(); selectedTask=null; selectedEvent=null; }
  if(['tasks','queue','reports','dashboard'].includes(view)) {
    workspaceMode=view; originalSetView('dashboard',category);
    const titles={dashboard:'工作台',tasks:'审核任务',queue:'待我复核',reports:'审核记录'};
    $('page-title').textContent=titles[view]; $('breadcrumb').textContent=`审核工作台 / ${titles[view]}`;
    $('tasks-heading').textContent=view==='queue'?'待处理任务':view==='reports'?'已有检查结果的任务':'全部审核任务';
    $('summary-grid').hidden=view!=='dashboard';
    $('task-status-filter').value='all'; $('task-search').value='';
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.view===view));
    renderTasks(cachedTasks);
  } else if(view==='review') {
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.view==='tasks'));
    document.querySelectorAll('.view').forEach(n=>n.classList.toggle('active',n.id==='review-dialog'));
    $('page-title').textContent='片段复核'; $('breadcrumb').textContent='审核任务 / 人物出镜';
  } else if(view==='media') {
    originalSetView(view,category);$('page-title').textContent='媒资库';$('breadcrumb').textContent='本地工作空间 / 媒资库';refreshMedia();
  } else originalSetView(view,category);
};
const timeLabel = (seconds=0) => { const s=Math.floor(seconds); return `${Math.floor(s/3600).toString().padStart(2,'0')}:${Math.floor(s/60)%60<10?'0':''}${Math.floor(s/60)%60}:${(s%60).toString().padStart(2,'0')}`; };
async function reviewRequest(url, options={}) {
  if(options.method==='PATCH'&&url.includes('/events/'))options.body=JSON.stringify({...JSON.parse(options.body),reason:$('review-reason').value});
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
function taskStats(task) {
  const events=task.result?.events || [];
  return Object.fromEntries(['pending','confirmed','rejected','uncertain'].map(status=>[status,events.filter(e=>(e.review_status||'pending')===status).length]));
}
renderTasks = function(tasks) {
  cachedTasks=tasks;
  const query=$('task-search').value.trim().toLowerCase(), status=$('task-status-filter').value;
  tasks=tasks.filter(t=>(t.purpose||'validation')===activePurpose&&(workspaceMode!=='queue'||t.status==='needs_review')&&(workspaceMode!=='reports'||t.status==='completed')&&(status==='all'||t.status===status)&&(!query||`${t.name} ${t.asset_path}`.toLowerCase().includes(query)));
  $('task-result-count').textContent=`共 ${tasks.length} 个任务`;
  const markup=tasks.length?`<div class="task-table">${tasks.map(task=>{
    const stats=taskStats(task), events=task.result?.events;
    return `<article><div><strong>${esc(taskName(task))}</strong><small>${esc(task.asset_path.split('/').pop())}</small>${task.import_key?'<small>历史抽检记录</small>':''}</div><div><span class="muted">核查人物</span><p>${task.object_ids.map(id=>esc(allItems.find(i=>i.item_id===id)?.name||'未命名人物')).join(' · ')||'尚未选择'}</p>${events?`<small>${stats.pending+stats.uncertain} 条待处理 · ${stats.confirmed} 条确认出现 · ${stats.rejected} 条已排除</small>`:'<small>提交后系统将整理需要复核的片段</small>'}</div><div><span class="status-badge ${esc(task.status)}">${esc(labels[task.status]||task.status)}</span>${task.status==='running'?`<progress aria-label="检查进度" max="1" value="${Number(task.progress)||0}"></progress><small>已完成 ${Math.round((task.progress||0)*100)}%</small>`:''}<button class="${task.status==='needs_review'?'primary':'quiet'}" data-task-detail="${esc(task.task_id)}">${task.status==='needs_review'?'继续复核':task.status==='completed'?'查看审核记录':'查看任务'}</button>${!task.result&&task.status!=='running'?`<button class="primary" data-task-run="${esc(task.task_id)}">${task.status==='failed'?'重新检查':'开始检查'}</button>`:''}</div></article>`;
  }).join('')}</div>`:'<p>当前筛选下没有任务。</p>';
  if(markup!==lastTasksMarkup){$('task-list').innerHTML=markup;lastTasksMarkup=markup;}
};
const originalSummary = renderSummary;
renderSummary = function(overview) {
  overview={...overview,tasks:overview.tasks.filter(t=>(t.purpose||'validation')===activePurpose)};
  originalSummary(overview);
  const tasks=overview.tasks, events=tasks.flatMap(t=>t.result?.events||[]), reviewed=events.filter(e=>['confirmed','rejected'].includes(e.review_status));
  $('summary-grid').innerHTML=[['待复核任务',tasks.filter(t=>t.status==='needs_review').length,'打开任务即可继续处理'],['系统检查中',tasks.filter(t=>t.status==='running').length,'结果生成后进入待复核'],['待处理线索',events.filter(e=>!e.review_status||['pending','uncertain'].includes(e.review_status)).length,'需要您的判断'],['已完成审核',tasks.filter(t=>t.status==='completed').length,'可查看与导出审核记录']].map(([label,count,note])=>`<article class="summary-card"><span>${label}</span><b>${count}</b><small>${note}</small></article>`).join('');
};
async function refreshTasks() {
  try { const overview=await reviewRequest('/api/overview'); renderSummary(overview); renderTasks(overview.tasks); }
  catch(error) { lastTasksMarkup=''; $('task-list').textContent='连接暂时中断，正在自动重试。'; }
}
function renderDetail() {
  const task=selectedTask, result=task.result, stats=taskStats(task), metrics=result?.metrics||{};
  $('detail-start').hidden=!!result||task.status==='running';
  $('detail-edit').hidden=!!result||task.status==='running';
  $('detail-retry').hidden=!result||task.status==='running';
  $('evidence-position').hidden=!selectedEvent;
  $('reason-control').hidden=!selectedEvent;
  document.querySelector('.review-layout').hidden=!result?.events.length;
  document.querySelector('.object-breakdown').hidden=!result;
  const available=(result?.events||[]).filter(e=>$('review-filter').value==='all'||e.review_status===$('review-filter').value);
  if(selectedEvent&&!available.some(e=>e.event_id===selectedEvent))selectedEvent=null;
  $('evidence-position').hidden=!selectedEvent;$('reason-control').hidden=!selectedEvent;
  if(available.length&&!selectedEvent){selectEvidence((available.find(e=>e.review_status==='pending')||available[0]).event_id);return;}
  document.querySelector('.review-focus').hidden=!selectedEvent;
  $('review-title').textContent=taskName(task);
  const processed=stats.confirmed+stats.rejected, total=result?.events.length||0;
  const step=task.status==='completed'?4:result?3:task.status==='running'?2:1;
  $('review-meta').innerHTML=`<ol class="review-steps">${['选择媒资与人物','系统检查','复核疑似片段','完成审核'].map((name,index)=>`<li class="${index+1===step?'current':index+1<step?'done':''}">${name}</li>`).join('')}</ol>${result?`<div class="review-metrics"><strong>已处理 ${processed} / ${total} 条</strong><span>确认出现 ${stats.confirmed}</span><span>已排除 ${stats.rejected}</span><span>留待复核 ${stats.uncertain}</span></div>${task.import_key?'<p class="scope-note">这是历史抽检记录，包含部分需核查画面。完成本次复核不代表已检查整部影片。</p>':''}${metrics.coverage_complete===false?'<p class="form-error">部分视频未能完成检查，请重新检查后再完成审核。</p>':''}`:`<p>${task.status==='running'?`系统正在检查，已完成 ${Math.round((task.progress||0)*100)}%。您可以先处理其他任务。`:'选择“开始检查”，系统将整理需要您核查的片段。'}</p>`}`;
  $('review-error').textContent=task.error?'本次检查未完成，请返回任务列表重试；持续失败请联系维护人员。':'';
  if(result&&!total)$('review-meta').insertAdjacentHTML('beforeend','<p class="scope-note">本次检查未发现需要复核的线索。请结合任务范围决定是否完成本次审核。</p>');
  const personIds=[...new Set((result?.events||[]).map(e=>e.person_id))];
  $('review-person-stats').innerHTML=personIds.length?`<table><thead><tr><th>人物对象</th><th>候选</th><th>确认</th><th>排除</th><th>未解决</th></tr></thead><tbody>${personIds.map(id=>{const list=result.events.filter(e=>e.person_id===id);return `<tr><td>${esc(list[0].person_name)}</td><td>${list.length}</td><td>${list.filter(e=>e.review_status==='confirmed').length}</td><td>${list.filter(e=>e.review_status==='rejected').length}</td><td>${list.filter(e=>['pending','uncertain'].includes(e.review_status||'pending')).length}</td></tr>`;}).join('')}</tbody></table>`:'<p>暂无候选数据。</p>';
  $('review-finish').disabled=!result||task.status==='completed'||task.status==='running'||stats.pending+stats.uncertain>0||metrics.coverage_complete===false;
  $('review-finish').title=stats.pending+stats.uncertain>0?'请处理所有未完成的线索后结束审核':'';
  $('review-export').disabled=!result;
  const filter=$('review-filter').value;
  const events=(result?.events||[]).filter(e=>filter==='all'||(e.review_status||'pending')===filter);
  $('review-events').innerHTML=events.length?events.map(e=>`<button class="candidate-row ${selectedEvent===e.event_id?'selected':''}" aria-pressed="${selectedEvent===e.event_id}" data-event="${esc(e.event_id)}"><img src="${esc(e.evidence_image)}" alt="" loading="lazy"/><span><strong>核查 ${esc(e.person_name)}</strong><small>${esc(verdictNames[e.review_status||'pending'])}</small></span></button>`).join(''):'<p class="muted">这里没有需要处理的片段。</p>';
  $('review-actions').hidden=!selectedEvent;
  const position=events.findIndex(e=>e.event_id===selectedEvent);
  if($('previous-clip'))$('previous-clip').disabled=position<=0;
  if($('next-clip'))$('next-clip').disabled=position<0||position>=events.length-1;
  document.querySelectorAll('[data-event] strong').forEach(node=>{const event=result.events.find(e=>e.event_id===node.closest('[data-event]').dataset.event);node.textContent=`${event.person_name} · 约 ${timeLabel(event.start_seconds)}`;});
}
function selectEvidence(id) {
  const event=selectedTask.result?.events.find(e=>e.event_id===id);
  if (!event) return;
  selectedEvent=id;
  $('review-image').src=event.evidence_image;
  $('review-image').hidden=false;
  $('review-note').value=event.note||'';
  $('review-evidence-info').textContent=`画面中是否出现「${event.person_name}」？`;
  const person=allItems.find(p=>p.item_id===event.person_id);
  const snapshot=selectedTask.result.reference_snapshot?.find(p=>p.person_id===event.person_id);
  const photos=(snapshot?.materials||person?.materials||[]).filter(m=>m.kind==='reference_image'&&m.status!=='disabled').slice(0,4);
  $('review-reason').value=event.reason||'';
  $('evidence-position').textContent=`第 ${selectedTask.result.events.indexOf(event)+1} 段 · 约 ${timeLabel(event.start_seconds)} · 疑似人物匹配，需人工确认${snapshot?.materials?'':' · 对照照片来自当前人物库'}`;
  $('reference-strip').innerHTML=`<span>人物参考照片<br/><small>点击放大对照</small></span>${photos.map(m=>`<button class="reference-thumb" data-reference="${esc(m.local_uri)}" aria-label="放大${esc(event.person_name)}的参考照片"><img src="${esc(m.local_uri)}" alt="${esc(event.person_name)}的参考照片"/></button>`).join('')}${photos.length?'':'<small>暂无可用参考照片</small>'}`;
  $('review-video').pause(); $('review-video').hidden=true; $('video-hint').hidden=true;
  const video=$('review-video');
  video.removeAttribute('src');video.load();
  renderDetail();
  void playEvidence();
}
async function openReview(id) {
  if(reviewBusy)return;
  const version=++navigationVersion;
  if(!allItems.length)allItems=await reviewRequest('/api/library-items');
  const task=await reviewRequest(`/api/review-tasks/${id}`);
  if(version!==navigationVersion)return;
  selectedTask=task; selectedEvent=null;
  activePurpose=task.purpose||'validation';$('workspace-purpose').value=activePurpose;
  $('review-filter').value='all'; $('review-image').hidden=true; $('review-note').value=''; $('review-evidence-info').textContent='';
  $('review-video').removeAttribute('src');$('review-video').load();
  setView('review');
  history.replaceState(null,'',`#task/${id}`);
  $('review-feedback').textContent='';
  $('video-hint').textContent='已定位到需要核查的片段，可播放前后画面辅助判断。';
  renderDetail();
}
$('task-list').addEventListener('click',async(event)=>{
  const detail=event.target.closest('[data-task-detail]'), run=event.target.closest('[data-task-run]');
  try { if(detail) await openReview(detail.dataset.taskDetail); if(run){run.disabled=true; await reviewRequest(`/api/review-tasks/${run.dataset.taskRun}/run`,{method:'POST'}); await refreshTasks(); await openReview(run.dataset.taskRun);} }
  catch(error){if(run)run.disabled=false; window.alert(error.message);}
});
$('review-close').onclick=()=>{history.replaceState(null,'','#tasks');setView('tasks');};
$('review-filter').onchange=()=>{selectedEvent=null;$('review-video').pause();renderDetail();};
$('review-events').onclick=event=>{const row=event.target.closest('[data-event]');if(row&&!reviewBusy)selectEvidence(row.dataset.event);};
$('review-video').onerror=()=>{if(!$('review-video').getAttribute('src'))return;$('review-video').hidden=true;$('review-image').hidden=false;$('video-hint').hidden=false;$('video-hint').textContent='片段暂时无法播放，已显示备用画面；可重试或留待复核。';};
$('review-actions').onclick=async(event)=>{
  const button=event.target.closest('[data-verdict]'); if(!button||!selectedEvent||reviewBusy)return;
  reviewBusy=true;
  $('review-filter').disabled=true;
  const buttons=[...$('review-actions').querySelectorAll('button')]; buttons.forEach(b=>b.disabled=true);
  try{
    const previousEvent=selectedEvent,filter=$('review-filter').value;
    selectedTask=await reviewRequest(`/api/review-tasks/${selectedTask.task_id}/events/${previousEvent}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({review_status:button.dataset.verdict,note:$('review-note').value})});
    const available=selectedTask.result.events.filter(e=>filter==='all'||e.review_status===filter);
    const next=available.find(e=>e.event_id!==previousEvent&&e.review_status==='pending');
    if(button.dataset.verdict!=='pending'&&next)selectEvidence(next.event_id);else renderDetail();
    $('review-feedback').textContent=next?'已保存，已打开下一条。':'处理结果已保存。';
    await refreshTasks();
  }
  catch(error){$('review-error').textContent=error.message;}
  finally{reviewBusy=false;$('review-filter').disabled=false;buttons.forEach(b=>b.disabled=false);}
};
setInterval(async()=>{
  await refreshTasks();
  if(selectedTask?.status==='running') {const id=selectedTask.task_id;try{const updated=await reviewRequest(`/api/review-tasks/${id}`);if(selectedTask?.task_id===id){selectedTask=updated;renderDetail();}}catch(error){$('review-error').textContent=error.message;}}
},4000);
$('task-search').oninput=()=>renderTasks(cachedTasks);
$('task-status-filter').onchange=()=>renderTasks(cachedTasks);
$('review-export').onclick=()=>{if(selectedTask)window.location.assign(`/api/review-tasks/${selectedTask.task_id}/report`);};
$('review-finish').onclick=async()=>{try{selectedTask=await reviewRequest(`/api/review-tasks/${selectedTask.task_id}/complete`,{method:'POST'});renderDetail();await refreshTasks();}catch(error){$('review-error').textContent=error.message;}};
if(location.hash.startsWith('#task/'))openReview(location.hash.slice(6)).catch(error=>{$('task-list').textContent=error.message;});
const originalOpenTask=openTaskDialog;
openTaskDialog=async function(){originalOpenTask();$('task-person-options').innerHTML=allItems.filter(p=>p.category==='person').map(p=>`<label class="person-choice"><input type="checkbox" value="${esc(p.item_id)}" ${p.materials?.some(m=>m.kind==='reference_image')?'':'disabled'}/><span>${esc(p.name)}</span>${p.materials?.some(m=>m.kind==='reference_image')?'':'<small>请先添加照片</small>'}</label>`).join('');try{const media=await reviewRequest('/api/local-media');$('task-local-media').innerHTML='<option value="">请选择要审核的视频</option>'+media.map(m=>`<option value="${esc(m.path)}">${esc(m.name)}</option>`).join('');}catch(error){$('task-error').textContent=error.message;$('task-error').classList.remove('hidden');}};
// Original callbacks were registered before this extension loaded.
$('new-task').removeEventListener('click',originalOpenTask); $('dashboard-create').removeEventListener('click',originalOpenTask);
$('new-task').addEventListener('click',openTaskDialog); $('dashboard-create').addEventListener('click',openTaskDialog);
$('task-local-media').onchange=()=>{if($('task-local-media').value)$('task-asset-path').value=$('task-local-media').value;};
$('show-image').textContent='查看定位截图';
$('show-image').onclick=()=>{playbackVersion++;$('review-video').pause();$('review-video').hidden=true;$('video-hint').hidden=true;$('review-image').hidden=false;$('show-video').textContent='播放片段';};
$('show-video').onclick=()=>void playEvidence();
$('review-video').muted=true;$('review-video').playsInline=true;$('review-video').preload='auto';
document.querySelector('.evidence-tabs').insertAdjacentHTML('beforeend','<button id="previous-clip" class="quiet" type="button">上一段</button><button id="next-clip" class="quiet" type="button">下一段</button><label class="playback-speed">播放速度<select id="playback-speed" aria-label="播放速度"><option value="0.5">0.5 倍</option><option value="1" selected>正常</option><option value="1.5">1.5 倍</option><option value="2">2 倍</option></select></label>');
function moveEvidence(direction){if(reviewBusy)return;const events=visibleEvidence(),index=events.findIndex(e=>e.event_id===selectedEvent),next=events[index+direction];if(next)selectEvidence(next.event_id);}
$('previous-clip').onclick=()=>moveEvidence(-1);$('next-clip').onclick=()=>moveEvidence(1);
$('playback-speed').onchange=()=>$('review-video').playbackRate=Number($('playback-speed').value);
$('review-video').onloadedmetadata=()=>$('review-video').playbackRate=Number($('playback-speed').value);
$('reference-strip').onclick=event=>{const button=event.target.closest('[data-reference]');if(button){$('reference-preview-image').src=button.dataset.reference;$('reference-preview').showModal();}};
$('reference-preview-close').onclick=()=>$('reference-preview').close();
$('library-table-body').addEventListener('click',event=>{
  const button=event.target.closest('[data-edit-object]');if(!button)return;
  const item=allItems.find(i=>i.item_id===button.dataset.editObject);if(!item)return;
  openLibraryDialog();editingLibraryId=item.item_id;$('dialog-title').textContent=`编辑 · ${item.name}`;
  for(const [id,value] of Object.entries({'item-id':item.item_id,'item-category':item.category,'item-classification':item.classification,'item-name':item.name,'item-aliases':item.aliases.join(','),'item-definition':item.definition,'item-status':item.status}))$(id).value=value;
  $('item-id').disabled=true;$('item-category').disabled=true;
});
const originalMaterials=showMaterials;
showMaterials=async function(id){
  await originalMaterials(id);
  document.querySelector('.materials-note').textContent='添加清晰的单人照片，建议覆盖不同年龄和角度。审核员将在核查片段时使用这些照片作对照。';
  const materials=await reviewRequest(`/api/library-items/${encodeURIComponent(id)}/materials`);
  const enabled=materials.filter(m=>m.status!=='disabled');
  const disabled=materials.filter(m=>m.status==='disabled');
  const card=m=>`<article class="material-card"><img src="${esc(m.local_uri)}" alt="人物参考照片"/><div><h3>${esc(m.title)}</h3><p>${m.status==='disabled'?'已停用，不参与新任务':'待人工确认；不代表识别效果已达标'}</p><p>${esc(m.quality_note)}</p><button class="quiet" type="button" data-material-id="${esc(m.material_id)}" data-material-disabled="${m.status==='disabled'}">${m.status==='disabled'?'恢复为待确认':'停用此照片'}</button></div></article>`;
  $('material-list').innerHTML=enabled.map(card).join('')||'<p>没有可用参考照片，请补充清晰正面原图。</p>';
  if(disabled.length)$('material-list').insertAdjacentHTML('beforeend',`<details><summary>已停用照片（${disabled.length}）</summary>${disabled.map(card).join('')}</details>`);
  $('material-list').onclick=async event=>{
    const button=event.target.closest('[data-material-id]');if(!button)return;
    const restore=button.dataset.materialDisabled==='true';
    const reason=window.prompt(restore?'请说明恢复原因（恢复后仍需人工确认）':'停用原因，例如模糊、角度偏侧或遮挡');
    if(!reason?.trim())return;
    button.disabled=true;
    try{await reviewRequest(`/api/library-items/${encodeURIComponent(id)}/materials/${encodeURIComponent(button.dataset.materialId)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:restore?'pending_validation':'disabled',quality_note:reason.trim()})});allItems=await reviewRequest('/api/library-items');renderLibrary();$('material-dialog').close();await showMaterials(id);}catch(error){window.alert(error.message);button.disabled=false;}
  };
  if(allItems.find(i=>i.item_id===id)?.category!=='person')return;
  const form=document.createElement('form');form.innerHTML='<label>添加本地参考图<input type="file" accept="image/jpeg,image/png" required /></label><button class="primary" type="submit">导入参考图</button><p role="status"></p>';
  form.onsubmit=async(event)=>{event.preventDefault();const file=form.querySelector('input').files[0];if(!file)return;const button=form.querySelector('button');button.disabled=true;const body=new FormData();body.append('file',file);try{await reviewRequest(`/api/library-items/${encodeURIComponent(id)}/upload-reference`,{method:'POST',body});allItems=await reviewRequest('/api/library-items');renderLibrary();$('material-dialog').close();await showMaterials(id);}catch(error){form.querySelector('p').textContent=error.message;}finally{button.disabled=false;}};
  $('material-list').prepend(form);
};

// Library copy describes review work; engineering details belong in maintenance.
Object.assign(libraryMeta.person,{description:'管理需要核查的人物与参考照片。审核员可在复核片段时对照这些照片。'});
Object.assign(libraryMeta.text,{description:'整理需要核查的词语与表达。当前仅支持管理，尚不参与任务检查。'});
Object.assign(libraryMeta.content,{description:'整理需要核查的内容类别与审核说明。当前仅支持管理，尚不参与任务检查。'});
$('item-id').required=false;
if(!location.hash.startsWith('#task/')){
  const route=location.hash.slice(1).split('/');
  setView(['tasks','queue','reports','library','analysis','media'].includes(route[0])?route[0]:'queue',route[1]||'person');
}

const priorTaskDialog=openTaskDialog;
openTaskDialog=async function(){
  editingTaskId=null;
  await priorTaskDialog();
  $('task-dialog').querySelector('h2').textContent='创建审核任务';
  $('person-search').value='';
  $('task-purpose-hint').textContent=activePurpose==='production'?'生产审核：仅可选择已启用且有参考照片的人物。':'算法验证：用于检验效果，结果不作为正式审核记录。';
  document.querySelectorAll('#task-person-options input').forEach(input=>{
    const item=allItems.find(p=>p.item_id===input.value);
    if(!item.materials.some(m=>m.kind==='reference_image'&&m.status!=='disabled')||item.status==='disabled'||(activePurpose==='production'&&item.status!=='active')){input.disabled=true;input.closest('label').insertAdjacentHTML('beforeend','<small>未启用或缺少可用照片</small>');}
  });
  $('task-form').querySelector('button[type="submit"]').textContent='提交并开始检查';
  $('person-selected-count').textContent='已选 0 人';
};
['new-task','dashboard-create'].forEach(id=>{$(id).removeEventListener('click',priorTaskDialog);$(id).addEventListener('click',openTaskDialog);});
$('person-search').oninput=()=>document.querySelectorAll('#task-person-options label').forEach(label=>{const item=allItems.find(p=>p.item_id===label.querySelector('input').value);label.hidden=!`${item.name} ${item.classification}`.includes($('person-search').value.trim());});
$('task-person-options').onchange=()=>$('person-selected-count').textContent=`已选 ${document.querySelectorAll('#task-person-options input:checked').length} 人`;
$('workspace-purpose').onchange=()=>{if(reviewBusy){$('workspace-purpose').value=activePurpose;return;}activePurpose=$('workspace-purpose').value;lastTasksMarkup='';setView('queue');refreshTasks();};
$('detail-start').onclick=async()=>{const button=$('detail-start');button.disabled=true;try{await reviewRequest(`/api/review-tasks/${selectedTask.task_id}/run`,{method:'POST'});await openReview(selectedTask.task_id);await refreshTasks();}catch(error){$('review-error').textContent=error.message;}finally{button.disabled=false;}};
$('detail-edit').onclick=async()=>{const task=selectedTask;await openTaskDialog();editingTaskId=task.task_id;$('task-name-input').value=task.name;$('task-asset-path').value=task.asset_path;$('task-local-media').value=task.asset_path;document.querySelectorAll('#task-person-options input').forEach(input=>input.checked=task.object_ids.includes(input.value)&&!input.disabled);$('task-person-options').onchange();$('task-form').querySelector('button[type="submit"]').textContent='保存任务范围';};
$('detail-retry').onclick=async()=>{const button=$('detail-retry');button.disabled=true;try{const task=await reviewRequest(`/api/review-tasks/${selectedTask.task_id}/retry`,{method:'POST'});await openReview(task.task_id);await refreshTasks();}catch(error){$('review-error').textContent=error.message;}finally{button.disabled=false;}};
window.addEventListener('hashchange',()=>{if(reviewBusy)return;const route=location.hash.slice(1).split('/');if(route[0]==='task')openReview(route[1]).catch(error=>$('review-error').textContent=error.message);else setView(['tasks','queue','reports','library','analysis','media'].includes(route[0])?route[0]:'queue',route[1]||'person');});
document.addEventListener('keydown',event=>{
  if(!selectedTask||!selectedEvent||reviewBusy||event.repeat||event.ctrlKey||event.metaKey||event.altKey||document.querySelector('dialog[open]')||['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;
  if(event.key===' '&&!['BUTTON','VIDEO','SUMMARY'].includes(event.target.tagName)){event.preventDefault();const video=$('review-video');if(video.paused)video.play().catch(()=>{});else video.pause();return;}
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){if(event.target.tagName==='VIDEO')return;event.preventDefault();moveEvidence(event.key==='ArrowLeft'?-1:1);return;}
  const verdict={'1':'confirmed','2':'rejected','3':'uncertain','0':'pending'}[event.key];
  if(verdict){event.preventDefault();document.querySelector(`[data-verdict="${verdict}"]`).click();}
});
$('review-actions').insertAdjacentHTML('afterend','<small class="shortcut-hint">空格 播放/暂停 · ← → 切换片段 · 1 确认 · 2 排除 · 3 留待复核 · 0 撤回</small>');
for(const id of ['item-status','library-status-filter']){
  const select=$(id);select.querySelector('[value="ready_for_validation"]').textContent='待验证';select.insertAdjacentHTML('beforeend','<option value="disabled">已停用</option>');
}
libraryMeta.text.title='敏感词库';libraryMeta.content.title='内容库';
$('reference-strip').after($('reason-control'));
$('review-evidence-info').after($('evidence-position'));
document.querySelector('.object-breakdown').appendChild($('detail-retry'));
const detailedRenderLibrary=renderLibrary;
renderLibrary=function(){
  detailedRenderLibrary();
  if(activeCategory!=='person')return;
  const items=filteredItems();
  document.querySelectorAll('#library-table-body tr').forEach((row,index)=>{
    const item=items[index],photo=item.materials?.find(m=>m.kind==='reference_image'&&m.status!=='disabled');
    const materialButton=row.querySelector('[data-materials-id]');
    const enabled=(item.materials||[]).filter(m=>m.kind==='reference_image'&&m.status!=='disabled').length;
    const disabled=(item.materials||[]).filter(m=>m.status==='disabled').length;
    if(materialButton)materialButton.textContent=`${enabled} 张候选照片${disabled?` · ${disabled} 张停用`:''}`;
    if(photo)row.cells[0].insertAdjacentHTML('afterbegin',`<img class="person-avatar" src="${esc(photo.local_uri)}" alt="" />`);
    row.cells[5].textContent=item.status==='active'?'可用于生产审核；具体出镜仍需人工判断。':item.status==='disabled'?'已停止用于新任务。':'请先验证参考照片和识别效果，再启用生产审核。';
  });
};
