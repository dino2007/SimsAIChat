# Server/database.py

import sqlite3
import json
import datetime

DB_FILE = "memory.db"

def init_db():
    """Initializes the database tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Chat Logs (Short Term / Debug)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sim_name TEXT NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 2. Location Context (Persistent Descriptions)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS location_context (
            zone_id INTEGER PRIMARY KEY,
            description TEXT
        )
    ''')

    # 3. Event-Based Long Term Memory
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS event_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_ids TEXT,    -- JSON List of IDs
            summary TEXT,            -- The AI generated summary
            participants_names TEXT, -- Readable names for debugging
            location TEXT,           
            time_context TEXT,       
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Server: Database initialized.")

# --- CHAT LOGGING ---
def add_message(sim_name, role, message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversation_history (sim_name, role, message) VALUES (?, ?, ?)', 
                   (sim_name, role, message))
    conn.commit()
    conn.close()

# --- LOCATION ---
def set_location_description(zone_id, description):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO location_context (zone_id, description) 
        VALUES (?, ?) 
        ON CONFLICT(zone_id) DO UPDATE SET description=excluded.description
    ''', (zone_id, description))
    conn.commit()
    conn.close()

def get_location_description(zone_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT description FROM location_context WHERE zone_id = ?', (zone_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- EVENT MEMORY MANAGEMENT ---

def save_event_memory(participant_ids_list, summary, names_str, location, time_context):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    ids_json = json.dumps(participant_ids_list)
    cursor.execute('''
        INSERT INTO event_memories 
        (participant_ids, summary, participants_names, location, time_context)
        VALUES (?, ?, ?, ?, ?)
    ''', (ids_json, summary, names_str, location, time_context))
    conn.commit()
    conn.close()
    print(f"DB: Event Memory saved for group: {names_str}")

def fetch_relevant_memories(current_sim_ids, limit=50):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT participant_ids, time_context, location, summary, participants_names
        FROM event_memories 
        ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    relevant_memories = []
    current_set = set(current_sim_ids)
    
    for row in rows:
        stored_ids_json, time_str, loc, text, names = row
        try:
            stored_ids = set(json.loads(stored_ids_json))
            overlap = stored_ids.intersection(current_set)
            if len(overlap) >= 2:
                relevant_memories.append(f"- [{time_str} at {loc}]: {text} (Participants: {names})")
                if len(relevant_memories) >= 5:
                    break
        except:
            continue
            
    if not relevant_memories:
        return "No relevant shared history found."
        
    return "\n".join(relevant_memories[::-1])

# --- NEW: MAINTENANCE ---
def purge_history():
    """Wipes conversation logs and event memories. Keeps Location data."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM conversation_history')
        cursor.execute('DELETE FROM event_memories')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="conversation_history"')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="event_memories"')
        conn.commit()
        print("DB: History and Memories purged.")
        return True
    except Exception as e:
        print(f"DB Error purging history: {e}")
        return False
    finally:
        conn.close()