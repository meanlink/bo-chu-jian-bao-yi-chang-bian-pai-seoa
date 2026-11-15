import time, json, logging
from pathlib import Path
from sqlalchemy import select
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report, IngestionAttempt
from src.services.business import analyze
from src.services.reports import deliver
from src.services.ingestion import run_attempt, INGESTION_QUEUE
from src.services.audit import record
logging.basicConfig(level=logging.INFO)
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        j.status='running'; db.commit()
        try:
            d=db.get(Dataset,j.dataset_id)
            result=analyze(d.records,j.params)
            json.dumps(result,allow_nan=False)
            j.result=result;j.status='completed';j.finished_at=time.time()
            record(db,'worker','job.completed',{'id':j.id})
        except Exception as e:
            logging.exception('Analysis failed')
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'error':j.error})
        db.commit()
def tick():
    # 接入校验：Redis 丢失时由 SQL queued 状态兜底
    with Session() as db:
        pending=list(db.scalars(select(IngestionAttempt.id).where(IngestionAttempt.status=='queued').limit(5)))
    for attempt_id in pending:
        try: run_attempt(attempt_id)
        except Exception: logging.exception('Ingestion attempt %s failed', attempt_id)
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()
def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        # 重放中断恢复：running 尝试回到排队，重试由状态机保证不重复发布
        for a in db.scalars(select(IngestionAttempt).where(IngestionAttempt.status=='running')):
            a.status='queued';record(db,'worker','ingest.recovered',{'id':a.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            # 先处理接入队列（非阻塞排空），再处理分析队列
            for _ in range(10):
                item=r.lpop(INGESTION_QUEUE)
                if not item: break
                try: run_attempt(int(item[1]))
                except Exception: logging.exception('Ingestion queue item failed')
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
