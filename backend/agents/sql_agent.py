"""
SQL Agent using LangChain ReAct pattern for multi-turn text-to-SQL
Implements the Interactive-T2S framework from the paper
"""
from typing import List, Dict, Any
from langchain.agents import AgentExecutor, create_react_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from backend.config import LLM_MODEL, LLM_TEMPERATURE, MAX_INTERACTION_ROUNDS


class SQLAgent:
    """
    Interactive SQL generation agent using the ReAct pattern.
    Implements tools: SearchColumn, SearchValue, FindShortestPath, ExecuteSQL
    """

    def __init__(self, tools: List, database):
        self.tools = tools
        self.database = database
        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE
        )

        # Create the agent prompt based on the paper's framework
        self.prompt = self._create_prompt()

        # Create the agent
        self.agent = create_react_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )

        # Create executor with memory for multi-turn
        self.agent_executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            max_iterations=MAX_INTERACTION_ROUNDS,
            verbose=True,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

    def _create_prompt(self) -> PromptTemplate:
        """
        Create the agent prompt template following the Interactive-T2S framework.
        Based on Section 3.4 and 3.5 of the paper.
        """
        template = """You are an expert SQL query generator that interacts with a database to answer questions.

Database Schema:
{schema_summary}

You have access to the following tools:

{tools}

Tool Descriptions:
- SearchColumn: Find relevant columns by semantic meaning (handles wide tables efficiently)
- SearchValue: Search for specific cell values in the database
- FindShortestPath: Find the join path between tables/columns (handles complex joins)
- ExecuteSQL: Execute SQL queries to get results

General Process (from Interactive-T2S paper):
1. **Locate Elements**: Use SearchColumn to find relevant columns and SearchValue to find cell values
2. **Join Tables**: Use FindShortestPath to identify how to join multiple tables
3. **Execute SQL**: Use ExecuteSQL to run the query and get results

IMPORTANT Guidelines:
- Think step-by-step: decompose the question into sub-tasks
- For wide tables (50+ columns), use SearchColumn instead of guessing column names
- For complex joins (3+ tables), use FindShortestPath to find the correct join path
- Always verify your SQL with ExecuteSQL before providing the final answer
- Use the exact column names and table names returned by the tools
- The result from the FINAL ExecuteSQL call is your answer to the user

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought: {agent_scratchpad}"""

        return PromptTemplate(
            template=template,
            input_variables=["input", "agent_scratchpad", "schema_summary"],
            partial_variables={
                "tools": "\n".join([f"{tool.name}: {tool.description}" for tool in self.tools]),
                "tool_names": ", ".join([tool.name for tool in self.tools])
            }
        )

    def query(self, question: str) -> Dict[str, Any]:
        """
        Process a text-to-SQL query with multi-turn interaction

        Args:
            question: Natural language question

        Returns:
            Dictionary containing the SQL query, result, and interaction history
        """
        # Get schema summary
        schema_summary = self.database.get_schema_summary()

        # Run the agent
        response = self.agent_executor.invoke({
            "input": question,
            "schema_summary": schema_summary
        })

        # Extract SQL queries from intermediate steps
        sql_queries = []
        for step in response.get('intermediate_steps', []):
            action, observation = step
            if hasattr(action, 'tool') and action.tool == 'ExecuteSQL':
                sql_queries.append(action.tool_input)

        return {
            "question": question,
            "answer": response.get('output', ''),
            "sql_queries": sql_queries,
            "intermediate_steps": response.get('intermediate_steps', []),
            "final_sql": sql_queries[-1] if sql_queries else None
        }

    def create_conversation_agent(self):
        """
        Create an agent with conversation memory for multi-turn interactions
        """
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            memory=memory,
            max_iterations=MAX_INTERACTION_ROUNDS,
            verbose=True,
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

        return executor
