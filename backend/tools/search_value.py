"""
SearchValue Tool - Search for cell values in the database
"""
from typing import Optional, List, Dict, Union
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class SearchValueInput(BaseModel):
    """Input schema for SearchValue tool"""
    query: Union[str, List[str]] = Field(
        description="Value to search for in the database"
    )
    table: Optional[str] = Field(
        default=None,
        description="Optional: limit search to specific table"
    )
    column: Optional[str] = Field(
        default=None,
        description="Optional: limit search to specific column"
    )
    limit: int = Field(default=5, description="Maximum number of results")


class SearchValueTool(BaseTool):
    """
    Tool to search for cell values across the database.
    Useful for finding exact or similar values when generating SQL queries.
    """
    name: str = "SearchValue"
    description: str = """
    Searches for values in the database using fuzzy matching.
    Input can be a string or list of strings to search for.
    Optionally specify table and/or column to narrow the search.
    Returns matching values with their table and column locations.

    Example: SearchValue("Barcelona") finds cells containing "Barcelona".
    Example: SearchValue("Messi", table="Player") searches only in Player table.
    """
    args_schema: type[BaseModel] = SearchValueInput
    database: any = Field(default=None, exclude=True)

    def __init__(self, database, **kwargs):
        super().__init__(**kwargs)
        self.database = database

    def _run(
        self,
        query: Union[str, List[str]],
        table: Optional[str] = None,
        column: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """Execute the search"""
        if isinstance(query, list):
            all_results = []
            for q in query:
                results = self.database.search_values(q, table, column, limit)
                all_results.extend(results)
            return all_results[:limit]
        else:
            return self.database.search_values(query, table, column, limit)

    async def _arun(
        self,
        query: Union[str, List[str]],
        table: Optional[str] = None,
        column: Optional[str] = None,
        limit: int = 5
    ):
        """Async version"""
        return self._run(query, table, column, limit)
