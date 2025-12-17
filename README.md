# 🤖 Agentic RAG Teaching Assistant

This project originated from the final course assignment of **CS4314: Natural Language Processing at Shanghai Jiao Tong University**. Building upon the base curriculum code, we have developed a highly efficient, transparent, and educationally-tailored Agentic RAG Teaching Assistant.

Developed by: [Zhuoying Ou](https://github.com/ZNightshade) & [Yachen Hu](https://github.com/yachenhu81-a11y)

## ✨ Key Features
- **Agentic Reasoning**: Beyond simple retrieval, the agent autonomously plans and reasons through complex student queries.
- **Pedagogical Alignment**: Tailored specifically for educational contexts with higher transparency and factual grounding.
- **Efficient Indexing**: Optimized data processing pipeline for fast and accurate retrieval from course-specific documents.
- **Transparent Sources**: Clearly cites sources and reasoning steps for every answer provided.

## 🚀 Quick Start
### 1. Install
Clone this repository and navigate to the folder.
```bash
git clone https://github.com/ZNightshade/Agentic-RAG-TA.git
cd Agentic-RAG-TA
```
Install the requirements to get started.
```bash
pip install -r requirements.txt
```
### 2. Configuration
Customize the system behavior by modifying the `config.py` file. You will need to set up your API keys and parameters.

### 3. Data Preparation
Place your course materials in the `data/` folder (or the directory specified in `config.py`).

Process your course materials and build the retrieval index.
```bash
python process_data.py
```

### 4. Launch Agent
Start an interactive session with the Agentic RAG Teaching Assistant.
```bash
python main.py
```
Note: Type `exit` to end the conversation.