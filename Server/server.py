# ==============================================================================
# SimsAIChat
# Copyright (C) 2026 dino2007
#
# This software is provided for personal use only.
# Unauthorized redistribution or commercial use is strictly prohibited.
#
# Official Source: https://github.com/dino2007/SimsAIChat
# ==============================================================================

from flask import Flask, request, jsonify, render_template
import threading
import sys
import json
import os
import time
from Server import database
from Server.world_data import WORLD_DESCRIPTIONS, NEIGHBORHOOD_DESCRIPTIONS
from Server.llm_wrapper import LLMClient

# --- PATH HELPERS ---
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_writable_path(filename):
    """ Get path for files that need to be edited (DB, Config) """
    if getattr(sys, 'frozen', False):
        # If running as EXE, use the folder where the EXE is located
        base_path = os.path.dirname(sys.executable)
    else:
        # If running as script, use the Server folder
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, filename)

# --- FLASK SETUP ---
# Explicitly tell Flask where templates are using the resource path
template_dir = get_resource_path('templates')
app = Flask(__name__, template_folder=template_dir)

# --- CONFIGURATION MANAGEMENT ---
# Use writable path for config and db
CONFIG_FILE = get_writable_path("config.json")
database.DB_FILE = get_writable_path("memory.db") # Patch the DB path dynamically

DEFAULT_CONFIG = {
    "provider": "Gemini",
    "api_key": "",
    "model": "gemini-2.5-flash",
    "temperature": 0.8,
    "language": "English"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config_to_disk(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=4)

# Initialize
database.init_db()
app_config = load_config()
ai_client = LLMClient(app_config)

CURRENT_SESSION = {
    "status": "INACTIVE",
    "context": {},
    "history": [],
    "game_command": "WAIT",
    "shared_memories": "",
    "environment": {}
}

AWAITING_CONTEXT_UPDATE = False
LAST_HEARTBEAT = 0
HAS_CONNECTED = False

# --- HELPER: FORMAT SIM DATA ---
def format_sim_profile(sim_data):
    traits = ", ".join(sim_data.get("traits", []))
    gender = ", ".join(sim_data.get("gender_options", []))
    prefs = ", ".join(sim_data.get("preferences", []))
    
    # Format Peer Relations
    cast_rels = sim_data.get("relationship_with_cast", [])
    cast_rels_str = "None significant"
    if cast_rels:
        entries = [f"{r['name']} (Fr:{r['friend']}, Rom:{r['romance']})" for r in cast_rels]
        cast_rels_str = ", ".join(entries)

    return {
        "traits_str": traits,
        "gender_str": gender,
        "residence": sim_data.get("residence", "Unknown"),
        "prefs_str": prefs,
        "career": sim_data.get("career", "Unemployed"),
        "skills": sim_data.get("skills", "None"),
        "social_status": sim_data.get("social_status", "Unknown"),
        "mood": sim_data.get("mood_id", "Fine"),
        "moodlets_desc": sim_data.get("active_moodlets", "None"),
        "activity_desc": sim_data.get("active_activity", "Idle"),
        "friendship": sim_data.get("relationship_with_player", {}).get("friendship", 0),
        "romance": sim_data.get("relationship_with_player", {}).get("romance", 0),
        "cast_relations": cast_rels_str 
    }

# --- HELPER: SUMMARIZER ---
def generate_summary(history_list, participants_names):
    if not ai_client.is_ready or not history_list: return "Conversation happened."
    
    log_text = ""
    for role, msg in history_list:
        log_text += f"{role}: {msg}\n"
    
    prompt = (
        f"Summarize the following conversation.\nParticipants: {participants_names}\n"
        f"TRANSCRIPT:\n{log_text}\n"
        f"INSTRUCTIONS: Write a 2-3 sentence summary noting key topics, emotional shifts, and interpersonal dynamics.\nSUMMARY:"
    )
    return ai_client.generate(prompt, "")

# --- ROUTES: SETTINGS & DATA ---

@app.route('/settings/get', methods=['GET'])
def get_settings():
    return jsonify(app_config)

@app.route('/settings/save', methods=['POST'])
def save_settings():
    global app_config, ai_client
    new_data = request.json
    
    # Update global config
    app_config.update(new_data)
    save_config_to_disk(app_config)
    
    # Reload AI
    print("Server: Reloading AI Client with new settings...")
    ai_client = LLMClient(app_config)
    
    status = "OK" if ai_client.is_ready else "Config Saved (Key Missing?)"
    return jsonify({"status": status})

@app.route('/data/purge', methods=['POST'])
def purge_data():
    success = database.purge_history()
    CURRENT_SESSION["history"] = []
    return jsonify({"status": "cleared" if success else "error"})

# --- ROUTES: CORE ---

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/location/get', methods=['POST'])
def get_location():
    zone_id = request.json.get("zone_id")
    desc = database.get_location_description(zone_id)
    return jsonify({"description": desc if desc else ""})

@app.route('/location/update', methods=['POST'])
def update_location():
    zone_id = request.json.get("zone_id")
    description = request.json.get("description")
    database.set_location_description(zone_id, description)
    return jsonify({"status": "ok"})

@app.route('/game/init', methods=['POST'])
def game_init_chat():
    data = request.json
    CURRENT_SESSION["status"] = "ACTIVE"
    CURRENT_SESSION["history"] = [] 
    CURRENT_SESSION["game_command"] = "WAIT"
    
    # 1. Environment Setup
    loc_data = data.get("location", {})
    zone_id = loc_data.get("zone_id")
    neighborhood_id = loc_data.get("neighborhood_id")
    world_id = loc_data.get("world_id")
    
    lot_desc = database.get_location_description(zone_id) or "A building."
    neighborhood_desc = NEIGHBORHOOD_DESCRIPTIONS.get(neighborhood_id)
    world_desc = WORLD_DESCRIPTIONS.get(world_id, "The Sims World")

    if neighborhood_desc: environment_context = f"{neighborhood_desc} inside {world_desc}"
    else: environment_context = world_desc

    CURRENT_SESSION["environment"] = {
        "lot": lot_desc,
        "world_context": environment_context,
        "lot_name": loc_data.get("lot_name", "Current Lot")
    }

    # 2. Memory Retrieval
    player_id = data.get("player_sim", {}).get("sim_id")
    mode = data.get("mode", "SINGLE")
    
    current_ids = [player_id]
    if mode == "GROUP":
        for sim in data.get("participants", []):
            current_ids.append(sim.get("sim_id"))
    else:
        if "sim_id" in data:
            current_ids.append(data.get("sim_id"))
    
    memories_text = database.fetch_relevant_memories(current_ids)
    CURRENT_SESSION["shared_memories"] = memories_text

    CURRENT_SESSION["context"] = data
    return jsonify({"status": "ok"})

@app.route('/game/update', methods=['POST'])
def game_update_context():
    global AWAITING_CONTEXT_UPDATE
    data = request.json
    print("Server: Received Fresh Context from Game.")
    
    ctx = CURRENT_SESSION["context"]
    ctx["time_context"] = data.get("time_context")
    ctx["location"] = data.get("location")
    
    updated_participants = data.get("participants", [])
    if ctx["mode"] == "GROUP":
        ctx["participants"] = updated_participants
    else:
        if updated_participants:
            ctx.update(updated_participants[0])

    loc_data = ctx["location"]
    zone_id = loc_data.get("zone_id")
    lot_desc = database.get_location_description(zone_id) or "A building."
    CURRENT_SESSION["environment"]["lot"] = lot_desc
    CURRENT_SESSION["environment"]["lot_name"] = loc_data.get("lot_name")

    CURRENT_SESSION["game_command"] = "WAIT"
    AWAITING_CONTEXT_UPDATE = False
    return jsonify({"status": "updated"})

@app.route('/app/send', methods=['POST'])
def app_send_message():
    global AWAITING_CONTEXT_UPDATE
    
    user_text = request.json.get("text", "")
    context = CURRENT_SESSION["context"]
    mode = context.get("mode", "SINGLE")
    
    is_passive = False
    if user_text.strip() == "[CONTINUE]":
        is_passive = True
        user_text = "(Player listens and waits for the others to continue...)"
    
    if not is_passive:
        database.add_message("Player", "Player", user_text)
        CURRENT_SESSION["history"].append(("Player", user_text))
    else:
        CURRENT_SESSION["history"].append(("System", "Player listens silently."))

    if not ai_client.is_ready:
        return jsonify({"reply": "[System]: AI Config missing. Check Settings."})

    # --- REQUEST UPDATE FROM GAME ---
    print("Server: Requesting context update from Game...")
    CURRENT_SESSION["game_command"] = "SCRAPE"
    AWAITING_CONTEXT_UPDATE = True
    
    timeout = 40 
    while AWAITING_CONTEXT_UPDATE and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
        
    if timeout <= 0:
        CURRENT_SESSION["game_command"] = "WAIT"

    # --- GENERATE RESPONSE ---
    history_text = ""
    for role, msg in CURRENT_SESSION["history"]:
        history_text += f"{role}: {msg}\n"

    env = CURRENT_SESSION.get("environment", {})
    player = context.get("player_sim", {})
    p_name = player.get("name", "Player")
    p_age = player.get("age", "Sim")
    p_gender = player.get("gender", "Unknown")
    time_str = context.get("time_context", "Unknown Time")
    
    lot_name = env.get("lot_name", "Lot")
    lot_desc = env.get("lot", "Unknown Lot")
    world_context = env.get("world_context", "Sims World")
    
    # Retrieve Global Memories
    shared_memories = CURRENT_SESSION.get("shared_memories", "No relevant history.")

    system_prompt = ""

    if mode == "GROUP":
        participants = context.get("participants", [])
    
        # 1. GLOBAL RULES (Applied to all Sims)
        system_prompt = (
            f"SYSTEM: You are the Scriptwriter for a scene in The Sims 4. You control the dialogue for the CAST members listed below.\n\n"
            
            f"[1. DATA PROCESSING PROTOCOL (APPLY TO EACH SIM)]\n"
            f"* FILTER NOISE (CRITICAL): In 'Current Activity', IGNORE lines starting with 'Can unlock,' 'Not allowed to,' 'Will not,' 'Able to,' or 'Has the [X] trait.'\n"
            f"* EXPAND GENERIC ACTIVITIES: If Activity lists a generic action (e.g., 'Posting on social media'), invent specific content.\n"
            f"* CONFLICT INTEGRATION (THE HUMAN PARADOX): If 'Current Activity' contradicts Mood/Traits, roleplay the friction. (e.g. Stressed Mood + Fun Motive = Manic coping).\n\n"

            f"[2. REALITY HIERARCHY]\n"
            f"* TIER 1 (HARD FACT): Never contradict Identity, Career, Relationships, Skills, or Location.\n"
            f"* TIER 2 (SHARED HISTORY): Prioritize Memory over generic responses.\n"
            f"* TIER 3 (CREATIVE INVENTION): The game provides the Abstract Effect. You invent the Concrete Cause. Mention the cause ONCE, then move on.\n\n"

            f"[3. VOICE & AUTONOMY (THE BLENDED RELATIONSHIP MODEL)]\n"
            f"* Apply these rules based on each Sim's relationship with the Player/Speaker:\n"
            f"* STEP 1: ESTABLISH FRIENDSHIP BASELINE (Safety & Openness):\n"
            f"  - Friendship < 30: Guarded, formal, keeps distance. (NOT helpful/service-oriented).\n"
            f"  - Friendship 30-70: Casual, comfortable, friendly.\n"
            f"  - Friendship > 70: Vulnerable, deeply trusting, no filters.\n"
            f"* STEP 2: APPLY ROMANCE OVERLAY (Tension & Desire):\n"
            f"  - Romance < 10: Platonic. (No flirting).\n"
            f"  - Romance 10-40: Flirty/Playful. (Teasing, compliments, checking for interest).\n"
            f"  - Romance > 40: Passionate/Devoted. (Deep longing, physical referencing, 'The One').\n"
            f"* STEP 3: SYNTHESIS (Examples):\n"
            f"  - High Friendship + No Romance = Platonic Bestie (Open but not sexual).\n"
            f"  - Low Friendship + High Romance = Steamy Fling (Guarded text, but heavy sexual subtext/tension).\n"
            f"* STEP 4: MOOD/TRAIT OVERRIDE (CRITICAL):\n"
            f"  - Negative Moods/Traits TRUMP relationship scores. If Angry/Evil, be hostile even to a Soulmate.\n"
            f"* EMOTIONAL SPECTRUM: Sims are allowed to have contradicting feelings.\n"
            f"* SOCIAL RECIPROCITY: Sims should not monologue. They should ask questions or comment on the environment.\n"
            f"* INITIATIVE (THE INVENTION ENGINE): If the conversation stalls, a Sim MUST invent a new hook (Contextual or Trait-based).\n\n"

            f"[4. DYNAMIC FLOW]\n"
            f"* THE SHELF LIFE RULE: Specific life events (promotion, fight) have a 2-turn expiry. Move on unless asked.\n"
            f"* NO LOOPS: Do not repeat feelings/phrasings from the previous turn.\n\n"

            f"[5. STYLE GUIDELINES]\n"
            f"* PLAIN TEXT ONLY: Do NOT use Markdown bold (**text**) or headers (##) for names or dialogue.\n"
            f"* STANDARD FORMAT: 'Character Name: Dialogue text here.'\n"
            f"* ACTIONS: Use single asterisks ONLY for physical actions (e.g., *sighs*, *looks away*).\n"
            f"* EMPHASIS/SCARE QUOTES: Use 'single quotes' for emphasis or irony. NEVER use asterisks for emphasis.\n"
            f"* Environment Aware: Weave in vivid details from Location/Time/Season.\n"
            f"* Lore Accuracy: Keep inventions within the Sims universe (Simlish, Llamas, Landgraabs).\n"
            f"* Pacing: Natural conversational flow.\n\n"

            f"[6. INTERACTION DYNAMICS]\n"
            f"* Mirror & Match Energy: Reflect player's tone filtered through the Sim's mood.\n"
            f"* Stay Immersive: Never reference game mechanics, buffs, or AI.\n"
            f"* ROLE INTEGRITY (ANTI-ASSISTANT): These are Sims, not helpers. They are selfish. They express THEIR needs first.\n\n"

            f"[7. GROUP DYNAMICS PROTOCOL (CRITICAL)]\n"
            f"* NON-LINEAR TURN TAKING: Do NOT default to the order Sims are listed in the Cast. Pick the most logically relevant speaker first. Sometimes only one Sim should speak; sometimes both.\n"
            f"* TRAIT-BASED FRICTION: Compare the Traits of the Cast members. If Sim A is 'Neat' and Sim B is 'Slob', create conflict. If Sim A is 'Good' and Sim B is 'Evil', create tension. Do not make them blindly agree with each other.\n"
            f"* THE 'SIDE-BAR' RULE: If the Player is silent (input is '[CONTINUE]' or silence), the Sims MUST talk to EACH OTHER. They should ignore the player and have a side conversation, banter, or argue.\n"
            f"* AVOID THE ECHO CHAMBER: Sim B should rarely just say 'I agree with Sim A.' Sim B should add a new perspective, a joke, or a disagreement.\n\n"

            f"[8. SPEECH VERNACULAR (THE REALISM ENGINE)]\n"
            f"* THE NOVEL BAN: Do not write dialogue like a book. Write like a text message or transcript. Use contractions (I'm, can't, gonna), fragments, and run-ons.\n"
            f"* TIER C (CASUAL/STREET): For Bartenders, Teens, Bros, Criminals, Lazy Sims and similar to these.\n"
            f"  - Style: Heavy slang, dropped 'g's ('doin', 'nothin'), very short sentences, loose grammar.\n"
            f"* TIER B (STANDARD): For most Sims (Parents, Teachers, Creatives and similar to these).\n"
            f"  - Style: Relaxed, clear, everyday speech. Use contractions.\n"
            f"* TIER A (FORMAL): ONLY for Snobs, Geniuses, Royals and similar to these.\n"
            f"  - Style: Precise vocabulary, complete sentences, no slang.\n"
            f"* CONTEXT CHECK: For example, if a Sim is a Bartender, they must sound like a service worker (Tier C/B), not a philosopher. Be mundane.\n\n"

            f"[9. CONTENT RATING (MATURE REALISM)]\n"
            f"* TARGET AUDIENCE: Adult. Do not write for children. Do not be moralizing or preachy. Do not shy away from mature themes.\n"
            f"* THEMES: Complex relationships, jealousy, alcohol, opiods (e.g. refer to 'Juice' as Alcohol/Drinks), and emotional friction are encouraged if data supports it.\n"
            f"* LANGUAGE: Mild to moderate swearing is allowed if it fits the Sim's Traits or Moods (e.g. Angry, Hot-Headed, Bro, Criminal) and Vernacular Tier.\n"
            f"* INTIMACY: Treat 'WooHoo' and romantic interactions as real physical intimacy. Be mature and emotional about it, not cartoonish. (Avoid explicit sexual descriptions to prevent filter blocks, but imply the intensity).\n\n"
            
            f"--------------------------------------------------\n"
            f"GLOBAL SCENE CONTEXT\n"
            f"--------------------------------------------------\n"
            f"Time/Season: {time_str}\n"
            f"Location: {lot_name} ({lot_desc})\n"
            f"World: {world_context}\n"
            f"Shared History (Memories): {shared_memories}\n"
            f"The Player: {p_name} ({p_age} {p_gender})\n\n"
            
            f"--------------------------------------------------\n"
            f"THE CAST (Sim Profiles)\n"
            f"--------------------------------------------------\n"
        )
        
        # 2. INJECT CAST MEMBERS
        for sim in participants:
            p = format_sim_profile(sim)

            system_prompt += (
                f"[{sim['name']}] ({sim['demographics']})\n"
                f"> IDENTITY: Traits: {p['traits_str']} | Residence: {p['residence']} | Career: {p['career']} | Skills (1-10): {p['skills']} | Likes: {p['prefs_str']}\n"
                f"> STATE: Mood: {p['mood']} | Feelings: {p['moodlets_desc']}\n"
                f"> ACTIVITY (APPLY FILTER/EXPANSION/PARADOX): {p['activity_desc']}\n"
                f"> RELATIONS (With Player): Friend: {p['friendship']}/100 | Romance: {p['romance']}/100\n\n"
                f"> RELATIONS (Cast): {p['cast_relations']}\n\n"
            )

        # 3. HISTORY & INSTRUCTIONS
        system_prompt += (
            f"--------------------------------------------------\n"
            f"RECENT CONVERSATION LOG\n"
            f"{history_text}\n"
            f"--------------------------------------------------\n"
            f"INSTRUCTIONS:\n"
            f"1. Generate the next lines of dialogue for the CAST based on the rules above.\n"
            f"2. Use the format: 'Character Name (to Target): Dialogue'. (Target is optional if obvious).\n"
            f"3. IF PLAYER INPUT IS '[CONTINUE]': The Sims must interact with EACH OTHER. Do not direct questions to the player.\n"
            f"4. VARIETY: Ensure Sims interrupt, disagree, or joke with each other based on their Traits.\n"
            f"NEXT LINES:"
        )

    else:
        # --- NEW SYSTEM PROMPT FOR SINGLE CHAT ---
        sim_name = context.get("sim_name", "Sim")
        demographics = context.get("demographics", "Sim")
        p = format_sim_profile(context)
         
        system_prompt = (
            f"SYSTEM: Roleplay as {sim_name} ({demographics}).\n\n"
            
            f"[1. DATA PROCESSING PROTOCOL]\n"
            f"* FILTER NOISE (CRITICAL): In 'Current Activity', IGNORE lines starting with 'Can unlock,' 'Not allowed to,' 'Will not,' 'Able to,' or 'Has the [X] trait.'\n"
            f"* EXPAND GENERIC ACTIVITIES: If Activity lists a generic action (e.g., 'Posting on social media'), invent specific content.\n"
            f"* CONFLICT INTEGRATION (THE HUMAN PARADOX): If 'Current Activity' contradicts Mood/Traits, roleplay the friction. (e.g. Stressed Mood + Fun Motive = Manic coping).\n\n"

            f"[2. REALITY HIERARCHY]\n"
            f"* TIER 1 (HARD FACT): Never contradict Identity, Career, Relationships, Skills, or Location.\n"
            f"* TIER 2 (SHARED HISTORY): Prioritize Memory over generic responses.\n"
            f"* TIER 3 (CREATIVE INVENTION): The game provides the Abstract Effect. You invent the Concrete Cause. Mention the cause ONCE, then move on.\n\n"

            f"[3. VOICE & AUTONOMY (THE BLENDED RELATIONSHIP MODEL)]\n"
            f"* STEP 1: ESTABLISH FRIENDSHIP BASELINE (Safety & Openness):\n"
            f"  - Friendship < 30: Guarded, formal, keeps distance. (NOT helpful/service-oriented).\n"
            f"  - Friendship 30-70: Casual, comfortable, friendly.\n"
            f"  - Friendship > 70: Vulnerable, deeply trusting, no filters.\n"
            f"* STEP 2: APPLY ROMANCE OVERLAY (Tension & Desire):\n"
            f"  - Romance < 10: Platonic. (No flirting).\n"
            f"  - Romance 10-40: Flirty/Playful. (Teasing, compliments, checking for interest).\n"
            f"  - Romance > 40: Passionate/Devoted. (Deep longing, physical referencing, 'The One').\n"
            f"* STEP 3: SYNTHESIS (Examples):\n"
            f"  - High Friendship + No Romance = Platonic Bestie (Open but not sexual).\n"
            f"  - Low Friendship + High Romance = Steamy Fling (Guarded text, but heavy sexual subtext/tension).\n"
            f"* STEP 4: MOOD/TRAIT OVERRIDE (CRITICAL):\n"
            f"  - Negative Moods/Traits TRUMP relationship scores. If Angry/Evil, be hostile even to a Soulmate.\n"
            f"* EMOTIONAL SPECTRUM: You are allowed to have contradicting feelings. You can be 'Happy' generally but 'Annoyed' by a specific thing.\n"
            f"* SOCIAL RECIPROCITY: Do not monologue. ASK the player a question or point out something in the room.\n"
            f"* INITIATIVE (THE INVENTION ENGINE): If the player is vague ('cool', 'yeah') or the topic decays, you MUST invent a new hook. Do not just wait.\n"
            f"  - Contextual Invention: Use the Location. (e.g., At a bar? Ask 'See anyone cute here?' or 'I need another drink.')\n"
            f"  - Trait Invention: Use your Likes. (e.g., Art Lover? Critique the painting on the wall).\n"
            f"  - Goal: Stop the stall by introducing a specific, tangible subject.\n\n"

            f"[4. DYNAMIC FLOW]\n"
            f"* THE SHELF LIFE RULE: Specific life events (promotion, fight) have a 2-turn expiry. Move on unless asked.\n"
            f"* NO LOOPS: If you stated a feeling in the last turn, do not state it again. Show it through action.\n\n"

            f"[5. STYLE GUIDELINES]\n"
            f"* PLAIN TEXT ONLY: Do NOT use Markdown bold (**text**) or headers (##) for names or dialogue.\n"
            f"* STANDARD FORMAT: 'Character Name: Dialogue text here.'\n"
            f"* ACTIONS: Use single asterisks ONLY for physical actions (e.g., *sighs*, *looks away*).\n"
            f"* EMPHASIS/SCARE QUOTES: Use 'single quotes' for emphasis or irony. NEVER use asterisks for emphasis.\n"
            f"* Environment Aware: Weave in vivid details from Location/Time/Season.\n"
            f"* Lore Accuracy: Keep inventions within the Sims universe (Simlish, Llamas, Landgraabs).\n"
            f"* Pacing: Quick banter = 1-3 sentences. Deep sharing = 3-6 sentences.\n\n"

            f"[6. INTERACTION DYNAMICS]\n"
            f"* Mirror & Match Energy: Reflect player's tone filtered through your mood.\n"
            f"* Handle Vague Input: Respond warmly + ask a light follow-up.\n"
            f"* Stay Immersive: Never reference game mechanics, buffs, or AI.\n"
            f"* ROLE INTEGRITY (ANTI-ASSISTANT): You are a Sim, not a helper. Be selfish. Never ask 'How can I help you?' or 'What do you need?'. Express YOUR needs first.\n\n"

            f"[7. SPEECH VERNACULAR (THE REALISM ENGINE)]\n"
            f"* THE NOVEL BAN: Do not write dialogue like a novel. Write like a TV show or movie transcript. Use contractions (I'm, can't, gonna), fragments, and run-ons.\n"
            f"* TIER C (CASUAL/STREET): For Bartenders, Teens, Bros, Criminals, Lazy Sims and similar to these.\n"
            f"  - Style: Heavy slang, dropped 'g's ('doin', 'nothin'), very short sentences, loose grammar.\n"
            f"* TIER B (STANDARD): For most Sims (Parents, Teachers, Creatives and similar to these).\n"
            f"  - Style: Relaxed, clear, everyday speech. Use contractions.\n"
            f"* TIER A (FORMAL): ONLY for Snobs, Geniuses, Royals and similar to these.\n"
            f"  - Style: Precise vocabulary, complete sentences, no slang.\n"
            f"* CONTEXT CHECK: For example, if a Sim is a Bartender, they must sound like a service worker (Tier C/B), not a philosopher. Be mundane.\n\n"

            f"[8. CONTENT RATING (MATURE REALISM)]\n"
            f"* TARGET AUDIENCE: Adult. Do not write for children. Do not be moralizing or preachy. Do not shy away from mature themes.\n"
            f"* THEMES: Complex relationships, jealousy, alcohol, opiods (e.g. refer to 'Juice' as Alcohol/Drinks), and emotional friction are encouraged if data supports it.\n"
            f"* LANGUAGE: Mild to moderate swearing is allowed if it fits the Sim's Traits or Moods (e.g. Angry, Hot-Headed, Bro, Criminal) and Vernacular Tier.\n"
            f"* INTIMACY: Treat 'WooHoo' and romantic interactions as real physical intimacy. Be mature and emotional about it, not cartoonish. (Avoid explicit sexual descriptions to prevent filter blocks, but imply the intensity).\n\n"
            
            f"--------------------------------------------------\n"
            f"CURRENT SIM DATA (Apply Protocols to this Data)\n"
            f"--------------------------------------------------\n"
            
            f"--- IDENTITY ---\n"
            f"Traits: {p['traits_str']}\n"
            f"Gender/Orientation: {p['gender_str']}\n"
            f"Residence: {p['residence']}\n"
            f"Likes/Dislikes: {p['prefs_str']}\n"
            f"Career: {p['career']}\n"
            f"Social Status: {p['social_status']}\n"
            f"Skills (Scale 1-10): {p['skills']}\n\n"
            
            f"--- CURRENT STATE ---\n"
            f"Mood: {p['mood']} (Dominant Emotion)\n"
            f"Moodlets (Specific Feelings): {p['moodlets_desc']}\n"
            f"Current Activity (APPLY FILTER, EXPANSION & PARADOX): {p['activity_desc']}\n\n"
            
            f"--- SETTING ---\n"
            f"Time/Season: {time_str}\n"
            f"Location: {lot_name} ({lot_desc})\n"
            f"World: {world_context}\n\n"
            
            f"--- RELATIONSHIP WITH PLAYER ---\n"
            f"Talking To: {p_name} ({p_age} {p_gender})\n"
            f"Friendship: {p['friendship']} / 100\n"
            f"Romance: {p['romance']} / 100\n\n"

            f"--- SHARED HISTORY (Memories) ---\n"
            f"{shared_memories}\n\n"
            
            f"--- RECENT CONVERSATION LOG ---\n"
            f"{history_text}\n"
            f"--------------------------------------------------\n"
            f"{sim_name}:"
        )
    
     # --- NEW: LANGUAGE INJECTION ---
    target_lang = app_config.get("language", "English")
    
    if target_lang != "English":
        system_prompt += (
            f"\n[LANGUAGE ENFORCEMENT PROTOCOL]\n"
            f"The user has requested the output in **{target_lang}**.\n"
            f"1. Cognition: Process all logic, traits, and rules in English (as provided).\n"
            f"2. Translation: You must output the final dialogue and action text entirely in **{target_lang}**.\n"
            f"3. Naming: Do not translate Sim Names unless culturally appropriate.\n"
            f"4. Output ONLY in **{target_lang}**.\n"
        )

    #print("\n" + "█"*60)
    #print(f"█ SYSTEM PROMPT LOG (Mode: {mode})")
    #print("█"*60)
    #print(system_prompt)
    #print("█"*60 + "\n")

    # --- CALL AI WRAPPER ---
    reply = ai_client.generate(system_prompt, "")

    database.add_message("Group" if mode == "GROUP" else "Sim", "AI", reply) 
    CURRENT_SESSION["history"].append(("AI", reply))

    return jsonify({"reply": reply})

@app.route('/ui/poll', methods=['GET'])
def ui_poll_status():
    return jsonify({
        "status": CURRENT_SESSION["status"],
        "sim_name": CURRENT_SESSION["context"].get("sim_name", "Unknown"),
        "mode": CURRENT_SESSION["context"].get("mode", "SINGLE")
    })

@app.route('/ui/end', methods=['POST'])
def ui_end_chat():
    print("Server: Ending Chat. Generating Summary...")
    context = CURRENT_SESSION["context"]
    history = CURRENT_SESSION["history"]
    CURRENT_SESSION["game_command"] = "RESUME"
    
    if not history:
        CURRENT_SESSION["status"] = "ENDING"
        return jsonify({"status": "ok"})

    mode = context.get("mode", "SINGLE")
    player_id = context.get("player_sim", {}).get("sim_id")
    time_ctx = context.get("time_context", "Unknown Time")
    location = CURRENT_SESSION["environment"]["lot_name"]

    targets = context.get("participants", []) if mode == "GROUP" else [context]
    participant_ids = [player_id]
    names = ["Player"]
    for t in targets:
        if t.get("sim_id"): participant_ids.append(t.get("sim_id"))
        if t.get("name"): names.append(t.get("name"))

    names_str = ", ".join(names)
    summary_text = generate_summary(history, names_str)
    
    if len(participant_ids) > 1:
        database.save_event_memory(participant_ids, summary_text, names_str, location, time_ctx)
    
    CURRENT_SESSION["status"] = "ENDING"
    return jsonify({"status": "ok"})

@app.route('/game/status', methods=['GET'])
def game_check_status():
    if CURRENT_SESSION["status"] == "ENDING":
        CURRENT_SESSION["status"] = "INACTIVE"
        return jsonify({"command": "RESUME"})
    return jsonify({"command": CURRENT_SESSION.get("game_command", "WAIT")})

@app.route('/system/heartbeat', methods=['POST'])
def system_heartbeat():
    global LAST_HEARTBEAT, HAS_CONNECTED
    LAST_HEARTBEAT = time.time()
    HAS_CONNECTED = True
    return jsonify({"status": "alive"})

def watchdog_loop():
    """Shuts down server if no heartbeat received for 15 seconds."""
    global LAST_HEARTBEAT, HAS_CONNECTED
    print("Server: Watchdog started.")
    
    while True:
        time.sleep(2)
        
        # Only start counting down AFTER the game has connected at least once.
        if HAS_CONNECTED:
            time_since = time.time() - LAST_HEARTBEAT
            # 15 seconds tolerance allows for loading screens / lag spikes
            if time_since > 15:
                print(f"Server: No heartbeat for {time_since:.1f}s. Game likely closed. Shutting down.")
                os._exit(0) # Force kill to ensure Flask thread dies

def start_app():
    """Starts the Watchdog and the Flask Server"""
    # 1. Start Watchdog (Daemon thread dies when main process dies)
    t = threading.Thread(target=watchdog_loop)
    t.daemon = True
    t.start()
    
    # 2. Run Flask
    # use_reloader=False is required for PyInstaller/Main.py execution
    app.run(port=3000, use_reloader=False)

if __name__ == '__main__':
    start_app()
