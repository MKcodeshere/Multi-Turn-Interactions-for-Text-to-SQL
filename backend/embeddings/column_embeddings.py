"""
Column embedding manager using text-embedding-3-large
"""
from typing import List, Dict, Any
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document
from backend.database import Database
from backend.config import EMBEDDING_MODEL, EMBEDDING_DIMENSION, COLUMN_DESCRIPTIONS, load_column_descriptions
import os


class ColumnEmbeddingManager:
    """Manage column embeddings for semantic search"""

    def __init__(self, db: Database):
        self.db = db
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSION if EMBEDDING_DIMENSION < 3072 else None
        )
        self.vector_store = None
        self.column_metadata = {}

        # Load column descriptions
        load_column_descriptions()

    def build_embeddings(self):
        """Build embeddings for all columns in the database"""
        all_columns = self.db.get_all_columns()
        documents = []

        for col_info in all_columns:
            table = col_info['table']
            column = col_info['column']
            col_type = col_info['type']

            # Get description from metadata if available
            desc = ""
            if table in COLUMN_DESCRIPTIONS and column in COLUMN_DESCRIPTIONS[table]:
                desc = COLUMN_DESCRIPTIONS[table][column].get('description', '')

            # Get statistics
            statistics = self.db.get_column_statistics(table, column)

            # Create semantic text for embedding
            semantic_text = f"a column named {column} in table {table}"
            if desc:
                semantic_text += f" about {desc}"

            # Store metadata
            metadata = {
                'table': table,
                'column': column,
                'type': col_type,
                'full_name': f"{table}.{column}",
                'description': desc,
                'statistics': statistics
            }

            # Create document
            doc = Document(
                page_content=semantic_text,
                metadata=metadata
            )
            documents.append(doc)

            # Store metadata for later retrieval
            self.column_metadata[f"{table}.{column}"] = metadata

        # Create vector store
        self.vector_store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name="column_embeddings"
        )

        return len(documents)

    def search_columns(self, semantic_query: str, k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for columns by semantic similarity

        Args:
            semantic_query: Natural language description of desired columns
            k: Number of results to return

        Returns:
            List of column information dictionaries with similarity scores
        """
        if not self.vector_store:
            self.build_embeddings()

        # Perform similarity search with scores
        results = self.vector_store.similarity_search_with_score(semantic_query, k=k)

        # Format results
        formatted_results = []
        for doc, score in results:
            formatted_results.append({
                'column_name': doc.metadata['column'],
                'table_name': doc.metadata['table'],
                'data_type': doc.metadata['type'],
                'description': doc.metadata['description'],
                'statistics': doc.metadata['statistics'],
                'similarity': float(1.0 / (1.0 + score))  # Convert distance to similarity (0-1 range)
            })

        return formatted_results

    def search_columns_batch(self, queries: List[str], k: int = 5) -> Dict[str, List[Dict]]:
        """
        Search for multiple column queries at once

        Args:
            queries: List of semantic queries
            k: Number of results per query

        Returns:
            Dictionary mapping queries to their results
        """
        results = {}
        for query in queries:
            results[query] = self.search_columns(query, k=k)
        return results
