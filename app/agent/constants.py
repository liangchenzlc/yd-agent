# 最大反思重试次数
MAX_REFINEMENTS = 2

# Refiner 评分阈值（0-10），低于此值触发重试
REFINER_SCORE_THRESHOLD = 7

# Docker 沙箱镜像
DOCKER_SANDBOX_IMAGE = "python:3.12-slim"

# 代码执行超时（秒）
CODE_TIMEOUT = 30

# Worker 名称常量
WORKER_RETRIEVAL = "retrieval"
WORKER_CODE = "code"
WORKER_ACTION = "action"
WORKER_SUMMARY = "summary"

ALL_WORKERS = [WORKER_RETRIEVAL, WORKER_CODE, WORKER_ACTION, WORKER_SUMMARY]
