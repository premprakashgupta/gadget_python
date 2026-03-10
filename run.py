import sys
import subprocess
import os

def main():
    # 1. Determine the path to the virtual environment's python
    # Works for both Windows (Scripts) and Linux/Pi (bin)
    venv_dir = os.path.join(os.path.dirname(__file__), ".venv")
    if os.name == 'nt':
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")

    # 2. Check if the current process is already inside a virtual environment
    # sys.prefix != sys.base_prefix is the standard way to detect venv
    is_venv = sys.prefix != sys.base_prefix

    # 3. Add environment variable for UTF-8 encoding (crucial for Windows console)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # 4. Check/Setup Models
    target_python = venv_python if (not is_venv and os.path.exists(venv_python)) else sys.executable
    if os.path.exists("setup_models.py"):
        print("[Launcher] 🔍 Checking AI models...")
        try:
            subprocess.run([target_python, "setup_models.py"], check=True, env=env)
        except Exception as e:
            print(f"[Launcher] ⚠️ Model setup warning: {e}")

    if not is_venv and os.path.exists(venv_python):
        print(f"[Launcher] 🚀 Virtual environment detected. Activating and running main.py...")
        # Use subprocess to run main.py with the venv python
        try:
            subprocess.run([venv_python, "main.py"], check=True, env=env)
        except KeyboardInterrupt:
            print("\n[Launcher] Stopped by user.")
        except Exception as e:
            print(f"[Launcher] Error running project: {e}")
    else:
        if is_venv:
            print(f"[Launcher] ✅ Already running in Virtual Environment. Starting main.py...")
        else:
            print(f"[Launcher] ⚠️ No .venv found at {venv_dir}. Running with system Python...")
            
        # Run main.py using current python
        try:
            subprocess.run([sys.executable, "main.py"], check=True, env=env)
        except KeyboardInterrupt:
            print("\n[Launcher] Stopped by user.")
        except Exception as e:
            print(f"[Launcher] Error running project: {e}")

if __name__ == "__main__":
    main()
