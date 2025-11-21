# =============================================================
# CONFIGURAÇÃO CENTRALIZADA DO SISTEMA SMART_TRADER
# =============================================================
# Todas as variáveis de ambiente devem ser acessadas APENAS através deste arquivo.
# Para alternar entre testnet e mainnet, altere a variável BYBIT_TESTNET no .env.
#
# VARIÁVEIS DO .ENV:
#
# [OBRIGATÓRIAS - Banco de Dados]
#   DB_HOST=localhost
#   DB_NAME=smarttrader
#   DB_USER=seu_usuario
#   DB_PASSWORD=sua_senha
#   DB_PORT=5432                    # OPCIONAL (padrão: 5432)
#
# [OBRIGATÓRIAS - Telegram]
#   TELEGRAM_BOT_TOKEN=seu_token
#   TELEGRAM_CHAT_ID=seu_chat_id
#
# [OBRIGATÓRIAS - Bybit (conforme BYBIT_TESTNET)]
#   Se BYBIT_TESTNET=True:
#     TESTNET_BYBIT_API_KEY=sua_key
#     TESTNET_BYBIT_API_SECRET=sua_secret
#   Se BYBIT_TESTNET=False:
#     BYBIT_API_KEY=sua_key
#     BYBIT_API_SECRET=sua_secret
#
# [OPCIONAIS - Bybit]
#   BYBIT_TESTNET=True              # True=testnet, False=mainnet (padrão: False)
#   BYBIT_MARKET=linear             # Tipo de mercado (padrão: linear)
#
# [OPCIONAIS - Caminhos]
#   SCHEMA_JSON_PATH=utils/schema.json
#   PAIRS_JSON_PATH=utils/pares.json
#
# [OPCIONAIS - Filtro Automático de Ativos]
#   REMOVIDO: FILTRO_VOLUME_MINIMO (não é mais necessário)
#   O Filtro Dinâmico (PluginFiltroDinamico) faz a seleção inteligente de pares
#
# [OPCIONAIS - Inteligência Artificial (Groq API - 2025)]
#   IA_ON=False              # True=modo ativo, False=modo passivo (padrão)
#   IA_TRADES=FALSE          # True=permite trades automáticos, False=apenas análise (padrão)
#   IA_API_KEY=sua_key       # Chave da API Groq (obrigatória se IA_ON=True ou IA_TRADES=TRUE)
#   IA_API_URL=https://api.groq.com/openai/v1/chat/completions
#   IA_MODEL=llama-3.1-8b-instant  # Modelo Llama (2025) - Outros: llama-3.1-8b-instruct, llama-3.1-70b-instruct, mixtral-8x7b-instruct
#   IA_DB_PATH removido - agora usa PostgreSQL via GerenciadorBanco
#   IA_BUFFER_SIZE=10         # Tamanho do buffer para análise em lote
#   IA_API_TIMEOUT=60         # Timeout da API em segundos
#   IA_API_RETRY_ATTEMPTS=3   # Tentativas de retry em caso de falha
#   IA_API_RETRY_DELAY=2.0    # Delay entre tentativas (segundos)
#
# Exemplo no .env:
#   BYBIT_TESTNET=True   # Para usar a testnet (ambiente de testes)
#   BYBIT_TESTNET=False  # Para usar a mainnet (ambiente real)
#   IA_ON=False          # Modo passivo (aprendizado silencioso)
#   IA_ON=True           # Modo ativo (sugestões estratégicas)
# =============================================================

from utils.logging_config import get_logger
from dotenv import load_dotenv
import os
from typing import Dict, Any, List, Optional

# Carrega o .env ANTES de ler qualquer variável de ambiente
try:
    load_dotenv(encoding="utf-8")
except UnicodeDecodeError:
    load_dotenv(encoding="latin-1")  # Fallback para latin-1

# Centralização da escolha de ambiente
BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "False").lower() == "true"

# Define o logger ANTES de usá-lo
logger = get_logger(__name__)

# Log do ambiente sendo usado
logger.info(f"[main_config] Ambiente Bybit: {'TESTNET' if BYBIT_TESTNET else 'MAINNET'}")
logger.info(
    f"[main_config] BYBIT_TESTNET do .env: {os.getenv('BYBIT_TESTNET', 'Não definido')}"
)

# Constantes globais
MIN_CONFIDENCE = 0.5  # Sinal só é válido se confiança >= este valor (50%)

# Caminhos padrão para arquivos de configuração
SCHEMA_JSON_PATH = os.getenv(
    "SCHEMA_JSON_PATH", os.path.join("utils", "schema.json")
)
PAIRS_JSON_PATH = os.getenv(
    "PAIRS_JSON_PATH", os.path.join("utils", "pares.json")
)

# Cache de configuração (singleton pattern)
_config_cache = None


# Função _filtrar_ativos_por_volume removida
# O Filtro Dinâmico (PluginFiltroDinamico) agora faz a seleção inteligente de pares
# usando 4 camadas de filtro: liquidez, maturidade, atividade recente e integridade técnica


def _validar_estilos_sltp(estilos: dict) -> dict:
    """
    Valida os estilos SLTP para garantir que sl_mult e tp_mult sejam float > 0.
    
    Args:
        estilos: Dicionário com estilos SLTP
        
    Returns:
        dict: Estilos validados
    """
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
                f"Estilo SLTP inválido removido: '{nome}' "
                f"(sl_mult={sl_mult}, tp_mult={tp_mult})"
            )
    return estilos_validos


class ConfigManager:
    """
    Gerenciador de configuração singleton.
    
    Centraliza todo o acesso a variáveis de ambiente (.env) e configurações
    do sistema. Todas as partes do código devem acessar configurações através
    deste gerenciador.
    
    Attributes:
        _instance: Instância única do singleton
        _config: Cache de configuração carregada
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = {}
        return cls._instance

    def carregar_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Carrega as configurações do arquivo .env, com cache para evitar múltiplas leituras.
        
        Todas as variáveis de ambiente são acessadas aqui e centralizadas no dicionário
        de configuração retornado.
        
        Args:
            force_reload: Se True, recarrega a configuração do zero (ignora cache).
            
        Returns:
            dict: Configuração completa do sistema com todas as seções:
                - bot: Configurações do bot (intervalo, pares, etc.)
                - bybit: Credenciais e configurações da API Bybit
                - db: Configurações do banco de dados
                - telegram: Configurações do Telegram
                - trading: Parâmetros de trading (risco, alavancagem, etc.)
                - indicadores: Parâmetros dos 8 indicadores (Sistema 6/8)
                - sltp_estilos: Estilos de Stop Loss e Take Profit
                
        Raises:
            ValueError: Se alguma variável obrigatória estiver ausente ou inválida.
        """
        global _config_cache
        if _config_cache is not None and not force_reload:
            return _config_cache

        # Utiliza a variável centralizada BYBIT_TESTNET
        testnet = BYBIT_TESTNET

        # ============================================================
        # VALIDAÇÃO DE VARIÁVEIS OBRIGATÓRIAS DO .ENV
        # ============================================================
        # Variáveis obrigatórias: devem estar presentes no .env
        # Variáveis opcionais: DB_PORT (padrão: 5432), BYBIT_MARKET (padrão: linear)
        chaves = [
            "DB_HOST",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
        ]

        # Adiciona chaves específicas da Bybit conforme ambiente
        if testnet:
            chaves += ["TESTNET_BYBIT_API_KEY", "TESTNET_BYBIT_API_SECRET"]
        else:
            chaves += ["BYBIT_API_KEY", "BYBIT_API_SECRET"]

        # Validação geral das variáveis sensíveis
        for chave in chaves:
            valor = os.getenv(chave, "").strip()
            if not valor:
                raise ValueError(
                    f"Variável de ambiente obrigatória ausente ou vazia: {chave}"
                )

        # ============================================================
        # CONFIGURAÇÕES DE PARES E OPERAÇÃO
        # ============================================================
        # Ativos a serem observados
        # O Filtro Dinâmico (PluginFiltroDinamico) fará a seleção inteligente de pares
        # Para definir manualmente, use: ["BTCUSDT", "ETHUSDT", ...]
        # Para usar todos os pares disponíveis (o Filtro Dinâmico filtrará), use: []
        ativos = []  # Lista vazia permite que o Filtro Dinâmico selecione os pares
        
        # Se lista estiver vazia, usa lista padrão como ponto de partida
        # O Filtro Dinâmico fará a filtragem inteligente posteriormente
        if not ativos:
            logger.info(
                "[main_config] Lista de ativos vazia. Usando lista padrão. "
                "O Filtro Dinâmico fará a seleção inteligente de pares."
            )
            ativos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

        # Intervalo do ciclo principal do bot (em segundos)
        # Intervalo do ciclo: ajustado para 25s (recomendado: 20-30s)
        # Motivo: PluginDadosVelas leva ~19s para processar 4 pares
        # Com mais pares, tempo aumenta proporcionalmente
        # Intervalo maior evita sobrecarga e permite processamento completo
        bot_cycle_interval = int(os.getenv("BOT_CYCLE_INTERVAL", "25"))

        # ============================================================
        # CREDENCIAIS BYBIT (conforme ambiente)
        # ============================================================
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

        # ============================================================
        # ESTILOS DE RISCO SLTP
        # ============================================================
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

        # ============================================================
        # CONFIGURAÇÃO DE PARES POR LIQUIDEZ/VOLATILIDADE (Sistema 6/8)
        # ============================================================
        # Conforme regras: volume > $100M → 15m | 3x | até 1.5%
        #                  volume $50M–$100M → 15m | 2x | até 1.0%
        #                  volume < $50M → 5m | 2x | até 0.7%
        pares_config = {
            "BTCUSDT": {
                "timeframe": "15m",
                "alavancagem": 3,
                "risco_percentual": 1.5,
            },
            "ETHUSDT": {
                "timeframe": "15m",
                "alavancagem": 3,
                "risco_percentual": 1.2,
            },
            "SOLUSDT": {
                "timeframe": "5m",
                "alavancagem": 2,
                "risco_percentual": 1.0,
            },
            "XRPUSDT": {
                "timeframe": "5m",
                "alavancagem": 2,
                "risco_percentual": 0.8,
            },
        }

        # ============================================================
        # FUNÇÃO AUXILIAR PARA NORMALIZAÇÃO DE VALORES
        # ============================================================
        def _normalizar_valor_env(chave, padrao=None):
            """Normaliza valor de variável de ambiente para UTF-8 válido."""
            valor = os.getenv(chave, padrao)
            if valor is None:
                return None
            if isinstance(valor, str):
                # Remove espaços e garante UTF-8 válido
                valor = valor.strip()
                try:
                    # Tenta codificar/decodificar para garantir UTF-8 válido
                    return valor.encode('utf-8', errors='replace').decode('utf-8')
                except Exception:
                    # Fallback: remove caracteres problemáticos
                    return valor.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
            return str(valor)
        
        # ============================================================
        # MONTAÇÃO DO DICIONÁRIO DE CONFIGURAÇÃO
        # ============================================================
        config = {
            # Configurações gerais do bot
            "bot": {"cycle_interval": bot_cycle_interval},
            "ativos": ativos,
            "pares": ativos,
            "pares_config": pares_config,
            
            # Tipos de mercado a serem analisados
            "spot": False,  # True para analisar pares spot
            "futuros": False,  # True para analisar futuros ("future")
            "swap": True,  # True para analisar swaps perpétuos
            "option": False,  # True para analisar opções
            
            # Timeframes: 15m (alta liquidez) | 5m (altcoins voláteis)
            "timeframes": ["15m", "5m"],
            
            # Processamento em lote
            "batch_size": 3,
            "executor_max_workers": 4,
            
            # Processamento paralelo de pares
            "processamento": {
                # NOTA: max_workers_paralelo não é mais usado pelo PluginDadosVelas
                # O número de workers é calculado dinamicamente: max(1, pares // 3)
                # Mantido aqui apenas para compatibilidade com outros plugins que possam usar
                "max_workers_paralelo": int(os.getenv("PROCESSAMENTO_MAX_WORKERS", "3")),  # Workers paralelos (não usado pelo PluginDadosVelas)
            },
            
            # Configurações de trading
            "trading": {
                "auto_trade": False,
                "risco_por_operacao": 0.05,
                "alavancagem_maxima": 3,
                "alavancagem_minima": 2,
                "dca_percentual": 0.15,
                "rr_ratio": 2.3,  # R:R fixo conforme estratégia (2.3 × SL)
            },
            
            # Configurações Bybit
            "bybit": {
                "api_key": api_key,
                "api_secret": api_secret,
                "market": os.getenv("BYBIT_MARKET", "linear"),
                "testnet": testnet,
                "base_url": base_url,
            },
            
            # Configurações do banco de dados (normalizadas para UTF-8 válido)
            "db": {
                "host": _normalizar_valor_env("DB_HOST"),
                "database": _normalizar_valor_env("DB_NAME"),
                "user": _normalizar_valor_env("DB_USER"),
                "password": _normalizar_valor_env("DB_PASSWORD"),
                "port": int(os.getenv("DB_PORT", "5432")),  # PostgreSQL padrão: 5432
                "schema_path": SCHEMA_JSON_PATH,
            },
            
            # Configurações Telegram
            "telegram": {
                "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
                "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            },
            
            # Estilos SLTP
            "sltp_estilos": sltp_estilos,
            "sltp_estilo_padrao": sltp_estilo_padrao,
        }

        # ============================================================
        # CONFIGURAÇÕES DOS 8 INDICADORES (Sistema 6/8)
        # ============================================================
        config["indicadores"] = {
            # 1. Ichimoku Cloud (9,26,52,26)
            "ichimoku": {
                "tenkan": 9,
                "kijun": 26,
                "senkou_b": 52,
                "chikou": 26,
            },
            # 2. Supertrend (10, 3)
            "supertrend": {
                "periodo": 10,
                "multiplier": 3,
            },
            # 3. Bollinger Bands (20, 2) + Squeeze
            "bollinger": {
                "periodo": 20,
                "desvio_padrao": 2,
                "squeeze_width_max": 0.04,  # BB Width < 0.04
                "squeeze_velas_minimas": 5,  # ≥5 velas consecutivas
            },
            # 4. Volume + Breakout
            "volume": {
                "periodo_media": 20,
                "multiplier_breakout": 2.0,  # Volume > 2.0 × média(20)
                "periodo_maxima": 20,
            },
            # 5. EMA Crossover (9/21)
            "ema": {
                "rapida": 9,
                "lenta": 21,
            },
            # 6. MACD (12,26,9)
            "macd": {
                "rapida": 12,
                "lenta": 26,
                "sinal": 9,
            },
            # 7. RSI (14)
            "rsi": {
                "periodo": 14,
                "limite_long": 35,  # RSI ≤ 35 (ideal ≤ 30)
                "limite_short": 65,  # RSI ≥ 65 (ideal ≥ 70)
            },
            # 8. VWAP (intraday – reset 00:00 UTC)
            "vwap": {
                "tolerancia_percentual": 0.003,  # ±0.3% (≤ +0.3% LONG, ≥ -0.3% SHORT)
            },
        }

        # ============================================================
        # CONFIGURAÇÕES DE INTELIGÊNCIA ARTIFICIAL (Groq API - 2025)
        # ============================================================
        config["ia"] = {
            "on": os.getenv("IA_ON", "False").lower() == "true",  # Modo passivo por padrão
            "api_url": os.getenv("IA_API_URL", "https://api.groq.com/openai/v1/chat/completions"),
            "model": os.getenv("IA_MODEL", "llama-3.1-8b-instant"),  # Groq 2025 - melhor custo x benefício
            "db_path": os.getenv("IA_DB_PATH", "data/ia_llama.db"),
            "buffer_size": int(os.getenv("IA_BUFFER_SIZE", "10")),  # Tamanho do buffer para análise
            "api_timeout": int(os.getenv("IA_API_TIMEOUT", "60")),  # Timeout da API em segundos
            "api_retry_attempts": int(os.getenv("IA_API_RETRY_ATTEMPTS", "3")),  # Tentativas de retry
            "api_retry_delay": float(os.getenv("IA_API_RETRY_DELAY", "2.0")),  # Delay entre retries
        }

        # ============================================================
        # VALIDAÇÕES FINAIS
        # ============================================================
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

        # Cache a configuração
        _config_cache = config
        logger.info("[main_config] Configuração carregada com sucesso")
        return config


# Singleton global - ÚNICO ponto de acesso às configurações
config_manager = ConfigManager()

# Função pública para carregar configuração (compatibilidade)
carregar_config = config_manager.carregar_config


if __name__ == "__main__":
    # Teste: imprime a configuração carregada
    from pprint import pprint

    print("=" * 60)
    print("CONFIGURAÇÃO CARREGADA DO SISTEMA SMART_TRADER")
    print("=" * 60)
    pprint(carregar_config())

