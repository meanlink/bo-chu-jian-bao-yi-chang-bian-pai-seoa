from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset
from src.middlewares.auth import current_user
from src.utils.serialization import dataset_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    # 仅返回已发布业务批次（待审核区数据不对外可见为业务批次）
    rows=db.scalars(select(Dataset).where(Dataset.ingestion_batch_id.isnot(None)).order_by(Dataset.id.desc()))
    return [dataset_dict(d) for d in rows]
@router.post('',status_code=201)
def create():
    # 直建入口已废止：原始文件必须先进待审核区，审核通过后由发布动作生成业务批次
    raise HTTPException(410,'直建数据批次入口已废止，请使用 /ingestion-batches 上传原文并完成审核发布')
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d or d.ingestion_batch_id is None:raise HTTPException(404,'已发布数据批次不存在')
    return {**dataset_dict(d),'records':d.records}
