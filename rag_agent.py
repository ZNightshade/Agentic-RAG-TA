from typing import List, Dict, Optional, Tuple
from pathlib import Path
from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    OPENAI_API_BASE,
    MODEL_NAME,
    TOP_K,
    MAX_ITER,
)
from vector_store import VectorStore
import json
import re
from colorama import init, Fore, Back, Style


class RAGAgent:
    def __init__(
        self,
        model: str = MODEL_NAME,
    ):
        self.model = model

        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)

        self.vector_store = VectorStore()

        self.Docs = {}

        
        # 实现并调整提示词，使其符合课程助教的角色和回答策略
        self.pred0_system = Path("prompts/pred0_system_message.md").read_text(encoding="utf-8")
        self.pred1_system = Path("prompts/pred1_system_message.md").read_text(encoding="utf-8")
        self.pred0_history = [{"role": "system", "content": self.pred0_system}]
        self.pred1_history = [{"role": "system", "content": self.pred1_system}]
        self.pred0_user = Path("prompts/pred0_user_message.md").read_text(encoding="utf-8")
        self.pred1_user = Path("prompts/pred1_user_message.md").read_text(encoding="utf-8")

    def format_res(self, res):
        result = f"filename: {res["metadata"]["filename"]}\npage_number: {res["metadata"]["page_number"]}\ncontent: {res["content"]}"
        return result

    def search_courseware(self, query: str, top_k: int = TOP_K) -> str:
        # 根据query检索课程资料，前3个结果返回内容，文件名和页码，除此之外返回文件名和页码

        res = self.vector_store.search(query=query, top_k=top_k)
        result = ""
        for i in range(min(3, len(res))):
            result += self.format_res(res[i]) + "\n\n"
            self.Docs[(res[i]["metadata"]["filename"], res[i]["metadata"]["page_number"])] = res[i]["content"]
            print(Style.DIM + Fore.BLUE + f"{res[i]["metadata"]["filename"]}, page {res[i]["metadata"]["page_number"]}")
        for i in range(3, len(res)):
            result += f"filename: {res[i]['metadata']['filename']}\npage_number: {res[i]['metadata']['page_number']}\n\n"
            self.Docs[(res[i]["metadata"]["filename"], res[i]["metadata"]["page_number"])] = res[i]["content"]
            print(Style.DIM + Fore.BLUE + f"{res[i]["metadata"]["filename"]}, page {res[i]["metadata"]["page_number"]}")
        return result

    def lookup_courseware(self, filename: str, page_number: int) -> str:
        # 先在self.Docs中查找，如果没有再检索

        if (filename, page_number) in self.Docs:
            return self.Docs[(filename, page_number)]
        else:
            res = self.vector_store.search(query=f"filename:{filename} page_number:{page_number}", top_k=1)
            if res:
                self.Docs[(res[0]["metadata"]["filename"], res[0]["metadata"]["page_number"])] = res[0]["content"]
                return res[0]["content"]
            else:
                return ""

    def get_new_user_message(self, old_user_message: str, response: str, index: int):
        # 识别模型的回复，执行对应的工具调用，并将结果整合为新的用户消息。

        # 解析响应中的各个字段
        next_thought_match = re.search(r'\[\[ ## next_thought ## \]\](.*?)\[\[ ## next_tool_name ## \]\]', response, re.DOTALL)
        next_tool_name_match = re.search(r'\[\[ ## next_tool_name ## \]\](.*?)\[\[ ## next_tool_args ## \]\]', response, re.DOTALL)
        next_tool_args_match = re.search(r'\[\[ ## next_tool_args ## \]\](.*?)\[\[ ## completed ## \]\]', response, re.DOTALL)
        
        next_thought = next_thought_match.group(1).strip() if next_thought_match else ""
        next_tool_name = next_tool_name_match.group(1).strip() if next_tool_name_match else ""
        next_tool_args_str = next_tool_args_match.group(1).strip() if next_tool_args_match else "{}"
        
        # 清理工具名称：移除回车、注释、引号、多余空白
        # 1. 移除 # 注释及其后面的内容
        next_tool_name = next_tool_name.split('#')[0]
        # 2. 移除所有回车和制表符，只保留空格
        next_tool_name = re.sub(r'[\r\n\t]+', '', next_tool_name)
        # 3. 移除引号和多余空白
        next_tool_name = next_tool_name.strip().strip("'\"").strip()
        
        # 清理工具参数 JSON 字符串：移除注释和多余空白
        # 1. 移除 Python 风格注释（# 后面的内容）
        next_tool_args_str = re.sub(r'#.*?$', '', next_tool_args_str, flags=re.MULTILINE)
        # 2. 移除多余的回车和空白（保留 JSON 格式需要的空格）
        next_tool_args_str = re.sub(r'[\r\n]+', ' ', next_tool_args_str)
        # 3. 最后再 strip 一次
        next_tool_args_str = next_tool_args_str.strip()
        
        # 解析工具参数JSON
        try:
            next_tool_args = json.loads(next_tool_args_str)
        except json.JSONDecodeError as e:
            # 如果 JSON 解析失败，尝试进一步清理（移除可能的尾部逗号）
            try:
                cleaned_str = re.sub(r',\s*}', '}', next_tool_args_str)
                cleaned_str = re.sub(r',\s*]', ']', cleaned_str)
                next_tool_args = json.loads(cleaned_str)
            except json.JSONDecodeError:
                next_tool_args = {}
        
        print(Style.DIM + Fore.BLUE + next_thought)

        # 检查是否完成
        is_finished = next_tool_name.lower() == 'finish'
        
        # 执行对应的工具调用
        observation = ""
        try:
            if next_tool_name.lower() == 'search_courseware':
                query = next_tool_args.get('query', '')
                print(Style.DIM + Fore.BLUE + f"Calling tool search_courseware with query: {query}")
                if query:
                    observation = self.search_courseware(query)
                else:
                    print(Style.DIM + Fore.BLUE + "Invalid next_tool_args for search_courseware.")
                    observation = "Invalid next_tool_args. Tool search_courseware takes arguments {'query': 'str'} in JSON format."
            elif next_tool_name.lower() == 'lookup_courseware':
                filename = next_tool_args.get('filename', '')
                page_number = next_tool_args.get('page_number', 0)
                print(Style.DIM + Fore.BLUE + f"Calling tool lookup_courseware with filename: {filename}, page_number: {page_number}")
                if filename and page_number:
                    observation = self.lookup_courseware(filename, page_number)
                else:
                    print(Style.DIM + Fore.BLUE + "Invalid next_tool_args for lookup_courseware.")
                    observation = "Invalid next_tool_args. Tool lookup_courseware takes arguments {'filename': 'str', 'page_number': 'int'} in JSON format."
            elif is_finished:
                print(Style.DIM + Fore.BLUE + "Search completed.")
                observation = "Completed."
            else:
                print(Style.DIM + Fore.BLUE + f"Invalid tool name.")
                observation = "Invalid tool name. It must be formatted as a valid Python Literal[search_courseware, lookup_courseware, finish]"
        except Exception as e:
            observation = f"Error: {str(e)}"
        
        # 构建新的trajectory条目
        trajectory_entry = Path("prompts/trajectory_entry.md").read_text(encoding="utf-8").format(
            index = index,
            next_thought = next_thought,
            next_tool_name = next_tool_name,
            next_tool_args = next_tool_args_match.group(1).strip() if next_tool_args_match else "{}",
            observation = observation
        )
        
        # 将新的trajectory条目整合到旧的user message中
        new_user_message = old_user_message.replace('\nRespond with', trajectory_entry + '\nRespond with')
        
        return new_user_message, is_finished


    def predictor0(self, query: str):
        # 每次要调用对应工具以及将得到的回复和结果整合到user message中

        user_message = self.pred0_user.format(question = query, trajectory = "")
        self.pred0_history.append({"role": "user", "content": user_message})
        for i in range(MAX_ITER):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, messages=self.pred0_history, temperature=0.7
                )
            except Exception as e:
                return f"生成回答时出错: {str(e)}"
            user_message, if_finish = self.get_new_user_message(user_message, response.choices[0].message.content, i)
            if if_finish or i==MAX_ITER-1:
                break
            self.pred0_history[-1] = {"role": "user", "content": user_message}
        self.pred0_history.append({"role": "assistant", "content": response.choices[0].message.content})
        trajectory = re.search(r'\[\[ ## trajectory ## \]\](.*?)\n\nRespond with', user_message, re.DOTALL)
        return trajectory.group(1).strip() if trajectory else ""

    def predictor1(self, query: str, trajectory: str):
        # 根据predictor0的轨迹得出最终的回复
        user_message = self.pred1_user.format(question=query, trajectory=trajectory)
        self.pred1_history.append({"role": "user", "content": user_message})
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=self.pred1_history, temperature=0.7
            )
        except Exception as e:
            return f"生成回答时出错: {str(e)}"
        response = response.choices[0].message.content
        self.pred1_history.append({"role": "assistant", "content": response})
        reasoning = re.search(r'\[\[ ## reasoning ## \]\](.*?)\[\[ ## answer ## \]\]', response, re.DOTALL)
        print('\n' + Style.DIM + Fore.BLUE + reasoning.group(1).strip() if reasoning else "")
        answer = re.search(r'\[\[ ## answer ## \]\](.*?)\[\[ ## completed ## \]\]', response, re.DOTALL)
        return answer.group(1).strip() if answer else ""

    def chat(self) -> None:
        # 交互式对话
        init(autoreset=True)
        print(Style.BRIGHT + "=" * 60)
        print(Fore.WHITE + Back.BLUE + Style.BRIGHT + "欢迎使用智能课程助教系统！")
        print(Style.BRIGHT + "=" * 60)

        while True:
            try:
                query = input(Style.BRIGHT + "\n学生: " + Style.RESET_ALL).strip()

                if not query:
                    continue

                if query == "exit":
                    print(Fore.WHITE + Back.BLUE + Style.BRIGHT + "\n感谢使用智能课程助教系统，再见！")
                    break
                
                print(Style.DIM + Fore.BLUE + "智能课程助教思考中...")
                pred0_trajectory = self.predictor0(query)
                answer = self.predictor1(query, pred0_trajectory)

                print(Fore.BLUE + Style.BRIGHT + "\n助教: " + Style.RESET_ALL + Fore.BLUE + answer)

            except Exception as e:
                print(Fore.RED + Style.BRIGHT + "\n错误: " + Style.RESET_ALL + Fore.RED + str(e))
