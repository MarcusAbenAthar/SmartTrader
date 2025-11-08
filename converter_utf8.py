import shutil
from pathlib import Path

# ========================
# Configurações principais
# ========================
ROOT = Path(".").resolve()
BACKUP_DIR = ROOT / "_backup_encoding"
EXTENSOES = [".py", ".md", ".txt", ".json", ".ini", ".env"]

# Pastas que devem ser varridas recursivamente
PASTAS_RECURSIVAS = ["plugins", "utils", "docs"]

# Cria pasta de backup se não existir
BACKUP_DIR.mkdir(exist_ok=True)

def converter_para_utf8(caminho: Path):
    """Tenta converter o arquivo para UTF-8 e substitui o original."""
    try:
        dados = caminho.read_bytes()
        try:
            dados.decode("utf-8")
            print(f"[OK UTF-8] {caminho}")
            return
        except UnicodeDecodeError:
            texto = dados.decode("latin-1")
            backup_path = BACKUP_DIR / caminho.relative_to(ROOT)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, backup_path)
            caminho.write_text(texto, encoding="utf-8")
            print(f"[CONVERTIDO] {caminho} -> UTF-8 (backup em {backup_path})")
    except Exception as e:
        print(f"[ERRO] {caminho}: {e}")

def listar_arquivos():
    """Gera a lista de arquivos válidos na raiz e nas pastas especificadas."""
    arquivos = []

    # 1️⃣ Arquivos diretamente na raiz (sem subpastas)
    for ext in EXTENSOES:
        arquivos.extend(ROOT.glob(f"*{ext}"))

    # 2️⃣ Arquivos dentro das pastas recursivas
    for nome_pasta in PASTAS_RECURSIVAS:
        pasta = ROOT / nome_pasta
        if not pasta.exists():
            continue
        for ext in EXTENSOES:
            arquivos.extend(pasta.rglob(f"*{ext}"))

    return arquivos

def main():
    print(f"Iniciando conversão de encodings em: {ROOT}")
    print(f"Pastas recursivas: {PASTAS_RECURSIVAS}")
    print(f"Arquivos de backup serão salvos em: {BACKUP_DIR}\n")

    arquivos = listar_arquivos()
    total = len(arquivos)
    print(f"{total} arquivo(s) encontrados.\n")

    for arquivo in arquivos:
        if BACKUP_DIR in arquivo.parents:
            continue
        converter_para_utf8(arquivo)

    print("\nConversão concluída.")
    print("→ Verifique a pasta '_backup_encoding' caso precise restaurar algum arquivo.")

if __name__ == "__main__":
    main()
