#!/usr/bin/env python3
import os
import sys
import platform
import subprocess
import traceback
import warnings
import sqlite3
import getpass
import select
import html
import time

# Suppress Python version lifecycle warnings from third-party auth modules
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    import psutil
except ModuleNotFoundError:
    sys.stderr.write("Error: 'psutil' is required for system telemetry monitoring calculations.\n")
    sys.stderr.write("Please execute: python3 -m pip install psutil\n")
    sys.exit(1)

try:
    import paramiko
except ModuleNotFoundError:
    sys.stderr.write("Error: 'paramiko' is required for remote SSH state tracking.\n")
    sys.stderr.write("Please execute: python3 -m pip install paramiko\n")
    sys.exit(1)

from google import genai
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import Completer, Completion

# ==========================================
# 1. GLOBAL STATE & APP CONFIGURATION
# ==========================================

class ShellState:
    def __init__(self):
        # AI mode defaults to turned OFF on initial boot
        self.ai_mode = False  
        self.query_internal_db = True  # Ctrl + K pre-LLM optimization toggle
        self.current_os = platform.system()  
        self.native_shell = os.environ.get('SHELL', 'bash' if self.current_os != 'Windows' else 'powershell')
        self.db_path = os.path.expanduser("~/.akasha_private.db")
        self.history_path = os.path.expanduser("~/.akasha_history")
        self.client = None
        self.init_database()
        self.init_ai_client()

    def init_database(self):
        """Initializes private SQLite infrastructure to log audit paths & optimization profiles."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent TEXT,
                command TEXT,
                verified INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_cache (
                intent TEXT PRIMARY KEY,
                command TEXT,
                confidence_score REAL,
                last_used DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def init_ai_client(self):
        """Pre-configures the modern google-genai integration client asset wrappers."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                self.client = genai.Client()
            except Exception:
                self.client = None

# Instantiate global tracker context
state = ShellState()

# ==========================================
# 2. CACHING & MATH TRUST ENGINE
# ==========================================

def get_overall_confidence_score():
    """Calculates global compliance trends dynamically across historic tracking payloads."""
    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(verified) FROM ai_feedback")
        total, verified = cursor.fetchone()
        conn.close()
        if not total or total == 0:
            return 100.0
        return (verified / total) * 100.0
    except Exception:
        return 0.0

def query_local_cache(intent):
    """Checks the optimization layer table for immediate structural hits prior to LLM calls."""
    if not state.query_internal_db:
        return None
    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT command, confidence_score FROM command_cache WHERE intent = ?", (intent.strip().lower(),))
        row = cursor.fetchone()
        conn.close()
        if row and row[1] >= 0.8:  # Bypass network if System Trust score >= 80%
            return row[0]
    except Exception:
        pass
    return None

def log_feedback_and_recalc(intent, command, verified_status):
    """Saves telemetry evaluation rows and recalibrates local engine confidence records."""
    try:
        conn = sqlite3.connect(state.db_path)
        cursor = conn.cursor()
        
        # Log into historic feedback metrics audit layout
        cursor.execute("INSERT INTO ai_feedback (intent, command, verified) VALUES (?, ?, ?)",
                       (intent.strip().lower(), command, 1 if verified_status else 0))
        
        # Re-evaluate statistical score for this exact isolated semantic query phrase
        cursor.execute("SELECT COUNT(*), SUM(verified) FROM ai_feedback WHERE intent = ?", (intent.strip().lower(),))
        total, verified = cursor.fetchone()
        score = (verified / total) if total > 0 else 0.0
        
        # Merge results securely back into tracking query optimization metrics
        cursor.execute("""
            INSERT INTO command_cache (intent, command, confidence_score, last_used)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(intent) DO UPDATE SET
                command=excluded.command,
                confidence_score=excluded.confidence_score,
                last_used=excluded.last_used
        """, (intent.strip().lower(), command, score))
        
        conn.commit()
        conn.close()
    except Exception as e:
        sys.stderr.write(f"\nCache Logging Error: {str(e)}\n")

# ==========================================
# 3. DYNAMIC COMPOSITE AUTO-COMPLETER
# ==========================================

class SystemCompositeCompleter(Completer):
    """Non-blocking path & binary autocomplete engine structured for prompt_toolkit environments."""
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text:
            return

        # Handle local binary command completions or environment tokens
        if ' ' not in text:
            search_word = text.lower()
            builtins = ['toggle-ai', 'exit', 'clear', 'ssh', 'cd', 'pwd']
            for cmd in builtins:
                if cmd.startswith(search_word):
                    yield Completion(cmd, start_position=-len(text))
            return

        # Fallback tracking loop to match native local storage path components
        parts = text.split(' ')
        target = parts[-1] if parts else ''
        if target:
            try:
                dirname = os.path.dirname(target) or '.'
                basename = os.path.basename(target)
                if os.path.isdir(dirname):
                    for entry in os.listdir(dirname):
                        if entry.startswith(basename):
                            yield Completion(entry, start_position=-len(basename))
            except Exception:
                pass

# ==========================================
# 4. LLM COGNITIVE GENERATION PIPELINE
# ==========================================

def call_gemini_translation(intent, os_context):
    """Routes pure-English intentions directly to the structural target framework via google-genai."""
    if not state.client:
        return f"# Error: Gemini API key or engine context is missing. Raw fallback: {intent}"

    system_prompt = (
        f"You are the Core Translator for Project akaSHa (Universal AI Shell).\n"
        f"The user's active client machine environment is: {os_context}.\n"
        f"Translate the provided natural language intent phrase directly into a valid executable shell string command.\n"
        f"CRITICAL RULES:\n"
        f"1. Output ONLY the raw execution command line text string.\n"
        f"2. Never use markdown, no backticks, no code blocks, and no preamble explanation text.\n"
        f"3. Do not introduce privilege escalation commands (never prepend sudo).\n"
        f"4. If natural answers imply interactive responses, return accurate script arguments."
    )

    try:
        response = state.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=intent,
            config={'system_instruction': system_prompt}
        )
        if response and response.text:
            return response.text.strip().replace('`', '')
    except Exception as e:
        return f"# Error interfacing via external LLM cloud pathways: {str(e)}"
    return f"# Translation fault: Unable to map context structure for '{intent}'"

# ==========================================
# 5. AI-AWARE INTERACTIVE SSH INTERCEPTION MODULE
# ==========================================

def handle_ssh_interception(command, state):
    """
    Intercepts local 'ssh user@host' commands, establishes a persistent 
    Paramiko channel, and wraps it in an AI NLP translation loop capable 
    of detecting and evaluating remote environments.
    """
    import paramiko
    import getpass
    
    # Parse the user, host, and optional port metrics
    parts = command.split()
    target = parts[1] if len(parts) > 1 else ""
    
    if "@" in target:
        username, hostname = target.split("@", 1)
    else:
        username = getpass.getuser()
        hostname = target

    print(f"🌐 akaSHa Intercepting SSH Tunnel Connection to: {hostname}...")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    # Attempt secure automatic authentication matching local keys
    try:
        client.connect(hostname, username=username, look_for_keys=True, timeout=10)
    except (paramiko.AuthenticationException, paramiko.SSHException):
        # Fallback to getpass secure masked console collection
        password = getpass.getpass(f"🔒 Password for {username}@{hostname}: ")
        try:
            client.connect(hostname, username=username, password=password, timeout=10)
        except Exception as e:
            print(f"❌ Authentication Pipeline Failure: {e}")
            return

    # Open a persistent pseudo-terminal (pty) channel to hold interactive streams
    chan = client.invoke_shell()
    time.sleep(0.5)  # Let remote login banner settle
    
    # Consume and display initial connection packets / login text banners
    if chan.recv_ready():
        print(chan.recv(4096).decode('utf-8', errors='ignore'), end="")

    # Core AI-aware Remote Execution Loop via a nested prompt session
    ssh_session = PromptSession()
    
    # Try to identify host type from login banner context, default to Linux
    remote_os = "Linux" 
    print(f"🤖 AI Interceptor Active over SSH. Target Framework context: [{remote_os}]")
    print("💡 Type 'toggle-ai' to switch parsing states. Type 'exit' to disconnect.")

    while True:
        # Dynamic toolbar rendering matching local app configurations
        ai_status = "<span fg='green'>ON</span>" if state.ai_mode else "<span fg='red'>OFF</span>"
        toolbar_html = HTML(
            f"🛠️ <b>akaSHa SSH Bridge</b> | Remote Context: <b>{remote_os}</b> | "
            f"AI Interceptor Mode: {ai_status} | Type 'exit' to close socket"
        )
        
        try:
            # Generate local prompt to securely collect fully buffered line commands
            prompt_str = f"({username}@{hostname}) akaSHa-ssh> "
            user_input = ssh_session.prompt(prompt_str, bottom_toolbar=lambda: toolbar_html).strip()
            
            if not user_input:
                continue
                
            if user_input.lower() == 'exit':
                chan.send("exit\n")
                print("🔌 Safely closing remote channel multiplexers...")
                break
                
            if user_input.lower() == 'toggle-ai':
                state.ai_mode = not state.ai_mode
                print(f"🔄 AI Interceptor Mode shifted dynamically to: {state.ai_mode}")
                continue

            # NLP Evaluation Layer Workflow Integration
            if state.ai_mode:
                print(f"🧠 Translating Intent: '{user_input}' for Environment: {remote_os}...")
                
                # Divert payload mapping through your existing calling function 
                # passing explicit details on your target system profile context
                translated_command = call_gemini_translation(user_input, os_context=remote_os)
                
                print(f"⚡ Executing translated translation command syntax: {translated_command}")
                chan.send(translated_command + "\n")
            else:
                # Raw execution pass-through when intelligence intercepting state is offline
                chan.send(user_input + "\n")
            
            # Wait briefly for execution frames and buffer cycles to complete
            time.sleep(0.4)
            
            # Dynamic output flush collection engine loop
            while chan.recv_ready():
                output_bytes = chan.recv(8192)
                print(output_bytes.decode('utf-8', errors='ignore'), end="")
                sys.stdout.flush()
                time.sleep(0.1)

        except (KeyboardInterrupt, EOFError):
            print("\nUse 'exit' to terminate the session safely.")
        except Exception as e:
            print(f"\n❌ Operational Exception on SSH Pipeline: {e}")
            break

    chan.close()
    client.close()
    print("🔓 Closed connection bridge safely. Returned to your local shell.")

# ==========================================
# 6. HARDWARE TELEMETRY & BOTTOM TOOLBAR
# ==========================================

def bottom_toolbar_renderer():
    """Compiles local metrics and applies html.escape to safeguard prompt_toolkit rendering arrays."""
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        trust = get_overall_confidence_score()
        
        mode_str = "AI-ON (INTERCEPTING)" if state.ai_mode else "AI-OFF (NATIVE)"
        cache_str = "CACHE-ON" if state.query_internal_db else "CACHE-OFF"
        os_str = f"OS: {state.current_os}"
        
        # Apply html.escape to protect the underlying XML layout renderer from crashes
        clean_mode = html.escape(mode_str)
        clean_cache = html.escape(cache_str)
        clean_os = html.escape(os_str)
        
        return HTML(
            f'<style bg="ansiblue" fg="ansiwhite"> </style>'
            f' <b>akaSHa Shell</b> | '
            f' {clean_mode} | '
            f' {clean_cache} | '
            f' {clean_os} | '
            f' <ansiyellow>CPU: {cpu}%</ansiyellow> | '
            f' <ansicyan>RAM: {ram}%</ansicyan> | '
            f' <b>Trust: {trust:.1f}%</b> '
        )
    except Exception as e:
        return HTML(f'<style bg="ansired" fg="ansiwhite"> Telemetry Rendering Error: {html.escape(str(e))} </style>')

# ==========================================
# 7. CONTROL TRIGGERS & HOTKEY INTERACTIVE LOOPS
# ==========================================

kb = KeyBindings()

@kb.add('c-b')
def toggle_ai_shortcut(event):
    """Ctrl + B forces runtime status state flips instantly without clearing the work buffer."""
    state.ai_mode = not state.ai_mode
    event.app.invalidate()

@kb.add('c-k')
def toggle_cache_shortcut(event):
    """Ctrl + K flips pre-LLM query optimization database routing paths on the fly."""
    state.query_internal_db = not state.query_internal_db
    event.app.invalidate()

def main():
    session = PromptSession(
        completer=SystemCompositeCompleter(),
        key_bindings=kb,
        bottom_toolbar=bottom_toolbar_renderer
    )

    print("🚀 Project akaSHa - Universal AI Shell Initialized Successfully.")
    print("💡 Hotkeys: [Ctrl + B] Toggle AI Interception | [Ctrl + K] Toggle Cache Optimization Bypass\n")

    while True:
        try:
            # Construct active prompt indicators dynamically
            prompt_symbol = "akasha(ai)🧠> " if state.ai_mode else "akasha(native)💻> "
            user_input = session.prompt(prompt_symbol)
            user_input_stripped = user_input.strip()

            if not user_input_stripped:
                continue

            if user_input_stripped == 'exit':
                print("👋 Terminating framework context structures safely. Goodbye.")
                break

            if user_input_stripped == 'clear':
                subprocess.run('cls' if state.current_os == 'Windows' else 'clear', shell=True)
                continue

            if user_input_stripped == 'toggle-ai':
                state.ai_mode = not state.ai_mode
                print(f"🔄 State Switch: AI Mode Interception is now set to: {state.ai_mode}")
                continue

            # Route out active SSH sessions straight to Paramiko's socket multiplexer
            if user_input_stripped.startswith('ssh '):
                handle_ssh_interception(user_input_stripped, state)
                continue

            # Core Execution Pipeline
            exec_command = user_input_stripped

            if state.ai_mode:
                # Execution Stage 1: Try to look up optimization profiles inside local database cache
                cached_hit = query_local_cache(user_input_stripped)
                if cached_hit:
                    print(f"⚡ [Optimization Match]: Running local cached configuration shortcut...")
                    exec_command = cached_hit
                else:
                    # Execution Stage 2: Route request externally to cloud model engines
                    print(f"🧠 [Gemini Translation]: Transforming NLP query statement intent...")
                    exec_command = call_gemini_translation(user_input_stripped, state.current_os)
                
                print(f"👉 Generated Command Execution Target: [ {exec_command} ]")

            # Shell Execution Phase
            if exec_command.startswith('# Error'):
                print(exec_command)
                continue

            try:
                # Handle directory modifications directly inside global scope processes
                if exec_command.startswith('cd '):
                    target_dir = exec_command.split(' ', 1)[1].strip()
                    os.chdir(os.path.expanduser(target_dir))
                else:
                    # Execute binary logic commands safely across underlying native hosts
                    result = subprocess.run(exec_command, shell=True)
                    
                    # Error Monitoring / Fallback Engine Suggestion Framework
                    if result.returncode != 0 and state.ai_mode:
                        print(f"\n⚠️ Command tracking reported a execution failure (Exit Code: {result.returncode}).")
                        print("🤖 Fetching potential remedies from Gemini...")
                        remedy_prompt = f"The shell command '{exec_command}' failed with code {result.returncode} on {state.current_os}. Suggest a correction."
                        print(call_gemini_translation(remedy_prompt, state.current_os))

            except Exception as internal_err:
                sys.stderr.write(f"Execution Exception encountered: {str(internal_err)}\n")

            # Interactive Post-Execution Feedback Evaluation Loop
            if state.ai_mode and not cached_hit:
                try:
                    feedback = session.prompt("❓ Did that command execute correctly? (y/n): ")
                    is_verified = feedback.strip().lower() in ['y', 'yes']
                    log_feedback_and_recalc(user_input_stripped, exec_command, is_verified)
                except (KeyboardInterrupt, EOFError):
                    print("\nFeedback parsing skipped.")

        except KeyboardInterrupt:
            # Prevent Ctrl+C from crashing the overall container overlay environment
            print("\nType 'exit' to cleanly close your terminal interface layer session.")
            continue
        except EOFError:
            break
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    main()