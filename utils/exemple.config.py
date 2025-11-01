# =============================================================
# CONFIGURAÇÃO DE FONTE DE DADOS (TESTNET/MAINNET BYBIT)
# =============================================================
# Para alternar entre testnet e mainnet, altere a variável BYBIT_TESTNET
# no arquivo .env (recomendado) ou diretamente abaixo.
#
# Exemplo no .env:
#   BYBIT_TESTNET=True   # Para usar a testnet (ambiente de testes)
#   BYBIT_TESTNET=False  # Para usar a mainnet (ambiente real)
# =============================================================

from utils.logging_config import get_logger
from dotenv import load_dotenv
import os
from typing import Dict, Any
import json
from pathlib import Path

# Carrega o .env ANTES de ler qualquer variável de ambiente
try:
    load_dotenv(encoding="utf-8")
except UnicodeDecodeError:
    load_dotenv(encoding="latin-1")  # Carrega variáveis sensíveis do .env

# Centralização da escolha de ambiente
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "False").lower() == "true"

# Define o logger ANTES de usá-lo
logger = get_logger(__name__)

# Log do ambiente sendo usado
logger.info(f"[config] Ambiente Bybit: {'TESTNET' if BYBIT_TESTNET else 'MAINNET'}")
logger.info(f"[config] BYBIT_TESTNET do .env: {os.getenv('BYBIT_TESTNET', 'Não definido')}")

MIN_CONFIDENCE = 0.5  # Sinal só é válido se confiança >= este valor (50%)

# Caminho padrão para schema.json e pares.json sempre em utils/
SCHEMA_JSON_PATH = os.getenv("SCHEMA_JSON_PATH", os.path.join("utils", "schema.json"))
PAIRS_JSON_PATH = os.getenv("PAIRS_JSON_PATH", os.path.join("utils", "pares.json"))

_config_cache = None


def _validar_estilos_sltp(estilos: dict) -> dict:
    """Valida os estilos SLTP para garantir que sl_mult e tp_mult sejam float > 0."""
    estilos_validos = {}
    for nome, params in estilos.items():
        sl_mult = params.get("sl_mult")
        tp_mult = params.get("tp_mult")
        if (
            isinstance(sl_mult, (int, float))
            and sl_mult > 0
            and isinstance(tp_mult, (int, float))
            and tp_mult > 0
        ):
            estilos_validos[nome] = params
        else:
            logger.warning(
                f"Estilo SLTP inválido removido: '{nome}' (sl_mult={sl_mult}, tp_mult={tp_mult})"
            )
    return estilos_validos


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = {}
        return cls._instance

    def carregar_config(self, force_reload=False):
        """
        Carrega as configurações do arquivo .env e config.json, com cache para evitar múltiplas leituras.
        Args:
            force_reload (bool): Se True, recarrega a configuração do zero.
        Returns:
            dict: Configuração carregada.
        """
        global _config_cache
        if _config_cache is not None and not force_reload:
            return _config_cache
        # Utiliza a variável centralizada BYBIT_TESTNET
        testnet = BYBIT_TESTNET

        # Chaves obrigatórias mínimas
        chaves = [
            "DB_HOST",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ]

        # Adiciona chaves específicas da Bybit
        if testnet:
            chaves += ["TESTNET_BYBIT_API_KEY", "TESTNET_BYBIT_API_SECRET"]
        else:
            chaves += ["BYBIT_API_KEY", "BYBIT_API_SECRET"]

        # Validação geral das variáveis sensíveis
        for chave in chaves:
            if not os.getenv(chave, "").strip():
                raise ValueError(
                    f"Variável de ambiente obrigatória ausente ou vazia: {chave}"
                )

        # Configuração institucional pronta para uso
        # Edite aqui os pares que deseja monitorar
        ativos = ["XRPUSDT"]

        bot_cycle_interval = 5  # Intervalo do loop principal

        # Coleta de credenciais da Bybit conforme ambiente
        if testnet:
            api_key = os.getenv("TESTNET_BYBIT_API_KEY")
            api_secret = os.getenv("TESTNET_BYBIT_API_SECRET")
            base_url = "https://api-testnet.bybit.com"
            logger.debug("Credenciais da testnet carregadas.")
        else:
            api_key = os.getenv("BYBIT_API_KEY")
            api_secret = os.getenv("BYBIT_API_SECRET")
            base_url = "https://api.bybit.com"
            logger.debug("Credenciais da mainnet carregadas.")

        # Estilos de risco SLTP
        sltp_estilos = _validar_estilos_sltp(
            {
                "conservador": {"sl_mult": 0.5, "tp_mult": 1.0},
                "moderado": {"sl_mult": 1.0, "tp_mult": 1.5},
                "agressivo": {"sl_mult": 1.5, "tp_mult": 3.0},
            }
        )

        sltp_estilo_padrao = (
            "moderado" if "moderado" in sltp_estilos else next(iter(sltp_estilos), None)
        )
        if not sltp_estilo_padrao:
            raise ValueError("Nenhum estilo SLTP válido encontrado.")

        # Pesos para consolidação multi-timeframe e multi-plugin
        PESOS_TIMEFRAME = {"1d": 0.4, "4h": 0.3, "1h": 0.2, "15m": 0.1}
        # Plugins principais podem ser ajustados conforme arquitetura
        PESOS_PLUGIN = {"analise_mercado": 0.5, "calculo_risco": 0.3, "outros": 0.2}

        config = {
            "bot": {"cycle_interval": bot_cycle_interval},
            "ativos": ativos,
            # Configuração operacional
            "pares": ativos,
            # Tipos de mercado a serem analisados. Ative/desative conforme desejado:
            "spot": False,  # True para analisar pares spot
            "futuros": False,  # True para analisar futuros ("future")
            "swap": True,  # True para analisar swaps perpétuos
            "option": False,  # True para analisar opções
            "timeframes": ["15m", "1h", "4h", "1d"],
            # Quantidade de symbols processados em lote (ajuste conforme desejado)
            "batch_size": 3,
            # Número máximo de workers para o ThreadPoolExecutor (ajuste conforme desejado)
            "executor_max_workers": 4,
            "trading": {
                "auto_trade": False,
                "risco_por_operacao": 0.05,
                "alavancagem_maxima": 20,
                "alavancagem_minima": 5,
                "dca_percentual": 0.15,
            },
            "bybit": {
                "api_key": api_key,
                "api_secret": api_secret,
                "market": os.getenv("BYBIT_MARKET", "linear"),
                "testnet": testnet,
                "base_url": base_url,  # usado direto no conexao.py
            },
            "db": {
                "host": os.getenv("DB_HOST"),
                "database": os.getenv("DB_NAME"),
                "user": os.getenv("DB_USER"),
                "password": os.getenv("DB_PASSWORD"),
            },
            "telegram": {
                "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
                "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            },
            "sltp_estilos": sltp_estilos,
            "sltp_estilo_padrao": sltp_estilo_padrao,
        }

        # Validações finais
        if not config["pares"]:
            raise ValueError("A lista de pares não pode ser vazia.")
        if not config["timeframes"]:
            raise ValueError("A lista de timeframes não pode ser vazia.")
        if config["trading"]["risco_por_operacao"] <= 0:
            raise ValueError("O risco_por_operacao deve ser maior que 0.")
        if (
            config["trading"]["alavancagem_maxima"]
            <= config["trading"]["alavancagem_minima"]
        ):
            raise ValueError(
                "A alavancagem_maxima deve ser maior que a alavancagem_minima."
            )
        if config["trading"]["dca_percentual"] <= 0:
            raise ValueError("O dca_percentual deve ser maior que 0.")

        # Inclui os pesos globais na configuração retornada
        config["PESOS_TIMEFRAME"] = PESOS_TIMEFRAME
        config["PESOS_PLUGIN"] = PESOS_PLUGIN

        # --- CONFIGURAÇÕES PADRÃO DE INDICADORES ---
        config["indicadores"] = {
            "tendencia": {
                "sma_rapida": 9,
                "sma_lenta": 21,
                "ema_rapida": 12,
                "ema_lenta": 26,
                "macd_signal": 9,
                "adx_periodo": 14,
                "atr_periodo": 14,
            },
            "volatilidade": {
                "bb": 20,  # Parâmetro obrigatório para Bandas de Bollinger
                "atr": 14,  # Parâmetro obrigatório para ATR
                "bb_periodo_base": 20,
                "bb_desvio_padrao": 2,
                "atr_periodo_base": 14,
                "volatilidade_periodo_base": 14,
            },
            "osciladores": {
                "rsi_periodo": 14,
                "mfi_periodo": 14,
                "estocastico_fastk": 5,
                "estocastico_slowk": 3,
                "estocastico_slowd": 3,
            },
            # Outros grupos podem ser adicionados aqui
        }
        _config_cache = config
        return config


# Singleton global
config_manager = ConfigManager()
carregar_config = config_manager.carregar_config


if __name__ == "__main__":
    from pprint import pprint

    pprint(carregar_config())
