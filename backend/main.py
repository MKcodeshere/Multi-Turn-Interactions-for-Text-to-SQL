"""
FastAPI backend for Interactive Text-to-SQL system
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import Database
from backend.embeddings import ColumnEmbeddingManager
from backend.tools import SearchColumnTool, SearchValueTool, FindShortestPathTool, ExecuteSQLTool
from backend.agents import SQLAgent, SQLAgentWorkflow
from backend.config import HOST, PORT


# Global variables for database and agent
db = None
agent = None
agent_workflow = None  # LangGraph workflow
embedding_manager = None
USE_LANGGRAPH = os.getenv("USE_LANGGRAPH", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    global db, agent, agent_workflow, embedding_manager

    # Startup
    print("🚀 Starting Interactive Text-to-SQL backend...")

    # Initialize database
    db = Database()
    print(f"✓ Database connected: {db.db_path}")

    # Initialize embedding manager
    print("🔄 Building column embeddings (this may take a moment)...")
    embedding_manager = ColumnEmbeddingManager(db)
    num_columns = embedding_manager.build_embeddings()
    print(f"✓ Embedded {num_columns} columns")

    # Initialize tools
    tools = [
        SearchColumnTool(embedding_manager=embedding_manager),
        SearchValueTool(database=db),
        FindShortestPathTool(database=db),
        ExecuteSQLTool(database=db)
    ]

    # Initialize agent (choose between LangGraph and ReAct)
    if USE_LANGGRAPH:
        agent_workflow = SQLAgentWorkflow(tools=tools, database=db)
        print("✓ LangGraph SQL Workflow initialized")
    else:
        agent = SQLAgent(tools=tools, database=db)
        print("✓ ReAct SQL Agent initialized")

    print(f"\n🎉 Server ready at http://{HOST}:{PORT}")
    print(f"📊 Database schema: {len(db.get_tables())} tables")
    print(f"🔧 Using: {'LangGraph Workflow' if USE_LANGGRAPH else 'ReAct Agent'}")

    yield

    # Shutdown
    print("👋 Shutting down Interactive Text-to-SQL backend...")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="Interactive Text-to-SQL",
    description="Multi-turn text-to-SQL system with LangChain and text-embedding-3-large",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    final_sql: Optional[str]
    sql_queries: List[str]
    intermediate_steps: List[Dict]


class SchemaResponse(BaseModel):
    tables: List[str]
    foreign_keys: List[Dict]
    column_count: Dict[str, int]


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page"""
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if frontend_path.exists():
        with open(frontend_path, 'r', encoding='utf-8') as f:
            return f.read()
    return """
    <html>
        <head><title>Interactive Text-to-SQL</title></head>
        <body>
            <h1>Interactive Text-to-SQL API</h1>
            <p>Visit <a href="/docs">/docs</a> for API documentation</p>
        </body>
    </html>
    """


@app.get("/api/schema", response_model=SchemaResponse)
async def get_schema():
    """Get database schema information"""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    tables = db.get_tables()
    fks = db.get_all_foreign_keys()
    column_count = {}

    for table in tables:
        columns = db.get_columns(table)
        column_count[table] = len(columns)

    return SchemaResponse(
        tables=tables,
        foreign_keys=fks,
        column_count=column_count
    )


@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Process a natural language query and generate SQL

    This endpoint demonstrates the multi-turn interaction capability:
    - Uses SearchColumn for efficient column discovery (handles wide tables)
    - Uses SearchValue for cell value lookup
    - Uses FindShortestPath for complex joins
    - Uses ExecuteSQL for query execution
    """
    if USE_LANGGRAPH and agent_workflow is None:
        raise HTTPException(status_code=500, detail="Agent workflow not initialized")
    elif not USE_LANGGRAPH and agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    try:
        # Process query using the appropriate agent
        if USE_LANGGRAPH:
            result = agent_workflow.query(request.question)

            # Format intermediate steps from LangGraph
            formatted_steps = result.get('intermediate_steps', [])

        else:
            # Use ReAct agent
            result = agent.query(request.question)

            # Format intermediate steps for ReAct agent
            formatted_steps = []
            for step in result.get('intermediate_steps', []):
                action, observation = step
                formatted_steps.append({
                    "tool": action.tool if hasattr(action, 'tool') else "unknown",
                    "input": action.tool_input if hasattr(action, 'tool_input') else {},
                    "output": str(observation)[:500]  # Limit output length
                })

        return QueryResponse(
            question=result['question'],
            answer=result['answer'],
            final_sql=result['final_sql'],
            sql_queries=result['sql_queries'],
            intermediate_steps=formatted_steps
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing error: {str(e)}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    agent_status = "not initialized"
    if USE_LANGGRAPH:
        agent_status = "initialized (LangGraph)" if agent_workflow else "not initialized"
    else:
        agent_status = "initialized (ReAct)" if agent else "not initialized"

    return {
        "status": "healthy",
        "database": "connected" if db else "not connected",
        "agent": agent_status,
        "embeddings": "ready" if embedding_manager else "not ready",
        "mode": "LangGraph" if USE_LANGGRAPH else "ReAct"
    }


# Mount static files
static_dir = Path(__file__).parent.parent / "frontend" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def main():
    """Run the FastAPI server"""
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
