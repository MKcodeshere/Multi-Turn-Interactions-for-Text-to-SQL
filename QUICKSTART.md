# Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env  # or use your preferred editor
```

**Required**: Set your `OPENAI_API_KEY` in the `.env` file:
```
OPENAI_API_KEY=sk-your-api-key-here
```

### 3. Initialize Database

```bash
python scripts/init_database.py
```

This creates a SQLite database with:
- **7 tables**: Country, League, Team, Player, Player_Attributes, Team_Attributes, Match
- **Wide tables**: Player_Attributes (42 columns), Match (85 columns)
- **Sample data**: 10 famous soccer players with detailed attributes
- **Complex relationships**: Multi-table foreign keys

### 4. Start the Server

```bash
cd backend
python main.py
```

The server will:
1. Load the database
2. Build embeddings for all 42 columns (using text-embedding-3-large)
3. Initialize the LangChain agent
4. Start the web server at `http://localhost:8000`

### 5. Open the Application

Visit: **http://localhost:8000**

You'll see an interactive chat interface where you can ask natural language questions about the soccer database!

---

## 📝 Example Queries to Try

### Simple Queries
```
"Which countries have leagues?"
"Show me all players"
"What are the team names?"
```

### Wide Table Queries (42 columns)
```
"Find players with overall rating above 85"
"Who has the highest dribbling skill?"
"Show players with good sprint speed and acceleration"
```

### Complex Join Queries
```
"Which players play in the Premier League?"
"Show all attributes for Lionel Messi"
"Find players from Barcelona with their attributes"
```

### Multi-Turn Interactions
```
User: "Who is the best finisher?"
System: [Returns player with highest finishing]
User: "Show me all their attributes"
System: [Uses context from previous query]
```

---

## 🔧 Architecture Overview

### Backend Stack
- **FastAPI**: REST API server
- **LangChain**: Agent orchestration
- **text-embedding-3-large**: Semantic column search
- **SQLite**: Database storage
- **ChromaDB**: Vector store for embeddings

### Interactive-T2S Framework (4 Tools)

1. **SearchColumn** (uses embeddings)
   - Finds relevant columns by semantic meaning
   - Handles wide tables efficiently (42+ columns)
   - Example: "player finishing skill" → `Player_Attributes.finishing`

2. **SearchValue** (uses fuzzy search)
   - Searches for cell values across the database
   - Example: "Barcelona" → finds in Team table

3. **FindShortestPath** (graph-based)
   - Automatically finds join paths between tables
   - Example: Player → Team → League → Country (4-table join)

4. **ExecuteSQL**
   - Executes generated SQL queries
   - Returns results to the user

### Agent Workflow (ReAct Pattern)

```
User Question
    ↓
LLM Agent Thinks: "I need to find columns for player attributes"
    ↓
Action: SearchColumn("player rating, dribbling")
    ↓
Observation: Returns relevant columns
    ↓
Action: ExecuteSQL("SELECT ... WHERE ...")
    ↓
Observation: Query results
    ↓
Final Answer: Formatted response to user
```

---

## 📊 Database Schema

### Tables
- **Country** (2 columns): id, name
- **League** (3 columns): id, country_id, name
- **Team** (5 columns): id, team_api_id, team_fifa_api_id, team_long_name, team_short_name
- **Player** (7 columns): id, player_api_id, player_name, player_fifa_api_id, birthday, height, weight
- **Player_Attributes** (42 columns): All FIFA player stats (overall_rating, finishing, dribbling, sprint_speed, etc.)
- **Team_Attributes** (25 columns): Team tactics and style attributes
- **Match** (85 columns): Match details, player positions, betting odds

### Sample Data
- 5 countries (England, Spain, Germany, Italy, France)
- 5 leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1)
- 8 teams (Manchester United, Barcelona, Bayern Munich, etc.)
- 10 players (Messi, Ronaldo, Neymar, etc.)
- 10 player attribute records (full FIFA stats)

---

## 🎯 Key Features Demonstrated

### 1. Wide Table Handling
**Challenge**: Player_Attributes has 42 columns
**Solution**: Use embeddings to semantically search for relevant columns instead of loading all 42

**Example**:
```
Query: "Find players with good dribbling"
Tool: SearchColumn("dribbling skill")
Result: Finds Player_Attributes.dribbling (column 14 out of 42)
```

### 2. Complex Joins
**Challenge**: Joining 4+ tables (Player → Team → League → Country)
**Solution**: Graph-based shortest path algorithm

**Example**:
```
Query: "Which players are from England?"
Tool: FindShortestPath("Player.id", "Country.name")
Path: Player → Team → League → Country
```

### 3. Multi-Turn Conversations
**Challenge**: Maintaining context across queries
**Solution**: LangChain conversation memory

**Example**:
```
Turn 1: "Who has the highest rating?"
Turn 2: "Show all their skills"  ← Knows "their" refers to previous answer
```

---

## 🐛 Troubleshooting

### Database not found
```bash
python scripts/init_database.py
```

### API Key error
- Check `.env` file has `OPENAI_API_KEY=sk-...`
- Ensure the key is valid

### Import errors
```bash
pip install -r requirements.txt
```

### Port already in use
Edit `.env` and change `PORT=8000` to another port

---

## 📚 Learn More

- **Paper**: [Multi-Turn Interactions for Text-to-SQL](https://arxiv.org/abs/2408.11062v2)
- **LangChain Docs**: https://python.langchain.com/docs/
- **API Docs**: http://localhost:8000/docs (when server is running)

---

## 🎉 You're Ready!

Your Interactive Text-to-SQL system is now running! Try asking complex questions and watch how the agent uses tools to build SQL queries step by step.
