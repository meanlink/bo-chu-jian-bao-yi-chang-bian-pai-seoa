import time, json, csv, io
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, IngestionContract, IngestionBatch, IngestionAttempt
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services.ingestion import (
    contract_checksum, sha256_text, validate_rows, CANONICAL_KEYS,
)
from src.utils.security import hash_password
from src.utils.serialization import checksum

V1_VERSION = 'diary-v1-minutes'
V2_VERSION = 'diary-v2-seconds'

# v1：列名即标准 key，单位分钟；v2：新版日记以秒记录时长，中文列名
V1_MAPPING = {k: k for k in CANONICAL_KEYS}
V1_UNITS = {'planned_min': 'minute', 'aired_min': 'minute', 'interruption_min': 'minute', 'reach': 'count'}
V2_MAPPING = {
    '播出日': 'day', '播出链路': 'channel', '计划时长': 'planned_min',
    '实播时长': 'aired_min', '停播时长': 'interruption_min', '收视触达': 'reach',
}
V2_UNITS = {'planned_min': 'second', 'aired_min': 'second', 'interruption_min': 'second', 'reach': 'count'}


def _ensure_contract(db, source_version, name, mapping, units, admin):
    c = db.scalar(select(IngestionContract).where(
        IngestionContract.source_version == source_version,
        IngestionContract.version == 1,
    ))
    if c:
        return c
    c = IngestionContract(
        source_version=source_version, version=1, name=name, column_mapping=mapping, units=units,
        active=True, checksum=contract_checksum(mapping, units), created_by=admin.id, created_at=time.time(),
    )
    db.add(c)
    db.flush()
    return c


def _records_to_csv(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        admin=db.scalar(select(User).where(User.role=='admin'))
        c1=_ensure_contract(db, V1_VERSION, '播控日记（分钟版）', V1_MAPPING, V1_UNITS, admin)
        c2=_ensure_contract(db, V2_VERSION, '播控日记（秒级新版）', V2_MAPPING, V2_UNITS, admin)

        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            raw_text=_records_to_csv(rows)
            normalized, errors = validate_rows(rows, c1)
            assert not errors, errors
            b=IngestionBatch(
                name=m['dataset_name'], source=m['short']+'-202611.csv', source_version=V1_VERSION,
                raw_text=raw_text, raw_format='csv', raw_checksum=sha256_text(raw_text), raw_revision=1,
                status='published', errors=[], error_count=0,
                contract_id=c1.id, contract_version=c1.version, contract_checksum=c1.checksum,
                normalized_records=normalized, validated_at=time.time()-3700,
                created_by=admin.id, created_at=time.time()-3600,
            )
            db.add(b); db.flush()
            a1=IngestionAttempt(
                batch_id=b.id, kind='initial', status='passed', raw_checksum=b.raw_checksum, raw_revision=1,
                contract_id=c1.id, contract_version=1, contract_checksum=c1.checksum,
                errors=[], error_count=0, started_at=time.time()-3700, finished_at=time.time()-3600,
                created_at=time.time()-3700,
            )
            db.add(a1); db.flush()
            b.validated_attempt_id=a1.id
            d=Dataset(
                name=m['dataset_name'], source=b.source, records=normalized, checksum=checksum(normalized),
                created_at=time.time()-3600, ingestion_batch_id=b.id, contract_id=c1.id, contract_version=1,
            )
            db.add(d); db.flush()
            b.published_dataset_id=d.id; b.published_at=time.time()-3600; b.published_by=admin.id
            db.add(Audit(actor='seed', action='ingest.publish', detail={'id': b.id, 'dataset': d.id}, at=time.time()-3600))

        # 演示待审核区：新版秒级日记（时长换算为分钟），处于 passed 待审核状态
        demo_batch_name='海棠融媒_秒级新版日记_待审核.csv'
        if not db.scalar(select(IngestionBatch).where(IngestionBatch.name==demo_batch_name)):
            sample=seed_records()[:80]
            sec_rows=[{
                '播出日': r['day'], '播出链路': r['channel'],
                '计划时长': round(r['planned_min']*60, 2),
                '实播时长': round(r['aired_min']*60, 2),
                '停播时长': round(r['interruption_min']*60, 2),
                '收视触达': r['reach'],
            } for r in sample]
            raw_text=_records_to_csv(sec_rows)
            normalized, errors = validate_rows(sec_rows, c2)
            assert not errors, errors
            b2=IngestionBatch(
                name=demo_batch_name, source='diary-202611-seconds.csv', source_version=V2_VERSION,
                raw_text=raw_text, raw_format='csv', raw_checksum=sha256_text(raw_text), raw_revision=1,
                status='passed', errors=[], error_count=0,
                contract_id=c2.id, contract_version=c2.version, contract_checksum=c2.checksum,
                normalized_records=normalized, validated_at=time.time()-600,
                created_by=admin.id, created_at=time.time()-660,
            )
            db.add(b2); db.flush()
            a2=IngestionAttempt(
                batch_id=b2.id, kind='initial', status='passed', raw_checksum=b2.raw_checksum, raw_revision=1,
                contract_id=c2.id, contract_version=1, contract_checksum=c2.checksum,
                errors=[], error_count=0, started_at=time.time()-660, finished_at=time.time()-600,
                created_at=time.time()-660,
            )
            db.add(a2); db.flush()
            b2.validated_attempt_id=a2.id

        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,IngestionContract,IngestionBatch]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
