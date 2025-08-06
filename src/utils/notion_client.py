"""
Notion API 客戶端 - 自動記錄開發進度
"""
import os
import requests
import json
from datetime import datetime
from typing import Dict, Any, List, Optional


class NotionClient:
    def __init__(self, api_token: str, database_id: str):
        """
        初始化 Notion 客戶端
        
        Args:
            api_token: Notion Integration Token
            database_id: 要寫入的 Database ID
        """
        self.api_token = api_token
        self.database_id = database_id
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    def create_development_log(self, 
                             title: str, 
                             status: str = "In Progress",
                             priority: str = "Medium",
                             description: str = "",
                             tags: List[str] = None,
                             completion_percentage: int = 0) -> Dict[str, Any]:
        """
        創建開發進度記錄
        
        Args:
            title: 任務標題
            status: 狀態 (Not Started, In Progress, Completed, Blocked)
            priority: 優先級 (Low, Medium, High, Critical)
            description: 詳細描述
            tags: 標籤列表
            completion_percentage: 完成百分比 (0-100)
        """
        if tags is None:
            tags = []
        
        properties = {
            "Title": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            },
            "Status": {
                "select": {
                    "name": status
                }
            },
            "Priority": {
                "select": {
                    "name": priority
                }
            },
            "Completion": {
                "number": completion_percentage
            },
            "Created": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            }
        }
        
        # 添加標籤（如果資料庫有 Tags 屬性）
        if tags:
            properties["Tags"] = {
                "multi_select": [{"name": tag} for tag in tags]
            }
        
        # 添加描述（作為頁面內容）
        children = []
        if description:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": description
                            }
                        }
                    ]
                }
            })
        
        data = {
            "parent": {
                "database_id": self.database_id
            },
            "properties": properties
        }
        
        if children:
            data["children"] = children
        
        return self._make_request("POST", "/pages", data)
    
    def update_task_status(self, 
                          page_id: str, 
                          status: str = None,
                          completion_percentage: int = None,
                          notes: str = None) -> Dict[str, Any]:
        """
        更新任務狀態
        
        Args:
            page_id: Notion 頁面 ID
            status: 新狀態
            completion_percentage: 完成百分比
            notes: 更新註記
        """
        properties = {}
        
        if status:
            properties["Status"] = {
                "select": {
                    "name": status
                }
            }
        
        if completion_percentage is not None:
            properties["Completion"] = {
                "number": completion_percentage
            }
        
        # 更新最後修改時間
        properties["Last Modified"] = {
            "date": {
                "start": datetime.now().isoformat()
            }
        }
        
        data = {
            "properties": properties
        }
        
        # 如果有註記，添加到頁面內容
        if notes:
            # 先獲取現有內容，然後添加新的註記
            self._append_notes_to_page(page_id, notes)
        
        return self._make_request("PATCH", f"/pages/{page_id}", data)
    
    def log_feature_completion(self, 
                             feature_name: str,
                             implementation_details: str = "",
                             files_modified: List[str] = None,
                             test_results: str = "") -> Dict[str, Any]:
        """
        記錄功能完成
        
        Args:
            feature_name: 功能名稱
            implementation_details: 實作細節
            files_modified: 修改的檔案列表
            test_results: 測試結果
        """
        if files_modified is None:
            files_modified = []
        
        description = f"## 功能實作完成\n\n"
        
        if implementation_details:
            description += f"### 實作細節\n{implementation_details}\n\n"
        
        if files_modified:
            description += f"### 修改檔案\n"
            for file in files_modified:
                description += f"- {file}\n"
            description += "\n"
        
        if test_results:
            description += f"### 測試結果\n{test_results}\n"
        
        return self.create_development_log(
            title=f"✅ {feature_name}",
            status="Completed",
            priority="High",
            description=description,
            tags=["Feature", "Completed"],
            completion_percentage=100
        )
    
    def log_bug_fix(self, 
                   bug_description: str,
                   fix_details: str = "",
                   affected_files: List[str] = None) -> Dict[str, Any]:
        """
        記錄 Bug 修復
        
        Args:
            bug_description: Bug 描述
            fix_details: 修復細節
            affected_files: 影響的檔案
        """
        if affected_files is None:
            affected_files = []
        
        description = f"## Bug 修復\n\n"
        description += f"### 問題描述\n{bug_description}\n\n"
        
        if fix_details:
            description += f"### 修復方案\n{fix_details}\n\n"
        
        if affected_files:
            description += f"### 影響檔案\n"
            for file in affected_files:
                description += f"- {file}\n"
        
        return self.create_development_log(
            title=f"🐛 Bug Fix: {bug_description[:50]}...",
            status="Completed",
            priority="Medium",
            description=description,
            tags=["Bug Fix", "Completed"],
            completion_percentage=100
        )
    
    def log_todo_progress(self, todos: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        記錄 TODO 進度
        
        Args:
            todos: TODO 列表，格式 [{'content': '', 'status': '', 'priority': ''}]
        """
        title = f"📋 開發進度更新 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        description = "## TODO 進度追蹤\n\n"
        
        # 統計各狀態的任務數
        status_counts = {}
        for todo in todos:
            status = todo.get('status', 'pending')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        description += "### 狀態總覽\n"
        for status, count in status_counts.items():
            emoji = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(status, "📝")
            description += f"- {emoji} {status}: {count} 項\n"
        
        description += "\n### 詳細清單\n"
        
        # 按優先級分組
        priority_groups = {"high": [], "medium": [], "low": []}
        for todo in todos:
            priority = todo.get('priority', 'medium')
            priority_groups[priority].append(todo)
        
        for priority in ['high', 'medium', 'low']:
            if priority_groups[priority]:
                priority_emoji = {"high": "🔥", "medium": "⚡", "low": "🔧"}[priority]
                description += f"\n#### {priority_emoji} {priority.title()} Priority\n"
                
                for todo in priority_groups[priority]:
                    status = todo.get('status', 'pending')
                    status_emoji = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(status, "📝")
                    content = todo.get('content', '')
                    description += f"- {status_emoji} {content}\n"
        
        # 計算整體完成百分比
        total_tasks = len(todos)
        completed_tasks = len([t for t in todos if t.get('status') == 'completed'])
        completion_percentage = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
        
        return self.create_development_log(
            title=title,
            status="In Progress" if completion_percentage < 100 else "Completed",
            priority="Medium",
            description=description,
            tags=["Progress Update", "TODO"],
            completion_percentage=completion_percentage
        )
    
    def _append_notes_to_page(self, page_id: str, notes: str) -> Dict[str, Any]:
        """在頁面末尾添加註記"""
        data = {
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"\n📝 更新: {datetime.now().strftime('%Y-%m-%d %H:%M')} - {notes}"
                                }
                            }
                        ]
                    }
                }
            ]
        }
        
        return self._make_request("PATCH", f"/blocks/{page_id}/children", data)
    
    def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """發送 API 請求"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
            
            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "data": response.json()
                }
            else:
                return {
                    "success": False,
                    "error": f"API Error {response.status_code}: {response.text}",
                    "status_code": response.status_code
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Request failed: {str(e)}"
            }
    
    def test_connection(self) -> Dict[str, Any]:
        """測試 Notion API 連接"""
        try:
            # 測試獲取資料庫資訊
            result = self._make_request("GET", f"/databases/{self.database_id}")
            
            if result["success"]:
                db_info = result["data"]
                return {
                    "success": True,
                    "database_title": db_info.get("title", [{}])[0].get("text", {}).get("content", "Unknown"),
                    "message": "Notion API 連接成功"
                }
            else:
                return {
                    "success": False,
                    "error": result["error"]
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection test failed: {str(e)}"
            }


def get_notion_client() -> Optional[NotionClient]:
    """獲取 Notion 客戶端實例"""
    api_token = os.getenv('NOTION_API_TOKEN')
    database_id = os.getenv('NOTION_DATABASE_ID')
    
    if not api_token or not database_id:
        return None
    
    return NotionClient(api_token, database_id)