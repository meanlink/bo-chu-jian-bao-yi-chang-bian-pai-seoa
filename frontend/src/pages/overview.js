import {api} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {esc,date} from '../utils/dom.js';
export async function overview(){
 const [o,jobs,audits]=await Promise.all([api('/overview'),api('/jobs'),api('/audits')]),m=workspace.meta,baseline=jobs.find(j=>j.status==='completed');
 return heading('01 / DAILY BRIEF',m.name,m.workflow,'<a class="button primary" href="#/workbench">'+esc(m.action_label||'发起分析')+' ↗</a>')+'<section class="overview-hero"><div class="narrative"><p class="eyebrow">当前业务判断</p><h2>'+esc(baseline?.result?.summary||'先在接入审核区发布一批真实业务记录，形成可复核的分析结论。')+'</h2><p>'+esc(m.upstream)+' → '+esc(m.downstream)+'</p><a href="#/ingestion" class="text-link">前往接入审核区 ↗</a></div><div class="numbers">'+[['已发布记录',o.records],['业务批次',o.datasets],['待审核/拒绝',(o.batches_staged||0)+' / '+(o.batches_rejected||0)],['接入契约',o.contracts||0],['分析任务',o.jobs],['已批准结果',o.approved]].map(([k,v])=>'<div><span>'+k+'</span><strong>'+v+'</strong></div>').join('')+'</div></section><section class="panel"><div class="section-title"><h2>基线切片</h2><span>来自 Python 计算 · '+esc(m.method)+'</span></div>'+chart(baseline?.result?.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>今天需要回答</h2></div><ol class="questions">'+m.pains.map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol></section><section class="panel"><div class="section-title"><h2>最近动作</h2><span>可追溯记录</span></div><ul class="timeline">'+audits.slice(0,4).map(a=>'<li><strong>'+esc(a.action)+'</strong><span>'+esc(a.actor)+' · '+date(a.at)+'</span></li>').join('')+'</ul></section></div>';
}
