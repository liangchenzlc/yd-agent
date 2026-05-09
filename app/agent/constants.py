# 最大反思重试次数
MAX_REFINEMENTS = 2

# Refiner 评分阈值（0-10），低于此值触发重试
REFINER_SCORE_THRESHOLD = 7

# Docker 沙箱镜像
DOCKER_SANDBOX_IMAGE = "python:3.12-slim"

# 代码执行超时（秒）
CODE_TIMEOUT = 30

# GraphRAG
GRAPH_FIELD_SEP = "<SEP>"
DEFAULT_ENTITY_TYPES = ["person", "organization", "product", "concept", "location", "event", "technology"]
DEFAULT_MAX_GLEANING = 1

# 文档分块
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 100

# 检索
CHUNK_TOP_K = 20
ENTITY_TOP_K = 10
RELATIONSHIP_TOP_K = 10
COSINE_THRESHOLD = 0.6

# Worker 名称常量
WORKER_RETRIEVAL = "retrieval"
WORKER_CODE = "code"
WORKER_DOCS = "docs"
WORKER_SUMMARY = "summary"

ALL_WORKERS = [WORKER_RETRIEVAL, WORKER_CODE, WORKER_DOCS, WORKER_SUMMARY]

# 记忆
MEMORY_EXTRACTION_TYPES = ["fact", "preference", "pattern", "template"]
WORKING_MEMORY_TTL = 24  # 小时
MEMORY_TOP_K = 5
CORE_MEMORY_WEIGHT = 0.6
WORKING_MEMORY_WEIGHT = 0.4
DEFAULT_USER_ID = "default"

# Eval
EVAL_HARD_CASE_THRESHOLD = 5
EVAL_DIMENSIONS = ["faithfulness", "relevance", "completeness"]
EVAL_MAX_RECENT_RUNS = 200
EVAL_SCORE_BUCKETS = ["0-3", "4-6", "7-8", "9-10"]
