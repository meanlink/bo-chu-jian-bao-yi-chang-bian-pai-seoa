from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class BatchStatus(str, Enum):
    staged = 'staged'        # 原始文件已进入待审核区，等待校验
    validating = 'validating'
    rejected = 'rejected'    # 整批校验失败，不生成业务批次
    passed = 'passed'        # 校验通过，等待负责人审核
    published = 'published'  # 已发布，业务批次只读
class AttemptStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    passed = 'passed'
    failed = 'failed'
