import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum,
            'created_at':d.created_at, 'ingestion_batch_id':getattr(d,'ingestion_batch_id',None),
            'contract_id':getattr(d,'contract_id',None), 'contract_version':getattr(d,'contract_version',None)}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def contract_dict(c):
    return {'id':c.id,'source_version':c.source_version,'version':c.version,'name':c.name,
            'column_mapping':c.column_mapping,'units':c.units,'active':c.active,'checksum':c.checksum,
            'created_at':c.created_at}
def attempt_dict(a):
    return {'id':a.id,'batch_id':a.batch_id,'kind':a.kind,'status':a.status,'raw_checksum':a.raw_checksum,
            'raw_revision':a.raw_revision,'contract_id':a.contract_id,'contract_version':a.contract_version,
            'contract_checksum':a.contract_checksum,'errors':a.errors,'error_count':a.error_count,
            'started_at':a.started_at,'finished_at':a.finished_at,'created_at':a.created_at}
def batch_dict(b, include_raw=False):
    data = {'id':b.id,'name':b.name,'source':b.source,'source_version':b.source_version,
            'raw_format':b.raw_format,'raw_checksum':b.raw_checksum,'raw_revision':b.raw_revision,
            'status':b.status,'errors':b.errors,'error_count':b.error_count,
            'contract_id':b.contract_id,'contract_version':b.contract_version,'contract_checksum':b.contract_checksum,
            'normalized_rows':len(b.normalized_records or []),'validated_at':b.validated_at,
            'validated_attempt_id':getattr(b,'validated_attempt_id',None),
            'published_dataset_id':b.published_dataset_id,'published_at':b.published_at,
            'created_by':b.created_by,'created_at':b.created_at}
    if include_raw:
        data['raw_text'] = b.raw_text
        data['normalized_records'] = b.normalized_records
        data['attempts'] = None
    return data
