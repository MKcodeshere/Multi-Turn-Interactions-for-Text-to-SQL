"""
Database connection and utilities
"""
import sqlite3
from typing import List, Dict, Any, Tuple
from pathlib import Path
import networkx as nx
from backend.config import DATABASE_PATH


class Database:
    """Database connection and query manager"""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._schema_graph = None

    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def execute_query(self, sql: str, params: tuple = ()) -> List[Tuple]:
        """Execute a SQL query and return results"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            results = cursor.fetchall()
            return results
        except Exception as e:
            raise Exception(f"SQL execution error: {str(e)}")
        finally:
            conn.close()

    def get_tables(self) -> List[str]:
        """Get list of all tables in the database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables

    def get_columns(self, table: str) -> List[Dict[str, Any]]:
        """Get columns for a specific table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table})")
        columns = []
        for row in cursor.fetchall():
            columns.append({
                'name': row[1],
                'type': row[2],
                'notnull': row[3],
                'default_value': row[4],
                'pk': row[5]
            })
        conn.close()
        return columns

    def get_all_columns(self) -> List[Dict[str, str]]:
        """Get all columns from all tables"""
        all_columns = []
        for table in self.get_tables():
            columns = self.get_columns(table)
            for col in columns:
                all_columns.append({
                    'table': table,
                    'column': col['name'],
                    'type': col['type'],
                    'full_name': f"{table}.{col['name']}"
                })
        return all_columns

    def get_foreign_keys(self, table: str) -> List[Dict[str, str]]:
        """Get foreign key relationships for a table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fks = []
        for row in cursor.fetchall():
            fks.append({
                'from_table': table,
                'from_column': row[3],
                'to_table': row[2],
                'to_column': row[4]
            })
        conn.close()
        return fks

    def get_all_foreign_keys(self) -> List[Dict[str, str]]:
        """Get all foreign key relationships"""
        all_fks = []
        for table in self.get_tables():
            all_fks.extend(self.get_foreign_keys(table))
        return all_fks

    def build_schema_graph(self) -> nx.Graph:
        """Build a graph representation of the database schema"""
        if self._schema_graph is not None:
            return self._schema_graph

        G = nx.Graph()

        # Add all columns as nodes
        for col_info in self.get_all_columns():
            node_name = f"{col_info['table']}.{col_info['column']}"
            G.add_node(node_name, **col_info)

        # Add edges for columns in the same table
        for table in self.get_tables():
            columns = self.get_columns(table)
            col_names = [f"{table}.{col['name']}" for col in columns]
            for i, col1 in enumerate(col_names):
                for col2 in col_names[i+1:]:
                    G.add_edge(col1, col2, relation='same_table')

        # Add edges for foreign key relationships
        for fk in self.get_all_foreign_keys():
            from_node = f"{fk['from_table']}.{fk['from_column']}"
            to_node = f"{fk['to_table']}.{fk['to_column']}"
            G.add_edge(from_node, to_node, relation='foreign_key')

        self._schema_graph = G
        return G

    def find_shortest_path(self, start: str, end: str) -> List[str]:
        """Find shortest path between two columns"""
        G = self.build_schema_graph()
        try:
            path = nx.shortest_path(G, start, end)
            return path
        except nx.NetworkXNoPath:
            return []

    def get_column_statistics(self, table: str, column: str) -> str:
        """Get statistics for a column"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get column type
        cursor.execute(f"PRAGMA table_info({table})")
        col_info = [row for row in cursor.fetchall() if row[1] == column]
        if not col_info:
            conn.close()
            return "Column not found"

        col_type = col_info[0][2].upper()

        try:
            # For text columns, get sample values
            if 'TEXT' in col_type or 'VARCHAR' in col_type or 'CHAR' in col_type:
                cursor.execute(f"""
                    SELECT DISTINCT {column}
                    FROM {table}
                    WHERE {column} IS NOT NULL
                    LIMIT 5
                """)
                samples = [row[0] for row in cursor.fetchall()]
                if samples:
                    return f"text field. e.g. {', '.join(str(s)[:50] for s in samples)}"
                else:
                    return "text field (no data)"

            # For numeric columns, get min/max
            elif 'INT' in col_type or 'REAL' in col_type or 'NUMERIC' in col_type:
                cursor.execute(f"""
                    SELECT MIN({column}), MAX({column}), COUNT(DISTINCT {column})
                    FROM {table}
                    WHERE {column} IS NOT NULL
                """)
                min_val, max_val, distinct = cursor.fetchone()
                if min_val is not None:
                    return f"numeric field. range: {min_val} to {max_val}, distinct count: {distinct}"
                else:
                    return "numeric field (no data)"

            else:
                cursor.execute(f"SELECT COUNT(DISTINCT {column}) FROM {table}")
                distinct = cursor.fetchone()[0]
                return f"distinct count: {distinct}"

        except Exception as e:
            return f"Error getting statistics: {str(e)}"
        finally:
            conn.close()

    def search_values(self, query: str, table: str = None, column: str = None, limit: int = 5) -> List[Dict]:
        """Search for values in the database (simple implementation without Elasticsearch)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        results = []

        tables_to_search = [table] if table else self.get_tables()

        for tbl in tables_to_search:
            columns = self.get_columns(tbl)
            columns_to_search = [column] if column else [c['name'] for c in columns]

            for col in columns_to_search:
                # Only search text columns
                col_info = [c for c in columns if c['name'] == col]
                if not col_info:
                    continue

                col_type = col_info[0]['type'].upper()
                if 'TEXT' not in col_type and 'VARCHAR' not in col_type and 'CHAR' not in col_type:
                    continue

                try:
                    cursor.execute(f"""
                        SELECT DISTINCT {col}
                        FROM {tbl}
                        WHERE {col} LIKE ? AND {col} IS NOT NULL
                        LIMIT {limit}
                    """, (f"%{query}%",))

                    for row in cursor.fetchall():
                        results.append({
                            'contents': row[0],
                            'table': tbl,
                            'column': col
                        })

                    if len(results) >= limit:
                        break
                except Exception:
                    continue

            if len(results) >= limit:
                break

        conn.close()
        return results[:limit]

    def get_schema_summary(self) -> str:
        """Get a summary of the database schema"""
        tables = self.get_tables()
        fks = self.get_all_foreign_keys()

        summary = "Database Schema:\n"
        summary += f"Tables: {', '.join(tables)}\n\n"
        summary += "Foreign Keys:\n"
        for fk in fks:
            summary += f"  {fk['from_table']}.{fk['from_column']} -> {fk['to_table']}.{fk['to_column']}\n"

        return summary
