import {contracts,ingestion,datasets} from '../api/entities.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify,date} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {BatchStatus,AttemptStatus,Role} from '../constants/enums.js';

const isAdmin=()=>session.user.role==='admin';
const canWrite=()=>session.user.role!=='viewer';
let selectedBatchId=null;

export const badge=v=>'<span class="batch-badge '+esc(v)+'">'+esc(BatchStatus[v]||v)+'</span>';
const attemptBadge=v=>'<span class="attempt-badge '+esc(v)+'">'+esc(AttemptStatus[v]||v)+'</span>';

const UNIT_OPTIONS=[['second','秒（入库前 ÷60 换算为分钟）'],['minute','分钟'],['count','个/次（不换算）'],['none','无单位']];

export async function ingestionPage(){
 const [batchList,contractList]=await Promise.all([ingestion.list(),contracts.list()]);
 workspace.batches=batchList; workspace.contracts=contractList;
 selectedBatchId=batchList[0]?.id??null;
 const m=workspace.meta;
 const versions=[...new Set(contractList.map(c=>c.source_version))];
 return heading('02 / DATA INTAKE','接入契约与待审核区','原始文件先进入待审核区，按来源版本的列映射与单位整批校验；负责人发布后才生成只读业务批次，分析只读取已发布批次。')
 +'<div class="ingest-grid">'
 // 左栏：契约 + 上传
 +'<section class="panel"><div class="section-title"><h2>接入契约</h2><span>按来源版本登记列映射和单位</span></div>'
 +contractPanel(contractList)
 +(isAdmin()?'<form id="contract-form" class="sub-form"><label>来源版本<input name="source_version" required placeholder="例如 diary-v2-seconds" list="version-list"></label><datalist id="version-list">'+versions.map(v=>'<option value="'+esc(v)+'">').join('')+'</datalist><div class="mapping-head"><span>标准列</span><span>原始文件列名</span><span>原始单位</span></div>'
   +m.columns.map(c=>'<div class="mapping-row"><label class="canonical">'+esc(c.label)+'<small>'+esc(c.key)+'</small></label><input name="map-'+esc(c.key)+'" required placeholder="原始列名" value="'+esc(c.key)+'"><select name="unit-'+esc(c.key)+'">'+UNIT_OPTIONS.map(([v,l])=>{const dv=c.key==='reach'?'count':(c.type==='number'?'minute':'none');return '<option value="'+v+'"'+(v===dv?' selected':'')+'>'+esc(l)+'</option>';}).join('')+'</select></div>').join('')
   +'<p class="hint">同来源版本再次登记会生成新版本并停用旧版；已在审批次的旧审核结果将自动失效。</p><button type="submit" class="primary small">登记/改版契约</button></form>'
   :'<p class="hint">观察员仅可查看契约，登记与改版由业务负责人执行。</p>')
 +'<div class="section-title" style="margin-top:34px"><h2>上传原始文件到待审核区</h2><span>未知版本直接拒收</span></div>'
 +(canWrite()?'<form id="stage-form" class="sub-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月秒级日记批次"></label><label>来源文件名<input name="source" value="diary.csv"></label><label>来源版本<input name="source_version" required list="version-list" placeholder="选择或输入来源版本"></label><label>原始 CSV / JSON 文件<input type="file" id="raw-file" accept=".csv,.json,.txt"></label><label>原文内容（只读留痕，不做前端换算）<textarea name="raw_text" rows="7" required placeholder="选择文件自动填入，或直接粘贴原文"></textarea></label><button type="submit" class="primary small">送入待审核区</button></form>'
   :'<p class="hint">观察员只读，不能上传或发布。</p>')
 +'</section>'
 // 右栏：批次列表 + 详情
 +'<section class="panel"><div class="section-title"><h2>待审核区批次</h2><span id="batch-count">'+batchList.length+' 批</span></div><div class="batch-list" id="batch-list">'+batchList.map(batchItem).join('')+'</div><div id="batch-detail" class="batch-detail">'+(batchList[0]?await batchDetailHtml(batchList[0].id):'<div class="empty">尚无接入批次。</div>')+'</div></section>'
 +'</div>';
}

function contractPanel(list){
 if(!list.length)return '<p class="hint">尚未登记任何接入契约，此时上传文件会因未知版本被拒收。</p>';
 const groups={};
 for(const c of list){(groups[c.source_version]??=[]).push(c);}
 return '<div class="contract-list">'+Object.entries(groups).map(([sv,cs])=>'<article class="contract-group"><header><strong>'+esc(sv)+'</strong><span>'+cs.length+' 个版本</span></header>'
   +cs.map(c=>'<div class="contract-version '+(c.active?'active':'retired')+'"><span>v'+c.version+'</span><span>'+(c.active?'当前生效':'已停用')+'</span><small>SHA256 '+esc(c.checksum.slice(0,16))+'…</small><details><summary>列映射与单位</summary><pre>'+esc(JSON.stringify({column_mapping:c.column_mapping,units:c.units},null,2))+'</pre></details></div>').join('')
   +'</article>').join('')+'</div>';
}

function batchItem(b){
 return '<button class="batch-item" data-batch="'+b.id+'"><strong>'+esc(b.name)+'</strong><span>'+esc(b.source_version)+' · 原文修订 '+b.raw_revision+' · '+(b.normalized_rows||0)+' 条标准记录</span><span>'+badge(b.status)+(b.error_count?'<em class="error-count">'+b.error_count+' 个错误</em>':'')+'</span><small>SHA256 '+esc(b.raw_checksum.slice(0,16))+'…</small></button>';
}

async function batchDetailHtml(id){
 const b=await ingestion.get(id);
 const m=workspace.meta;
 const errorRows=(b.errors||[]).slice(0,50).map(e=>({line:e.line?('第 '+e.line+' 行'):'整批',column:e.column||'—',message:e.message}));
 const attempts=(b.attempts||[]).map(a=>({id:a.id,kind:a.kind==='initial'?'初次接入':'重放',status:AttemptStatus[a.status]||a.status,revision:a.raw_revision,contract:a.contract_version?('v'+a.contract_version):'—',errors:a.error_count,finished:a.finished_at?date(a.finished_at):'—'}));
 return '<div class="detail-head"><h3>'+esc(b.name)+'</h3>'+badge(b.status)+'</div>'
 +'<dl class="basis-grid"><div><dt>来源版本</dt><dd>'+esc(b.source_version)+'</dd></div><div><dt>原文指纹</dt><dd title="'+esc(b.raw_checksum)+'">'+esc(b.raw_checksum.slice(0,24))+'…</dd></div><div><dt>原文修订</dt><dd>第 '+b.raw_revision+' 版</dd></div><div><dt>所用契约</dt><dd>'+(b.contract_version?('v'+b.contract_version+' · '+(b.contract_checksum||'').slice(0,12)+'…'):'—')+'</dd></div><div><dt>校验尝试</dt><dd>#'+(b.validated_attempt_id||'—')+'</dd></div><div><dt>发布依据</dt><dd>'+(b.published_dataset_id?('业务批次 #'+b.published_dataset_id):'未发布')+'</dd></div></dl>'
 +(b.error_count?'<div class="section-title"><h2>整批校验错误</h2><span>原文与旧错误保留留痕</span></div>'+table([{key:'line',label:'位置'},{key:'column',label:'列'},{key:'message',label:'错误说明'}],errorRows):'')
 +'<div class="section-title"><h2>尝试与重放历史</h2><span>保留每次所用契约与错误</span></div>'
 +(attempts.length?table([{key:'id',label:'尝试'},{key:'kind',label:'类型'},{key:'status',label:'结果'},{key:'revision',label:'原文修订'},{key:'contract',label:'契约版本'},{key:'errors',label:'错误数'},{key:'finished',label:'结束时间'}],attempts):'<div class="empty">无尝试记录。</div>')
 +'<div class="section-title"><h2>标准化记录预览</h2><span>单位已按契约换算（分钟）</span></div>'
 +(b.normalized_records?.length?table(m.columns,b.normalized_records.slice(0,15)):'<div class="empty">校验未通过或尚未校验，无标准化记录。</div>')
 +'<div class="section-title"><h2>原始文件</h2><span>不可编辑，替换原文会产生新修订号</span></div><pre class="raw-preview">'+esc((b.raw_text||'').slice(0,2000))+((b.raw_text||'').length>2000?'\n…（仅预览前 2000 字符）':'')+'</pre>'
 +actionBar(b);
}

function actionBar(b){
 if(!canWrite())return '<p class="hint">当前为'+Role[session.user.role]+'视图：全部操作只读。</p>';
 const buttons=[];
 if(b.status==='rejected')buttons.push('<button class="small" data-action="replay" data-id="'+b.id+'">按当前契约重放</button>');
 if(['rejected','passed'].includes(b.status))buttons.push('<button class="small" data-action="replace" data-id="'+b.id+'">替换原文并重新校验</button>');
 if(b.status==='passed'&&isAdmin())buttons.push('<button class="primary small" data-action="publish" data-id="'+b.id+'">审核通过并发布</button>');
 if(b.status==='passed'&&!isAdmin())buttons.push('<p class="hint">校验通过，等待业务负责人发布。</p>');
 if(b.status==='published')buttons.push('<a class="small button" href="#/datasets">查看已发布业务批次 ↗</a>');
 if(['staged','validating'].includes(b.status))buttons.push('<p class="hint">校验进行中，页面将自动刷新。</p>');
 return '<div class="action-bar" id="action-bar">'+buttons.join('')+'</div>';
}

export function bindIngestion(){
 const file=document.querySelector('#raw-file');
 file?.addEventListener('change',async e=>{
   const f=e.target.files[0];if(!f)return;
   document.querySelector('[name=raw_text]').value=await f.text();
   const source=document.querySelector('[name=source]');if(source&&!source.value.endsWith(f.name))source.value=f.name;
 });
 const cf=document.querySelector('#contract-form');
 if(cf)submit(cf,async f=>{
   const column_mapping={},units={};
   for(const c of workspace.meta.columns){
     column_mapping[f.get('map-'+c.key).trim()]=c.key;
     const unit=f.get('unit-'+c.key);units[c.key]=unit==='none'?'':unit;
   }
   await contracts.create({source_version:f.get('source_version').trim(),column_mapping,units});
   notify('契约已登记新版本，旧版本已停用');location.reload();
 });
 const sf=document.querySelector('#stage-form');
 if(sf)submit(sf,async f=>{
   const b=await ingestion.stage({name:f.get('name'),source:f.get('source')||'diary.csv',source_version:f.get('source_version').trim(),raw_text:f.get('raw_text')});
   notify(b.status==='rejected'?'未知版本或校验未通过，批次已拒收并保留原文':'原文已进入待审核区，后台整批校验中');
   refreshList(b.id);
 });
 document.querySelectorAll('[data-batch]').forEach(btn=>btn.onclick=()=>{selectedBatchId=Number(btn.dataset.batch);refreshDetail(selectedBatchId);});
 bindActions();
 startPolling();
}

function bindActions(){
 document.querySelectorAll('[data-action]').forEach(btn=>{
  btn.onclick=async()=>{
   const id=btn.dataset.id,action=btn.dataset.action;
   try{
    if(action==='replay'){await ingestion.replay(id);notify('已按当前契约发起重放，旧错误与契约仍保留');}
    if(action==='publish'){const r=await ingestion.publish(id);notify('已发布，业务批次 #'+r.dataset_id+' 进入分析范围');}
    if(action==='replace'){
      const input=document.createElement('input');input.type='file';input.accept='.csv,.json,.txt';
      input.onchange=async()=>{const f=input.files[0];if(!f)return;
        await ingestion.replaceRaw(id,{source:f.name,raw_text:await f.text()});
        notify('原文已替换，旧审核依据失效，正在重新校验');refreshList(id);};
      input.click();return;
    }
    refreshList(id);
   }catch(e){notify(e.message,true);}
  };
 });
}

async function refreshList(selectId){
 const list=await ingestion.list();workspace.batches=list;
 const el=document.querySelector('#batch-list');
 if(el){el.innerHTML=list.map(batchItem).join('');document.querySelector('#batch-count').textContent=list.length+' 批';
   document.querySelectorAll('[data-batch]').forEach(btn=>btn.onclick=()=>refreshDetail(btn.dataset.batch));}
 if(selectId)refreshDetail(selectId);
}
async function refreshDetail(id){
 const el=document.querySelector('#batch-detail');if(!el)return;
 el.innerHTML=await batchDetailHtml(id);bindActions();
}
function startPolling(){
 stopPolling();
 window.__ingestTimer=setInterval(async()=>{
   const busy=(workspace.batches||[]).some(b=>['staged','validating'].includes(b.status));
   if(!busy)return;
   const list=await ingestion.list();
   const changed=JSON.stringify(list.map(b=>[b.id,b.status,b.error_count]))!==JSON.stringify(workspace.batches.map(b=>[b.id,b.status,b.error_count]));
   workspace.batches=list;
   if(changed)refreshList(selectedBatchId);
 },3000);
 addEventListener('hashchange',stopPolling,{once:true});
}
function stopPolling(){if(window.__ingestTimer){clearInterval(window.__ingestTimer);window.__ingestTimer=null;}}
