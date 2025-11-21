"""
Helper para padronizar logs nos indicadores e adicionar funcionalidades avançadas.

Inclui:
- Nível TRACE para logs cirúrgicos
- Cores ANSI para melhor visualização no console
- Formatador customizado integrado com GerenciadorLog
"""

import logging
import sys
from datetime import datetime
from typing import Optional
import pytz

# ============================
#   NOVO NÍVEL DE LOG: TRACE
# ============================
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def trace(self, message, *args, **kws):
    """Método trace para Logger."""
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kws)


# Adiciona método trace ao Logger
logging.Logger.trace = trace


# ============================
#   CORES (ANSI)
# ============================
COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "INFO": "\033[38;5;39m",      # azul
    "DEBUG": "\033[38;5;244m",     # cinza
    "TRACE": "\033[38;5;245m",     # cinza claro
    "WARNING": "\033[38;5;214m",   # amarelo
    "ERROR": "\033[38;5;196m",     # vermelho
    "CRITICAL": "\033[48;5;196m\033[38;5;231m"  # vermelho fundo branco
}


# ============================
#   FORMATADOR CUSTOM COM CORES
# ============================
class SmartFormatter(logging.Formatter):
    """
    Formatador customizado com cores ANSI para console.
    Integrado com o sistema existente (timezone BRT, arquivo:linha).
    """
    
    def __init__(self, fmt=None, datefmt=None, timezone_sp=None, use_colors=True):
        """
        Inicializa o formatador.
        
        Args:
            fmt: Formato da mensagem
            datefmt: Formato da data
            timezone_sp: Timezone de São Paulo (pytz)
            use_colors: Se deve usar cores ANSI (True para console, False para arquivo)
        """
        super().__init__(fmt, datefmt)
        self.timezone_sp = timezone_sp
        self.use_colors = use_colors
    
    def formatTime(self, record, datefmt=None):
        """Formata o tempo com timezone de São Paulo."""
        if self.timezone_sp:
            # Converte de UTC para timezone de São Paulo (mesma lógica do GerenciadorLog)
            dt_utc = datetime.fromtimestamp(record.created, tz=pytz.UTC)
            dt_sp = dt_utc.astimezone(self.timezone_sp)
            if datefmt:
                s = dt_sp.strftime(datefmt)
            else:
                s = dt_sp.strftime(self.default_time_format)
            return s
        return super().formatTime(record, datefmt)
    
    def format(self, record):
        """Formata a mensagem com cores se habilitado."""
        # Verifica se a mensagem começa com [CATEGORIA] (ex: [CORE], [FILTRO])
        # Se sim, substitui o nível de log pela categoria
        # Estratégia: lê mensagem original ANTES de formatar
        mensagem_original = None
        try:
            # Obtém mensagem original do record ANTES de formatar
            if hasattr(record, 'msg'):
                if isinstance(record.msg, str):
                    mensagem_original = record.msg
                elif record.args:
                    # Se há args, a mensagem será formatada - precisamos processar depois
                    mensagem_original = None
                else:
                    mensagem_original = str(record.msg)
        except:
            pass
        
        # Se não conseguiu, tenta getMessage() mas isso pode já ter processado
        if not mensagem_original:
            try:
                mensagem_original = record.getMessage()
            except:
                mensagem_original = None
        
        categoria_extraida = None
        
        # Primeiro, verifica se a categoria foi armazenada diretamente no record
        if hasattr(record, '_categoria_log') and record._categoria_log:
            categoria_extraida = record._categoria_log
            # Remove categoria da mensagem se estiver presente
            if mensagem_original and isinstance(mensagem_original, str) and mensagem_original.startswith(f"[{categoria_extraida}]"):
                mensagem_sem_categoria = mensagem_original[len(f"[{categoria_extraida}]"):].strip()
                record.msg = mensagem_sem_categoria
                record.args = ()
        # Se não encontrou, tenta extrair da mensagem
        elif mensagem_original and isinstance(mensagem_original, str) and mensagem_original.startswith("[") and "]" in mensagem_original:
            fim_categoria = mensagem_original.find("]")
            if fim_categoria > 0:
                categoria_extraida = mensagem_original[1:fim_categoria]
                # Remove categoria da mensagem para não aparecer duplicada
                mensagem_sem_categoria = mensagem_original[fim_categoria + 1:].strip()
                record.msg = mensagem_sem_categoria
                record.args = ()
        
        # Formata normalmente
        msg_formatada = super().format(record)
        
        # Se encontrou categoria, substitui [LEVEL] por [CATEGORIA] na mensagem formatada
        if categoria_extraida:
            level = record.levelname
            # Substitui [LEVEL] por [CATEGORIA] no formato (apenas primeira ocorrência)
            if f"[{level}]" in msg_formatada:
                msg_formatada = msg_formatada.replace(f"[{level}]", f"[{categoria_extraida}]", 1)
        
        # Adiciona cores apenas no console (não em arquivos)
        if self.use_colors and sys.stdout.isatty():
            # Usa categoria se disponível, senão usa level
            nivel_para_cor = categoria_extraida if categoria_extraida else record.levelname
            color = COLORS.get(nivel_para_cor, COLORS.get(record.levelname, COLORS["RESET"]))
            reset = COLORS["RESET"]
            
            # Aplica cor ao nível/categoria na mensagem
            if categoria_extraida and f"[{categoria_extraida}]" in msg_formatada:
                msg_formatada = msg_formatada.replace(f"[{categoria_extraida}]", f"{color}[{categoria_extraida}]{reset}", 1)
            elif f"[{record.levelname}]" in msg_formatada:
                msg_formatada = msg_formatada.replace(f"[{record.levelname}]", f"{color}[{record.levelname}]{reset}", 1)
        
        return msg_formatada


# ============================
#   FUNÇÕES HELPER PARA LOGS
# ============================
def adicionar_logs_inicio_execucao(plugin_name: str, logger, plugin_dados_velas, dados_entrada):
    """
    Adiciona logs padronizados no início da execução de um indicador.
    
    Returns:
        tuple: (dados_velas, should_return, return_value)
    """
    if logger:
        logger.debug(f"[{plugin_name}] ▶ Iniciando execução do indicador")
    
    # Obtém dados de velas
    if not dados_entrada and plugin_dados_velas:
        dados_velas = plugin_dados_velas.dados_completos.get("crus", {})
        if logger:
            logger.debug(f"[{plugin_name}] Dados obtidos do PluginDadosVelas: {len(dados_velas)} pares")
    elif dados_entrada:
        dados_velas = dados_entrada
        if logger:
            logger.debug(f"[{plugin_name}] Dados recebidos como entrada: {len(dados_velas)} pares")
    else:
        if logger:
            logger.error(f"[{plugin_name}] Dados de velas não disponíveis")
        return None, True, {"status": "erro", "mensagem": "Dados de velas não disponíveis"}
    
    return dados_velas, False, None


def adicionar_logs_fim_execucao(plugin_name: str, logger, resultados):
    """
    Adiciona logs padronizados no fim da execução de um indicador.
    """
    if logger:
        total_pares = len(resultados)
        total_sinais_long = sum(1 for par_data in resultados.values() 
                               for tf_data in par_data.values() 
                               if isinstance(tf_data, dict) and tf_data.get("long", False))
        total_sinais_short = sum(1 for par_data in resultados.values() 
                                for tf_data in par_data.values() 
                                if isinstance(tf_data, dict) and tf_data.get("short", False))
        logger.debug(
            f"[{plugin_name}] ✓ Execução concluída: {total_pares} pares processados, "
            f"{total_sinais_long} LONG, {total_sinais_short} SHORT"
        )


def criar_logger_com_cores(
    component: str, 
    level: str = "INFO",
    timezone_sp=None,
    formato: Optional[str] = None
):
    """
    Cria um logger com cores ANSI para uso direto (não integrado com GerenciadorLog).
    
    Útil para scripts standalone ou testes.
    
    Args:
        component: Nome do componente
        level: Nível de log (INFO, DEBUG, TRACE, etc.)
        timezone_sp: Timezone de São Paulo (pytz.timezone)
        formato: Formato customizado (opcional)
    
    Returns:
        logging.Logger: Logger configurado com cores
    """
    logger = logging.getLogger(component)
    
    if not logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        
        # Handler para console com cores
        handler = logging.StreamHandler(sys.stdout)
        
        # Formato padrão se não fornecido
        if not formato:
            formato = "[%(asctime)s BRT] [%(name)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
        
        formatter = SmartFormatter(
            formato,
            datefmt="%Y-%m-%d %H:%M:%S",
            timezone_sp=timezone_sp,
            use_colors=True
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


# ============================
#   EXEMPLO DE USO
# ============================
"""
# Uso básico (standalone)
from utils.log_helper import criar_logger_com_cores
import pytz

logger = criar_logger_com_cores("DOTUSDT | EMA", level="DEBUG", timezone_sp=pytz.timezone('America/Sao_Paulo'))

logger.info("Iniciando execução do indicador EMA")
logger.debug("EMA(20)=7.12 / EMA(50)=7.09 — cruzamento detectado")
logger.trace("vela 151 → close=6.22 ema_fast=6.19 ema_slow=6.08")
logger.warning("Velas insuficientes — mínimo 50")
logger.error("Divisão por zero — volume=0")
logger.critical("Falha irreversível no plugin")

# Uso integrado com GerenciadorLog
# O GerenciadorLog já usa SmartFormatter no console handler
# Apenas use logger.trace() para logs cirúrgicos
"""
