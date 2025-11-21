# Smart_Trader - Sistema 6/8 Trading Bot

Bot de trading automatizado para Bybit utilizando 8 indicadores técnicos com validação cruzada (Sistema 6/8).

## 📋 Descrição

O sistema utiliza 8 indicadores técnicos e executa trades quando **6 ou mais** indicadores apontam na mesma direção. Qualquer reversão em 1 indicador encerra a posição imediatamente.

### Os 8 Indicadores

1. **Ichimoku Cloud** (9,26,52,26)
2. **Supertrend** (10, 3)
3. **Bollinger Bands + Squeeze** (20, 2)
4. **Volume + Breakout**
5. **EMA Crossover** (9/21)
6. **MACD** (12,26,9)
7. **RSI** (14)
8. **VWAP** (intraday)

## 🏗️ Estrutura do Projeto

```
Smart_Trader/
├── main.py                 # Ponto de entrada principal
├── .env                    # Configurações sensíveis (não versionado)
├── CHANGELOG.md            # Histórico de alterações
├── requirements.txt        # Dependências Python
│
├── plugins/
│   ├── __init__.py
│   ├── base_plugin.py      # Classe base para todos os plugins
│   │
│   ├── indicadores/        # Plugins de indicadores técnicos
│   │   ├── __init__.py
│   │   ├── plugin_dados_velas.py  # Coleta de dados OHLCV
│   │   ├── plugin_ichimoku.py     # ✅ Ichimoku Cloud
│   │   ├── plugin_supertrend.py   # ✅ Supertrend
│   │   ├── plugin_bollinger.py    # ✅ Bollinger Bands + Squeeze
│   │   ├── plugin_volume.py       # ✅ Volume + Breakout
│   │   ├── plugin_ema.py          # ✅ EMA Crossover
│   │   ├── plugin_macd.py         # ✅ MACD
│   │   ├── plugin_rsi.py          # ✅ RSI
│   │   └── plugin_vwap.py         # ✅ VWAP
│   │
│   ├── conexoes/           # Plugins de conexão
│   │   ├── __init__.py
│   │   └── plugin_bybit_conexao.py  # Conexão com API Bybit
│   │
│   ├── padroes/            # Plugins de padrões de trading
│   │   ├── __init__.py
│   │   └── plugin_padroes.py  # Sistema de detecção de padrões (Top 30)
│   │
│   ├── backtest/           # Plugins de backtest
│   │   ├── __init__.py
│   │   └── plugin_backtest.py  # Simulação de trades
│   │
│   ├── ia/                 # Plugins de IA
│   │   ├── __init__.py
│   │   └── plugin_ia_llama.py  # Inteligência Artificial (Llama)
│   │
│   ├── plugin_banco_dados.py  # Plugin de banco de dados PostgreSQL
│   │
│   └── gerenciadores/      # Gerenciadores principais
│       ├── __init__.py
│       ├── gerenciador.py           # Classe base
│       ├── gerenciador_log.py       # Sistema de logs v2.0
│       ├── gerenciador_banco.py     # Persistência de dados
│       ├── gerenciador_plugins.py   # Orquestração de plugins
│       └── gerenciador_bot.py       # Controle de trades (Sistema 6/8)
│
├── utils/
│   ├── __init__.py
│   ├── main_config.py      # Configuração centralizada (main_config.py)
│   └── logging_config.py   # Helpers de logging
│
└── logs/                   # Logs organizados por tipo (v2.0)
    ├── system/             # Sistema, inicialização, erros gerais
    ├── banco/              # Operações do banco de dados
    ├── sinais/             # Sinais de trading detectados
    ├── erros/              # Erros do sistema
    ├── warnings/           # Avisos e inconsistências
    ├── critical/           # Erros críticos
    ├── padroes/            # Padrões detectados
    ├── ia/                 # Análises e insights da IA
    ├── spot/               # Mercado à vista
    └── futures/            # Contratos perpétuos/alavancados
```

## 🚀 Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/MarcusAbenAthar/Smart_Trader.git
cd Smart_Trader
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure o arquivo .env

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# Bybit API (Mainnet ou Testnet)
BYBIT_TESTNET=True  # True para testnet, False para mainnet
BYBIT_API_KEY=sua_api_key_aqui
BYBIT_API_SECRET=sua_api_secret_aqui
TESTNET_BYBIT_API_KEY=sua_testnet_api_key  # Se usar testnet
TESTNET_BYBIT_API_SECRET=sua_testnet_api_secret  # Se usar testnet

# Banco de Dados PostgreSQL
DB_HOST=localhost
DB_NAME=smarttrader
DB_USER=seu_usuario
DB_PASSWORD=sua_senha

# Telegram (opcional, para notificações)
TELEGRAM_BOT_TOKEN=seu_bot_token
TELEGRAM_CHAT_ID=seu_chat_id
```

## 🎯 Uso

### Executar o bot

```bash
python main.py
```

### Modo Testnet vs Mainnet

Edite a variável `BYBIT_TESTNET` no arquivo `.env`:
- `True`: Usa a testnet (recomendado para testes)
- `False`: Usa a mainnet (ambiente real)

## 📊 Estratégia de Trading

### Regras de Entrada

- **Mínimo 6/8 indicadores** devem estar alinhados na mesma direção
- **Filtros obrigatórios:**
  1. Cloud + Supertrend devem estar OK
  2. Squeeze BB (< 0.04 por ≥5 velas)
  3. Rompimento BB + Volume > 2x média

### Regras de Saída

Qualquer um dos seguintes eventos fecha a posição imediatamente:
- Supertrend muda de cor
- Preço cruza o lado oposto da Cloud
- MACD histograma reverte
- Volume < 40% da média(20)
- Distância VWAP > 3% sem volume > 1.5x média

### Gerenciamento de Risco

- **SL**: Nível mais próximo entre base da Cloud ou Supertrend
- **TP**: 2.3 × distância do SL (R:R fixo)
- **Trailing Stop**: Supertrend (ativa após +1.0 × SL)
- **Tamanho da posição**: Ajustado por ATR(14) e liquidez (máx 2% capital)

## 🔧 Configuração de Pares

Configurações padrão por par (em `utils/main_config.py`):

| Par       | Timeframe | Alavancagem | Risco |
|-----------|-----------|-------------|-------|
| BTC/USDT  | 15m       | 3x          | 1.5%  |
| ETH/USDT  | 15m       | 3x          | 1.2%  |
| SOL/USDT  | 5m        | 2x          | 1.0%  |
| XRP/USDT  | 5m        | 2x          | 0.8%  |

## 📝 Documentação

- **Regras de Ouro**: `docs/regras_de_ouro.md`
- **Definição da Estratégia**: `docs/definicao_estrategia.md`
- **Definição do Banco**: `docs/definicao_banco.md`
- **Próxima Atualização**: `docs/proxima_atualizacao.md`
- **Changelog**: `CHANGELOG.md`
- **Status do Projeto**: `STATUS_PROJETO.md`

## 🧩 Arquitetura

### Plugins

Todos os plugins seguem o padrão:
- Herdam de `Plugin` (em `plugins/base_plugin.py`)
- Ciclo de vida: `inicializar()` → `executar()` → `finalizar()`
- Armazenam dados em `self.dados_completos` (crus e analisados)
- Persistem dados via `GerenciadorBanco`

### Sistema de Armazenamento de Indicadores Técnicos (v1.4.0)

**Tabelas de Indicadores:**
- ✅ 8 tabelas criadas no banco de dados para armazenar dados dos indicadores
- ✅ Persistência automática após cada cálculo
- ✅ Histórico completo disponível para análise
- ✅ Upsert automático para evitar duplicatas
- ✅ Índices otimizados para consultas rápidas

**Indicadores Armazenados:**
- `indicadores_ichimoku`: Ichimoku Cloud (tenkan, kijun, senkou_a, senkou_b, chikou)
- `indicadores_supertrend`: Supertrend (valor, direção)
- `indicadores_bollinger`: Bollinger Bands (upper, middle, lower, width, squeeze)
- `indicadores_volume`: Volume (médio, ratio, breakout)
- `indicadores_ema`: EMA Crossover (rapida, lenta, crossover)
- `indicadores_macd`: MACD (line, signal, histogram)
- `indicadores_rsi`: RSI (valor)
- `indicadores_vwap`: VWAP (valor, distância percentual)

### Filtro Dinâmico do SmartTrader (v1.4.0)

**Sistema de Seleção Inteligente de Pares:**
- ✅ 4 camadas de filtro progressivas
- ✅ 100% dinâmico, recalculado a cada ciclo
- ✅ Adaptado ao estado real do mercado

**Camadas de Filtro:**
1. **Liquidez Diária Real**: Mediana de Volume 24h (remove pares sem liquidez)
2. **Maturidade do Par**: Idade Mínima >= 60 dias (remove tokens novos)
3. **Atividade Recente**: Volume médio 15m e 1h > 0 (remove pares inativos)
4. **Integridade Técnica**: Timeframes vazios e fail_rate < 30% (remove pares problemáticos)

**Benefícios:**
- ❌ Menos pares inúteis processados
- ❌ Menos requisições desperdiçadas
- ❌ Menos timeframes vazios
- ✅ Mais velocidade e consistência
- ✅ Mais precisão e estabilidade

### Sistema de Padrões de Trading (v1.3.0)

O sistema implementa detecção de padrões técnicos conforme `proxima_atualizacao.md`:

**Top 30 Padrões Implementados (100% Completo - v1.5.2):**
- ✅ Top 10 padrões principais
- ✅ Próximos 20 padrões adicionais
- ✅ Harmonic patterns (#27) - Completo (AB=CD, Gartley, Butterfly, Bat, Crab) com detecção robusta e validação Fibonacci rigorosa
- ✅ Multi-timeframe confirmation (#29) - Completo com acesso real a múltiplos timeframes e sistema de pesos

**Características:**
- Filtro de Regime de Mercado (Trending vs Range)
- Confidence Decay (decaimento de confiança)
- Score final: `(technical_score * 0.6) + (confidence * 0.4)`
- Persistência automática no banco de dados
- Validação Temporal implementada (Walk-Forward, OOS e Rolling Window completos)
- ✅ Backtest completo implementado (PluginBacktest)
- ✅ Ensemble de Padrões implementado e integrado
- ✅ Harmonic Patterns com detecção robusta e validação Fibonacci
- ✅ Multi-Timeframe Confirmation com acesso real a múltiplos timeframes

### Sistema de Logs (v2.0)

**Estrutura de Logs:**
- `logs/system/` - Sistema, inicialização, erros gerais
- `logs/banco/` - Operações do banco de dados
- `logs/sinais/` - Sinais de trading detectados
- `logs/erros/` - Erros do sistema
- `logs/warnings/` - Avisos e inconsistências
- `logs/critical/` - Erros críticos
- `logs/padroes/` - Padrões detectados
- `logs/ia/` - Análises e insights da IA
- `logs/spot/` - Mercado à vista
- `logs/futures/` - Contratos perpétuos/alavancados

**Características:**
- Formato BRT (São Paulo) com milissegundos
- Rastreabilidade total: `[arquivo:linha]` em todas as mensagens
- Logs consolidados por par após análise completa
- Execução paralela de indicadores com logs consolidados
- Logs de sinais automáticos quando 6/8 indicadores alinhados

### Gerenciadores

- **GerenciadorLog**: Sistema de logs estruturado
- **GerenciadorBanco**: Validação e persistência de dados
- **GerenciadorPlugins**: Orquestração do ciclo de vida dos plugins
- **GerenciadorBot**: Controle de trades e validação 6/8

## ⚠️ Avisos

- **SEMPRE use testnet para testes**
- **Nunca compartilhe suas chaves API**
- **O bot opera com capital real em mainnet - use com cuidado**
- **Recomendado**: Comece com valores baixos até validar a estratégia

## 📄 Licença

Ver arquivo `LICENSE` para detalhes.

## 🔗 Links

- Repositório: https://github.com/MarcusAbenAthar/Smart_Trader
- Documentação: `docs/`

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, siga as regras definidas em `docs/regras_de_ouro.txt`.

---

**Desenvolvido seguindo as Regras de Ouro do projeto**
