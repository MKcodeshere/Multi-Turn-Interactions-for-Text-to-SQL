"""
FindShortestPath Tool - Find join paths between columns
"""
from typing import List, Union
from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class FindShortestPathInput(BaseModel):
    """Input schema for FindShortestPath tool"""
    start: Union[str, List[str]] = Field(
        description="Starting column(s) in format 'table.column'"
    )
    end: Union[str, List[str]] = Field(
        description="Ending column(s) in format 'table.column'"
    )


class FindShortestPathTool(BaseTool):
    """
    Tool to find the shortest join path between columns in the database schema.
    Treats the schema as a graph where columns are nodes and foreign keys are edges.
    """
    name: str = "FindShortestPath"
    description: str = """
    Finds the shortest path for joining tables between specified columns.
    Input should be start and end columns in 'table.column' format.
    Can accept single columns or lists of columns.
    Returns the join path that can be used in SQL queries.

    Example: FindShortestPath(start="Player.player_name", end="Match.date")
    Example: FindShortestPath(start=["Player.player_name", "Team.team_name"], end="Match.date")
    """
    args_schema: type[BaseModel] = FindShortestPathInput
    database: any = Field(default=None, exclude=True)

    def __init__(self, database, **kwargs):
        super().__init__(**kwargs)
        self.database = database

    def _format_path(self, path: List[str]) -> str:
        """Format a path for display"""
        if not path:
            return "No path found"
        return " <-> ".join(path)

    def _run(
        self,
        start: Union[str, List[str]],
        end: Union[str, List[str]]
    ) -> Union[str, List[tuple]]:
        """Execute the path finding"""
        start_cols = [start] if isinstance(start, str) else start
        end_cols = [end] if isinstance(end, str) else end

        results = []

        for start_col in start_cols:
            for end_col in end_cols:
                path = self.database.find_shortest_path(start_col, end_col)
                formatted_path = self._format_path(path)
                results.append((start_col, end_col, formatted_path))

        # If only one path, return the formatted string
        if len(results) == 1:
            return results[0][2]

        return results

    async def _arun(
        self,
        start: Union[str, List[str]],
        end: Union[str, List[str]]
    ):
        """Async version"""
        return self._run(start, end)
