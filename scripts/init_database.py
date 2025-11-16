"""
Initialize SQLite database with soccer data
Creates tables with schema based on the database_description CSV files
"""
import sqlite3
import csv
import os
from pathlib import Path

# Define the database path
DB_PATH = Path(__file__).parent.parent / "data" / "soccer.db"
DESC_PATH = Path(__file__).parent.parent / "database_description"

# Schema definitions based on the CSV descriptions
SCHEMAS = {
    "Country": """
        CREATE TABLE IF NOT EXISTS Country (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """,
    "League": """
        CREATE TABLE IF NOT EXISTS League (
            id INTEGER PRIMARY KEY,
            country_id INTEGER,
            name TEXT NOT NULL,
            FOREIGN KEY (country_id) REFERENCES Country(id)
        )
    """,
    "Team": """
        CREATE TABLE IF NOT EXISTS Team (
            id INTEGER PRIMARY KEY,
            team_api_id INTEGER,
            team_fifa_api_id INTEGER,
            team_long_name TEXT,
            team_short_name TEXT
        )
    """,
    "Player": """
        CREATE TABLE IF NOT EXISTS Player (
            id INTEGER PRIMARY KEY,
            player_api_id INTEGER,
            player_name TEXT,
            player_fifa_api_id INTEGER,
            birthday TEXT,
            height REAL,
            weight REAL
        )
    """,
    "Player_Attributes": """
        CREATE TABLE IF NOT EXISTS Player_Attributes (
            id INTEGER PRIMARY KEY,
            player_fifa_api_id INTEGER,
            player_api_id INTEGER,
            date TEXT,
            overall_rating INTEGER,
            potential INTEGER,
            preferred_foot TEXT,
            attacking_work_rate TEXT,
            defensive_work_rate TEXT,
            crossing INTEGER,
            finishing INTEGER,
            heading_accuracy INTEGER,
            short_passing INTEGER,
            volleys INTEGER,
            dribbling INTEGER,
            curve INTEGER,
            free_kick_accuracy INTEGER,
            long_passing INTEGER,
            ball_control INTEGER,
            acceleration INTEGER,
            sprint_speed INTEGER,
            agility INTEGER,
            reactions INTEGER,
            balance INTEGER,
            shot_power INTEGER,
            jumping INTEGER,
            stamina INTEGER,
            strength INTEGER,
            long_shots INTEGER,
            aggression INTEGER,
            interceptions INTEGER,
            positioning INTEGER,
            vision INTEGER,
            penalties INTEGER,
            marking INTEGER,
            standing_tackle INTEGER,
            sliding_tackle INTEGER,
            gk_diving INTEGER,
            gk_handling INTEGER,
            gk_kicking INTEGER,
            gk_positioning INTEGER,
            gk_reflexes INTEGER,
            FOREIGN KEY (player_api_id) REFERENCES Player(player_api_id)
        )
    """,
    "Team_Attributes": """
        CREATE TABLE IF NOT EXISTS Team_Attributes (
            id INTEGER PRIMARY KEY,
            team_fifa_api_id INTEGER,
            team_api_id INTEGER,
            date TEXT,
            buildUpPlaySpeed INTEGER,
            buildUpPlaySpeedClass TEXT,
            buildUpPlayDribbling INTEGER,
            buildUpPlayDribblingClass TEXT,
            buildUpPlayPassing INTEGER,
            buildUpPlayPassingClass TEXT,
            buildUpPlayPositioningClass TEXT,
            chanceCreationPassing INTEGER,
            chanceCreationPassingClass TEXT,
            chanceCreationCrossing INTEGER,
            chanceCreationCrossingClass TEXT,
            chanceCreationShooting INTEGER,
            chanceCreationShootingClass TEXT,
            chanceCreationPositioningClass TEXT,
            defencePressure INTEGER,
            defencePressureClass TEXT,
            defenceAggression INTEGER,
            defenceAggressionClass TEXT,
            defenceTeamWidth INTEGER,
            defenceTeamWidthClass TEXT,
            defenceDefenderLineClass TEXT,
            FOREIGN KEY (team_api_id) REFERENCES Team(team_api_id)
        )
    """,
    "Match": """
        CREATE TABLE IF NOT EXISTS Match (
            id INTEGER PRIMARY KEY,
            country_id INTEGER,
            league_id INTEGER,
            season TEXT,
            stage INTEGER,
            date TEXT,
            match_api_id INTEGER,
            home_team_api_id INTEGER,
            away_team_api_id INTEGER,
            home_team_goal INTEGER,
            away_team_goal INTEGER,
            home_player_X1 REAL,
            home_player_X2 REAL,
            home_player_X3 REAL,
            home_player_X4 REAL,
            home_player_X5 REAL,
            home_player_X6 REAL,
            home_player_X7 REAL,
            home_player_X8 REAL,
            home_player_X9 REAL,
            home_player_X10 REAL,
            home_player_X11 REAL,
            away_player_X1 REAL,
            away_player_X2 REAL,
            away_player_X3 REAL,
            away_player_X4 REAL,
            away_player_X5 REAL,
            away_player_X6 REAL,
            away_player_X7 REAL,
            away_player_X8 REAL,
            away_player_X9 REAL,
            away_player_X10 REAL,
            away_player_X11 REAL,
            home_player_Y1 REAL,
            home_player_Y2 REAL,
            home_player_Y3 REAL,
            home_player_Y4 REAL,
            home_player_Y5 REAL,
            home_player_Y6 REAL,
            home_player_Y7 REAL,
            home_player_Y8 REAL,
            home_player_Y9 REAL,
            home_player_Y10 REAL,
            home_player_Y11 REAL,
            away_player_Y1 REAL,
            away_player_Y2 REAL,
            away_player_Y3 REAL,
            away_player_Y4 REAL,
            away_player_Y5 REAL,
            away_player_Y6 REAL,
            away_player_Y7 REAL,
            away_player_Y8 REAL,
            away_player_Y9 REAL,
            away_player_Y10 REAL,
            away_player_Y11 REAL,
            home_player_1 INTEGER,
            home_player_2 INTEGER,
            home_player_3 INTEGER,
            home_player_4 INTEGER,
            home_player_5 INTEGER,
            home_player_6 INTEGER,
            home_player_7 INTEGER,
            home_player_8 INTEGER,
            home_player_9 INTEGER,
            home_player_10 INTEGER,
            home_player_11 INTEGER,
            away_player_1 INTEGER,
            away_player_2 INTEGER,
            away_player_3 INTEGER,
            away_player_4 INTEGER,
            away_player_5 INTEGER,
            away_player_6 INTEGER,
            away_player_7 INTEGER,
            away_player_8 INTEGER,
            away_player_9 INTEGER,
            away_player_10 INTEGER,
            away_player_11 INTEGER,
            goal TEXT,
            shoton TEXT,
            shotoff TEXT,
            foulcommit TEXT,
            card TEXT,
            cross TEXT,
            corner TEXT,
            possession TEXT,
            FOREIGN KEY (country_id) REFERENCES Country(id),
            FOREIGN KEY (league_id) REFERENCES League(id),
            FOREIGN KEY (home_team_api_id) REFERENCES Team(team_api_id),
            FOREIGN KEY (away_team_api_id) REFERENCES Team(team_api_id)
        )
    """
}

# Sample data for demonstration
SAMPLE_DATA = {
    "Country": [
        (1, "England"),
        (2, "Spain"),
        (3, "Germany"),
        (4, "Italy"),
        (5, "France")
    ],
    "League": [
        (1, 1, "Premier League"),
        (2, 2, "La Liga"),
        (3, 3, "Bundesliga"),
        (4, 4, "Serie A"),
        (5, 5, "Ligue 1")
    ],
    "Team": [
        (1, 8455, 673, "Manchester United", "Man United"),
        (2, 8650, 675, "Manchester City", "Man City"),
        (3, 8586, 681, "Arsenal", "Arsenal"),
        (4, 9825, 83, "Real Madrid", "Real Madrid"),
        (5, 8634, 81, "FC Barcelona", "Barcelona"),
        (6, 9789, 85, "Bayern Munich", "Bayern"),
        (7, 10260, 103, "Juventus", "Juve"),
        (8, 8528, 110, "Paris Saint-Germain", "PSG")
    ],
    "Player": [
        (1, 30572, "Cristiano Ronaldo", 20801, "1985-02-05", 185.0, 80.0),
        (2, 30981, "Lionel Messi", 158023, "1987-06-24", 170.0, 72.0),
        (3, 37412, "Neymar", 190871, "1992-02-05", 175.0, 68.0),
        (4, 38817, "Kevin De Bruyne", 192985, "1991-06-28", 181.0, 76.0),
        (5, 31921, "Robert Lewandowski", 188545, "1988-08-21", 185.0, 81.0),
        (6, 26112, "Manuel Neuer", 167495, "1986-03-27", 193.0, 92.0),
        (7, 20276, "Sergio Ramos", 155862, "1986-03-30", 184.0, 82.0),
        (8, 41412, "Kylian Mbappé", 231747, "1998-12-20", 178.0, 73.0),
        (9, 37399, "Mohamed Salah", 209331, "1992-06-15", 175.0, 71.0),
        (10, 26949, "Luis Suárez", 176580, "1987-01-24", 182.0, 86.0)
    ],
    "Player_Attributes": [
        # Cristiano Ronaldo - 42 values total
        (1, 20801, 30572, "2016-02-18", 94, 94, "right", "high", "low", 85, 95, 88, 83, 88, 91, 81, 77, 84, 89, 89, 92, 89, 96, 70, 95, 78, 92, 80, 93, 63, 33, 92, 85, 43, 28, 33, 90, 11, 15, 11, 14, 11),
        # Lionel Messi - 42 values total
        (2, 158023, 30981, "2016-02-18", 93, 93, "left", "medium", "medium", 77, 95, 71, 88, 86, 97, 93, 84, 92, 96, 91, 87, 96, 97, 95, 95, 68, 73, 59, 88, 48, 22, 95, 90, 75, 13, 26, 90, 6, 11, 15, 8, 8),
        # Neymar - 42 values total
        (3, 190871, 37412, "2016-02-18", 92, 92, "right", "high", "medium", 75, 89, 62, 81, 83, 96, 88, 62, 79, 94, 84, 90, 96, 92, 84, 80, 61, 78, 53, 78, 36, 25, 87, 80, 81, 33, 24, 85, 9, 11, 8, 15, 11),
        # Kevin De Bruyne - 42 values total
        (4, 192985, 38817, "2016-02-18", 88, 88, "right", "high", "medium", 93, 82, 71, 93, 83, 86, 85, 75, 93, 87, 78, 77, 91, 77, 68, 88, 73, 75, 86, 91, 76, 68, 87, 94, 79, 58, 66, 70, 15, 11, 12, 15, 11),
        # Robert Lewandowski - 42 values total
        (5, 188545, 31921, "2016-02-18", 89, 89, "right", "high", "medium", 62, 91, 85, 83, 87, 85, 78, 60, 83, 83, 79, 78, 60, 90, 78, 88, 82, 89, 83, 84, 80, 44, 91, 75, 85, 30, 45, 60, 11, 11, 11, 11, 11),
        # Manuel Neuer - 42 values total
        (6, 167495, 26112, "2016-02-18", 92, 92, "right", "medium", "medium", 15, 13, 10, 25, 11, 11, 12, 11, 25, 17, 58, 52, 11, 70, 25, 78, 73, 25, 58, 29, 11, 30, 10, 11, 11, 15, 30, 25, 91, 90, 95, 88, 89),
        # Sergio Ramos - 42 values total
        (7, 155862, 20276, "2016-02-18", 90, 90, "right", "medium", "high", 55, 60, 85, 71, 58, 63, 68, 51, 71, 64, 75, 67, 60, 83, 71, 75, 73, 86, 90, 86, 68, 92, 60, 70, 78, 90, 93, 65, 11, 11, 11, 11, 11),
        # Kylian Mbappé - 42 values total
        (8, 231747, 41412, "2018-02-18", 88, 95, "right", "high", "low", 76, 89, 64, 80, 81, 92, 81, 66, 78, 82, 96, 96, 92, 87, 95, 88, 76, 88, 78, 87, 52, 24, 90, 85, 72, 34, 27, 45, 11, 11, 11, 11, 11),
        # Mohamed Salah - 42 values total
        (9, 209331, 37399, "2018-02-18", 88, 89, "left", "high", "medium", 81, 87, 62, 84, 82, 90, 81, 68, 81, 79, 90, 94, 90, 83, 91, 87, 77, 86, 76, 83, 45, 32, 89, 87, 75, 45, 38, 50, 11, 11, 11, 11, 11),
        # Luis Suárez - 42 values total
        (10, 176580, 26949, "2016-02-18", 92, 92, "right", "high", "low", 77, 94, 77, 83, 88, 86, 81, 64, 83, 83, 77, 80, 60, 92, 80, 87, 80, 89, 87, 88, 84, 45, 92, 84, 86, 38, 45, 60, 11, 11, 11, 11, 11)
    ],
    "Team_Attributes": [
        (1, 673, 8455, "2016-02-18", 60, "Balanced", 50, "Normal", 50, "Mixed", "Organised", 60, "Normal", 60, "Normal", 55, "Normal", "Organised", 50, "Medium", 55, "Press", 50, "Normal", "Cover"),
        (2, 675, 8650, "2016-02-18", 70, "Fast", 70, "Lots", 70, "Short", "Organised", 70, "Risky", 65, "Normal", 65, "Normal", "Organised", 70, "High", 70, "Double", 45, "Narrow", "Cover"),
        (3, 681, 8586, "2016-02-18", 65, "Balanced", 60, "Normal", 65, "Short", "Organised", 65, "Normal", 60, "Normal", 60, "Normal", "Organised", 55, "Medium", 60, "Press", 55, "Normal", "Cover")
    ],
    "Match": []  # Simplified for demo - Match table has 85 columns which is complex for sample data
}


def create_database():
    """Create and populate the SQLite database"""
    print(f"Creating database at: {DB_PATH}")

    # Ensure data directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing database if it exists
    if DB_PATH.exists():
        os.remove(DB_PATH)
        print("Removed existing database")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables
    print("\nCreating tables...")
    for table_name, schema in SCHEMAS.items():
        print(f"  - Creating table: {table_name}")
        cursor.execute(schema)

    # Insert sample data
    print("\nInserting sample data...")
    for table_name, data in SAMPLE_DATA.items():
        if data:
            print(f"  - Inserting {len(data)} rows into {table_name}")
            placeholders = ','.join(['?' for _ in range(len(data[0]))])
            cursor.executemany(
                f"INSERT INTO {table_name} VALUES ({placeholders})",
                data
            )

    # Commit and close
    conn.commit()

    # Print statistics
    print("\nDatabase statistics:")
    for table_name in SCHEMAS.keys():
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"  - {table_name}: {count} rows")

    # Print column counts for wide tables
    print("\nWide table column counts:")
    cursor.execute("PRAGMA table_info(Player_Attributes)")
    player_attr_cols = cursor.fetchall()
    print(f"  - Player_Attributes: {len(player_attr_cols)} columns")

    cursor.execute("PRAGMA table_info(Match)")
    match_cols = cursor.fetchall()
    print(f"  - Match: {len(match_cols)} columns")

    conn.close()
    print(f"\n✓ Database created successfully at: {DB_PATH}")


if __name__ == "__main__":
    create_database()
