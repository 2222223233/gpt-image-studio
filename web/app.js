const $=id=>document.getElementById(id);
let sessionToken=location.hash.slice(1)||sessionStorage.getItem('studio-session')||'';
if(location.hash){sessionStorage.setItem('studio-session',sessionToken);history.replaceState(null,'',location.pathname);}
const fields=['base_url','model','size','custom_width','custom_height','quality','complexity','n','output_format','output_compression','background','response_format','timeout'];
try{const settings=JSON.parse(localStorage.getItem('gpt-image-studio-settings-v1')||'{}');for(const id of fields){if(settings[id]!==undefined)$(id).value=settings[id];}}catch{}
function configuration(){const data={api_key:$('api_key').value,prompt:$('prompt').value};for(const id of fields)data[id]=$(id).value;if(data.size==='custom')data.size=data.custom_width+'x'+data.custom_height;return data;}
function persistSettings(){const settings={};for(const id of fields)settings[id]=$(id).value;try{localStorage.setItem('gpt-image-studio-settings-v1',JSON.stringify(settings));}catch{}}
async function request(path,data){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':sessionToken},body:JSON.stringify(data)});let result;try{result=await response.json();}catch{throw new Error('本地服务返回了无效响应，请检查启动窗口。');}if(!response.ok){const error=new Error(result.error||'请求失败');error.details=result.details;throw error;}return result;}
function showDebug(data){$('debug').textContent=JSON.stringify(data,null,2);}
function updateHints(){const custom=$('size').value==='custom';$('custom-size').hidden=!custom;for(const id of ['custom_width','custom_height'])$(id).disabled=!custom;const size=configuration().size;$('size-hint').textContent=size&&size!=='auto'?'请求 '+size.replace('x',' × ')+'。超过 2560×1440 的分辨率在官方文档中标为实验性，第三方通道可能另有限制。':'4K 请显式选择 3840×2160。模型名含 -4k 并不能保证返回尺寸。';$('model-hint').textContent=$('model').value.endsWith('-4k')?'带 -4k 后缀的模型可能是服务商别名；名称将原样发送，请以服务商文档为准。':'模型名称原样发送；获取列表只检查名称，不验证生图能力。';}
for(const id of ['size','model','custom_width','custom_height'])$(id).addEventListener('input',updateHints);
$('preset-4k').onclick=()=>{$('size').value='3840x2160';$('n').value='1';$('timeout').value='600';updateHints();status('已设置 4K 横图、1 张、600 秒超时。模型与画质保持当前选择。');};
$('preset-default').onclick=()=>{for(const id of ['size','quality','complexity','n','output_format','output_compression','background','response_format'])$(id).value='';updateHints();status('已恢复兼容默认，保留当前参考图片；此设置不保证生成 4K。');};
$('preview').onclick=async()=>{if(busy)return;busy=true;referenceUploads.setBusy(true);try{const data=configuration();data.reference_images=await referenceUploads.serialize();const result=await request('/api/preview',data);showDebug(result.parameters);status('参数与参考图检查通过。没有调用服务商，不产生生图费用。');}catch(error){showDebug({error:error.message});status(error.message,true);}finally{busy=false;referenceUploads.setBusy(false);}};
updateHints();
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
let total=0,busy=false;
function syncCanvas(){const empty=total===0;$('empty').hidden=!empty;$('count').textContent=String(total).padStart(2,'0')+' IMAGES';}
function addImage(item,data){const card=document.createElement('article');card.className='card';const full=document.createElement('a');full.href=item.url;full.target='_blank';full.rel='noopener';const img=document.createElement('img');img.alt=data.prompt;img.loading='lazy';full.append(img);const body=document.createElement('div');body.className='card-body';const prompt=document.createElement('p');prompt.textContent=item.revised_prompt||data.prompt;const dimension=document.createElement('div');dimension.className='dimension';const setDimensions=(w,h)=>{dimension.textContent=(w&&h?'实际 '+w+' × '+h:'尺寸未识别')+' · '+(item.bytes/1024/1024).toFixed(2)+' MB';if(w&&h&&data.size&&data.size!=='auto'&&data.size!==w+'x'+h){dimension.classList.add('warn');dimension.textContent+=' · 与请求尺寸不同';}};setDimensions(item.width,item.height);img.onload=()=>{if(!item.width)setDimensions(img.naturalWidth,img.naturalHeight);};img.src=item.url;const meta=document.createElement('div');meta.className='card-meta';const model=document.createElement('span');model.textContent=data.model;const download=document.createElement('a');download.className='download';download.href=item.url;download.download=item.name;download.textContent='保存原图 ↓';meta.append(model,download);const reuse=document.createElement('button');reuse.type='button';reuse.className='subtle reuse-reference';reuse.textContent='用作参考 / 继续修改';reuse.onclick=()=>referenceUploads.useResult(item);body.append(prompt,dimension,meta,reuse);card.append(full,body);$('gallery').prepend(card);total++;syncCanvas();}
$('show-key').onclick=()=>{const visible=$('api_key').type==='password';$('api_key').type=visible?'text':'password';$('show-key').textContent=visible?'隐藏':'显示';$('show-key').setAttribute('aria-label',visible?'隐藏 API Key':'显示 API Key');};
function setModelOptions(open) {
  $('model-options').hidden = !open;
  $('toggle-models').setAttribute('aria-expanded', String(open));
  $('toggle-models').textContent = open ? '收起全部上游模型 ▴' : '展开全部上游模型 ▾';
  if (open) {
    const current = $('model').value.trim();
    $('model-picker').value = current;
    if ($('model-picker').selectedIndex < 0) $('model-picker').selectedIndex = 0;
  }
}
$('toggle-models').onclick = () => setModelOptions($('model-options').hidden);
$('model-picker').onchange = () => {
  const selected = $('model-picker').value;
  if (!selected) return;
  $('model').value = selected;
  updateHints();
  setModelOptions(false);
  $('model').focus();
};
$('model-picker').onkeydown = event => {
  if (event.key === 'Escape') {setModelOptions(false); $('toggle-models').focus();}
};
function clearModelOptions() {
  $('model-picker').replaceChildren();
  $('toggle-models').disabled = true;
  setModelOptions(false);
}
$('base_url').addEventListener('input', () => {
  clearModelOptions();
  $('models-status').textContent = 'API 地址已修改，请重新获取该服务商的模型列表。';
});
$('models').onclick = async () => {
  const button = $('models');
  const data = configuration();
  button.disabled = true;
  clearModelOptions();
  $('models-status').textContent = '正在读取服务商模型列表…';
  try {
    const result = await request('/api/models', data);
    if ($('base_url').value !== data.base_url || $('api_key').value !== data.api_key) {
      $('models-status').textContent = '连接信息已变更，请重新获取模型列表。';
      return;
    }
    const sorted = [...result.models].sort((a,b) => Number(/image/i.test(b))-Number(/image/i.test(a)) || a.localeCompare(b));
    const placeholder = document.createElement('option');
    placeholder.value = ''; placeholder.textContent = '请选择一个模型'; placeholder.disabled = true;
    $('model-picker').append(placeholder);
    for (const name of sorted) {
      const option = document.createElement('option');
      option.value = name; option.textContent = name;
      $('model-picker').append(option);
    }
    $('toggle-models').disabled = sorted.length === 0;
    $('models-status').textContent = sorted.length ? `已读取 ${sorted.length} 个模型；展开列表显示全部模型，选择后才更新输入框。` : '服务商返回了空模型列表，仍可手动填写模型名称。';
    setModelOptions(sorted.length > 0);
  } catch (error) {
    $('models-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
$('form').onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;referenceUploads.setBusy(true);const data=configuration();persistSettings();$('generate').disabled=true;$('preview').disabled=true;$('clear').disabled=true;$('generate-label').textContent='正在生成…';$('empty').classList.add('busy');$('empty-title').textContent='正在把灵感变成画面…';$('empty-text').textContent='生成可能需要数分钟，请保持程序与页面打开。';const start=Date.now();const tick=()=>status(`正在生成 · 已等待 ${Math.floor((Date.now()-start)/1000)} 秒\n请勿重复提交。`);tick();const timer=setInterval(tick,1000);try{data.reference_images=await referenceUploads.serialize();const result=await request('/api/generate',data);for(const item of result.images)addImage(item,data);showDebug(result.parameters);status(`已生成 ${result.images.length} 张，耗时 ${Math.round((Date.now()-start)/1000)} 秒。原图已保存到 generated 文件夹。`+(result.warnings.length?'\n注意：'+result.warnings.join('\n'):''));}catch(error){showDebug(error.details||{});$('debug-panel').open=true;status(error instanceof TypeError?'连接中断。请确认启动窗口仍在运行。服务商可能仍在生成，重试前请检查记录。':error.message,true);}finally{clearInterval(timer);busy=false;referenceUploads.setBusy(false);$('generate').disabled=false;$('preview').disabled=false;$('clear').disabled=false;$('empty').classList.remove('busy');$('empty-title').textContent='每一张好图，始于一个想法。';$('empty-text').textContent='从左侧写下你的画面描述，或用下面的灵感开启第一次创作。';}};
$('clear').onclick=()=>{$('gallery').replaceChildren();total=0;syncCanvas();status('预览已清空，本地图片文件仍然保留。');};
const presets={photo:'一只橘猫坐在雨后的木质窗台上，窗外是模糊的城市街景，柔和的午后光线照亮毛发。35mm 胶片摄影，细腻颗粒，温暖低饱和色调，自然构图。',product:'设计一张极简香水产品海报：透明玻璃瓶放在浅米色石台上，周围有水波投影和一枝绿叶，柔和的棚拍光线，留白充足，高级杂志广告质感，不添加文字。',illustration:'一座漂浮在云海上的小书店，门口有发光的花，橘色小猫坐在门边，远处是淡紫色的月亮。温柔的手绘插画，丰富细节，安静梦幻的氛围。'};
document.querySelectorAll('[data-preset]').forEach(button=>button.onclick=()=>{$('prompt').value=presets[button.dataset.preset];$('prompt').focus();});
if(!sessionToken)status('请使用 start.bat 启动，并通过启动窗口中的完整链接访问。',true);
