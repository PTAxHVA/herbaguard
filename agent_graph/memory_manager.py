
import json
import os
from typing import List, Dict, Any

class MemoryManager:
    def __init__(self, session_id: str, redis_url: str = "redis://localhost:6379/0", file_path: str = "chat_history_graph.json"):
        self.session_id = session_id
        self.redis_client = None
        self.use_redis = False
        self.local_memory = []
        
        # We store the file in the same directory as this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.file_path = os.path.join(current_dir, file_path)

        # Try connecting to Redis
        try:
            import redis
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            self.use_redis = True
            print("✅ Connected to Redis for memory storage")
        except (ImportError, Exception):
            print(f"⚠️  Redis not available. Using local file storage ({self.file_path})")
            self.use_redis = False
            self._load_from_file()

    def _load_from_file(self):
        """Load history from JSON file if it exists."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    all_history = json.load(f)
                    self.local_memory = all_history.get(self.session_id, [])
            except json.JSONDecodeError:
                self.local_memory = []

    def _save_to_file(self):
        """Save current session history to JSON file."""
        all_history = {}
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    all_history = json.load(f)
            except json.JSONDecodeError:
                pass
        
        all_history[self.session_id] = self.local_memory
        
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(all_history, f, ensure_ascii=False, indent=2)

    def add_message(self, role: str, content: str):
        message = {"role": role, "content": content}
        
        if self.use_redis:
            try:
                # Append to Redis list
                self.redis_client.rpush(f"chat_history:{self.session_id}", json.dumps(message))
                # Set expiry (e.g., 24 hours)
                self.redis_client.expire(f"chat_history:{self.session_id}", 86400)
            except Exception:
                # Fallback to local
                self.use_redis = False
                self.local_memory.append(message)
                self._save_to_file()
        else:
            self.local_memory.append(message)
            self._save_to_file()

    def get_history(self) -> List[Dict[str, str]]:
        if self.use_redis:
            # Retrieve all messages
            try:
                raw_history = self.redis_client.lrange(f"chat_history:{self.session_id}", 0, -1)
                return [json.loads(msg) for msg in raw_history]
            except Exception:
                return []
        else:
            return self.local_memory

    def get_context_string(self, limit: int = 5) -> str:
        """Returns the last `limit` messages formatted as a string for context."""
        history = self.get_history()
        recent = history[-limit:]
        return "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent])

    def clear_history(self):
        if self.use_redis:
            self.redis_client.delete(f"chat_history:{self.session_id}")
        else:
            self.local_memory = []
            self._save_to_file()
