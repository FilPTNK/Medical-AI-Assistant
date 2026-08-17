import os
import sys
import subprocess
import threading
import time

def print_banner():
    banner = """
============================================================
              [+] MedRetrieve - Medical RAG App [+]
============================================================
    This runner script will:
      1. Verify/Install backend Python packages (requirements.txt)
      2. Verify/Install frontend node modules (npm install)
      3. Start the FastAPI backend server (Port 8000)
      4. Start the Vite React development server (Port 3000)
============================================================
    """
    # Use fallback encoding print
    try:
        print(banner)
    except UnicodeEncodeError:
        print(banner.encode('ascii', 'ignore').decode('ascii'))

def log_output(process, prefix):
    """Log subprocess output line by line with a prefix."""
    try:
        # Reconfigure stream to prevent CP1252 errors on Windows
        for line in iter(process.stdout.readline, ""):
            if line:
                print(f"[{prefix}] {line.strip()}")
    except Exception as e:
        pass

def run_backend(project_root):
    backend_dir = os.path.join(project_root, "backend")
    print("[SYSTEM] Starting backend FastAPI server...")
    
    # Run uvicorn on port 8000
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8"
    )
    return process

def run_frontend(project_root):
    frontend_dir = os.path.join(project_root, "frontend")
    print("[SYSTEM] Starting frontend Vite server...")
    
    # Use shell=True for npm commands on Windows
    process = subprocess.Popen(
        "npm run dev",
        cwd=frontend_dir,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8"
    )
    return process

def setup_dependencies(project_root):
    backend_dir = os.path.join(project_root, "backend")
    frontend_dir = os.path.join(project_root, "frontend")

    print("[SYSTEM] 1. Checking Python dependencies...")
    try:
        # Install packages using current Python environment
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=backend_dir,
            check=True
        )
        print("[SYSTEM] Python dependencies verified successfully.")
    except Exception as e:
        print(f"[SYSTEM] Warning: Python dependency installation failed: {e}")
        print("[SYSTEM] Please install them manually if needed.")

    print("\n[SYSTEM] 2. Checking Node.js dependencies...")
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("[SYSTEM] node_modules not found in frontend. Running 'npm install'...")
        try:
            subprocess.run(
                "npm install",
                cwd=frontend_dir,
                shell=True,
                check=True
            )
            print("[SYSTEM] npm install completed.")
        except Exception as e:
            print(f"[SYSTEM] Error: npm install failed: {e}")
            print("[SYSTEM] Please install frontend dependencies manually.")
            sys.exit(1)
    else:
        print("[SYSTEM] node_modules verified.")

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    print_banner()
    
    # 1. Check and install dependencies
    setup_dependencies(project_root)
    
    print("\n============================================================")
    print("           Lauchning Backend & Frontend Dev Servers           ")
    print("============================================================\n")

    # 2. Start servers
    backend_process = run_backend(project_root)
    time.sleep(1.5)  # Let backend start binding ports first
    frontend_process = run_frontend(project_root)
    
    # 3. Create threads to pipe log outputs
    backend_thread = threading.Thread(target=log_output, args=(backend_process, "FastAPI"), daemon=True)
    frontend_thread = threading.Thread(target=log_output, args=(frontend_process, "Vite"), daemon=True)
    
    backend_thread.start()
    frontend_thread.start()
    
    print("\n[+] App is launching! Open http://127.0.0.1:3000 in your browser.")
    print("Type Ctrl+C in this terminal to stop all servers.\n")
    
    try:
        while True:
            # Check if either process terminated unexpectedly
            b_status = backend_process.poll()
            f_status = frontend_process.poll()
            
            if b_status is not None:
                print(f"\n[SYSTEM] Backend process stopped with code {b_status}.")
                break
            if f_status is not None:
                print(f"\n[SYSTEM] Frontend process stopped with code {f_status}.")
                break
                
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SYSTEM] Shutting down servers...")
    finally:
        # Kill processes
        try:
            backend_process.terminate()
        except:
            pass
        try:
            frontend_process.terminate()
        except:
            pass
        print("[SYSTEM] Done. Goodbye!")

if __name__ == "__main__":
    main()
