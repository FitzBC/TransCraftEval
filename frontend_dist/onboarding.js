// Explicit import is idempotent and never resets an existing workspace.
let importBusy=false;
function setImportBusy(busy){
  importBusy=busy;
  ['setup-upload','setup-files','setup-skip','setup-done'].forEach(id=>$(id).disabled=busy);
  $('setup-defaults').disabled=busy||$('setup-defaults').dataset.available!=='true';
}
async function showImportDialog(initial=false){
  const dialog=$('workspace-setup');
  $('setup-title').textContent=initial?'准备您的审核工作空间':'导入素材';
  $('setup-skip').textContent=initial?'暂不导入，进入工作空间':'返回工作空间';
  $('setup-status').textContent='';$('setup-results').replaceChildren();$('setup-files').value='';
  $('setup-progress').hidden=true;
  if(!dialog.open)dialog.showModal();
  try{
    const state=await reviewRequest('/api/workspace/setup');
    $('setup-defaults').dataset.available=String(state.bundle_available);
    $('setup-bundle-hint').textContent=state.bundle_available?'仅添加缺少的条目，保留已停用照片和人工审核记录。':'未安装内置素材包，可以直接导入自己的视频。';
    setImportBusy(false);
  }catch(error){$('setup-status').textContent=`无法读取导入配置：${error.message}`;$('setup-defaults').disabled=true;}
}
$('import-media').onclick=()=>showImportDialog();
$('workspace-setup').addEventListener('cancel',event=>{if(importBusy)event.preventDefault();});
async function closeImport(){
  if(importBusy)return;
  try{await reviewRequest('/api/workspace/skip',{method:'POST'});$('workspace-setup').close();setView('media');await loadApp();}
  catch(error){$('setup-status').textContent=error.message;}
}
$('setup-skip').onclick=closeImport;$('setup-done').onclick=closeImport;
$('setup-defaults').onclick=async()=>{
  if(importBusy)return;setImportBusy(true);$('setup-status').textContent='正在导入内置素材，请稍候…';
  try{
    const result=await reviewRequest('/api/workspace/import-defaults',{method:'POST'});
    activePurpose='validation';$('workspace-purpose').value=activePurpose;
    const {media,objects,tasks}=result.added;
    $('setup-status').textContent=media||objects||tasks?`导入完成：${media} 个视频、${objects} 个审核对象、${tasks} 个验证任务。已有数据保持不变。`:'内置素材已经导入，无需重复添加；现有记录保持不变。';
    await loadApp();await refreshMedia();
  }catch(error){$('setup-status').textContent=`导入失败：${error.message}，可重试。`;}
  finally{setImportBusy(false);}
};
function uploadLocalVideo(file,index,total){
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST','/api/media/import');xhr.responseType='json';
    xhr.upload.onprogress=event=>{if(event.lengthComputable){const percent=Math.round(event.loaded/event.total*100);$('setup-progress').value=percent;$('setup-status').textContent=`${index}/${total} · ${file.name} · ${percent===100?'正在校验并保存…':percent+'%'}`;}};
    xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(xhr.response):reject(new Error(typeof xhr.response?.detail==='string'?xhr.response.detail:'视频导入失败'));
    xhr.onerror=()=>reject(new Error('与本地服务连接中断，可重新导入；同一文件会自动去重'));
    const body=new FormData();body.append('file',file);xhr.send(body);
  });
}
$('setup-upload').onclick=async()=>{
  const files=Array.from($('setup-files').files);
  if(!files.length){$('setup-status').textContent='请先选择一个或多个 MP4 视频。';return;}
  setImportBusy(true);$('setup-results').replaceChildren();$('setup-progress').hidden=false;
  let added=0,duplicates=0,failed=0;
  for(const [index,file] of files.entries()){
    const row=document.createElement('li');$('setup-results').append(row);
    $('setup-progress').value=0;
    try{
      if(!file.name.toLowerCase().endsWith('.mp4'))throw new Error('仅支持 MP4 视频');
      if(file.size>20*1024**3)throw new Error('文件超过 20 GB');
      const result=await uploadLocalVideo(file,index+1,files.length);
      result.duplicate?duplicates++:added++;
      row.textContent=`${file.name}：${result.duplicate?'已存在，未重复添加':'已导入'}`;
    }catch(error){failed++;row.textContent=`${file.name}：${error.message}`;}
  }
  $('setup-status').textContent=`新增 ${added} 个，已存在 ${duplicates} 个，失败 ${failed} 个。${failed?'成功项已保留，可重新选择失败项重试。':'可进入媒资库创建审核任务。'}`;
  $('setup-progress').hidden=true;setImportBusy(false);
  try{await refreshMedia();await loadApp();}catch(error){$('setup-status').textContent+=' 刷新失败，请重新打开媒资库。';}
};
reviewRequest('/api/workspace/setup').then(state=>{if(state.enabled&&!state.initialized)showImportDialog(true);}).catch(()=>{});
