import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc} from '../utils/dom.js';
export async function dataPage(){
 workspace.datasets=await datasets.list();let selected=workspace.datasets[0]?await datasets.get(workspace.datasets[0].id):null,m=workspace.meta;
 return heading('03 / PUBLISHED DATA','已发布业务批次','分析只读取已发布批次。每个业务批次都可追溯到待审核区的原始文件、所用契约版本与发布尝试；批次发布后只读。')+'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>已发布业务批次</h2><span>'+workspace.datasets.length+' 批 · 只读</span></div><div class="batch-list">'+(workspace.datasets.length?workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span>'+d.rows+' 条 · 契约 v'+esc(d.contract_version??'—')+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…</small></button>').join(''):'<div class="empty">尚无已发布批次。<a href="#/ingestion">前往接入审核区 ↗</a></div>')+'</div><p class="hint">原始文件必须先在接入审核区通过整批校验并经业务负责人发布；本页不再提供直建入口。</p><a class="button small" href="#/ingestion">前往接入审核区 ↗</a></section><section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无已发布批次')+'</h2><span>预览前 30 条（分钟口径）</span></div>'+(selected?'<dl class="basis-grid"><div><dt>发布依据批次</dt><dd>#'+esc(selected.ingestion_batch_id)+'</dd></div><div><dt>契约版本</dt><dd>v'+esc(selected.contract_version)+'</dd></div><div><dt>内容指纹</dt><dd>'+esc(selected.checksum.slice(0,24))+'…</dd></div></dl>':'')+'<div id="data-preview">'+table(m.columns,selected?.records.slice(0,30)||[])+'</div></section></div>';
}
export function bindData(){
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{const d=await datasets.get(button.dataset.dataset);document.querySelector('#preview-name').textContent=d.name;document.querySelector('#data-preview').innerHTML=table(workspace.meta.columns,d.records.slice(0,30));});
}
