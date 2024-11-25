import logging
from pathlib import Path
from typing import Dict, List, Set
import threading
import time
import json
from datetime import datetime
import warnings

# Suppress Whoosh warning
warnings.filterwarnings("ignore", category=SyntaxWarning, module="whoosh.codec.whoosh3")

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from whoosh.index import create_in, open_dir
from whoosh.fields import Schema, TEXT, ID, DATETIME
from whoosh.qparser import QueryParser
from pypdf import PdfReader
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class SearchResult(BaseModel):
    path: str
    content_preview: str
    score: float
    modified: datetime

class VaultChangeHandler(FileSystemEventHandler):
    def __init__(self, search_manager):
        self.search_manager = search_manager
        self.pending_changes: Set[Path] = set()
        self._lock = threading.Lock()
        self._running = True
        logger.info("VaultChangeHandler initialized")
        # Start background processing thread
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def _process_loop(self):
        """Continuously process pending changes"""
        while self._running:
            try:
                with self._lock:
                    if self.pending_changes:
                        logger.info(f"Processing {len(self.pending_changes)} pending changes")
                        self.search_manager.index_specific_files(self.pending_changes)
                        self.pending_changes.clear()
                        logger.info("Successfully processed changes")
            except Exception as e:
                logger.error(f"Error in process loop: {e}")
            time.sleep(3)  # Wait 3 seconds between checks

    def on_created(self, event):
        if event.is_directory:
            return
        logger.info(f"File created: {event.src_path}")
        self._handle_change(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        logger.info(f"File modified: {event.src_path}")
        self._handle_change(event.src_path)

    def _handle_change(self, file_path: str):
        path = Path(file_path)
        if path.suffix.lower() in ['.md', '.txt', '.pdf'] and not path.name.startswith('.'):
            logger.info(f"Queueing change for: {path}")
            try:
                if not path.is_absolute():
                    path = path.absolute()
                with self._lock:
                    self.pending_changes.add(path)
                    logger.info("Change queued successfully")
            except Exception as e:
                logger.error(f"Error handling change for {path}: {str(e)}")

    def shutdown(self):
        """Stop the background processing"""
        self._running = False
        self._thread.join(timeout=5)
        logger.info("VaultChangeHandler shutdown complete")

class SearchManager:
    def __init__(self, vault_path: str, index_path: str = "/data/search_index"):
        self.vault_path = Path(vault_path)
        self.index_path = Path(index_path)
        self.state_file = self.index_path / "index_state.json"
        self.schema = Schema(
            path=ID(stored=True, unique=True),
            content=TEXT(stored=True),
            modified=DATETIME(stored=True)
        )
        logger.info(f"Initializing SearchManager with vault path: {vault_path}")
        
        self.setup_index()
        self.setup_file_watcher()
        self.check_consistency()  # Initial indexing

    def setup_index(self):
        """Ensure index exists and is properly initialized"""
        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
            
            try:
                open_dir(str(self.index_path))
                logger.info("Using existing search index")
            except:
                create_in(str(self.index_path), self.schema)
                logger.info("Created new search index")
        except Exception as e:
            logger.error(f"Error setting up index: {e}")
            raise

    def setup_file_watcher(self):
        """Setup real-time file system monitoring"""
        try:
            self.event_handler = VaultChangeHandler(self)
            self.observer = Observer()
            self.observer.schedule(self.event_handler, str(self.vault_path), recursive=True)
            self.observer.start()
            logger.info(f"File watcher started for path: {self.vault_path}")
        except Exception as e:
            logger.error(f"Error setting up file watcher: {e}")
            raise

    def load_index_state(self) -> Dict:
        """Load the saved state of indexed files"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading index state: {e}")
            return {}

    def save_index_state(self, state: Dict):
        """Save the current state of indexed files"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Error saving index state: {e}")

    def get_file_hash(self, file_path: Path) -> str:
        """Get a hash of file's content and metadata"""
        try:
            stat = file_path.stat()
            return f"{stat.st_mtime}_{stat.st_size}"
        except Exception as e:
            logger.error(f"Error getting file hash: {e}")
            return ""

    def _extract_pdf_text(self, pdf_path: Path) -> str:
        """Extract text from PDF file"""
        try:
            reader = PdfReader(str(pdf_path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting PDF text from {pdf_path}: {e}")
            return ""

    def _index_file(self, writer, file_path: Path):
        """Index a single file"""
        try:
            if file_path.suffix.lower() == '.pdf':
                content = self._extract_pdf_text(file_path)
            else:  # Markdown or other text files
                content = file_path.read_text(encoding='utf-8')
            
            rel_path = str(file_path.relative_to(self.vault_path))
            logger.info(f"Indexing file: {rel_path}")
            
            writer.update_document(
                path=rel_path,
                content=content,
                modified=datetime.fromtimestamp(file_path.stat().st_mtime)
            )
        except Exception as e:
            logger.error(f"Error indexing {file_path}: {e}")

    def index_specific_files(self, file_paths: Set[Path]):
        """Index specific files and update state"""
        logger.info(f"Starting indexing of {len(file_paths)} files")
        try:
            idx = open_dir(str(self.index_path))
            state = self.load_index_state()
            logger.info("Opened index and loaded state")
            
            with idx.writer() as writer:
                for file_path in file_paths:
                    try:
                        if not file_path.exists():
                            logger.info(f"File doesn't exist: {file_path}")
                            continue

                        if file_path.is_file():
                            try:
                                content = file_path.read_text(encoding='utf-8')
                                rel_path = str(file_path.relative_to(self.vault_path))
                                
                                logger.info(f"Writing to index: {rel_path} (content length: {len(content)})")
                                writer.add_document(
                                    path=rel_path,
                                    content=content,
                                    modified=datetime.fromtimestamp(file_path.stat().st_mtime)
                                )
                                state[rel_path] = self.get_file_hash(file_path)
                                logger.info(f"Successfully added to index: {rel_path}")
                            except Exception as e:
                                logger.error(f"Error reading or indexing file {file_path}: {e}")
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {e}")
            
            self.save_index_state(state)
            logger.info("Successfully saved index state")
            
        except Exception as e:
            logger.error(f"Error in index_specific_files: {e}", exc_info=True)
            raise

    def check_consistency(self):
        """Check if index matches current file system state"""
        current_state = self.load_index_state()
        files_to_update = set()
        
        for file_path in self.vault_path.rglob('*'):
            if file_path.is_file() and not file_path.name.startswith('.'):
                if file_path.suffix.lower() in ['.md', '.txt', '.pdf']:
                    try:
                        rel_path = str(file_path.relative_to(self.vault_path))
                        current_hash = self.get_file_hash(file_path)
                        
                        if rel_path not in current_state or current_state[rel_path] != current_hash:
                            files_to_update.add(file_path)
                    except Exception as e:
                        logger.error(f"Error checking file {file_path}: {e}")

        # Check for deleted files
        indexed_paths = set(current_state.keys())
        existing_paths = {str(p.relative_to(self.vault_path)) 
                         for p in self.vault_path.rglob('*') 
                         if p.is_file()}
        deleted_paths = indexed_paths - existing_paths

        if deleted_paths:
            logger.info(f"Found {len(deleted_paths)} deleted files to remove from index")
            self.remove_deleted_files(deleted_paths)

        if files_to_update:
            logger.info(f"Found {len(files_to_update)} files to update")
            self.index_specific_files(files_to_update)

    def remove_deleted_files(self, paths: Set[str]):
        """Remove deleted files from the index"""
        try:
            idx = open_dir(str(self.index_path))
            state = self.load_index_state()
            
            with idx.writer() as writer:
                for path in paths:
                    writer.delete_by_term('path', path)
                    state.pop(path, None)
                    logger.info(f"Removed deleted file from index: {path}")
            
            self.save_index_state(state)
            
        except Exception as e:
            logger.error(f"Error removing deleted files: {e}")

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search the index"""
        try:
            idx = open_dir(str(self.index_path))
            results = []
            
            with idx.searcher() as searcher:
                logger.info(f"Searching for query: {query}")
                query = QueryParser("content", idx.schema).parse(query)
                search_results = searcher.search(query, limit=limit)
                logger.info(f"Found {len(search_results)} results")
                
                for hit in search_results:
                    preview = hit.highlights("content") or hit["content"][:200] + "..."
                    results.append(SearchResult(
                        path=hit['path'],
                        content_preview=preview,
                        score=hit.score,
                        modified=hit['modified']
                    ))
            
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            raise

    def shutdown(self):
        """Clean shutdown of the search manager"""
        try:
            if hasattr(self.event_handler, 'shutdown'):
                self.event_handler.shutdown()
            self.observer.stop()
            self.observer.join()
            logger.info("Search manager shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")