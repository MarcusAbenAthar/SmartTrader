# 📋 Exemplos de Uso das Categorias de Log

## 🎯 Categorias Disponíveis

```python
from plugins.gerenciadores.gerenciador_log import CategoriaLog

# Categorias:
CategoriaLog.CORE      # Núcleo do sistema
CategoriaLog.CONEXAO   # Ligação com exchange
CategoriaLog.BANCO     # Operações de banco
CategoriaLog.PLUGIN    # Execução de plugins
CategoriaLog.ANALISE  # Processamento de dados
CategoriaLog.SINAL     # Sinais de trading
CategoriaLog.FILTRO    # Filtro dinâmico
CategoriaLog.IA        # Inteligência artificial
CategoriaLog.UTIL      # Utilitários
```

## 📝 Exemplos de Uso

### 1. CORE - Núcleo do Sistema

```python
# Ciclo completo
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.CORE,
    nome_origem="SmartTrader",
    mensagem="Ciclo concluído — plugins: 2/2, tempo: 2.00 ms",
    nivel=logging.INFO,
    detalhes={"status": "ok", "executados": 2, "tempo_total_ms": 2.0}
)
```

### 2. CONEXAO - Ligação com Exchange

```python
# Latency da API
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.CONEXAO,
    nome_origem="PluginBybitConexao",
    mensagem="Latency da API: 45ms",
    nivel=logging.INFO,
    detalhes={"endpoint": "/v5/market/tickers", "latency_ms": 45}
)
```

### 3. BANCO - Operações de Banco

```python
# Insert de velas
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.BANCO,
    nome_origem="PluginBancoDados",
    mensagem="Inseridas 100 velas",
    nivel=logging.INFO,
    tipo_log="banco",
    detalhes={"tabela": "velas", "registros": 100, "par": "BTCUSDT"}
)
```

### 4. PLUGIN - Execução de Plugins

```python
# Plugin específico
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.PLUGIN,
    nome_origem="PluginSupertrend",
    mensagem="Execução concluída",
    nivel=logging.INFO,
    plugin_nome="PluginSupertrend",  # Aparece como [PLUGIN:PluginSupertrend]
    detalhes={"pares_processados": 50, "tempo_ms": 120}
)
```

### 5. ANALISE - Processamento de Dados

```python
# Cálculo de indicadores
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.ANALISE,
    nome_origem="PluginIchimoku",
    mensagem="Cálculo de Ichimoku concluído",
    nivel=logging.DEBUG,
    detalhes={"par": "BTCUSDT", "timeframe": "15m", "tenkan_sen": 45000}
)
```

### 6. SINAL - Sinais de Trading

```python
# Sinal LONG
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.SINAL,
    nome_origem="PluginPadroes",
    mensagem="SINAL LONG detectado",
    nivel=logging.INFO,
    tipo_log="sinais",
    detalhes={
        "par": "BTCUSDT",
        "timeframe": "15m",
        "padrao": "Bullish Engulfing",
        "forca": 0.85,
        "indicadores_confirmando": ["Supertrend", "Ichimoku"]
    }
)
```

### 7. FILTRO - Filtro Dinâmico

```python
# Resultado do filtro
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.FILTRO,
    nome_origem="PluginFiltroDinamico",
    mensagem="✓ Filtro concluído: 45/200 pares aprovados",
    nivel=logging.INFO,
    detalhes={
        "total_pares": 200,
        "aprovados": 45,
        "rejeitados": 155,
        "rejeicoes_por_camada": {"liquidez": 100, "maturidade": 50, "atividade": 5}
    }
)
```

### 8. IA - Inteligência Artificial

```python
# Decisão da IA
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.IA,
    nome_origem="PluginIaLlama",
    mensagem="Decisão da IA: HOLD",
    nivel=logging.INFO,
    tipo_log="ia",
    detalhes={
        "par": "BTCUSDT",
        "decisao": "HOLD",
        "confianca": 0.72,
        "pesos_aplicados": {"padroes": 0.4, "indicadores": 0.6},
        "explicacao": "Múltiplos indicadores neutros"
    }
)
```

### 9. UTIL - Utilitários

```python
# Helper/conversor
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.UTIL,
    nome_origem="Conversor",
    mensagem="Conversão de símbolo: BTCUSDT -> BTC/USDT:USDT",
    nivel=logging.DEBUG,
    detalhes={"entrada": "BTCUSDT", "saida": "BTC/USDT:USDT"}
)
```

## 🔍 Formato no Log

O log aparecerá assim:

```
[2025-11-16 21:41:50.123 BRT] [PluginFiltroDinamico] [INFO] [plugin_filtro_dinamico.py:542] [FILTRO] ✓ Filtro concluído: 45/200 pares aprovados | Detalhes: total_pares: 200, aprovados: 45, rejeitados: 155
```

## ✅ Compatibilidade

O sistema antigo ainda funciona! Você pode usar:

```python
# Método antigo (ainda funciona)
self.logger.info("[PluginFiltroDinamico] Mensagem")

# Método novo (com categoria)
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.FILTRO,
    nome_origem="PluginFiltroDinamico",
    mensagem="Mensagem",
    nivel=logging.INFO
)
```

## 🎨 Tags Curtas

Para plugins, use `plugin_nome` para tags curtas:

```python
# Aparece como [PLUGIN:Supertrend]
self.gerenciador_log.log_categoria(
    categoria=CategoriaLog.PLUGIN,
    nome_origem="PluginSupertrend",
    mensagem="Execução concluída",
    plugin_nome="Supertrend"  # Tag curta
)
```

