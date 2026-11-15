import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id)};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const contracts={
 list:()=>api('/contracts'),
 create:data=>api('/contracts',{method:'POST',body:JSON.stringify(data)}),
};
export const ingestion={
 list:()=>api('/ingestion-batches'),
 get:id=>api('/ingestion-batches/'+id),
 stage:data=>api('/ingestion-batches',{method:'POST',body:JSON.stringify(data)}),
 replay:id=>api('/ingestion-batches/'+id+'/replay',{method:'POST'}),
 replaceRaw:(id,data)=>api('/ingestion-batches/'+id+'/raw',{method:'POST',body:JSON.stringify(data)}),
 publish:id=>api('/ingestion-batches/'+id+'/publish',{method:'POST'}),
};
