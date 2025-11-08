# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

## [v1.3.0] - 2025-11-08

### Sistema de Padrões de Trading - Top 10 Implementado

#### Adicionado
- ✅ **PluginPadroes** - Plugin de detecção de padrões técnicos
  - Localização: `plugins/padroes/plugin_padroes.py`
  - Orquestra detecção dos Top 10 padrões de trading
  - Implementa filtro de regime de mercado (Trending vs Range)
  - Sistema de Confidence Decay (decaimento de confiança)
  - Cálculo de score final (technical_score * 0.6 + confidence * 0.4)
  
- ✅ **Top 30 Padrões Implementados** (Top 10 + Próximos 20)
  1. Breakout de suporte/resistência com volume confirmado
  2. Pullback válido após breakout (reteste + suporte segurando)
  3. EMA crossover (9/21) com confirmação de volume
  4. RSI divergence (price × RSI) - bullish/bearish
  5. Bollinger Squeeze + rompimento (BB Width < 0.04 por ≥5 velas)
  6. VWAP rejection / acceptance (preço testa e volta)
  7. Candlestick Engulfing (bull/bear) com volume confirmado
  8. Hammer / Hanging Man + confirmação no fechamento seguinte
  9. Volume spike anomaly (z-score sobre média(20))
  10. False breakout (fechamento de volta dentro da zona)
  
  **Próximos 20 Padrões (11-30):**
  11. Head & Shoulders / Inverse H&S (neckline break)
  12. Double Top / Double Bottom
  13. Triangle (Asc/Desc/Sym) (breakout + volume)
  14. Flag / Pennant (continuation)
  15. Wedge rising / falling (reversão)
  16. Rectangle (range breakout)
  17. Three White Soldiers / Three Black Crows
  18. Morning Star / Evening Star
  19. Tweezer Tops / Tweezer Bottoms
  20. Harami / Harami Cross
  21. Piercing Line / Dark Cloud Cover
  22. Gap types (breakaway / runaway / exhaustion)
  23. MACD divergence + histogram reversal
  24. ATR-based volatility breakout (> k × ATR)
  25. Fibonacci retracement confluence (61.8% + suporte)
  26. Liquidity sweep (long wick into stops)
  27. Harmonic patterns (AB=CD, Gartley) — estrutura básica
  28. Volume–price divergence (decoupling em tendência)
  29. Multi-timeframe confirmation (15m + 1h) — estrutura básica
  30. Order-flow proxy (wick + volume = stop hunt)

- ✅ **Filtro de Regime de Mercado**
  - Detecta Trending vs Range baseado em:
    - `trend_strength = abs(ema_50 - ema_200) / atr_14`
    - `volatility_regime = bb_width.pct_change().rolling(20).std()`
  - Regime Trending: `trend_strength > 1.5` e `volatility_regime < 0.3`
  - Regime Range: caso contrário
  - Campo `regime` obrigatório na telemetria

- ✅ **Confidence Decay**
  - Fórmula: `confidence_score = base_score * exp(-0.01 * days_since_last_win)`
  - Quarentena automática se `confidence_score < 0.5`
  - Peso maior no ensemble se `confidence_score > 0.8`

- ✅ **Tabelas no Banco de Dados**
  - `padroes_detectados`: Padrões detectados com telemetria completa
    - Campos: symbol, timeframe, open_time, tipo_padrao, direcao, score, confidence, regime, suggested_sl, suggested_tp, final_score, meta (JSONB)
  - `padroes_metricas`: Métricas de performance por padrão
    - Campos: tipo_padrao, frequency, precision, recall, expectancy, sharpe_condicional, drawdown_condicional, winrate, avg_rr, total_trades, etc.
  - `padroes_confidence`: Histórico de confidence decay por padrão
    - Campos: tipo_padrao, data_ultimo_win, days_since_last_win, base_score, confidence_score, em_quarentena

- ✅ **Estrutura Modular**
  - Cada padrão é uma função separada (`_detectar_*`)
  - Código vetorizado usando Pandas/NumPy
  - Fácil expansão para os próximos 20 padrões

#### Características
- Modular: cada padrão é uma função separada
- Vetorizado: usa Pandas/NumPy para performance
- Telemetria completa: regime, confidence, métricas
- Persistência automática no banco de dados
- Serialização correta de datetime e tipos numpy/pandas para PostgreSQL

#### Conforme Documentação
- Segue `proxima_atualizacao.md` rigorosamente
- Implementa Top 10 padrões primeiro (PoC)
- Validação temporal implementada (Walk-Forward, Rolling Window, OOS)
- Pronto para backtest completo (simulação de trades)

#### Validação Temporal
- ✅ Método `validar_temporal()` implementado
  - Walk-Forward: 60% treino → 40% teste
  - Rolling Window: 180 dias → recalcula a cada 30 dias (básico)
  - Out-of-Sample (OOS): ≥ 30% dos dados nunca vistos
- ✅ Método `_calcular_metricas()` implementado
  - Frequency: Ocorrências por 1.000 velas
  - Estrutura pronta para métricas completas (precision, expectancy, sharpe, etc.)
- ✅ Persistência automática de métricas no banco

#### Documentação Atualizada
- ✅ `definicao_banco.md` atualizado com campo `testnet` e tabelas de padrões
- ✅ `STATUS_PROJETO.md` atualizado com sistema de padrões
- ✅ `README.md` atualizado com informações sobre padrões de trading
- ✅ `CHANGELOG.md` atualizado com todas as mudanças

#### Versão
- PluginPadroes: v1.0.0
- Schema versão: v1.0.0

---

## [v1.2.0] - 2025-11-05

### PluginBancoDados - Refatoração Completa

#### Adicionado
- ✅ **CRUD Completo Implementado**
  - Método `inserir()` - Inserção de dados com upsert para velas
  - Método `consultar()` - Consulta com filtros, campos e ordenação
  - Método `atualizar()` - Atualização com filtros e validação
  - Método `deletar()` - Exclusão com filtros obrigatórios (segurança)
  
- ✅ **Estrutura de Métodos**
  - Métodos internos com underscore (_inserir_velas, _consultar, etc.)
  - Métodos públicos sem underscore (inserir, consultar, atualizar, deletar)
  - Separação clara entre lógica interna e interface pública
  
- ✅ **Logs Padronizados**
  - Formato: `[BancoDados][INSERT]`, `[UPDATE]`, `[SELECT]`, `[DELETE]`
  - Facilita depuração e auditoria
  - Logs informativos por operação com detalhes
  
- ✅ **Retorno Padronizado**
  - Dicionário padronizado para todas as operações CRUD
  - Facilita integração com IA
  - Estrutura:
    ```python
    {
        "sucesso": bool,
        "operacao": str,  # INSERT, UPDATE, SELECT, DELETE
        "tabela": str,
        "dados": Any,
        "mensagem": str,
        "linhas_afetadas": int,
        "erro": Optional[str],
        "timestamp": str
    }
    ```
  
- ✅ **Melhorias de Segurança**
  - Uso de `sql.Identifier` para prevenir SQL injection
  - Validação de filtros obrigatórios em UPDATE e DELETE
  - Validação de dados antes de inserção
  
- ✅ **Métodos Auxiliares**
  - `_formatar_retorno()` - Formata retorno padronizado
  - `_inserir_generico()` - Inserção genérica para qualquer tabela
  - `atualizar_view_materializada()` - Atualiza view materializada
  
- ✅ **Documentação Completa**
  - Docstrings em todos os métodos
  - Exemplos de uso na documentação
  - Tipagem completa com type hints

#### Melhorado
- ✅ Estrutura de código mais organizada
- ✅ Tratamento de erros mais robusto
- ✅ Logs mais informativos e padronizados
- ✅ Retorno padronizado para facilitar integração com IA

#### Versão
- PluginBancoDados: v1.0.0 → v1.2.0
- Schema versão: v1.0.0 → v1.2.0

---

## [v1.1.0] - 2025-11-05

### Melhorias e Robustez

#### Adicionado
- ✅ Enums para Status e Tipos (StatusExecucao, TipoPlugin, NivelGravidade)
- ✅ Metadados de Plugin (autor, data, dependências)
- ✅ Monitoramento e Telemetria (tolerância de erro temporal, armazenamento)
- ✅ Ações Automáticas (ERROR → recuperação, CRITICAL → reinicialização)
- ✅ Suporte Assíncrono (executar_async())
- ✅ GerenciadorBot Melhorado (tratamento de empates)
- ✅ Banco de Dados Expandido (campo exchange, view materializada, histórico de schema)

---

## [v1.0.0] - 2025-01-XX

### Adicionado
- Estrutura base do projeto conforme regras de ouro
- Classe base `Plugin` com ciclo de vida completo
- `GerenciadorLog` com sistema de logs estruturado por tipo
- `GerenciadorBanco` para persistência de dados com validação
- `GerenciadorPlugins` para orquestração de plugins
- `GerenciadorBot` para controle de trades (Sistema 6/8)
- `ConfigManager` com suporte a testnet/mainnet Bybit
- `main.py` como ponto de entrada do sistema
- Sistema de diretórios de logs organizados por tipo

### Estrutura
- `plugins/base_plugin.py`: Classe base para todos os plugins
- `plugins/gerenciadores/`: Gerenciadores principais do sistema
- `plugins/indicadores/`: Preparado para 8 plugins de indicadores
- `utils/config.py`: Configuração centralizada
- `utils/logging_config.py`: Helpers de logging

