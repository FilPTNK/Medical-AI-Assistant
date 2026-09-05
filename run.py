import os
import sys
import socket
import subprocess
import threading
import time

def log(msg):
    """In và đẩy ra ngay: stdout của runner cũng có thể là pipe bị đệm."""
    print(msg, flush=True)


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
    """Đọc log của tiến trình con và in ra, KHÔNG BAO GIỜ dừng sớm.

    Vòng lặp này là thứ duy nhất rút dữ liệu khỏi pipe của tiến trình con. Nếu
    nó thoát, pipe đầy (vài chục KB) rồi tiến trình con ĐỨNG YÊN ngay giữa lúc
    đang ghi log — kể cả khi đang xử lý request. Triệu chứng đúng như đã gặp:
    backend còn LISTENING trên cổng 8000, CPU 0%, nhưng không trả lời nổi
    /docs; py-spy cho thấy luồng chính kẹt trong logging.emit.

    Bản trước bọc cả vòng lặp trong `try/except: pass`, nên một lỗi mã hoá ở
    MỘT dòng làm chết hẳn luồng đọc và treo backend vĩnh viễn, im lặng. Giờ mỗi
    dòng được bọc riêng, và nếu có sự cố thì vẫn phải rút hết pipe.
    """
    try:
        for line in iter(process.stdout.readline, ""):
            if not line:
                continue
            try:
                print(f"[{prefix}] {line.rstrip()}", flush=True)
            except Exception:
                # In được gì hay nấy: mất một dòng log còn hơn treo tiến trình.
                safe = line.rstrip().encode("ascii", "replace").decode("ascii")
                try:
                    print(f"[{prefix}] {safe}", flush=True)
                except Exception:
                    pass
    except Exception as e:
        print(f"[SYSTEM] Luồng đọc log {prefix} gặp lỗi: {e!r}. Vẫn rút pipe để "
              f"tiến trình con không bị treo.", flush=True)
        try:
            for _ in iter(process.stdout.readline, ""):
                pass
        except Exception:
            pass

def run_backend(project_root):
    backend_dir = os.path.join(project_root, "backend")
    print("[SYSTEM] Starting backend FastAPI server...")
    
    # Uvicorn được khởi động qua backend/dev_server.py chứ không phải tham số
    # dòng lệnh: trên Windows các mẫu glob của --reload-exclude bị nở thành
    # hàng nghìn đường dẫn trước khi tới uvicorn ("Got unexpected extra
    # arguments", thoát mã 2). dev_server.py giữ cấu hình reload ở dạng Python
    # nên không có gì để shell hay CRT nở ra.
    # PYTHONUNBUFFERED: stdout của backend là pipe nên mặc định bị đệm theo
    # khối; không có biến này thì dòng "[STARTUP] ..." chỉ hiện ra rất muộn,
    # hoặc mất hẳn nếu tiến trình bị tắt giữa chừng.
    # PYTHONIOENCODING: khi stdout bị chuyển thành pipe, Python của tiến trình
    # con dùng mã hoá locale (cp1252 trên máy này) chứ không phải UTF-8. Mọi
    # dòng log tiếng Việt của backend đều ném UnicodeEncodeError, còn phía cha
    # đọc bằng encoding="utf-8" nên gặp byte cp1252 thì ném UnicodeDecodeError.
    # Ép cả hai đầu về UTF-8 để hai bên nói cùng một thứ tiếng.
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    process = subprocess.Popen(
        [sys.executable, "dev_server.py"],
        cwd=backend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )
    return process

def stop_process_tree(process, label):
    """Tắt tiến trình VÀ toàn bộ tiến trình con của nó.

    `process.terminate()` chỉ giết tiến trình cha. Uvicorn ở chế độ reload chạy
    hai tiến trình (reloader + worker), còn `npm run dev` sinh ra node; giết
    cha thì con sống sót và tiếp tục GIỮ cổng 8000/3000. Lần chạy sau sẽ không
    bind được cổng, và vì tiến trình cha đã chết nên netstat vẫn báo cổng bị
    chiếm bởi một PID không còn tồn tại — rất khó lần ra.
    """
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            # /T lấy cả cây con, /F là bắt buộc vì worker không xử lý tín hiệu.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()
        process.wait(timeout=10)
    except Exception as e:
        print(f"[SYSTEM] Không tắt được {label}: {e}")


def wait_for_backend(process, host="127.0.0.1", port=8000, timeout=180):
    """Chờ tới khi backend thực sự nhận kết nối, rồi mới bật Vite.

    Backend phải import torch + chromadb trước khi uvicorn bind cổng, mất
    khoảng 20-30s trên máy không có SSD nhanh. Trước đây runner chỉ sleep 1.5s
    rồi bật Vite ngay, nên trình duyệt gọi /api/auth/status khi cổng 8000 chưa
    mở và nhận ECONNREFUSED — giao diện hiện "không kết nối được với máy chủ".
    """
    print("[SYSTEM] Đang chờ backend sẵn sàng (nạp thư viện AI, thường 20-40s)...")
    started = time.time()
    while time.time() - started < timeout:
        if process.poll() is not None:
            print(f"[SYSTEM] Backend đã thoát sớm với mã {process.poll()}.")
            return False
        try:
            with socket.create_connection((host, port), timeout=1):
                elapsed = time.time() - started
                log(f"[SYSTEM] Backend đã sẵn sàng sau {elapsed:.0f}s.")
                return True
        except OSError:
            time.sleep(1)
    print(f"[SYSTEM] Hết {timeout}s chờ backend. Vẫn bật giao diện, bạn thử tải lại trang sau.")
    return False


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
        encoding="utf-8",
        errors="replace",
    )
    return process

def setup_dependencies(project_root):
    backend_dir = os.path.join(project_root, "backend")
    frontend_dir = os.path.join(project_root, "frontend")

    # `pip install -r requirements.txt` chạy lại MỖI lần khởi động tốn vài phút
    # và làm ngập terminal, dù gần như lần nào cũng chỉ in "already satisfied".
    # Chỉ cài khi requirements.txt mới hơn mốc đã cài, hoặc khi chạy với cờ
    # `--reinstall`.
    marker = os.path.join(backend_dir, ".deps-installed")
    req = os.path.join(backend_dir, "requirements.txt")
    force = "--reinstall" in sys.argv
    up_to_date = (
        not force
        and os.path.exists(marker)
        and os.path.getmtime(marker) >= os.path.getmtime(req)
    )

    if up_to_date:
        print("[SYSTEM] 1. Thư viện Python đã cài (chạy `python run.py --reinstall` để cài lại).")
    else:
        print("[SYSTEM] 1. Đang cài/cập nhật thư viện Python (chỉ chạy lần đầu hoặc khi đổi requirements)...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=backend_dir,
                check=True
            )
            with open(marker, "w", encoding="utf-8") as f:
                f.write("ok")
            print("[SYSTEM] Đã cài xong thư viện Python.")
        except Exception as e:
            print(f"[SYSTEM] Cảnh báo: cài thư viện thất bại: {e}")
            print("[SYSTEM] Hãy cài thủ công nếu cần.")

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
    # Bat line-buffering cho MOI print cua runner. Khi stdout la pipe (chay
    # trong terminal khac, CI, hoac ghi ra file) Python dem theo khoi, nen moi
    # thong bao tien do chi hien ra rat muon hoac mat han neu bi tat giua chung.
    # encoding/errors: stdout cua chinh runner cung co the la cp1252 (khi bi
    # pipe). Log cua backend co dau tieng Viet, in thang se nem
    # UnicodeEncodeError va giet luon luong dang rut pipe -> backend treo.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass

    project_root = os.path.dirname(os.path.abspath(__file__))
    print_banner()
    
    # 1. Check and install dependencies
    setup_dependencies(project_root)
    
    print("\n============================================================")
    print("           Lauchning Backend & Frontend Dev Servers           ")
    print("============================================================\n")

    # 2. Start servers
    backend_process = run_backend(project_root)

    # Log của backend phải được đọc NGAY, trước khi chờ: stdout của nó là pipe
    # có bộ đệm, không ai đọc thì tiến trình sẽ nghẽn khi đệm đầy.
    backend_thread = threading.Thread(target=log_output, args=(backend_process, "FastAPI"), daemon=True)
    backend_thread.start()

    wait_for_backend(backend_process)
    frontend_process = run_frontend(project_root)
    
    # 3. Đọc log của frontend (log backend đã được đọc từ trước khi chờ)
    frontend_thread = threading.Thread(target=log_output, args=(frontend_process, "Vite"), daemon=True)
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
        # Tắt cả cây tiến trình, nếu không worker của uvicorn và node của Vite
        # sẽ sống sót và giữ cổng 8000/3000 cho lần chạy sau.
        stop_process_tree(backend_process, "backend")
        stop_process_tree(frontend_process, "frontend")
        print("[SYSTEM] Done. Goodbye!")

if __name__ == "__main__":
    main()
