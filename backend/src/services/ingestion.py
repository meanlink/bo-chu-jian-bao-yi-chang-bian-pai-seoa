"""接入契约与待审核区：按来源版本登记列映射和单位，原始文件先进待审核区，
未知版本或整批校验失败不生成业务批次；负责人审核通过后才发布。"""
import csv
import hashlib
import io
import json
import math
import time
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.config.database import Session
from src.models import (
    Dataset, IngestionAttempt, IngestionBatch, IngestionContract,
)
from src.services.audit import record
from src.utils.serialization import checksum

# 标准列（与业务算法口径一致），时长类列统一换算为分钟入库
CANONICAL_COLUMNS = [
    {"key": "day", "label": "播出日", "type": "string", "kind": "date"},
    {"key": "channel", "label": "播出链路", "type": "string", "kind": "dimension"},
    {"key": "planned_min", "label": "计划分钟", "type": "number", "kind": "duration"},
    {"key": "aired_min", "label": "实播分钟", "type": "number", "kind": "duration"},
    {"key": "interruption_min", "label": "停播分钟", "type": "number", "kind": "duration"},
    {"key": "reach", "label": "触达估计", "type": "number", "kind": "count"},
]
CANONICAL_KEYS = [c["key"] for c in CANONICAL_COLUMNS]
# 原始单位 -> 换算为标准单位（分钟 / 个）的系数
UNIT_FACTORS = {
    "second": 1 / 60.0, "seconds": 1 / 60.0, "sec": 1 / 60.0, "秒": 1 / 60.0,
    "minute": 1.0, "minutes": 1.0, "min": 1.0, "分钟": 1.0, "分": 1.0,
    "count": 1.0, "个": 1.0, "次": 1.0, "none": 1.0, "": 1.0,
}
MAX_ROWS = 5000
MIN_ROWS = 5
MAX_ERRORS_KEPT = 200
INGESTION_QUEUE = "ingestion:queue"


# ---------------------------------------------------------------- 契约
def contract_checksum(column_mapping, units):
    return hashlib.sha256(
        json.dumps({"mapping": column_mapping, "units": units}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def validate_contract_payload(source_version, column_mapping, units):
    source_version = str(source_version).strip()
    if not source_version:
        raise HTTPException(422, "来源版本不能为空")
    if not isinstance(column_mapping, dict) or not column_mapping:
        raise HTTPException(422, "列映射必须是非空对象：原始列名 -> 标准列")
    targets = [str(v).strip() for v in column_mapping.values()]
    missing = [k for k in CANONICAL_KEYS if k not in targets]
    if missing:
        raise HTTPException(422, "列映射缺少标准列：" + "、".join(missing))
    unknown = [t for t in targets if t not in CANONICAL_KEYS]
    if unknown:
        raise HTTPException(422, "列映射包含未知标准列：" + "、".join(sorted(set(unknown))))
    if len(set(targets)) != len(targets):
        raise HTTPException(422, "列映射中每个标准列只能对应一个原始列")
    if not isinstance(units, dict):
        raise HTTPException(422, "单位登记必须是对象：标准列 -> 原始单位")
    for key, raw_unit in units.items():
        if key not in CANONICAL_KEYS:
            raise HTTPException(422, f"单位登记包含未知标准列：{key}")
        if str(raw_unit).strip().lower() not in UNIT_FACTORS:
            raise HTTPException(422, f"列 {key} 的单位 {raw_unit} 不受支持（支持秒/分钟/个等）")
    normalized_units = {k: str(v).strip() for k, v in units.items()}
    return source_version, {str(k).strip(): str(v).strip() for k, v in column_mapping.items()}, normalized_units


def create_contract(db, data, user):
    source_version, mapping, units = validate_contract_payload(
        data.source_version, data.column_mapping, data.units
    )
    last = db.scalar(
        select(IngestionContract)
        .where(IngestionContract.source_version == source_version)
        .order_by(IngestionContract.version.desc())
    )
    if last:
        last.active = False
        db.flush()
    version = (last.version + 1) if last else 1
    c = IngestionContract(
        source_version=source_version, version=version, name=data.name.strip() or source_version,
        column_mapping=mapping, units=units, active=True,
        checksum=contract_checksum(mapping, units), created_by=user.id, created_at=time.time(),
    )
    db.add(c)
    db.flush()
    record(db, user.email, "contract.create", {"id": c.id, "source_version": source_version, "version": version})
    return c


def active_contract(db, source_version):
    return db.scalar(
        select(IngestionContract)
        .where(IngestionContract.source_version == source_version, IngestionContract.active == True)  # noqa: E712
        .order_by(IngestionContract.version.desc())
    )


# ---------------------------------------------------------------- 原文解析
def parse_raw(raw_text, raw_format):
    try:
        if raw_text.startswith("\ufeff"):
            raw_text = raw_text.lstrip("\ufeff")
        if raw_format == "json":
            rows = json.loads(raw_text)
            if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
                raise ValueError("JSON 必须是对象数组，且至少包含一行")
            return rows
        reader = csv.DictReader(io.StringIO(raw_text))
        if not reader.fieldnames:
            raise ValueError("CSV 缺少表头")
        rows = [dict(r) for r in reader]
        if not rows:
            raise ValueError("CSV 没有数据行")
        return rows
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"原始 JSON 解析失败：{e.msg}")
    except csv.Error as e:
        raise HTTPException(422, f"原始 CSV 解析失败：{e}")
    except ValueError as e:
        raise HTTPException(422, str(e))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 整批校验
def _convert_row(raw_row, mapping, units, line_no, errors):
    record = {}
    for col in CANONICAL_COLUMNS:
        key = col["key"]
        raw_name = next((r for r, target in mapping.items() if target == key), None)
        value = raw_row.get(raw_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({"line": line_no, "column": col["label"], "message": "缺少字段"})
            continue
        if col["type"] == "string":
            record[key] = str(value).strip()
            continue
        try:
            if isinstance(value, bool):
                raise ValueError
            number = float(value)
            if not math.isfinite(number):
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"line": line_no, "column": col["label"], "message": f"非有限数值：{value}"})
            continue
        factor = UNIT_FACTORS[units.get(key, "").strip().lower()]
        record[key] = round(number * factor, 6)
    return record


def validate_rows(rows, contract):
    """按契约映射列并换算单位，执行业务口径校验；返回(标准记录, 错误清单)。"""
    mapping, units = contract.column_mapping, contract.units
    errors, normalized = [], []
    if not (MIN_ROWS <= len(rows) <= MAX_ROWS):
        errors.append({"line": 0, "column": "", "message": f"记录数须在 {MIN_ROWS}–{MAX_ROWS} 之间，当前 {len(rows)}"})
    seen = set()
    for index, raw_row in enumerate(rows, start=1):
        rec = _convert_row(raw_row, mapping, units, index, errors)
        if len(errors) > MAX_ERRORS_KEPT:
            break
        # 业务口径：日期、分钟范围、实播/停播不超过计划
        day_text = rec.get("day")
        if day_text is not None:
            try:
                day = date.fromisoformat(day_text)
            except ValueError:
                errors.append({"line": index, "column": "播出日", "message": f"不是 ISO 日期：{day_text}"})
            else:
                identity = (day, rec.get("channel"))
                if identity in seen:
                    errors.append({"line": index, "column": "播出日", "message": f"链路 {rec.get('channel')} 日期重复：{day_text}"})
                seen.add(identity)
        planned, aired, interruption = rec.get("planned_min"), rec.get("aired_min"), rec.get("interruption_min")
        if planned is not None and not 0 < planned <= 1440:
            errors.append({"line": index, "column": "计划分钟", "message": f"换算后 {planned} 不在 (0,1440] 分钟区间，请核对原始单位"})
        if planned is not None and aired is not None and not 0 <= aired <= planned:
            errors.append({"line": index, "column": "实播分钟", "message": f"{aired} 超出计划分钟 {planned}"})
        if planned is not None and interruption is not None and not 0 <= interruption <= planned:
            errors.append({"line": index, "column": "停播分钟", "message": f"{interruption} 超出计划分钟 {planned}"})
        normalized.append(rec)
    return normalized, errors


# ---------------------------------------------------------------- 待审核区
def stage_batch(db, data, user):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, "批次名称去除空格后至少需要两个字符")
    if db.scalar(select(IngestionBatch).where(IngestionBatch.name == name)):
        raise HTTPException(409, "该接入批次名已存在，请修改名称")
    raw_text = data.raw_text
    if not raw_text or not raw_text.strip():
        raise HTTPException(422, "原始文件内容为空")
    raw_format = "csv" if raw_text.lstrip()[:1] != "[" else "json"
    if data.source.lower().endswith(".json"):
        raw_format = "json"
    raw_checksum = sha256_text(raw_text)
    source_version = data.source_version.strip()
    if not source_version:
        raise HTTPException(422, "请声明原始文件的来源版本")
    contract = active_contract(db, source_version)
    batch = IngestionBatch(
        name=name, source=data.source, source_version=source_version, raw_text=raw_text,
        raw_format=raw_format, raw_checksum=raw_checksum, raw_revision=1,
        status="staged", created_by=user.id, created_at=time.time(),
    )
    db.add(batch)
    db.flush()
    attempt = IngestionAttempt(
        batch_id=batch.id, kind="initial", status="queued", raw_checksum=raw_checksum,
        raw_revision=1, created_at=time.time(),
    )
    if contract is None:
        # 未知版本：直接拒绝，绝不生成业务批次
        batch.status = "rejected"
        batch.errors = [{"line": 0, "column": "", "message": f"未知来源版本 {source_version}，请先登记接入契约"}]
        batch.error_count = 1
        attempt.status = "failed"
        attempt.errors = batch.errors
        attempt.error_count = 1
        attempt.finished_at = time.time()
        record(db, user.email, "ingest.reject_unknown_version", {"id": batch.id, "source_version": source_version})
    else:
        attempt.contract_id = contract.id
        attempt.contract_version = contract.version
        attempt.contract_checksum = contract.checksum
        record(db, user.email, "ingest.stage", {"id": batch.id, "source_version": source_version})
    db.add(attempt)
    db.flush()
    return batch, attempt


def run_attempt(attempt_id):
    """worker 执行：整批校验（全有或全无），任何失败都只留在待审核区。"""
    with Session() as db:
        attempt = db.get(IngestionAttempt, attempt_id)
        if attempt is None:
            return
        # 幂等：已结束的尝试不重复执行
        if attempt.status != "queued":
            return
        batch = db.get(IngestionBatch, attempt.batch_id)
        if batch is None or batch.status == "published":
            attempt.status = "failed"
            attempt.errors = [{"line": 0, "column": "", "message": "批次不存在或已发布，尝试作废"}]
            attempt.error_count = 1
            attempt.finished_at = time.time()
            db.commit()
            return
        attempt.status = "running"
        attempt.started_at = time.time()
        batch.status = "validating"
        db.commit()
        try:
            contract = db.get(IngestionContract, attempt.contract_id) if attempt.contract_id else None
            errors = []
            normalized = None
            if contract is None:
                errors = [{"line": 0, "column": "", "message": f"未知来源版本 {batch.source_version}，请先登记接入契约"}]
            else:
                # 重放期间契约改版：旧尝试引用的契约若已停用，按当前活跃契约重放由新尝试承担；
                # 这里先确认所用契约仍是登记版本，防止校验口径被静默替换
                if contract.checksum != attempt.contract_checksum:
                    errors = [{"line": 0, "column": "", "message": "所用契约在执行前已被替换，本次尝试作废，请重新发起重放"}]
                else:
                    rows = parse_raw(batch.raw_text, batch.raw_format)
                    normalized, errors = validate_rows(rows, contract)
            now = time.time()
            attempt.errors = errors[:MAX_ERRORS_KEPT]
            attempt.error_count = len(errors)
            attempt.finished_at = now
            if errors:
                attempt.status = "failed"
                batch.status = "rejected"
                batch.errors = errors[:MAX_ERRORS_KEPT]
                batch.error_count = len(errors)
                batch.normalized_records = None
                batch.contract_id, batch.contract_version, batch.contract_checksum = None, None, None
                batch.validated_at = None
                batch.validated_attempt_id = None
                record(db, "worker", "ingest.failed", {"id": batch.id, "attempt": attempt.id, "errors": len(errors)})
            else:
                attempt.status = "passed"
                batch.status = "passed"
                batch.errors = []
                batch.error_count = 0
                batch.normalized_records = normalized
                batch.contract_id = contract.id
                batch.contract_version = contract.version
                batch.contract_checksum = contract.checksum
                batch.validated_at = now
                batch.validated_attempt_id = attempt.id
                record(db, "worker", "ingest.passed", {"id": batch.id, "attempt": attempt.id, "rows": len(normalized)})
            db.commit()
        except HTTPException as e:
            attempt.status = "failed"
            attempt.errors = [{"line": 0, "column": "", "message": str(e.detail)}]
            attempt.error_count = 1
            attempt.finished_at = time.time()
            batch.status = "rejected"
            batch.errors = attempt.errors
            batch.error_count = 1
            record(db, "worker", "ingest.failed", {"id": batch.id, "attempt": attempt.id})
            db.commit()
        except Exception:
            # 中断恢复：running 尝试由 worker 启动时重置为 queued
            db.rollback()
            raise


def replay_batch(db, batch_id, user):
    batch = db.get(IngestionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "接入批次不存在")
    if batch.status == "published":
        raise HTTPException(409, "已发布批次不能重放；如需修订请上传新原文建立新批次")
    if batch.status in ("staged", "validating"):
        raise HTTPException(409, "批次仍在校验队列中，请等待当前尝试结束")
    contract = active_contract(db, batch.source_version)
    # 重放幂等：已有排队/运行中的尝试时不重复创建
    busy = db.scalar(
        select(IngestionAttempt)
        .where(IngestionAttempt.batch_id == batch.id, IngestionAttempt.status.in_(["queued", "running"]))
    )
    if busy:
        raise HTTPException(409, "该批次已有进行中的重放尝试，请勿重复发起")
    attempt = IngestionAttempt(
        batch_id=batch.id, kind="replay", status="queued",
        raw_checksum=batch.raw_checksum, raw_revision=batch.raw_revision,
        created_at=time.time(),
    )
    if contract is None:
        attempt.status = "failed"
        attempt.errors = [{"line": 0, "column": "", "message": f"未知来源版本 {batch.source_version}，请先登记接入契约"}]
        attempt.error_count = 1
        attempt.finished_at = time.time()
        batch.status = "rejected"
        batch.errors = attempt.errors
        batch.error_count = 1
    else:
        attempt.contract_id = contract.id
        attempt.contract_version = contract.version
        attempt.contract_checksum = contract.checksum
        batch.status = "staged"
    db.add(attempt)
    db.flush()
    record(db, user.email, "ingest.replay", {"id": batch.id, "attempt": attempt.id, "contract": attempt.contract_version})
    return attempt


def replace_raw(db, batch_id, data, user):
    """审核期间原文被替换：修订号+1，旧审核依据失效，必须重新校验。"""
    batch = db.get(IngestionBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "接入批次不存在")
    if batch.status == "published":
        raise HTTPException(409, "已发布批次只读，不能替换原文；请建立新批次")
    if batch.status in ("staged", "validating"):
        raise HTTPException(409, "批次仍在校验队列中，暂不能替换原文")
    raw_text = data.raw_text
    if not raw_text or not raw_text.strip():
        raise HTTPException(422, "原始文件内容为空")
    new_checksum = sha256_text(raw_text)
    if new_checksum == batch.raw_checksum:
        raise HTTPException(422, "新原文与当前原文指纹一致，无需替换")
    raw_format = "csv" if raw_text.lstrip()[:1] != "[" else "json"
    if data.source.lower().endswith(".json"):
        raw_format = "json"
    batch.raw_text = raw_text
    batch.raw_format = raw_format
    batch.raw_checksum = new_checksum
    batch.raw_revision += 1
    batch.status = "staged"
    batch.normalized_records = None
    batch.contract_id, batch.contract_version, batch.contract_checksum = None, None, None
    batch.validated_at = None
    batch.validated_attempt_id = None
    attempt = IngestionAttempt(
        batch_id=batch.id, kind="replay", status="queued",
        raw_checksum=new_checksum, raw_revision=batch.raw_revision, created_at=time.time(),
    )
    contract = active_contract(db, batch.source_version)
    if contract is None:
        attempt.status = "failed"
        attempt.errors = [{"line": 0, "column": "", "message": f"未知来源版本 {batch.source_version}，请先登记接入契约"}]
        attempt.error_count = 1
        attempt.finished_at = time.time()
        batch.status = "rejected"
        batch.errors = attempt.errors
        batch.error_count = 1
    else:
        attempt.contract_id = contract.id
        attempt.contract_version = contract.version
        attempt.contract_checksum = contract.checksum
    db.add(attempt)
    db.flush()
    record(db, user.email, "ingest.replace_raw", {"id": batch.id, "revision": batch.raw_revision})
    return attempt


# ---------------------------------------------------------------- 审核发布
def publish_batch(db, batch_id, user):
    """负责人审核通过后发布。并发审核、契约改版、原文替换都会让旧审核结果失效。"""
    batch = db.scalar(
        select(IngestionBatch).where(IngestionBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(404, "接入批次不存在")
    if batch.status == "published":
        # 重试不重复发布：返回已发布结果
        return db.get(Dataset, batch.published_dataset_id)
    if batch.status != "passed":
        raise HTTPException(409, "仅校验通过的批次可以审核发布；被拒批次请修正契约或原文后重放")
    contract = db.get(IngestionContract, batch.contract_id) if batch.contract_id else None
    if contract is None or not contract.active or contract.checksum != batch.contract_checksum:
        raise HTTPException(409, "审核依据已失效：契约在审核期间改版，请按新契约重放后再审核")
    if sha256_text(batch.raw_text) != batch.raw_checksum:
        raise HTTPException(409, "审核依据已失效：原文在审核期间被替换，请重新校验后再审核")
    basis = db.get(IngestionAttempt, batch.validated_attempt_id) if batch.validated_attempt_id else None
    if basis is None or basis.status != "passed" or basis.raw_checksum != batch.raw_checksum \
            or basis.contract_checksum != batch.contract_checksum:
        raise HTTPException(409, "审核依据已失效：校验尝试与当前原文/契约不一致，请重放后再审核")
    records = batch.normalized_records
    if not records:
        raise HTTPException(409, "缺少校验通过的标准记录，无法发布")
    dataset = Dataset(
        name=batch.name, source=batch.source, records=records,
        checksum=checksum(records), created_at=time.time(),
        ingestion_batch_id=batch.id, contract_id=contract.id, contract_version=contract.version,
    )
    db.add(dataset)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同名业务批次已存在，发布已中止")
    batch.status = "published"
    batch.published_dataset_id = dataset.id
    batch.published_at = time.time()
    batch.published_by = user.id
    record(db, user.email, "ingest.publish", {
        "id": batch.id, "dataset": dataset.id, "contract": contract.version,
        "raw_revision": batch.raw_revision, "raw_checksum": batch.raw_checksum,
    })
    return dataset
