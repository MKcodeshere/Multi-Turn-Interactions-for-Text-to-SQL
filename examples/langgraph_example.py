"""
Example usage of the LangGraph-based SQL Agent workflow

This script demonstrates how to use the LangGraph workflow directly
without going through the FastAPI server.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import Database
from backend.embeddings import ColumnEmbeddingManager
from backend.tools import SearchColumnTool, SearchValueTool, FindShortestPathTool, ExecuteSQLTool
from backend.agents import SQLAgentWorkflow


def main():
    print("=" * 80)
    print("LangGraph SQL Agent Workflow Example")
    print("=" * 80)

    # Initialize database
    print("\n1. Initializing database...")
    db = Database()
    print(f"   ✓ Connected to: {db.db_path}")
    print(f"   ✓ Tables: {', '.join(db.get_tables()[:5])}...")

    # Initialize embedding manager
    print("\n2. Building column embeddings...")
    embedding_manager = ColumnEmbeddingManager(db)
    num_columns = embedding_manager.build_embeddings()
    print(f"   ✓ Embedded {num_columns} columns")

    # Initialize tools
    print("\n3. Initializing tools...")
    tools = [
        SearchColumnTool(embedding_manager=embedding_manager),
        SearchValueTool(database=db),
        FindShortestPathTool(database=db),
        ExecuteSQLTool(database=db)
    ]
    print(f"   ✓ {len(tools)} tools ready: {', '.join([t.name for t in tools])}")

    # Initialize LangGraph workflow
    print("\n4. Building LangGraph workflow...")
    workflow = SQLAgentWorkflow(tools=tools, database=db)
    print("   ✓ Workflow compiled with nodes and edges")

    # Example queries
    questions = [
        "Which player scored the most goals?",
        "List the top 3 teams with the highest average attendance",
        "Find all matches played in 2020 where the home team scored more than 3 goals"
    ]

    print("\n" + "=" * 80)
    print("Running Example Queries")
    print("=" * 80)

    for i, question in enumerate(questions, 1):
        print(f"\n{'─' * 80}")
        print(f"Query {i}: {question}")
        print('─' * 80)

        try:
            # Execute the workflow
            result = workflow.query(question, max_iterations=3)

            # Display results
            print(f"\n📝 Plan: {result.get('plan', 'N/A')}")

            print(f"\n🔍 Intermediate Steps:")
            for j, step in enumerate(result.get('intermediate_steps', []), 1):
                print(f"   {j}. {step.get('step', 'N/A')}")

            print(f"\n💾 SQL Query:")
            print(f"   {result.get('final_sql', 'N/A')}")

            print(f"\n✅ Answer:")
            print(f"   {result.get('answer', 'N/A')}")

            if result.get('execution_result'):
                print(f"\n📊 Raw Result (first 5 rows):")
                exec_result = result['execution_result']
                if isinstance(exec_result, list):
                    for row in exec_result[:5]:
                        print(f"   {row}")
                else:
                    print(f"   {exec_result}")

        except Exception as e:
            print(f"\n❌ Error: {str(e)}")

    print("\n" + "=" * 80)
    print("Example completed!")
    print("=" * 80)


def visualize_workflow():
    """
    Visualize the LangGraph workflow structure
    """
    print("\n" + "=" * 80)
    print("Workflow Visualization")
    print("=" * 80)

    # Initialize minimal setup for visualization
    from backend.database import Database
    from backend.tools import SearchColumnTool, SearchValueTool, FindShortestPathTool, ExecuteSQLTool

    db = Database()

    # Create dummy tools (no embedding needed for structure visualization)
    tools = [
        SearchColumnTool(embedding_manager=None),
        SearchValueTool(database=db),
        FindShortestPathTool(database=db),
        ExecuteSQLTool(database=db)
    ]

    workflow = SQLAgentWorkflow(tools=tools, database=db)

    # Print ASCII representation
    print("\nWorkflow Graph (ASCII):")
    print("─" * 80)
    try:
        workflow.app.get_graph().print_ascii()
    except Exception as e:
        print(f"Could not print ASCII graph: {e}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LangGraph SQL Agent Example")
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Visualize the workflow graph structure"
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Run a custom query"
    )

    args = parser.parse_args()

    if args.visualize:
        visualize_workflow()
    elif args.query:
        # Run custom query
        db = Database()
        embedding_manager = ColumnEmbeddingManager(db)
        embedding_manager.build_embeddings()

        tools = [
            SearchColumnTool(embedding_manager=embedding_manager),
            SearchValueTool(database=db),
            FindShortestPathTool(database=db),
            ExecuteSQLTool(database=db)
        ]

        workflow = SQLAgentWorkflow(tools=tools, database=db)
        result = workflow.query(args.query)

        print("\n" + "=" * 80)
        print(f"Query: {args.query}")
        print("=" * 80)
        print(f"\n💾 SQL: {result.get('final_sql')}")
        print(f"\n✅ Answer: {result.get('answer')}")
        print("\n" + "=" * 80)
    else:
        main()
