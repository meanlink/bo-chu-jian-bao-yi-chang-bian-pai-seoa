from fastapi import APIRouter, Depends
from sqlalchemy import select
from src.config.database import get_db
from src.models import IngestionContract
from src.schemas.ingestion import ContractInput
from src.middlewares.auth import current_user, admin_only
from src.services import ingestion
from src.services.audit import record
from src.utils.serialization import contract_dict

router = APIRouter(prefix='/contracts')

@router.get('')
def listing(db=Depends(get_db), u=Depends(current_user)):
    rows = db.scalars(select(IngestionContract).order_by(
        IngestionContract.source_version, IngestionContract.version.desc()))
    return [contract_dict(c) for c in rows]

@router.post('', status_code=201)
def create(data: ContractInput, db=Depends(get_db), u=Depends(admin_only)):
    c = ingestion.create_contract(db, data, u)
    db.commit()
    return contract_dict(c)
