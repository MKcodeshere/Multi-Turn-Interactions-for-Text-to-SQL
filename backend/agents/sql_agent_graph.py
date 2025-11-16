"""
LangGraph-based SQL Agent for multi-turn text-to-SQL interactions
Implements explicit workflow with nodes and edges for better control
"""
from typing import TypedDict, List, Dict, Any, Annotated, Literal
from typing_extensions import TypedDict as ExtTypedDict
import operator
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from backend.config import LLM_MODEL, LLM_TEMPERATURE


# ============================================================================
# STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """
    State of the SQL generation workflow

    The state is passed between nodes and accumulates information
    throughout the workflow execution.
    """
    # User input
    question: str

    # Schema information
    schema_summary: str

    # Workflow tracking
    current_step: str
    iteration: int
    max_iterations: int

    # Planning
    plan: str
    required_actions: List[str]

    # Search results
    relevant_columns: List[Dict[str, Any]]
    relevant_values: List[Dict[str, Any]]
    join_paths: List[Dict[str, Any]]

    # SQL generation
    sql_query: str
    sql_queries: Annotated[List[str], operator.add]  # Accumulate all SQL attempts

    # Execution results
    execution_result: Any
    execution_error: str

    # Decision making
    needs_column_search: bool
    needs_value_search: bool
    needs_path_finding: bool
    needs_sql_generation: bool
    ready_to_execute: bool

    # Final output
    final_answer: str
    messages: Annotated[List[Any], operator.add]  # Conversation history


# ============================================================================
# WORKFLOW NODES
# ============================================================================

class SQLAgentWorkflow:
    """
    LangGraph workflow for text-to-SQL generation
    Implements nodes and edges for multi-turn interaction
    """

    def __init__(self, tools: List, database):
        self.tools = {tool.name: tool for tool in tools}
        self.database = database
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE
        )

        # Build the graph
        self.graph = self._build_graph()
        self.app = self.graph.compile()

    # ========================================================================
    # NODE IMPLEMENTATIONS
    # ========================================================================

    def planning_node(self, state: AgentState) -> AgentState:
        """
        Analyze the question and create a plan
        Determines which tools/actions are needed
        """
        print(f"\n🎯 [PLANNING] Analyzing question: {state['question']}")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a SQL generation planner. Analyze the user's question and determine what steps are needed.

Available actions:
- SearchColumn: Find relevant columns by semantic meaning (use for wide tables or when column names are unclear)
- SearchValue: Find specific values in the database (use when looking for specific entities)
- FindShortestPath: Find join paths between tables (use when joining 2+ tables)
- GenerateSQL: Generate the SQL query
- ExecuteSQL: Execute the SQL and get results

Database Schema:
{schema_summary}

Question: {question}

Analyze the question and provide:
1. A brief plan (2-3 sentences)
2. Required actions as a comma-separated list

Format your response as:
PLAN: <your plan>
ACTIONS: <action1>, <action2>, <action3>"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                schema_summary=state["schema_summary"],
                question=state["question"]
            )
        )

        content = response.content

        # Parse plan and actions
        plan = ""
        actions = []

        for line in content.split('\n'):
            if line.startswith('PLAN:'):
                plan = line.replace('PLAN:', '').strip()
            elif line.startswith('ACTIONS:'):
                actions_str = line.replace('ACTIONS:', '').strip()
                actions = [a.strip() for a in actions_str.split(',')]

        # Update state flags based on required actions
        print(f"   📋 Plan: {plan}")
        print(f"   ✅ Required actions: {', '.join(actions)}")

        return {
            **state,
            "plan": plan,
            "required_actions": actions,
            "needs_column_search": "SearchColumn" in actions,
            "needs_value_search": "SearchValue" in actions,
            "needs_path_finding": "FindShortestPath" in actions,
            "needs_sql_generation": True,  # Always need to generate SQL
            "current_step": "planning_complete",
            "messages": [AIMessage(content=f"Plan: {plan}\nRequired actions: {', '.join(actions)}")]
        }

    def column_search_node(self, state: AgentState) -> AgentState:
        """
        Search for relevant columns using semantic similarity
        """
        print(f"\n🔍 [COLUMN SEARCH] Searching for relevant columns...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Based on the question and plan, identify what columns you need to search for.
Provide 2-3 semantic descriptions of columns.

Question: {question}
Plan: {plan}

Provide column search queries as a comma-separated list:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                plan=state.get("plan", "")
            )
        )

        # Parse search queries
        queries = [q.strip() for q in response.content.split(',')]

        # Execute search using the tool
        search_tool = self.tools.get("SearchColumn")
        if search_tool:
            results = search_tool._run(queries, k=5)

            # Flatten results
            all_columns = []
            for query, cols in results.items():
                all_columns.extend(cols)

            print(f"   ✅ Found {len(all_columns)} relevant columns")

            return {
                **state,
                "relevant_columns": all_columns,
                "needs_column_search": False,
                "current_step": "column_search_complete",
                "messages": [AIMessage(content=f"Found {len(all_columns)} relevant columns")]
            }

        return {**state, "needs_column_search": False}

    def value_search_node(self, state: AgentState) -> AgentState:
        """
        Search for specific values in the database
        """
        print(f"\n🔎 [VALUE SEARCH] Searching for specific values...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Based on the question, identify specific values to search for in the database.
These could be names, IDs, or other specific entities.

Question: {question}
Plan: {plan}
Relevant columns: {columns}

If there are specific values to search for, provide them as a comma-separated list.
If no specific values are needed, respond with: NONE

Search values:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                plan=state.get("plan", ""),
                columns=str(state.get("relevant_columns", []))[:500]
            )
        )

        content = response.content.strip()

        if content == "NONE" or not content:
            print(f"   ⏭️  Skipping value search (not needed)")
            return {
                **state,
                "needs_value_search": False,
                "current_step": "value_search_skipped"
            }

        # Parse search values
        values = [v.strip() for v in content.split(',')]

        # Execute search using the tool
        search_tool = self.tools.get("SearchValue")
        all_results = []

        if search_tool:
            for value in values[:3]:  # Limit to 3 searches
                try:
                    results = search_tool._run(value)
                    all_results.extend(results)
                except Exception as e:
                    print(f"   ❌ Value search error for '{value}': {e}")

        print(f"   ✅ Found {len(all_results)} relevant values")

        return {
            **state,
            "relevant_values": all_results,
            "needs_value_search": False,
            "current_step": "value_search_complete",
            "messages": [AIMessage(content=f"Found {len(all_results)} relevant values")]
        }

    def path_finding_node(self, state: AgentState) -> AgentState:
        """
        Find join paths between tables
        """
        print(f"\n🗺️  [PATH FINDING] Finding join paths between tables...")

        # Extract unique tables from relevant columns
        tables = set()
        for col in state.get("relevant_columns", []):
            if "table_name" in col:
                tables.add(col["table_name"])

        if len(tables) < 2:
            # No join needed - single table query
            print(f"   ⏭️  Skipping path finding (single table query)")
            return {
                **state,
                "needs_path_finding": False,
                "current_step": "path_finding_skipped"
            }

        # Find paths between tables
        path_tool = self.tools.get("FindShortestPath")
        paths = []

        if path_tool:
            table_list = list(tables)
            for i in range(len(table_list) - 1):
                try:
                    path = path_tool._run(
                        table_list[i],
                        table_list[i + 1]
                    )
                    paths.append(path)
                except Exception as e:
                    print(f"   ❌ Path finding error: {e}")

        print(f"   ✅ Found {len(paths)} join paths")

        return {
            **state,
            "join_paths": paths,
            "needs_path_finding": False,
            "current_step": "path_finding_complete",
            "messages": [AIMessage(content=f"Found {len(paths)} join paths")]
        }

    def sql_generation_node(self, state: AgentState) -> AgentState:
        """
        Generate SQL query based on gathered information
        """
        print(f"\n💡 [SQL GENERATION] Generating SQL query...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert SQL query generator. Generate a SQL query to answer the question.

Question: {question}

Database Schema Summary:
{schema_summary}

Relevant Columns:
{columns}

Relevant Values:
{values}

Join Paths:
{paths}

Previous SQL attempts:
{previous_sql}

Generate a valid SQL query. Output ONLY the SQL query, no explanations.
SQL Query:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                schema_summary=state["schema_summary"],
                columns=str(state.get("relevant_columns", []))[:1000],
                values=str(state.get("relevant_values", []))[:500],
                paths=str(state.get("join_paths", []))[:500],
                previous_sql="\n".join(state.get("sql_queries", []))
            )
        )

        sql_query = response.content.strip()

        # Clean up SQL (remove markdown code blocks if present)
        if sql_query.startswith("```sql"):
            sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        elif sql_query.startswith("```"):
            sql_query = sql_query.replace("```", "").strip()

        print(f"   ✅ Generated SQL: {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}")

        return {
            **state,
            "sql_query": sql_query,
            "sql_queries": [sql_query],
            "needs_sql_generation": False,
            "ready_to_execute": True,
            "current_step": "sql_generated",
            "messages": [AIMessage(content=f"Generated SQL: {sql_query}")]
        }

    def sql_execution_node(self, state: AgentState) -> AgentState:
        """
        Execute the generated SQL query
        """
        print(f"\n⚡ [SQL EXECUTION] Executing SQL query...")

        sql_query = state.get("sql_query", "")

        if not sql_query:
            print(f"   ❌ No SQL query to execute")
            return {
                **state,
                "execution_error": "No SQL query to execute",
                "current_step": "execution_failed"
            }

        # Execute using the tool
        execute_tool = self.tools.get("ExecuteSQL")

        if execute_tool:
            try:
                result = execute_tool._run(sql_query)
                print(f"   ✅ Query executed successfully")
                print(f"   📊 Result preview: {str(result)[:150]}{'...' if len(str(result)) > 150 else ''}")

                return {
                    **state,
                    "execution_result": result,
                    "execution_error": "",
                    "ready_to_execute": False,
                    "current_step": "execution_complete",
                    "messages": [AIMessage(content=f"Query executed successfully. Result: {str(result)[:200]}")]
                }
            except Exception as e:
                print(f"   ❌ Execution error: {str(e)}")
                return {
                    **state,
                    "execution_error": str(e),
                    "ready_to_execute": False,
                    "current_step": "execution_failed",
                    "messages": [AIMessage(content=f"Execution error: {str(e)}")]
                }

        return {**state, "execution_error": "ExecuteSQL tool not available"}

    def answer_generation_node(self, state: AgentState) -> AgentState:
        """
        Generate final answer based on execution results
        """
        print(f"\n📝 [ANSWER GENERATION] Generating natural language answer...")

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Generate a natural language answer to the user's question based on the SQL execution result.

Question: {question}
SQL Query: {sql_query}
Result: {result}

Provide a clear, concise answer:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                sql_query=state.get("sql_query", ""),
                result=str(state.get("execution_result", ""))
            )
        )

        print(f"   ✅ Answer generated")
        print(f"   📋 Final answer: {response.content[:150]}{'...' if len(response.content) > 150 else ''}\n")

        return {
            **state,
            "final_answer": response.content,
            "current_step": "complete",
            "messages": [AIMessage(content=response.content)]
        }

    # ========================================================================
    # CONDITIONAL EDGES (ROUTING LOGIC)
    # ========================================================================

    def should_search_columns(self, state: AgentState) -> Literal["search_columns", "check_value_search"]:
        """Decide if we need to search for columns"""
        if state.get("needs_column_search", False):
            return "search_columns"
        return "check_value_search"

    def should_search_values(self, state: AgentState) -> Literal["search_values", "check_path_finding"]:
        """Decide if we need to search for values"""
        if state.get("needs_value_search", False):
            return "search_values"
        return "check_path_finding"

    def should_find_paths(self, state: AgentState) -> Literal["find_paths", "generate_sql"]:
        """Decide if we need to find join paths"""
        if state.get("needs_path_finding", False):
            return "find_paths"
        return "generate_sql"

    def should_execute_sql(self, state: AgentState) -> Literal["execute_sql", "answer"]:
        """Decide if SQL is ready to execute"""
        if state.get("ready_to_execute", False):
            return "execute_sql"
        return "answer"

    def should_retry_or_finish(self, state: AgentState) -> Literal["generate_sql", "answer", END]:
        """Decide if we should retry SQL generation or finish"""
        # If execution failed and we haven't exceeded max iterations, retry
        if state.get("execution_error") and state.get("iteration", 0) < state.get("max_iterations", 3):
            return "generate_sql"

        # If we have a result, generate answer
        if state.get("execution_result"):
            return "answer"

        # Otherwise end
        return END

    # ========================================================================
    # GRAPH CONSTRUCTION
    # ========================================================================

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow with nodes and edges
        """
        # Initialize the graph with our state schema
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("planning", self.planning_node)
        workflow.add_node("search_columns", self.column_search_node)
        workflow.add_node("search_values", self.value_search_node)
        workflow.add_node("find_paths", self.path_finding_node)
        workflow.add_node("generate_sql", self.sql_generation_node)
        workflow.add_node("execute_sql", self.sql_execution_node)
        workflow.add_node("answer", self.answer_generation_node)

        # Set entry point
        workflow.set_entry_point("planning")

        # Add conditional edges (routing logic)
        workflow.add_conditional_edges(
            "planning",
            self.should_search_columns,
            {
                "search_columns": "search_columns",
                "check_value_search": "search_values"  # Skip to value search
            }
        )

        workflow.add_conditional_edges(
            "search_columns",
            self.should_search_values,
            {
                "search_values": "search_values",
                "check_path_finding": "find_paths"  # Skip to path finding
            }
        )

        workflow.add_conditional_edges(
            "search_values",
            self.should_find_paths,
            {
                "find_paths": "find_paths",
                "generate_sql": "generate_sql"  # Skip to SQL generation
            }
        )

        workflow.add_edge("find_paths", "generate_sql")

        workflow.add_conditional_edges(
            "generate_sql",
            self.should_execute_sql,
            {
                "execute_sql": "execute_sql",
                "answer": "answer"
            }
        )

        workflow.add_conditional_edges(
            "execute_sql",
            self.should_retry_or_finish,
            {
                "generate_sql": "generate_sql",  # Retry
                "answer": "answer",
                END: END
            }
        )

        workflow.add_edge("answer", END)

        return workflow

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def query(self, question: str, max_iterations: int = 3) -> Dict[str, Any]:
        """
        Execute the workflow for a given question

        Args:
            question: Natural language question
            max_iterations: Maximum SQL generation attempts

        Returns:
            Dictionary with results and intermediate steps
        """
        print(f"\n{'='*80}")
        print(f"🚀 STARTING LANGGRAPH WORKFLOW")
        print(f"{'='*80}")

        # Get schema summary
        schema_summary = self.database.get_schema_summary()

        # Initialize state
        initial_state = {
            "question": question,
            "schema_summary": schema_summary,
            "current_step": "start",
            "iteration": 0,
            "max_iterations": max_iterations,
            "plan": "",
            "required_actions": [],
            "relevant_columns": [],
            "relevant_values": [],
            "join_paths": [],
            "sql_query": "",
            "sql_queries": [],
            "execution_result": None,
            "execution_error": "",
            "needs_column_search": False,
            "needs_value_search": False,
            "needs_path_finding": False,
            "needs_sql_generation": False,
            "ready_to_execute": False,
            "final_answer": "",
            "messages": []
        }

        # Run the workflow
        final_state = self.app.invoke(initial_state)

        print(f"{'='*80}")
        print(f"✅ WORKFLOW COMPLETED")
        print(f"{'='*80}\n")

        # Format response
        return {
            "question": question,
            "answer": final_state.get("final_answer", ""),
            "sql_queries": final_state.get("sql_queries", []),
            "final_sql": final_state.get("sql_query", ""),
            "execution_result": final_state.get("execution_result"),
            "plan": final_state.get("plan", ""),
            "intermediate_steps": [
                {
                    "step": msg.content,
                    "type": "ai"
                }
                for msg in final_state.get("messages", [])
            ]
        }
