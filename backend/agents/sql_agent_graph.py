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
    selected_path_indices: List[int]  # Indices of join paths selected by LLM
    path_selection_reasoning: str  # LLM's explanation for path selection

    # Execution results
    execution_result: Any
    execution_error: str

    # Decision making
    needs_column_search: bool
    needs_value_search: bool
    needs_path_finding: bool
    needs_sql_generation: bool
    ready_to_execute: bool
    path_finding_deferred: bool  # Path finding postponed to SQL generation
    path_finding_failed: bool  # Path finding was attempted but found no paths
    path_finding_errors: List[str]  # Errors encountered during path finding
    single_table_with_join_indicators: bool  # Single table but query suggests joins

    # Human interaction (multi-turn)
    needs_human_input: bool
    human_feedback: str
    awaiting_confirmation: bool
    confirmation_type: str  # 'plan', 'sql', 'error'

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

    def __init__(self, tools: List, database, enable_human_interaction: bool = False):
        self.tools = {tool.name: tool for tool in tools}
        self.database = database
        self.enable_human_interaction = enable_human_interaction
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE
        )

        # Build the graph
        self.graph = self._build_graph()
        self.app = self.graph.compile()

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _normalize_path(self, path_result) -> dict:
        """
        Normalize path data to consistent dictionary format for frontend

        Args:
            path_result: Can be a string (formatted path) or tuple (start, end, path)

        Returns:
            Dictionary with 'path' key containing list of table names
        """
        if isinstance(path_result, tuple):
            # Format: (start_col, end_col, formatted_path_string)
            path_str = path_result[2] if len(path_result) > 2 else ""
        elif isinstance(path_result, str):
            path_str = path_result
        else:
            return {"path": []}

        # Parse the path string to extract table names
        # Path format: "Table1.col <-> Table2.col <-> Table3.col"
        if "No path found" in path_str or not path_str:
            return {"path": []}

        # Extract table names from the path
        parts = [p.strip() for p in path_str.split("<->")]
        tables = []
        seen = set()

        for part in parts:
            if "." in part:
                table = part.split(".")[0]
                if table not in seen:
                    tables.append(table)
                    seen.add(table)

        return {"path": tables, "full_path": path_str}

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
- FindShortestPath: Find join paths between tables. ALWAYS use when:
  * The question involves entities from different tables (e.g., players AND teams, matches AND players)
  * You need to lookup IDs from names (e.g., finding team_id for "Barcelona")
  * You need to display related information (e.g., showing team names in match results)
  * Any query that requires joining 2+ tables
- GenerateSQL: Generate the SQL query
- ExecuteSQL: Execute the SQL and get results

Database Schema:
{schema_summary}

Question: {question}

Examples:
- "Show me all players" → ACTIONS: SearchColumn, GenerateSQL (single table)
- "Find matches where Barcelona played" → ACTIONS: SearchValue, FindShortestPath, GenerateSQL (need to join Match with Team)
- "Show player names with their team names" → ACTIONS: FindShortestPath, GenerateSQL (join Player with Team)

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
            "awaiting_confirmation": True,  # Wait for human confirmation
            "confirmation_type": "plan",
            "messages": [AIMessage(content=f"Plan: {plan}\nRequired actions: {', '.join(actions)}")]
        }

    def column_search_node(self, state: AgentState) -> AgentState:
        """
        Search for relevant columns using semantic similarity
        Falls back to showing all columns if not enough results found
        """
        is_retry = state.get("execution_error", "") != ""
        retry_context = f" (retry due to error)" if is_retry else ""
        print(f"\n🔍 [COLUMN SEARCH] Searching for relevant columns...{retry_context}")

        # Include error context if this is a retry
        error_hint = ""
        if is_retry:
            error_msg = state.get('execution_error', '')
            # Extract the invalid column name from the error if possible
            # Error format: "no such column: table.column" or "no such column: column"
            import re
            match = re.search(r'no such column:\s*(?:\w+\.)?(\w+)', error_msg.lower())
            if match:
                bad_column = match.group(1)
                error_hint = f"\n\nPrevious error: {error_msg}\nThe column '{bad_column}' does not exist. Please search for alternative columns that might contain the data we're looking for."
            else:
                error_hint = f"\n\nPrevious error: {error_msg}\nPlease search for columns that might resolve this error."

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Based on the question and plan, identify what columns you need to search for.
Provide 2-3 semantic descriptions of columns.

Question: {question}
Plan: {plan}
{error_hint}

Provide column search queries as a comma-separated list:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                plan=state.get("plan", ""),
                error_hint=error_hint
            )
        )

        # Parse search queries
        queries = [q.strip() for q in response.content.split(',')]

        # Execute search using the tool
        search_tool = self.tools.get("SearchColumn")
        all_columns = []

        if search_tool:
            results = search_tool._run(queries, k=10)

            # Flatten results
            for query, cols in results.items():
                all_columns.extend(cols)

            # Fallback: If we didn't find enough columns, get all columns from relevant tables
            if len(all_columns) < 3:
                print(f"   ⚠️  Found only {len(all_columns)} columns, fetching all columns as fallback")

                # Get all columns from database
                all_db_columns = self.database.get_all_columns()

                # Convert to the format expected by the workflow
                for col_info in all_db_columns[:50]:  # Limit to 50 columns to avoid overwhelming the LLM
                    stats = self.database.get_column_statistics(col_info['table'], col_info['column'])
                    all_columns.append({
                        'table_name': col_info['table'],
                        'column_name': col_info['column'],
                        'data_type': col_info['type'],
                        'statistics': stats
                    })

                print(f"   ℹ️  Showing all columns (fallback): {len(all_columns)} total")

            print(f"   ✅ Found {len(all_columns)} relevant columns")

            return {
                **state,
                "relevant_columns": all_columns,
                "needs_column_search": False,
                "needs_value_search": False if is_retry else state.get("needs_value_search", True),
                "needs_path_finding": False if is_retry else state.get("needs_path_finding", True),
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

    def _is_join_related_error(self, error: str) -> bool:
        """
        Detect if an error is related to missing joins
        """
        error_lower = error.lower()
        join_error_indicators = [
            "no such column",
            "ambiguous column",
            "unknown column",
            "table not found",
            "cannot find table",
            "cross join",
            "cartesian product",
            "missing join",
            "foreign key"
        ]
        return any(indicator in error_lower for indicator in join_error_indicators)

    def _perform_fallback_path_finding(self, state: AgentState) -> dict:
        """
        Perform path finding when it was skipped earlier but turns out to be needed
        """
        print(f"\n🔄 [FALLBACK PATH FINDING] Performing deferred path finding...")

        # Extract tables and their columns from relevant columns
        tables = set()
        table_columns = {}  # Map table -> list of columns
        for col in state.get("relevant_columns", []):
            if "table_name" in col and "column_name" in col:
                table_name = col["table_name"]
                column_name = col["column_name"]
                tables.add(table_name)
                if table_name not in table_columns:
                    table_columns[table_name] = []
                table_columns[table_name].append(column_name)

        # Also try to extract tables from the SQL error if present
        error = state.get("execution_error", "")
        if error:
            # Simple heuristic: look for table names in error messages
            # This is database-specific, but works for many SQL databases
            import re
            table_pattern = r'\b([A-Z][a-zA-Z_]*)\b'  # Capitalized words (common table naming)
            potential_tables = re.findall(table_pattern, error)
            for table in potential_tables:
                tables.add(table)

        if len(tables) < 2:
            print(f"   ⚠️  Still only {len(tables)} table(s) found, cannot perform path finding")
            return {}

        # Find paths between tables using proper table.column format
        path_tool = self.tools.get("FindShortestPath")
        paths = []

        if path_tool:
            table_list = list(tables)
            print(f"   🔗 Finding paths between {len(table_list)} tables: {table_list}")

            for i in range(len(table_list) - 1):
                source_table = table_list[i]
                target_table = table_list[i + 1]

                # Get representative columns for each table (use first column or primary key)
                source_col = f"{source_table}.{table_columns.get(source_table, ['id'])[0]}"
                target_col = f"{target_table}.{table_columns.get(target_table, ['id'])[0]}"

                try:
                    path = path_tool._run(source_col, target_col)
                    normalized_path = self._normalize_path(path)
                    paths.append(normalized_path)
                    print(f"      ✓ Fallback path {i+1}: {source_table} → {target_table}")
                    print(f"        {normalized_path.get('full_path', path)}")
                except Exception as e:
                    print(f"      ✗ Fallback path error {source_table} → {target_table}: {e}")

        print(f"   ✅ Fallback path finding complete: found {len(paths)} paths")

        return {
            "join_paths": paths,
            "path_finding_deferred": False
        }

    def path_finding_node(self, state: AgentState) -> AgentState:
        """
        Find join paths between tables with intelligent detection
        """
        print(f"\n🗺️  [PATH FINDING] Finding join paths between tables...")

        # Extract unique tables and their columns from relevant columns
        tables = set()
        table_columns = {}  # Map table -> list of columns
        for col in state.get("relevant_columns", []):
            if "table_name" in col and "column_name" in col:
                table_name = col["table_name"]
                column_name = col["column_name"]
                tables.add(table_name)
                if table_name not in table_columns:
                    table_columns[table_name] = []
                table_columns[table_name].append(column_name)

        # Analyze if joins are actually needed
        question = state.get("question", "").lower()
        planning_requires_path = "FindShortestPath" in state.get("required_actions", [])

        # Keywords that indicate cross-table relationships
        join_keywords = [
            "who played", "who scored", "which team", "players in",
            "matches with", "teams that", "players who", "games where",
            "between", "along with", "together with", "associated with",
            "belonging to", "owned by", "managed by", "working on",
            "during", "before", "after", "when", "where"
        ]
        has_join_keywords = any(keyword in question for keyword in join_keywords)

        # Check if the question suggests relationships even with single table
        # For example: "Show me players and their teams" might initially find only Player table
        relationship_indicators = ["and their", "with their", "including their", "along with"]
        suggests_relationships = any(indicator in question for indicator in relationship_indicators)

        # Determine if we should skip path finding
        should_skip = (
            len(tables) < 2 and
            not planning_requires_path and
            not has_join_keywords and
            not suggests_relationships
        )

        if should_skip:
            # No join needed - genuinely single table query
            print(f"   ⏭️  Skipping path finding (single table query, no join indicators)")
            print(f"      Tables found: {tables}")
            return {
                **state,
                "needs_path_finding": False,
                "current_step": "path_finding_skipped"
            }

        # If we have indicators but only one table, it might mean we need to look deeper
        if len(tables) < 2:
            print(f"   🔍 Only one table found, but join indicators present in question")
            print(f"      Tables: {tables}, Planning requires path: {planning_requires_path}")
            print(f"      Join keywords detected: {has_join_keywords}, Relationships suggested: {suggests_relationships}")

            # Store this information for SQL generation to handle
            return {
                **state,
                "needs_path_finding": False,
                "path_finding_deferred": True,  # New flag for deferred path finding
                "single_table_with_join_indicators": True,
                "current_step": "path_finding_deferred",
                "messages": [AIMessage(content="Path finding deferred - will analyze during SQL generation")]
            }

        # Find paths between tables using proper table.column format
        path_tool = self.tools.get("FindShortestPath")
        paths = []
        path_errors = []

        if path_tool:
            table_list = list(tables)
            print(f"   🔗 Finding paths between {len(table_list)} tables: {table_list}")

            for i in range(len(table_list) - 1):
                source_table = table_list[i]
                target_table = table_list[i + 1]

                # Get representative columns for each table (use first column or primary key)
                source_col = f"{source_table}.{table_columns.get(source_table, ['id'])[0]}"
                target_col = f"{target_table}.{table_columns.get(target_table, ['id'])[0]}"

                try:
                    path = path_tool._run(source_col, target_col)
                    normalized_path = self._normalize_path(path)
                    paths.append(normalized_path)
                    print(f"      ✓ Path {i+1}: {source_table} → {target_table}")
                    print(f"        {normalized_path.get('full_path', path)}")
                except Exception as e:
                    error_msg = f"{source_table} → {target_table}: {str(e)}"
                    path_errors.append(error_msg)
                    print(f"      ✗ Path finding error: {error_msg}")

        print(f"   ✅ Found {len(paths)} join paths")

        # Validate: If path finding was required by planner but we found no paths, flag it
        if planning_requires_path and len(paths) == 0:
            print(f"   ⚠️  WARNING: Planner required path finding but no paths were found!")
            print(f"      Errors: {path_errors}")
            print(f"      Will attempt SQL generation without explicit paths (fallback)")
            # Set flag to indicate path finding was attempted but failed
            return {
                **state,
                "join_paths": [],
                "path_finding_failed": True,
                "path_finding_errors": path_errors,
                "needs_path_finding": False,
                "current_step": "path_finding_failed",
                "messages": [AIMessage(content=f"Path finding failed: {'; '.join(path_errors[:3])}")]
            }

        return {
            **state,
            "join_paths": paths,
            "path_finding_failed": False,
            "needs_path_finding": False,
            "current_step": "path_finding_complete",
            "messages": [AIMessage(content=f"Found {len(paths)} join paths")]
        }

    def sql_generation_node(self, state: AgentState) -> AgentState:
        """
        Generate SQL query based on gathered information with fallback path finding
        """
        current_iteration = state.get("iteration", 0)
        print(f"\n💡 [SQL GENERATION] Generating SQL query... (Attempt {current_iteration + 1}/{state.get('max_iterations', 3)})")

        # Check if we need fallback path finding
        execution_error = state.get("execution_error", "")
        path_finding_deferred = state.get("path_finding_deferred", False)
        join_paths = state.get("join_paths", [])

        # If this is a retry and we have a join-related error, try fallback path finding
        if execution_error and self._is_join_related_error(execution_error) and not join_paths:
            print(f"   🔍 Detected join-related error, attempting fallback path finding...")
            fallback_result = self._perform_fallback_path_finding(state)
            if fallback_result.get("join_paths"):
                # Update state with the new paths
                state = {**state, **fallback_result}
                join_paths = fallback_result.get("join_paths", [])
                print(f"   ✅ Fallback path finding successful, retrying SQL generation with {len(join_paths)} paths")

        # If path finding was deferred and we still don't have paths, try to get them now
        elif path_finding_deferred and not join_paths:
            print(f"   🔍 Path finding was deferred, attempting now before SQL generation...")
            fallback_result = self._perform_fallback_path_finding(state)
            if fallback_result.get("join_paths"):
                state = {**state, **fallback_result}
                join_paths = fallback_result.get("join_paths", [])
                print(f"   ✅ Deferred path finding successful, proceeding with {len(join_paths)} paths")

        # If path finding failed, add warning to error context
        path_finding_failed = state.get("path_finding_failed", False)
        if path_finding_failed and not join_paths:
            path_errors = state.get("path_finding_errors", [])
            print(f"   ⚠️  WARNING: Path finding failed but proceeding with SQL generation")
            print(f"      Errors: {path_errors[:2]}")
            print(f"      Relying on LLM's schema knowledge to generate joins")

        # If this is a retry, include the previous error in the prompt
        error_context = ""
        if execution_error:
            error_context = f"\nPrevious Error: {execution_error}\nPlease fix the error in your SQL query."

        # Format paths with indices for LLM to reference
        paths_formatted = ""
        if join_paths:
            for idx, path in enumerate(join_paths):
                path_display = ' → '.join(path.get('path', [])) if path.get('path') else 'N/A'
                full_path = path.get('full_path', '')
                paths_formatted += f"\n[Path {idx}]: {path_display}\n  Details: {full_path}\n"
        else:
            paths_formatted = "No join paths found. Use your knowledge of the schema to construct appropriate joins."

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert SQL query generator. Generate a SQL query to answer the question.

Question: {question}

Database Schema Summary:
{schema_summary}

Relevant Columns:
{columns}

Relevant Values:
{values}

Join Paths Available:
{paths}

Previous SQL attempts and errors:
{previous_sql}
{error_context}

IMPORTANT: Respond with a JSON object in this exact format:
{{
  "selected_paths": [0, 1],  // Array of path indices you're using (empty array if no paths needed)
  "reasoning": "Brief explanation of why you chose these paths",
  "sql": "SELECT ... your SQL query here ..."
}}

Make sure to:
1. Include the path indices (e.g., [0], [1, 2], or []) you're actually using for joins
2. Provide brief reasoning for your path selection
3. Generate valid SQL that uses those paths

JSON Response:"""),
        ])

        response = self.llm.invoke(
            prompt.format_messages(
                question=state["question"],
                schema_summary=state["schema_summary"],
                columns=str(state.get("relevant_columns", []))[:1000],
                values=str(state.get("relevant_values", []))[:500],
                paths=paths_formatted,
                previous_sql="\n".join(state.get("sql_queries", [])),
                error_context=error_context
            )
        )

        response_text = response.content.strip()

        # Parse JSON response
        import json
        import re

        selected_paths = []
        reasoning = ""
        sql_query = ""

        try:
            # Try to extract JSON from response (handle markdown code blocks)
            json_text = response_text
            if "```json" in json_text:
                json_text = re.search(r'```json\s*(\{.*?\})\s*```', json_text, re.DOTALL)
                json_text = json_text.group(1) if json_text else response_text
            elif "```" in json_text:
                json_text = re.search(r'```\s*(\{.*?\})\s*```', json_text, re.DOTALL)
                json_text = json_text.group(1) if json_text else response_text

            # Remove any trailing commas before closing braces (common JSON error)
            json_text = re.sub(r',(\s*[}\]])', r'\1', json_text)

            parsed = json.loads(json_text)
            selected_paths = parsed.get("selected_paths", [])
            reasoning = parsed.get("reasoning", "No reasoning provided")
            sql_query = parsed.get("sql", "")

            print(f"   📊 Path Selection: {selected_paths}")
            print(f"   💭 Reasoning: {reasoning}")
            print(f"   ✅ Generated SQL: {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}")

        except (json.JSONDecodeError, AttributeError) as e:
            print(f"   ⚠️  Failed to parse JSON response, falling back to plain text: {e}")
            # Fallback: treat entire response as SQL
            sql_query = response_text
            # Clean up SQL (remove markdown code blocks if present)
            if sql_query.startswith("```sql"):
                sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
            elif sql_query.startswith("```"):
                sql_query = sql_query.replace("```", "").strip()
            reasoning = "Failed to parse structured response"
            print(f"   ✅ Generated SQL (fallback): {sql_query[:100]}{'...' if len(sql_query) > 100 else ''}")

        return {
            **state,
            "sql_query": sql_query,
            "sql_queries": [sql_query],
            "selected_path_indices": selected_paths,
            "path_selection_reasoning": reasoning,
            "needs_sql_generation": False,
            "ready_to_execute": False,  # Don't execute immediately
            "awaiting_confirmation": True,  # Wait for human confirmation
            "confirmation_type": "sql",
            "iteration": current_iteration + 1,  # Increment iteration counter
            "current_step": "sql_generated",
            "messages": [AIMessage(content=f"Generated SQL (Attempt {current_iteration + 1}): {sql_query}\nPaths used: {selected_paths}\nReasoning: {reasoning}")]
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

                # Check if result contains an error message
                result_str = str(result)
                if "Error:" in result_str or "error:" in result_str.lower():
                    print(f"   ❌ SQL execution returned error")
                    print(f"   📊 Error: {result_str[:150]}{'...' if len(result_str) > 150 else ''}")

                    return {
                        **state,
                        "execution_result": None,
                        "execution_error": result_str,
                        "ready_to_execute": False,
                        "current_step": "execution_failed",
                        "messages": [AIMessage(content=f"SQL execution error: {result_str}")]
                    }

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
        Generate final answer based on execution results or error
        Handles both successful queries and errors gracefully
        """
        print(f"\n📝 [ANSWER GENERATION] Generating natural language answer...")

        # Check if we have an error instead of a result
        execution_error = state.get("execution_error", "")
        execution_result = state.get("execution_result")

        if execution_error and not execution_result:
            # Generate error response
            prompt = ChatPromptTemplate.from_messages([
                ("system", """The SQL query execution failed after multiple attempts.
Provide a helpful error message to the user explaining what went wrong and suggest how they might rephrase their question.

Question: {question}
Error: {error}
SQL Attempts: {sql_queries}

Generate a user-friendly error message:"""),
            ])

            response = self.llm.invoke(
                prompt.format_messages(
                    question=state["question"],
                    error=execution_error,
                    sql_queries="\n".join(state.get("sql_queries", []))
                )
            )

            print(f"   ⚠️  Error response generated")
            print(f"   📋 Error message: {response.content[:150]}{'...' if len(response.content) > 150 else ''}\n")

            return {
                **state,
                "final_answer": f"I encountered an error: {response.content}",
                "current_step": "complete_with_error",
                "messages": [AIMessage(content=response.content)]
            }
        else:
            # Generate success response
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
                    result=str(execution_result if execution_result else "No results found")
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

    def human_interaction_node(self, state: AgentState) -> AgentState:
        """
        Checkpoint for human interaction
        Pauses execution and waits for human input/confirmation
        """
        confirmation_type = state.get("confirmation_type", "")

        print(f"\n👤 [HUMAN INTERACTION] Requesting {confirmation_type} confirmation...")
        print(f"   ⏸️  Workflow paused - awaiting human input")

        # This node just marks that we're waiting for human input
        # The actual interaction happens through the API
        return {
            **state,
            "needs_human_input": True,
            "current_step": f"awaiting_{confirmation_type}_confirmation",
            "messages": [AIMessage(content=f"Awaiting human confirmation for {confirmation_type}")]
        }

    # ========================================================================
    # CONDITIONAL EDGES (ROUTING LOGIC)
    # ========================================================================

    def should_request_confirmation(self, state: AgentState) -> Literal["human_interaction", "check_column_search"]:
        """Decide if we need human confirmation after planning"""
        if (self.enable_human_interaction and
            state.get("awaiting_confirmation", False) and
            state.get("confirmation_type") == "plan"):
            return "human_interaction"
        return "check_column_search"

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

    def should_confirm_sql(self, state: AgentState) -> Literal["human_interaction", "execute_sql"]:
        """Decide if we need human confirmation before SQL execution"""
        if (self.enable_human_interaction and
            state.get("awaiting_confirmation", False) and
            state.get("confirmation_type") == "sql"):
            return "human_interaction"
        # If no interaction needed, mark as ready to execute
        state["ready_to_execute"] = True
        return "execute_sql"

    def should_execute_sql(self, state: AgentState) -> Literal["execute_sql", "answer"]:
        """Decide if SQL is ready to execute"""
        if state.get("ready_to_execute", False):
            return "execute_sql"
        return "answer"

    def should_retry_or_finish(self, state: AgentState) -> Literal["search_columns", "generate_sql", "human_interaction", "answer", END]:
        """Decide if we should retry SQL generation, request human help, or finish"""
        execution_error = state.get("execution_error", "")
        current_iteration = state.get("iteration", 0)
        max_iterations = state.get("max_iterations", 3)

        print(f"\n🔍 [RETRY CHECK] Iteration: {current_iteration}/{max_iterations}, Error: {bool(execution_error)}")

        # If execution failed and we haven't exceeded max iterations
        if execution_error and current_iteration < max_iterations:
            # If we're on the last iteration before max, request human help if enabled
            if self.enable_human_interaction and current_iteration == max_iterations - 1:
                print(f"   👤 Requesting human help after {current_iteration} failed attempts")
                # Mark state for human interaction
                state["awaiting_confirmation"] = True
                state["confirmation_type"] = "error"
                return "human_interaction"

            # If it's a "no such column" error, re-search columns
            if "no such column" in execution_error.lower():
                print(f"   🔄 Retrying with column re-search (Retry {current_iteration}/{max_iterations - 1})")
                return "search_columns"
            else:
                # For other errors, just regenerate SQL
                print(f"   🔄 Retrying SQL generation (Attempt {current_iteration + 1}/{max_iterations})")
                return "generate_sql"

        # If we have a result, generate answer
        if state.get("execution_result"):
            print(f"   ✅ Execution successful, generating answer")
            return "answer"

        # If we've exceeded max iterations, still generate an answer explaining the failure
        if execution_error:
            print(f"   ⚠️  Max iterations ({max_iterations}) reached. Generating error response.")
            return "answer"

        # Otherwise end
        print(f"   ℹ️  No error and no result, ending workflow")
        return END

    # ========================================================================
    # GRAPH CONSTRUCTION
    # ========================================================================

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph workflow with nodes and edges
        Includes human interaction checkpoints for true multi-turn interaction
        """
        # Initialize the graph with our state schema
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("planning", self.planning_node)
        workflow.add_node("human_interaction", self.human_interaction_node)
        workflow.add_node("search_columns", self.column_search_node)
        workflow.add_node("search_values", self.value_search_node)
        workflow.add_node("find_paths", self.path_finding_node)
        workflow.add_node("generate_sql", self.sql_generation_node)
        workflow.add_node("execute_sql", self.sql_execution_node)
        workflow.add_node("answer", self.answer_generation_node)

        # Set entry point
        workflow.set_entry_point("planning")

        # Add conditional edges (routing logic)
        # After planning, check if we need human confirmation
        workflow.add_conditional_edges(
            "planning",
            self.should_request_confirmation,
            {
                "human_interaction": "human_interaction",
                "check_column_search": "search_columns"  # Skip to column search if no confirmation needed
            }
        )

        # After human confirms plan, proceed to column search
        workflow.add_conditional_edges(
            "human_interaction",
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

        # After SQL generation, request human confirmation before execution
        workflow.add_conditional_edges(
            "generate_sql",
            self.should_confirm_sql,
            {
                "human_interaction": "human_interaction",
                "execute_sql": "execute_sql"
            }
        )

        workflow.add_conditional_edges(
            "execute_sql",
            self.should_retry_or_finish,
            {
                "search_columns": "search_columns",  # Re-search columns on column errors
                "generate_sql": "generate_sql",  # Retry SQL generation
                "human_interaction": "human_interaction",  # Request human help on errors
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
            "selected_path_indices": [],
            "path_selection_reasoning": "",
            "execution_result": None,
            "execution_error": "",
            "needs_column_search": False,
            "needs_value_search": False,
            "needs_path_finding": False,
            "needs_sql_generation": False,
            "ready_to_execute": False,
            "path_finding_deferred": False,
            "path_finding_failed": False,
            "path_finding_errors": [],
            "single_table_with_join_indicators": False,
            "needs_human_input": False,
            "human_feedback": "",
            "awaiting_confirmation": False,
            "confirmation_type": "",
            "final_answer": "",
            "messages": []
        }

        # Run the workflow with increased recursion limit
        # Each retry cycle goes through 4-5 nodes, so we need more than the default 25
        final_state = self.app.invoke(
            initial_state,
            config={"recursion_limit": 50}
        )

        print(f"{'='*80}")
        print(f"✅ WORKFLOW COMPLETED")
        print(f"{'='*80}\n")

        # Format response with detailed intermediate steps
        return {
            "question": question,
            "answer": final_state.get("final_answer", ""),
            "sql_queries": final_state.get("sql_queries", []),
            "final_sql": final_state.get("sql_query", ""),
            "execution_result": final_state.get("execution_result"),
            "plan": final_state.get("plan", ""),
            "relevant_columns": final_state.get("relevant_columns", []),
            "relevant_values": final_state.get("relevant_values", []),
            "join_paths": final_state.get("join_paths", []),
            "selected_path_indices": final_state.get("selected_path_indices", []),
            "path_selection_reasoning": final_state.get("path_selection_reasoning", ""),
            "intermediate_steps": [
                {
                    "step": msg.content,
                    "type": "ai"
                }
                for msg in final_state.get("messages", [])
            ]
        }
