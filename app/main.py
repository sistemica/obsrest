from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
from datetime import datetime
import yaml
import logging
from .search_manager import SearchManager, SearchResult


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Obsidian Web API",
    description="API for managing an Obsidian-compatible vault through the web",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FileContent(BaseModel):
    content: str
    frontmatter: Optional[Dict] = None

class FileInfo(BaseModel):
    name: str
    path: str
    type: str
    modified: datetime
    children: Optional[List['FileInfo']] = None

VAULT_PATH = os.environ.get("VAULT_PATH", "/data/vault")


search_manager = None

search_manager = None

@app.on_event("startup")
async def startup_event():
    """Initialize search manager and ensure vault directory exists"""
    global search_manager
    logger.info(f"Starting with VAULT_PATH: {VAULT_PATH}")
    os.makedirs(VAULT_PATH, exist_ok=True)
    try:
        search_manager = SearchManager(VAULT_PATH)
        logger.info("Search manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize search manager: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup search manager on shutdown"""
    global search_manager
    if search_manager:
        search_manager.shutdown()


@app.get("/api/search", response_model=List[SearchResult])
async def search(q: str, limit: int = 10):
    """Search vault contents"""
    if not search_manager:
        raise HTTPException(status_code=500, detail="Search index not initialized")
    
    try:
        results = search_manager.search(q, limit)
        return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search/reindex")
async def reindex():
    """Manually trigger reindexing"""
    if not search_manager:
        raise HTTPException(status_code=500, detail="Search index not initialized")
    
    try:
        search_manager.check_consistency()
        return {"status": "success", "message": "Reindexing completed"}
    except Exception as e:
        logger.error(f"Reindex error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tree")
@app.get("/api/tree/")
@app.get("/api/tree/{path:path}")
async def get_directory_tree(path: str = ""):
    """List directory contents"""
    full_path = os.path.join(VAULT_PATH, path.lstrip("/"))
    logger.info(f"Reading directory: {full_path}")
    
    if not os.path.exists(full_path):
        logger.error(f"Path not found: {full_path}")
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    def scan_dir(dir_path: str) -> FileInfo:
        name = os.path.basename(dir_path) or os.path.basename(VAULT_PATH)
        rel_path = os.path.relpath(dir_path, VAULT_PATH)
        rel_path = "" if rel_path == "." else rel_path
        
        children = []
        if os.path.isdir(dir_path):
            for item in sorted(os.listdir(dir_path)):
                if not item.startswith('.'):
                    item_path = os.path.join(dir_path, item)
                    children.append(scan_dir(item_path))

        return FileInfo(
            name=name,
            path=rel_path,
            type="directory" if os.path.isdir(dir_path) else "file",
            modified=datetime.fromtimestamp(os.path.getmtime(dir_path)),
            children=children if os.path.isdir(dir_path) else None
        )

    return scan_dir(full_path)

@app.get("/api/files/{path:path}", response_model=FileContent)
async def get_file_content(path: str):
    """Get content of a specific file"""
    full_path = os.path.join(VAULT_PATH, path.lstrip("/"))
    logger.info(f"Reading file: {full_path}")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        frontmatter = {}
        if content.startswith('---'):
            try:
                _, fm, md = content.split('---', 2)
                frontmatter = yaml.safe_load(fm)
                content = md.strip()
            except:
                pass
                
        return FileContent(content=content, frontmatter=frontmatter)
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/files/{path:path}")
async def create_file(path: str, file_content: FileContent):
    """Create a new file"""
    full_path = os.path.join(VAULT_PATH, path.lstrip("/"))
    logger.info(f"Creating file: {full_path}")
    
    if os.path.exists(full_path):
        raise HTTPException(status_code=409, detail="File already exists")
    
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Prepare content with frontmatter
        content = ""
        if file_content.frontmatter:
            content = "---\n"
            content += yaml.dump(file_content.frontmatter)
            content += "---\n"
        content += file_content.content
        
        # Write file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return {"status": "success", "path": path}
    except Exception as e:
        logger.error(f"Error creating file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/files/{path:path}")
async def update_file(path: str, file_content: FileContent):
    """Update an existing file"""
    full_path = os.path.join(VAULT_PATH, path.lstrip("/"))
    logger.info(f"Updating file: {full_path}")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=400, detail="Path is not a file")
    
    try:
        content = ""
        if file_content.frontmatter:
            content = "---\n"
            content += yaml.dump(file_content.frontmatter)
            content += "---\n"
        content += file_content.content
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return {"status": "success", "path": path}
    except Exception as e:
        logger.error(f"Error updating file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/files/{path:path}/move")
async def move_file(path: str, new_path: str = None):
    """Move a file to a new location"""
    if not new_path:
        raise HTTPException(status_code=400, detail="new_path is required")
        
    full_path = os.path.join(VAULT_PATH, path.lstrip("/"))
    new_full_path = os.path.join(VAULT_PATH, new_path.lstrip("/"))
    logger.info(f"Moving file from {full_path} to {new_full_path}")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Source path not found")
    
    if os.path.exists(new_full_path):
        raise HTTPException(status_code=409, detail="Destination path already exists")
    
    try:
        os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
        os.rename(full_path, new_full_path)
        return {"status": "success", "from": path, "to": new_path}
    except Exception as e:
        logger.error(f"Error moving file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)