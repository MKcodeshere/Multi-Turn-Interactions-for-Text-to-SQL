"""
SearchColumn Tool - Find relevant columns using embeddings
"""
from typing import Dict, List, Union, Any
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class SearchColumnInput(BaseModel):
    """Input schema for SearchColumn tool"""
    query: Union[str, List[str]] = Field(
        description="Semantic description of desired columns (e.g., 'player name', 'goal scored')"
    )
    k: int = Field(default=10, description="Number of columns to return")


class SearchColumnTool(BaseTool):
    """
    Tool to search for columns in the database based on semantic similarity.
    Uses text-embedding-3-large to find relevant columns.
    """
    name: str = "SearchColumn"
    description: str = """
    Searches for columns in the database based on semantic meaning.
    Input should be a string or list of strings describing what columns you need.
    Returns column names, table names, types, descriptions, and statistics.

    Example: SearchColumn("player name") returns columns related to player names.
    Example: SearchColumn(["goal scored", "team name"]) returns columns for both queries.
    """
    args_schema: type[BaseModel] = SearchColumnInput
    embedding_manager: Any = Field(default=None, exclude=True)

    def __init__(self, embedding_manager, **kwargs):
        super().__init__(**kwargs)
        self.embedding_manager = embedding_manager

    def _run(self, query: Union[str, List[str]], k: int = 10) -> Dict[str, List[Dict]]:
        """Execute the search"""
        if isinstance(query, str):
            results = self.embedding_manager.search_columns(query, k=k)
            return {query: results}
        else:
            return self.embedding_manager.search_columns_batch(query, k=k)

    async def _arun(self, query: Union[str, List[str]], k: int = 10):
        """Async version"""
        return self._run(query, k)
