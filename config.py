#API配置
OPENAI_API_KEY = "your_api_key"
OPENAI_API_BASE = "your_api_base"
MODEL_NAME = "qwen2.5-72b-instruct"
OPENAI_EMBEDDING_MODEL = "text-embedding-v4"

# 数据目录配置
DATA_DIR = "./data"

#向量数据库配置
VECTOR_DB_PATH = "./vector_db"
COLLECTION_NAME = "collection"

# 文本处理配置
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_TOKENS = 100000

# RAG配置
TOP_K = 6
MAX_ITER = 10