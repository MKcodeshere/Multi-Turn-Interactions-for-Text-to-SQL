"""
ExecuteSQL Tool - Execute SQL queries on the database
"""
from typing import List, Tuple
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class ExecuteSQLInput(BaseModel):
    """Input schema for ExecuteSQL tool"""
    sql: str = Field(description="SQL query to execute")


class ExecuteSQLTool(BaseTool):
    """
    Tool to execute SQL queries against the database.
    Returns query results as a list of tuples.
    """
    name: str = "ExecuteSQL"
    description: str = """
    Executes a SQL query on the database and returns the results.
    Input should be a valid SQL query string.
    Returns a list of tuples containing the query results.
    Use this tool to verify column contents, test queries, or retrieve final answers.

    Example: ExecuteSQL("SELECT name FROM Player LIMIT 5")
    """
    args_schema: type[BaseModel] = ExecuteSQLInput
    database: any = Field(default=None, exclude=True)

    def __init__(self, database, **kwargs):
        super().__init__(**kwargs)
        self.database = database

    def _run(self, sql: str) -> List[Tuple]:
        """Execute the SQL query"""
        try:
            results = self.database.execute_query(sql)
            # Limit results to prevent overwhelming output
            if len(results) > 100:
                return results[:100] + [("... (truncated)",)]
            return results
        except Exception as e:
            return [(f"Error: {str(e)}",)]

    async def _arun(self, sql: str):
        """Async version"""
        return self._run(sql)
