from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from redis import Redis
from src.config.database import get_db
from src.config.settings import REDIS_URL
from src.models import IngestionAttempt, IngestionBatch
from src.schemas.ingestion import BatchInput, RawReplaceInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import ingestion
from src.utils.serialization import batch_dict, attempt_dict

router = APIRouter(prefix='/ingestion-batches')

def enqueue_attempt(attempt_id):
    try:
        r = Redis.from_url(REDIS_URL)
        r.rpush(ingestion.INGESTION_QUEUE, attempt_id)
        r.close()
    except Exception:
        pass  # SQL queued 状态是持久化兜底，worker tick 会捞起

@router.get('')
def listing(db=Depends(get_db), u=Depends(current_user)):
    rows = db.scalars(select(IngestionBatch).order_by(IngestionBatch.id.desc()).limit(200))
    return [batch_dict(b) for b in rows]

@router.post('', status_code=201)
def stage(data: BatchInput, db=Depends(get_db), u=Depends(can_write)):
    batch, attempt = ingestion.stage_batch(db, data, u)
    db.commit()
    if attempt.status == 'queued':
        enqueue_attempt(attempt.id)
    return batch_dict(db.get(IngestionBatch, batch.id))

@router.get('/{id}')
def detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    b = db.get(IngestionBatch, id)
    if not b:
        raise HTTPException(404, '接入批次不存在')
    data = batch_dict(b, include_raw=True)
    data['attempts'] = [attempt_dict(a) for a in db.scalars(
        select(IngestionAttempt).where(IngestionAttempt.batch_id == id).order_by(IngestionAttempt.id))]
    return data

@router.post('/{id}/replay', status_code=202)
def replay(id: int, db=Depends(get_db), u=Depends(can_write)):
    attempt = ingestion.replay_batch(db, id, u)
    db.commit()
    if attempt.status == 'queued':
        enqueue_attempt(attempt.id)
    return attempt_dict(db.get(IngestionAttempt, attempt.id))

@router.post('/{id}/raw', status_code=202)
def replace_raw(id: int, data: RawReplaceInput, db=Depends(get_db), u=Depends(can_write)):
    attempt = ingestion.replace_raw(db, id, data, u)
    db.commit()
    if attempt.status == 'queued':
        enqueue_attempt(attempt.id)
    return attempt_dict(db.get(IngestionAttempt, attempt.id))

@router.post('/{id}/publish', status_code=201)
def publish(id: int, db=Depends(get_db), u=Depends(admin_only)):
    dataset = ingestion.publish_batch(db, id, u)
    db.commit()
    return {'dataset_id': dataset.id, 'batch': batch_dict(db.get(IngestionBatch, id))}
