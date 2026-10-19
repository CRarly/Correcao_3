import sys
import os
import webbrowser
import threading
import uvicorn

# Suporte UTF-8 no Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def main():
    if "--cli" in sys.argv:
        from cli import menu_principal
        menu_principal()
    else:
        from config import DEFAULT_PORT, find_available_port

        target_port = DEFAULT_PORT
        for idx, arg in enumerate(sys.argv):
            if arg in ("--port", "-p") and idx + 1 < len(sys.argv):
                try:
                    target_port = int(sys.argv[idx + 1])
                except ValueError:
                    pass

        port = find_available_port(target_port)
        print("=" * 65)
        print("   BRIGHTSPACE GRADER 3.0 | Servidor Dashboard Web")
        print("=" * 65)
        print(f"Iniciando em http://127.0.0.1:{port} ...")

        from app import app
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

if __name__ == "__main__":
    main()
