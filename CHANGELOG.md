# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

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

