import re
from typing import List, Dict, Optional
from tqdm import tqdm


class TextSplitter:
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # 分隔符优先级：段落 > 换行 > 句子结束符 > 逗号 > 空格 > 字符
        self._separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " ", ""]

    def _split_text_with_separator(self, text: str, separator: str) -> List[str]:
        """使用指定分隔符拆分文本，保留分隔符"""
        if separator == "":
            return list(text)
        
        # 使用正则构建分隔模式，保留分隔符
        # 如果分隔符是标点，留在前一句话的末尾
        if separator in ["\n\n", "\n", " "]:
             splits = text.split(separator)
        else:
            # 对于标点符号，使用正则保留
            sep_pattern = re.escape(separator)
            splits = re.split(f"({sep_pattern})", text)
            # 重新组合：内容+分隔符
            new_splits = []
            for i in range(0, len(splits) - 1, 2):
                new_splits.append(splits[i] + splits[i+1])
            if splits[-1]:
                new_splits.append(splits[-1])
            splits = new_splits

        return [s for s in splits if s]

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """将切碎的片段合并成符合 chunk_size 的块"""
        final_chunks = []
        current_chunk = []
        current_length = 0
        
        separator_len = len(separator) if separator not in ["。", "！", "？", ".", "!", "?"] else 0

        for split in splits:
            split_len = len(split)
            
            # 如果当前块加上新片段超过了 chunk_size
            if current_length + split_len + (len(current_chunk) * separator_len) > self.chunk_size:
                if current_chunk:
                    # 1. 保存当前块
                    doc = "".join(current_chunk)
                    if final_chunks: 
                        # 采用简单的拼接输出)
                        pass
                    final_chunks.append(doc)
                
                # 2. 重置当前块，根据 overlap 回溯
                # 这是一个简化的 overlap 逻辑：保留当前块的最后一部分作为新块的开头
                # 在语义切分中，overlap 比较难精确控制字符数，我们优先保证语义
                overlap_len = 0
                new_chunk = []
                # 从后往前找，直到满足 overlap 要求
                for chunk_part in reversed(current_chunk):
                    if overlap_len + len(chunk_part) < self.chunk_overlap:
                        new_chunk.insert(0, chunk_part)
                        overlap_len += len(chunk_part)
                    else:
                        break
                
                current_chunk = new_chunk + [split]
                current_length = overlap_len + split_len
            else:
                current_chunk.append(split)
                current_length += split_len

        if current_chunk:
            final_chunks.append("".join(current_chunk))

        return final_chunks

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """核心递归函数"""
        final_chunks = []
        
        # 1. 找到合适的分隔符
        separator = separators[-1]
        new_separators = []
        for i, sep in enumerate(separators):
            if sep == "": # 字符级兜底
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break
        
        # 2. 使用该分隔符初步切分
        splits = self._split_text_with_separator(text, separator)
        
        # 3. 检查每个片段是否还需要细分
        good_splits = []
        for s in splits:
            if len(s) < self.chunk_size:
                good_splits.append(s)
            else:
                # 如果片段依然太大，且还有更细的分隔符可用，则递归
                if new_separators:
                    good_splits.extend(self._recursive_split(s, new_separators))
                else:
                    # 强制切分
                    good_splits.extend(self._split_text_with_separator(s, ""))

        # 4. 合并过小的片段
        return self._merge_splits(good_splits, separator)

    def split_text(self, text: str) -> List[str]:
        """
        [创新点] 递归语义文本切分
        1. 优先使用段落符(\n\n)切分
        2. 其次使用换行符(\n)
        3. 再次使用句子终止符(。！？)
        4. 保证每个块在 chunk_size 限制下，尽可能保持语义完整
        """
        if not text:
            return []
        
        return self._recursive_split(text, self._separators)

    def split_documents(self, documents: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """切分多个文档。"""
        chunks_with_metadata = []

        for doc in tqdm(documents, desc="[语义切分]处理文档", unit="文档"):
            content = doc.get("content", "")
            filetype = doc.get("filetype", "")
            
            chunks = self.split_text(content)
            
            for i, chunk in enumerate(chunks):
                # 过滤掉过短的无意义切片
                if len(chunk.strip()) < 5: 
                    continue
                    
                chunk_data = {
                    "content": chunk,
                    "filename": doc.get("filename", "unknown"),
                    "filepath": doc.get("filepath", ""),
                    "filetype": filetype,
                    "page_number": doc.get("page_number", 0),
                    "chunk_id": i,
                    "images": [],
                }
                chunks_with_metadata.append(chunk_data)

        print(f"\n文档语义处理完成，共 {len(chunks_with_metadata)} 个语义块")
        return chunks_with_metadata
