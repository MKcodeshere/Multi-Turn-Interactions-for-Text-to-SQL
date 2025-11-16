# LangGraph Workflow for Text-to-SQL

This document describes the LangGraph-based workflow implementation for the Interactive Text-to-SQL system.

## Overview

The system uses **LangGraph** to orchestrate a multi-turn text-to-SQL generation process with explicit nodes and edges, providing better control and transparency compared to the traditional ReAct agent pattern.

## Architecture

### State Definition

The workflow maintains a shared state (`AgentState`) that gets passed between nodes:

```python
class AgentState(TypedDict):
    # User input
    question: str
    schema_summary: str

    # Workflow tracking
    current_step: str
    iteration: int
    max_iterations: int

    # Planning
    plan: str
    required_actions: List[str]

    # Search results
    relevant_columns: List[Dict]
    relevant_values: List[Dict]
    join_paths: List[Dict]

    # SQL generation & execution
    sql_query: str
    sql_queries: List[str]  # Accumulates all attempts
    execution_result: Any
    execution_error: str

    # Decision flags
    needs_column_search: bool
    needs_value_search: bool
    needs_path_finding: bool
    ready_to_execute: bool

    # Output
    final_answer: str
    messages: List[Any]
```

## Workflow Graph

```
┌─────────────────┐
│   START         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PLANNING      │  ◄─── Analyzes question, creates plan
│                 │       Determines required actions
└────────┬────────┘
         │
         ▼
    ┌────────────┐
    │ Needs      │
    │ Column     │  Yes  ┌─────────────────┐
    │ Search?    ├──────►│ SEARCH_COLUMNS  │
    └────┬───────┘       │                 │
         │               │ - Uses embeddings│
         │ No            │ - Finds relevant │
         │               │   columns        │
         │               └────────┬─────────┘
         │                        │
         └────────────────────────┘
                 │
                 ▼
            ┌────────────┐
            │ Needs      │
            │ Value      │  Yes  ┌─────────────────┐
            │ Search?    ├──────►│ SEARCH_VALUES   │
            └────┬───────┘       │                 │
                 │               │ - Searches DB   │
                 │ No            │ - Finds entities│
                 │               └────────┬─────────┘
                 │                        │
                 └────────────────────────┘
                         │
                         ▼
                    ┌────────────┐
                    │ Needs      │
                    │ Path       │  Yes  ┌─────────────────┐
                    │ Finding?   ├──────►│ FIND_PATHS      │
                    └────┬───────┘       │                 │
                         │               │ - Finds joins   │
                         │ No            │ - Multi-table   │
                         │               └────────┬─────────┘
                         │                        │
                         └────────────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ GENERATE_SQL    │
                        │                 │
                        │ - Creates query │
                        │ - Uses context  │
                        └────────┬─────────┘
                                 │
                                 ▼
                            ┌────────────┐
                            │ Ready to   │
                            │ Execute?   │  Yes  ┌─────────────────┐
                            └────┬───────┘       │ EXECUTE_SQL     │
                                 │               │                 │
                                 │ No            │ - Runs query    │
                                 │               │ - Gets results  │
                                 │               └────────┬─────────┘
                                 │                        │
                                 │                        ▼
                                 │               ┌─────────────────┐
                                 │               │ Success?        │
                                 │               └────┬─────┬──────┘
                                 │                    │     │
                                 │            Yes     │     │ No (retry)
                                 │                    │     │
                                 │                    │     └────►GENERATE_SQL
                                 │                    │              (if iterations left)
                                 │                    │
                                 └────────────────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │ ANSWER          │
                                 │                 │
                                 │ - Formats result│
                                 │ - Natural lang. │
                                 └────────┬─────────┘
                                          │
                                          ▼
                                     ┌────────┐
                                     │  END   │
                                     └────────┘
```

## Nodes

### 1. Planning Node
**Purpose**: Analyzes the user's question and creates an execution plan

**Inputs**:
- `question`: User's natural language query
- `schema_summary`: Database schema overview

**Outputs**:
- `plan`: High-level strategy
- `required_actions`: List of actions needed
- `needs_*` flags: Boolean flags for routing

**Example**:
```
Question: "Which player scored the most goals?"

Plan: Find the goals column, identify player info, and aggregate by player
Required Actions: SearchColumn, GenerateSQL, ExecuteSQL
```

### 2. Search Columns Node
**Purpose**: Find relevant database columns using semantic search

**Inputs**:
- `question`: Original question
- `plan`: Execution plan

**Outputs**:
- `relevant_columns`: List of column metadata with similarity scores

**Tool Used**: `SearchColumnTool` (text-embedding-3-large)

### 3. Search Values Node
**Purpose**: Find specific cell values in the database

**Inputs**:
- `question`: Original question
- `relevant_columns`: Previously found columns

**Outputs**:
- `relevant_values`: Matching rows and values

**Tool Used**: `SearchValueTool`

### 4. Find Paths Node
**Purpose**: Discover join paths between multiple tables

**Inputs**:
- `relevant_columns`: Columns from different tables

**Outputs**:
- `join_paths`: Foreign key relationships and join sequences

**Tool Used**: `FindShortestPathTool` (uses NetworkX)

### 5. Generate SQL Node
**Purpose**: Create SQL query from gathered information

**Inputs**:
- `question`: Original question
- `relevant_columns`: Available columns
- `relevant_values`: Specific values
- `join_paths`: Join information
- `sql_queries`: Previous attempts (for retry)

**Outputs**:
- `sql_query`: Generated SQL
- `ready_to_execute`: True

**Uses**: ChatGPT-4 with context-aware prompting

### 6. Execute SQL Node
**Purpose**: Run the generated SQL and capture results

**Inputs**:
- `sql_query`: Query to execute

**Outputs**:
- `execution_result`: Query results
- `execution_error`: Error message (if failed)

**Tool Used**: `ExecuteSQLTool`

### 7. Answer Generation Node
**Purpose**: Convert SQL results into natural language

**Inputs**:
- `question`: Original question
- `sql_query`: Executed SQL
- `execution_result`: Query results

**Outputs**:
- `final_answer`: Natural language response

## Conditional Edges (Routing Logic)

### 1. Should Search Columns?
```python
if state["needs_column_search"]:
    → go to "search_columns"
else:
    → go to "search_values" (skip column search)
```

### 2. Should Search Values?
```python
if state["needs_value_search"]:
    → go to "search_values"
else:
    → go to "find_paths" (skip value search)
```

### 3. Should Find Paths?
```python
if state["needs_path_finding"]:
    → go to "find_paths"
else:
    → go to "generate_sql" (single table, skip path finding)
```

### 4. Should Execute SQL?
```python
if state["ready_to_execute"]:
    → go to "execute_sql"
else:
    → go to "answer" (skip execution)
```

### 5. Should Retry or Finish?
```python
if state["execution_error"] and iterations < max_iterations:
    → go to "generate_sql" (retry)
elif state["execution_result"]:
    → go to "answer"
else:
    → END
```

## Usage

### Configuration

Set environment variable to enable LangGraph:

```bash
export USE_LANGGRAPH=true  # Use LangGraph (default)
export USE_LANGGRAPH=false # Use ReAct agent
```

### API Endpoint

```bash
POST /api/query
{
    "question": "Which player scored the most goals in 2020?"
}
```

### Response Format

```json
{
    "question": "Which player scored the most goals in 2020?",
    "answer": "Cristiano Ronaldo scored the most goals with 45 goals in 2020.",
    "final_sql": "SELECT player_name, COUNT(*) as goals FROM ...",
    "sql_queries": ["SELECT ...", "SELECT ..."],
    "intermediate_steps": [
        {
            "step": "Plan: Find goals table and player info...",
            "type": "ai"
        },
        {
            "step": "Found 5 relevant columns",
            "type": "ai"
        },
        ...
    ]
}
```

## Advantages Over ReAct Agent

### 1. **Explicit Control Flow**
- Clear, deterministic workflow
- Predictable execution order
- Easy to debug and modify

### 2. **Better Performance**
- Skip unnecessary steps (conditional edges)
- Parallel execution possible
- Fewer LLM calls

### 3. **State Management**
- Typed state with TypedDict
- Accumulator pattern for messages/queries
- Full conversation history

### 4. **Modularity**
- Easy to add/remove nodes
- Reusable node functions
- Testable in isolation

### 5. **Visualization**
- Graph can be visualized
- Clear workflow diagram
- Better for documentation

## Example Workflow Execution

**Question**: "Find the top 3 teams by total goals in 2020"

```
1. PLANNING
   → Plan: Find team and goals tables, aggregate by team
   → Actions: SearchColumn, FindShortestPath, GenerateSQL, ExecuteSQL

2. SEARCH_COLUMNS
   → Queries: ["team name", "goals scored", "year"]
   → Found: teams.name, matches.goals_home, matches.date

3. FIND_PATHS
   → Tables: teams, matches
   → Path: teams.id → matches.team_id

4. GENERATE_SQL
   → SQL: SELECT t.name, SUM(m.goals_home) as total
          FROM teams t JOIN matches m ON t.id = m.team_id
          WHERE YEAR(m.date) = 2020
          GROUP BY t.name
          ORDER BY total DESC
          LIMIT 3

5. EXECUTE_SQL
   → Result: [(Barcelona, 156), (Real Madrid, 142), (PSG, 138)]

6. ANSWER
   → "The top 3 teams by total goals in 2020 are:
      1. Barcelona with 156 goals
      2. Real Madrid with 142 goals
      3. PSG with 138 goals"
```

## Debugging

To see the workflow execution:

```python
# The graph can be visualized
workflow = SQLAgentWorkflow(tools, database)
workflow.app.get_graph().print_ascii()

# Or export to mermaid diagram
print(workflow.app.get_graph().draw_mermaid())
```

## Future Enhancements

1. **Checkpointing**: Add memory persistence for multi-session conversations
2. **Parallel Nodes**: Run searches in parallel for better performance
3. **Human-in-the-Loop**: Add approval nodes for SQL execution
4. **Streaming**: Stream intermediate results to frontend
5. **A/B Testing**: Compare different node implementations
6. **Metrics**: Add timing and performance tracking per node

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Interactive-T2S Paper (CIKM 2025)](https://arxiv.org/abs/...)
- [StateGraph API](https://langchain-ai.github.io/langgraph/reference/graphs/)
