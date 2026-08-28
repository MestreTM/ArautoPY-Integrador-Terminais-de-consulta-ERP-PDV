import os
import subprocess
import sys


HOSTNAME = "arauto.localhost"


def contar_pacotes_requirements(req_file):
    try:
        with open(req_file, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip() and not line.strip().startswith("#"))
    except Exception:
        return 0


def run_with_progress(cmd, req_file=None):
    total_packages = contar_pacotes_requirements(req_file) if req_file else 0
    current_count = 0
    current_pkg = "Iniciando..."

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    full_log = []
    for line in process.stdout:
        full_log.append(line)
        if "Collecting " in line:
            current_pkg = line.split("Collecting ")[1].split()[0]
            current_count += 1
        elif "Requirement already satisfied:" in line:
            current_pkg = line.split("Requirement already satisfied: ")[1].split()[0]
            current_count += 1
        elif "Installing collected packages:" in line:
            current_pkg = "Finalizando instalação..."

        if total_packages > 0:
            progress = min(current_count / total_packages, 0.99)
        else:
            progress = 0.5

        bar_length = 25
        filled = int(bar_length * progress)
        bar = "█" * filled + "-" * (bar_length - filled)
        percent = int(progress * 100)
        status_line = f"\r[{bar}] {percent:3d}% | Processando: {current_pkg[:20]:<20}"
        sys.stdout.write(status_line.ljust(75))
        sys.stdout.flush()

    process.wait()

    if process.returncode == 0:
        bar = "█" * 25
        status_line = f"\r[{bar}] 100% | Status: Concluído com sucesso!"
        sys.stdout.write(status_line.ljust(75) + "\n")
        sys.stdout.flush()
        return True

    sys.stdout.write("\r" + " " * 75 + "\r")
    sys.stdout.flush()
    print("\n[ERRO FATAL] Falha durante a instalacao das dependencias!")
    print("=" * 60)
    print("".join(full_log[-20:]).strip())
    print("=" * 60)
    return False


def preparar_atalho():
    print("Atalho local: http://%s:6689/painel" % HOSTNAME)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    os.system("chcp 65001 >nul")
    os.system("title ArautoPY (venv)")

    print("\n ========================================")
    print("  ArautoPY - Servidor de integracao")
    print("  Ambiente virtual: .venv\\")
    print(" ========================================\n")

    preparar_atalho()

    venv_dir = os.path.join(base_dir, ".venv")
    venv_py = os.path.join(venv_dir, "Scripts", "python.exe")

    if not os.path.exists(venv_py):
        print("Criando ambiente virtual em .venv ...")
        try:
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
            print("Venv criado.\n")
        except subprocess.CalledProcessError:
            print("[ERRO] Nao foi possivel criar o venv.")
            input("Pressione Enter para sair...")
            sys.exit(1)
    else:
        print("Venv encontrado: .venv\\\n")

    print("Verificando integridade do ambiente...")
    check_deps_cmd = [venv_py, "-c", "import fastapi,uvicorn,jinja2,PIL,multipart,sqlalchemy"]

    if subprocess.call(check_deps_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        print("Bibliotecas ausentes. Iniciando download...\n")

        cmd_pip = [venv_py, "-m", "pip", "install", "--upgrade", "pip", "--no-color", "--quiet"]
        run_with_progress(cmd_pip)

        req_file = os.path.join(base_dir, "requirements.txt")
        cmd_req = [venv_py, "-m", "pip", "install", "-r", req_file, "--no-color"]

        if not run_with_progress(cmd_req, req_file):
            input("\nPressione Enter para sair...")
            sys.exit(1)

        print("\nAmbiente pronto.")
    else:
        print("Todas as dependencias estao OK.")

    print("\nIniciando: .venv\\Scripts\\python.exe run.py\n")

    extras = list(sys.argv[1:])
    run_cmd = [venv_py, os.path.join(base_dir, "run.py")] + extras
    run_result = subprocess.run(run_cmd)

    if run_result.returncode != 0:
        print(f"\n[ERRO] O processo terminou com codigo {run_result.returncode}.")
        input("Pressione Enter para sair...")

    sys.exit(run_result.returncode)


if __name__ == "__main__":
    main()
