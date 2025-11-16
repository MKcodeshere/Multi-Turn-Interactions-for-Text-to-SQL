# Multi-Turn Text-to-SQL with LangChain & LangGraph

An interactive text-to-SQL system implementing the Interactive-T2S framework from the paper "Multi-Turn Interactions for Text-to-SQL with Large Language Models" (CIKM 2025).

## Features

- **Multi-turn Interactions**: Step-by-step SQL generation through conversational interactions
- **LangGraph Workflow**: Explicit nodes and edges for transparent, controllable agent behavior
- **Wide Table Support**: Efficient handling of tables with 50+ columns using embeddings
- **Complex Joins**: Automatic shortest path finding for multi-table queries
- **Dual Agent Modes**: Choose between LangGraph (structured workflow) or ReAct (flexible reasoning)
- **Text-Embedding-3-Large**: OpenAI's latest embedding model for semantic column matching
- **Interactive UI**: Web-based chat interface for natural language queries

## Architecture

### Backend (FastAPI + LangChain + LangGraph)
- **Two Agent Modes**:
  - **LangGraph Workflow** (default): Explicit nodes and conditional edges for transparent control flow
  - **ReAct Agent**: Traditional thought-action-observation loop with flexible reasoning
- **Four General-Purpose Tools**: SearchColumn, SearchValue, FindShortestPath, ExecuteSQL
- **Embedding-based Schema Linking**: Efficient column discovery for wide tables

### LangGraph Workflow
The LangGraph implementation provides a structured, controllable workflow with explicit nodes and edges:

**Nodes**:
1. **Planning**: Analyzes question and creates execution plan
2. **Search Columns**: Semantic search for relevant columns
3. **Search Values**: Find specific entities in the database
4. **Find Paths**: Discover join paths between tables
5. **Generate SQL**: Create query from gathered context
6. **Execute SQL**: Run query and capture results
7. **Answer**: Format natural language response

**Conditional Edges**: Dynamic routing based on question complexity (skip unnecessary steps)

See [LANGGRAPH_WORKFLOW.md](./LANGGRAPH_WORKFLOW.md) for detailed documentation.

### Frontend (HTML + JavaScript)
- Real-time chat interface
- SQL query visualization
- Result table rendering
- Conversation history tracking

### Database
- Soccer database with 7 tables
- Player_Attributes: 60+ columns (demonstrates wide table handling)
- Match: 100+ columns with complex relationships
- Multi-table joins across Country → League → Team → Player → Match

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Optional: Choose agent mode (default: LangGraph)
export USE_LANGGRAPH=true   # Use LangGraph workflow (recommended)
# export USE_LANGGRAPH=false  # Use ReAct agent
```

4. Initialize the database:
```bash
python scripts/init_database.py
```

5. Start the backend server:
```bash
python backend/main.py
```

6. Open the frontend in your browser:
```
http://localhost:8000
```

## Running Examples

### Using the Example Script

Run the LangGraph workflow directly without the web interface:

```bash
# Run demo queries
python examples/langgraph_example.py

# Visualize the workflow graph
python examples/langgraph_example.py --visualize

# Run a custom query
python examples/langgraph_example.py --query "Which player scored the most goals?"
```

## Example Queries

### Simple Query
**User**: "Which countries have soccer leagues?"

### Complex Query (Wide Table)
**User**: "Find players with overall rating above 85, good dribbling skills, and high sprint speed"
- Demonstrates column search in Player_Attributes (60+ columns)

### Complex Query (Multiple Joins)
**User**: "Show me matches where the home team won with more than 3 goals, include the league name and country"
- Demonstrates: Match → Team → League → Country (4-table join)

### Multi-turn Interaction
**User**: "Which player has the highest overall rating?"
**System**: Executes query, finds result
**User**: "Show me all their attributes"
**System**: Uses context from previous query to fetch detailed player stats

## Project Structure

```
.
├── backend/
│   ├── main.py                    # FastAPI application
│   ├── config.py                  # Configuration management
│   ├── database.py                # Database connection
│   ├── tools/                     # LangChain tools
│   │   ├── search_column.py
│   │   ├── search_value.py
│   │   ├── find_path.py
│   │   └── execute_sql.py
│   ├── agents/                    # Agent implementations
│   │   ├── sql_agent.py           # ReAct agent (traditional)
│   │   └── sql_agent_graph.py     # LangGraph workflow (new!)
│   └── embeddings/                # Embedding management
│       └── column_embeddings.py
├── frontend/
│   ├── index.html                 # Main UI
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── app.js
├── examples/
│   └── langgraph_example.py       # LangGraph usage examples
├── data/
│   └── soccer.db                  # SQLite database
├── database_description/          # Schema metadata
├── scripts/
│   └── init_database.py           # Database initialization
├── LANGGRAPH_WORKFLOW.md          # LangGraph documentation
└── README.md
```

## Implementation Details

Based on the Interactive-T2S paper (Section 3.3 - Tools for Database):

1. **SearchColumn**: Uses text-embedding-3-large to find relevant columns by semantic similarity
2. **SearchValue**: BM25-based fuzzy search for cell values across the database
3. **FindShortestPath**: Graph-based shortest path algorithm for multi-table joins
4. **ExecuteSQL**: Direct SQL execution with result validation

## Performance

- **Token Efficiency**: ~4.6k tokens per query (vs 12.8k for traditional methods)
- **Wide Table Handling**: Dynamic column retrieval instead of loading all columns
- **Scalability**: Performance independent of schema size

## References

- Paper: [Multi-Turn Interactions for Text-to-SQL with Large Language Models](https://arxiv.org/abs/2408.11062v2)
- CIKM 2025
