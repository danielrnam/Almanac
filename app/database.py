import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_FILE = "almanac.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. User Profile Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_profile (
        user_id TEXT PRIMARY KEY,
        location_name TEXT,
        latitude REAL,
        longitude REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Plants Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        name TEXT,
        maturity TEXT,
        health_state TEXT,
        photo_path TEXT,
        watering_guidelines TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        removed_at TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES user_profile(user_id)
    )
    """)
    
    # Check if watering_guidelines column exists, if not alter the table
    cursor.execute("PRAGMA table_info(plants)")
    cols = [row["name"] for row in cursor.fetchall()]
    if "watering_guidelines" not in cols:
        cursor.execute("ALTER TABLE plants ADD COLUMN watering_guidelines TEXT")
    
    # 3. Watering Plans Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS watering_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        start_date TEXT,
        schedule_data TEXT,  -- JSON string of the 7-day schedule
        reasoning_summary TEXT,
        FOREIGN KEY(user_id) REFERENCES user_profile(user_id)
    )
    """)
    
    conn.commit()
    conn.close()

# --- User Profile operations ---

def save_user_profile(user_id: str, location_name: str, latitude: float, longitude: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_profile (user_id, location_name, latitude, longitude)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        location_name = excluded.location_name,
        latitude = excluded.latitude,
        longitude = excluded.longitude
    """, (user_id, location_name, latitude, longitude))
    conn.commit()
    conn.close()

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

# --- Plants operations ---

def add_plant(user_id: str, name: str, maturity: str, health_state: str, photo_path: Optional[str] = None, watering_guidelines: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO plants (user_id, name, maturity, health_state, photo_path, watering_guidelines)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, name, maturity, health_state, photo_path, watering_guidelines))
    conn.commit()
    conn.close()

def remove_plant(user_id: str, plant_id: int):
    """Soft deletes a plant by setting removed_at to the current timestamp."""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute("""
    UPDATE plants 
    SET removed_at = ? 
    WHERE id = ? AND user_id = ?
    """, (now, plant_id, user_id))
    conn.commit()
    conn.close()

def get_active_plants(user_id: str) -> List[Dict[str, Any]]:
    """Gets all plants currently on the premises (where removed_at is NULL)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM plants 
    WHERE user_id = ? AND removed_at IS NULL
    ORDER BY added_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Watering Plans operations ---

def save_watering_plan(user_id: str, start_date: str, schedule_data: Dict[str, Any], reasoning_summary: str):
    conn = get_connection()
    cursor = conn.cursor()
    schedule_json = json.dumps(schedule_data)
    cursor.execute("""
    INSERT INTO watering_plans (user_id, start_date, schedule_data, reasoning_summary)
    VALUES (?, ?, ?, ?)
    """, (user_id, start_date, schedule_json, reasoning_summary))
    conn.commit()
    conn.close()

def get_watering_plans(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM watering_plans 
    WHERE user_id = ? 
    ORDER BY generated_at DESC 
    LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    plans = []
    for r in rows:
        plan_dict = dict(r)
        # Load the JSON schedule data back into a python dictionary
        try:
            plan_dict["schedule_data"] = json.loads(plan_dict["schedule_data"])
        except Exception:
            plan_dict["schedule_data"] = {}
        plans.append(plan_dict)
    return plans
