import os
from typing import List, Dict, Any

import chromadb
from chromadb.config import Settings
from openai import OpenAI
from tqdm import tqdm

import jieba
from rank_bm25 import BM25Okapi
# ================

from config import (
    VECTOR_DB_PATH,
    COLLECTION_NAME,
    OPENAI_API_KEY,
    OPENAI_API_BASE,
    OPENAI_EMBEDDING_MODEL,
    TOP_K,
)


class VectorStore:

    def __init__(
        self,
        db_path: str = VECTOR_DB_PATH,
        collection_name: str = COLLECTION_NAME,
        api_key: str = OPENAI_API_KEY,
        api_base: str = OPENAI_API_BASE,
    ):
        self.db_path = db_path
        self.collection_name = collection_name

        # 初始化OpenAI客户端
        self.client = OpenAI(api_key=api_key, base_url=api_base)

        # 初始化ChromaDB
        os.makedirs(db_path, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=db_path, settings=Settings(anonymized_telemetry=False)
        )

        # 获取或创建collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name, metadata={"description": "课程材料向量数据库"}
        )

        # === 创新点：初始化 BM25 索引 ===
        self.bm25 = None
        self.documents_cache = []  # 用于内存中存储文档内容以供BM25检索
        self._build_bm25_index()   # 构建索引
        # ==============================

    def _build_bm25_index(self):
        """[创新点] 从 ChromaDB 加载所有文档并在内存中构建 BM25 索引"""
        print("正在加载文档以构建混合检索索引(BM25)...")
        # 获取数据库中所有文档
        all_docs = self.collection.get()
        
        if all_docs and all_docs['documents']:
            self.documents_cache = []
            tokenized_corpus = []
            
            # 整理数据格式
            count = len(all_docs['documents'])
            for idx in range(count):
                doc_text = all_docs['documents'][idx]
                doc_meta = all_docs['metadatas'][idx]
                doc_id = all_docs['ids'][idx]
                
                # 存入缓存，方便后续根据索引找回内容
                self.documents_cache.append({
                    "id": doc_id,
                    "content": doc_text,
                    "metadata": doc_meta
                })
                
                # 对文本进行分词（BM25需要分词后的列表）
                tokens = list(jieba.cut_for_search(doc_text))
                tokenized_corpus.append(tokens)
            
            # 构建 BM25 对象
            self.bm25 = BM25Okapi(tokenized_corpus)
            print(f"混合检索索引构建完成，包含 {count} 个文档块。")
        else:
            print("警告：数据库为空，跳过 BM25 索引构建。")

    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量表示"""
        # 防空判断
        if not text or not text.strip():
            print("警告：尝试获取空字符串的Embedding，已跳过。")
            return []

        try:
            text = text.replace("\n", " ")
            response = self.client.embeddings.create(
                input=text,
                model=OPENAI_EMBEDDING_MODEL
            )
            return response.data[0].embedding
        except Exception as e:
            # 过滤掉常见的鉴权错误打印，防止刷屏
            if "401" in str(e) or "invalid_api_key" in str(e):
                raise e
            print(f"获取Embedding失败: {e}")
            return []


    def add_documents(self, chunks: List[Dict[str, str]]) -> None:
        """添加文档块到向量数据库"""
        batch_size = 64
        total_chunks = len(chunks)
        
        print(f"开始处理 {total_chunks} 个文档块，分批存入向量数据库...")

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i : i + batch_size]
            
            ids = []
            documents = []
            metadatas = []
            embeddings = []

            for chunk in tqdm(batch_chunks, desc=f"Batch {i//batch_size + 1}", leave=False):
                content = chunk.get("content", "")
                if not content:
                    continue

                embedding = self.get_embedding(content)
                if not embedding:
                    continue

                safe_filename = chunk.get("filename", "unknown").replace(" ", "_")
                chunk_id = f"{safe_filename}_p{chunk.get('page_number', 0)}_c{chunk.get('chunk_id', 0)}"

                meta = chunk.copy()
                if "content" in meta: del meta["content"]
                if "images" in meta: del meta["images"]

                ids.append(chunk_id)
                documents.append(content)
                metadatas.append(meta)
                embeddings.append(embedding)

            if ids:
                try:
                    self.collection.upsert(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas,
                        embeddings=embeddings
                    )
                except Exception as e:
                    print(f"批量写入ChromaDB失败: {e}")

        print(f"成功将 {total_chunks} 个文档块存入向量数据库。")
        # 添加完数据后，重新构建BM25索引
        self._build_bm25_index()

    def hybrid_search(self, query: str, top_k: int = TOP_K) -> List[Dict]:
        """[创新点] 混合检索：结合 Vector Search 和 BM25 Search"""
        
        # 1. 向量检索 (Vector Search)
        query_embedding = self.get_embedding(query)
        vector_results = []
        if query_embedding:
            chroma_res = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2 #以此获取更多候选项用于融合
            )
            if chroma_res["ids"]:
                for i, doc_id in enumerate(chroma_res["ids"][0]):
                    vector_results.append({
                        "id": doc_id,
                        "content": chroma_res["documents"][0][i],
                        "metadata": chroma_res["metadatas"][0][i],
                        "score": 1 / (i + 60) # RRF 评分部分
                    })

        # 2. 关键词检索 (BM25 Search)
        bm25_results = []
        if self.bm25:
            tokenized_query = list(jieba.cut_for_search(query))
            # 获取 BM25 分数
            doc_scores = self.bm25.get_scores(tokenized_query)
            # 获取分数最高的索引
            top_n = min(len(doc_scores), top_k * 2)
            # argsort 得到的是从小到大，这里取最后 top_n 个并反转
            top_indices = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[:top_n]
            
            for rank, idx in enumerate(top_indices):
                # 过滤掉得分为0的相关性极低结果
                if doc_scores[idx] > 0:
                    cached_doc = self.documents_cache[idx]
                    bm25_results.append({
                        "id": cached_doc["id"],
                        "content": cached_doc["content"],
                        "metadata": cached_doc["metadata"],
                        "score": 1 / (rank + 60) # RRF 评分部分
                    })

        # 3. RRF 融合 (Reciprocal Rank Fusion)
        # 算法公式：Score = 1 / (rank + k)，取k=60
        combined_scores = {}
        all_docs_map = {}

        # 处理向量结果
        for item in vector_results:
            doc_id = item["id"]
            combined_scores[doc_id] = combined_scores.get(doc_id, 0) + item["score"]
            all_docs_map[doc_id] = item

        # 处理 BM25 结果
        for item in bm25_results:
            doc_id = item["id"]
            combined_scores[doc_id] = combined_scores.get(doc_id, 0) + item["score"]
            # 如果是纯关键词搜出来的，补全文档信息
            if doc_id not in all_docs_map:
                all_docs_map[doc_id] = item

        # 4. 排序并取 Top-K
        sorted_ids = sorted(combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True)[:top_k]
        
        final_results = []
        for doc_id in sorted_ids:
            doc = all_docs_map[doc_id]
            final_results.append({
                "content": doc["content"],
                "metadata": doc["metadata"],
                "score": combined_scores[doc_id] # 这里的 score 是融合后的 RRF score
            })

        return final_results

    def search(self, query: str, top_k: int = TOP_K) -> List[Dict]:
        """覆盖原有的search方法，改用混合检索"""
        return self.hybrid_search(query, top_k)

    def clear_collection(self) -> None:
        """清空collection"""
        try:
            self.chroma_client.delete_collection(name=self.collection_name)
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name, metadata={"description": "课程向量数据库"}
            )
            # 清空缓存
            self.bm25 = None
            self.documents_cache = []
            print("向量数据库已清空")
        except Exception as e:
            print(f"清空数据库时出错: {e}")

    def get_collection_count(self) -> int:
        """获取collection中的文档数量"""
        return self.collection.count()
