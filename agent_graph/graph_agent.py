
import asyncio
import os
import sys
from typing import List, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from ddgs import DDGS
from dataclasses import dataclass
import trafilatura
import time

def get_full_content(url):
    """Truy cập vào URL và lấy nội dung bài viết chính."""
    try:
        # Tải nội dung trang web
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            # Trích xuất văn bản (loại bỏ rác)
            result = trafilatura.extract(downloaded)
            # Trả về 1000 ký tự đầu tiên để tránh quá dài cho AI
            return result[:1500] if result else None
    except Exception as e:
        print(f"Lỗi khi đọc link {url}: {e}")
    return None

# Add parent directory to path to find .env if needed, but safer to just use load_dotenv()
load_dotenv()

# Import local modules
try:
    from knowledge_graph import KnowledgeGraph
    from memory_manager import MemoryManager
except ImportError:
    # If not running as module
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from knowledge_graph import KnowledgeGraph
    from memory_manager import MemoryManager

# --- Initialize Resources ---
# Initialize Graph (loads data once)
KG = KnowledgeGraph()

# Initialize Model
model_key = os.getenv('GOOGLE_API_KEY')
if not model_key:
    # Try multiple common locations for .env
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # 1. Look in herbaguard module (D:\herbguard\herbaguard\.env) - Most likely location
    herbaguard_env = os.path.join(project_root, 'herbaguard', '.env')
    if os.path.exists(herbaguard_env):
        print(f"Loading .env from: {herbaguard_env}")
        load_dotenv(herbaguard_env)
    
    # 2. Look in project root (D:\herbguard\.env)
    root_env = os.path.join(project_root, '.env')
    if os.path.exists(root_env):
        load_dotenv(root_env)

# Verify key exists now
if not os.getenv('GOOGLE_API_KEY'):
    print("❌ CRITICAL ERROR: GOOGLE_API_KEY not found in environment variables.")
    print("Please make sure D:\\herbguard\\herbaguard\\.env exists and contains GOOGLE_API_KEY.")
    sys.exit(1)
 # Reverting to known working model for safety, or trusting user string if compatible. 
# User asked for 'models/gemini-2.5-flash-lite', I will keep their string but handle the key.

model = GoogleModel('models/gemini-2.5-flash-lite')



# --- Agent Configuration ---

@dataclass
class AgentDeps:
    memory: MemoryManager
    graph: KnowledgeGraph

# --- System Prompt ---
# Moved system prompt definition below Agent instantiation to use decorator

agent = Agent(
    model,
    deps_type=AgentDeps,
)

@agent.system_prompt
def get_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    # Get history from memory manager
    history_str = ctx.deps.memory.get_context_string()
    
    return (
        "You are 'HerbGuard', an advanced medical AI assistant. "
        "You use a Knowledge Graph to find drug-herb interactions. "
        "You have three main responsibilities:\n"
        "1. **Greetings**: If the user says hello/hi, calling the `greet_user` tool is mandatory.\n"
        "2. **Drug Info**: If the user asks about a specific drug (e.g., 'What is Warfarin?'), call the `search_drug_info` tool.\n"
        "3. **Interactions**: If the user asks about interactions, follow this workflow:\n"
        "   a. Analyze the conversation history context below. If the user refers to previous entities (e.g., 'that drug' -> 'Panadol'), RESOLVE these references explicitly.\n"
        "   b. Call `identify_medical_entities_via_graph` to get the list of herbs and drugs mentioned. IMPORTANT: Pass the EXPLICIT query with resolved names (e.g., 'Does Panadol interact with Ginseng?').\n"
        "   c. Based on the query, determine which herbs pair with which drugs. (Usually check all combinations).\n"
        "   d. Loop through these pairs and call `check_interaction_pair_via_graph` for EACH pair.\n"
        "   e. Synthesize the findings into a clear Vietnamese response.\n\n"
        "GUIDELINES:\n"
        "- Respond in Vietnamese.\n"
        "- Maintain a polite, professional, and empathetic tone.\n"
        "- Always include the disclaimer: 'Thông tin chỉ mang tính chất tham khảo, vui lòng hỏi ý kiến bác sĩ.'\n\n"
        "GUIDELINES:\n"
        "- Respond in Vietnamese.\n"
        "- Maintain a polite, professional, and empathetic tone.\n"
        "- Always include the disclaimer: 'Thông tin chỉ mang tính chất tham khảo, vui lòng hỏi ý kiến bác sĩ.'\n\n"
        f"--- CONVERSATION HISTORY ---\n{history_str}\n----------------------------"
    )

agent = Agent(
    model,
    deps_type=AgentDeps,
)

@agent.system_prompt
def get_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    # Get history from memory manager
    history_str = ctx.deps.memory.get_context_string()

    return (
        "You are 'HerbGuard', an advanced medical AI assistant. "
        "You use a Knowledge Graph to find drug-herb interactions. "
        "You have three main responsibilities:\n"
        "1. **Greetings**: If the user says hello/hi, calling the `greet_user` tool is mandatory.\n"
        "2. **Drug Info**: If the user asks about a specific drug (e.g., 'What is Warfarin?'), call the `search_drug_info` tool.\n"
        "3. **Interactions**: If the user asks about interactions, follow this workflow:\n"
        "   a. Analyze the conversation history context below. If the user refers to previous entities (e.g., 'that drug' -> 'Panadol'), RESOLVE these references explicitly.\n"
        "   b. Call `identify_medical_entities_via_graph` to get the list of herbs and drugs mentioned. IMPORTANT: Pass the EXPLICIT query with resolved names (e.g., 'Does Panadol interact with Ginseng?').\n"
        "   c. Based on the query, determine which herbs pair with which drugs. (Usually check all combinations).\n"
        "   d. Loop through these pairs and call `check_interaction_pair_via_graph` for EACH pair.\n"
        "   e. Synthesize the findings into a clear Vietnamese response.\n\n"
        "GUIDELINES:\n"
        "- Respond in Vietnamese.\n"
        "- Maintain a polite, professional, and empathetic tone.\n"
        "- Always include the disclaimer: 'Thông tin chỉ mang tính chất tham khảo, vui lòng hỏi ý kiến bác sĩ.'\n\n"
        f"--- CONVERSATION HISTORY ---\n{history_str}\n----------------------------"
    )


# --- Tools ---

@agent.tool
def greet_user(ctx: RunContext) -> str:
    """Returns the standard greeting message."""
    return "Xin chào! Mình là HerbGuard, trợ lý AI sử dụng Knowledge Graph để tra cứu tương tác thuốc và thảo dược. Bạn cần giúp gì không?"

@agent.tool
def search_drug_info(ctx: RunContext, drug_name: str) -> str:
    """
    Searches for information about a specific drug using DuckDuckGo.
    """
    print(f"[Tool] Đang tìm kiếm chuyên sâu về: {drug_name}")
    try:
        with DDGS() as ddgs:
            # Lấy top 3 kết quả để đảm bảo tốc độ và chất lượng
            results = list(ddgs.text(f"thuốc {drug_name} là gì", region='vn-vi', max_results=3))
            
            if not results:
                return f"Rất tiếc, không tìm thấy thông tin về {drug_name}."

            detailed_results = []
            for i, r in enumerate(results):
                url = r['href']
                title = r['title']
                print(f"--- Đang đọc nguồn {i+1}: {url} ---")
                
                full_text = get_full_content(url)
                
                # Nếu cào được nội dung chi tiết thì dùng, không thì dùng snippet tạm
                content = full_text if full_text else f"(Chỉ có tóm tắt): {r['body']}"
                
                detailed_results.append(f"NGUỒN {i+1} ({title}):\nURL: {url}\nNỘI DUNG: {content}")
                
                # Nghỉ ngắn giữa các lần truy cập để tránh bị chặn (Rate limit)
                time.sleep(1)

            combined_info = "\n\n" + "="*30 + "\n\n".join(detailed_results)
            
            return (f"Đã tìm thấy thông tin chi tiết cho '{drug_name}':\n{combined_info}\n\n"
                    "--- DISCLAIMER ---\n"
                    "LƯU Ý: Thông tin này được thu thập tự động. "
                    "Vui lòng tham khảo ý kiến bác sĩ trước khi sử dụng thuốc.")

    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}"

@agent.tool
def identify_medical_entities_via_graph(ctx: RunContext[AgentDeps], user_question: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Identifies herbs and drugs mentioned in the user's question by searching the Knowledge Graph directly.
    The agent extracts potential names, but this tool verifies them against the graph nodes.
    
    Args:
        user_question: The resolved user question containing entity names.
    """
    print(f"\n[Tool] Identifying entities in graph for: {user_question}")
    
    # 1. Ask LLM to extract potential names first (using a lightweight regex or just simpler prompt is possible, 
    # but here we rely on the graph search to be fuzzy or exact).
    # Ideally, we should parse the question to extract candidate terms.
    # Since we can't easily parse NLP without another LLM call, we will ask the agent to provide the NAMES in the tool call if possible?
    # No, the tool signature is just `user_question`.
    
    # Let's perform a "Smart Search" on the graph.
    # We will search for every node name/alias in the graph to see if it appears in the question.
    # This is O(N) where N is number of nodes. Since our graph is small (<1000 nodes likely), this is efficient enough.
    
    found_herbs = []
    found_drugs = []
    
    normalized_question = user_question.lower()
    
    # Iterate all nodes in the graph
    for node_id, data in ctx.deps.graph.graph.nodes(data=True):
        # Check all aliases
        aliases = data.get("aliases", [])
        
        for alias in aliases:
            if alias in normalized_question:
                # MATCH FOUND
                entity = {
                    "id": data.get("official_id"), 
                    "name": data.get("name"),
                    "node_id": node_id
                }
                
                if data.get("type") == "herb":
                    # Avoid duplicates
                    if entity not in found_herbs:
                        found_herbs.append(entity)
                elif data.get("type") == "drug":
                    if entity not in found_drugs:
                        found_drugs.append(entity)
                break # Found one alias match for this node, move to next node
                
    print(f"Graph Search Result - Herbs: {len(found_herbs)}, Drugs: {len(found_drugs)}")
    return {
        "herbs": found_herbs,
        "drugs": found_drugs
    }

@agent.tool
def check_interaction_pair_via_graph(ctx: RunContext[AgentDeps], herb_id: int, drug_id: int) -> Dict[str, Any]:
    """
    Checks for interaction between a specific herb ID and drug ID by querying the Knowledge Graph edge.
    """
    print(f"[Tool] Graph Lookup: Herb {herb_id} <-> Drug {drug_id}")
    return ctx.deps.graph.check_interaction(herb_id, drug_id)


# --- Main Execution ---
async def main():
    # Initialize Memory
    session_id = "graph_session_001"
    memory = MemoryManager(session_id=session_id)
    memory.clear_history() # Start fresh
    
    # Initialize Deps
    deps = AgentDeps(memory=memory, graph=KG)

    questions = [
       
        "xin chào bạn?", # Tests memory + graph lookup
    ]
    
    print(f"--- Starting Graph-Powered Chat Session: {session_id} ---")

    for i, question in enumerate(questions):
        print(f"\n[{i+1}] User: {question}")
        memory.add_message("user", question)
        
        try:
            result = await agent.run(question, deps=deps)
            
            response_text = ""
            if hasattr(result, 'data'):
                response_text = str(result.data)
            elif hasattr(result, 'output'):
                response_text = str(result.output)
            else:
                response_text = str(result)
            
            print(f"[{i+1}] AI: {response_text}")
            memory.add_message("model", response_text)
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY"):
         print("Please check GOOGLE_API_KEY in .env")
    else:
        asyncio.run(main())
