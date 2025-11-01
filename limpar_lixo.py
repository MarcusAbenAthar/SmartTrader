import os
import shutil
import platform
import subprocess


def apagar_pastas_alvo(root_dir=".", nomes_alvo=("__pycache__", "log", "logs")):
    """Apaga pastas com nomes específicos recursivamente a partir do diretório root_dir."""
    contador = 0
    for dirpath, dirnames, _ in os.walk(root_dir):
        for nome in list(dirnames):  # cópia segura
            if nome in nomes_alvo:
                caminho_alvo = os.path.join(dirpath, nome)
                try:
                    shutil.rmtree(caminho_alvo)
                    print(f"[✔] Removido: {caminho_alvo}")
                    contador += 1
                except Exception as e:
                    print(f"[✖] Falha ao remover {caminho_alvo}: {e}")
    print(f"\n{contador} pasta(s) removida(s).")


def limpar_terminal():
    """Limpa o terminal (Windows/Linux/Mac)."""
    comando = "cls" if platform.system() == "Windows" else "clear"
    subprocess.call(comando, shell=True)


if __name__ == "__main__":
    apagar_pastas_alvo()
    limpar_terminal()
