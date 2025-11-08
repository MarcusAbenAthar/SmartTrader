#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""

Script para corrigir problemas de encoding em arquivos Python.

Converte caracteres mal codificados como "Histórico" para "Histórico"

"""



import os

import re

from pathlib import Path



# Mapeamento de caracteres mal codificados para corretos

CORRECOES = {

    # Caracteres comuns

    'á': 'á',  # á

    'é': 'é',  # é

    'í': 'í',  # í

    'ó': 'ó',  # ó

    'ú': 'ú',  # ú

    'ã': 'ã',  # ã

    'ç': 'ç',  # ç

    'õ': 'õ',  # õ

    'ê': 'ê',  # ê

    'ô': 'ô',  # ô

    'Í': 'Í',   # Í (pode ser problema de encoding)

    'â': 'â',  # â

    'ü': 'ü',  # ü

    'ñ': 'ñ',  # ñ

    

    # Palavras comuns mal codificadas

    'conexão': 'conexão',

    'operações': 'operações',

    'operação': 'operação',

    'Métodos': 'Métodos',

    'métodos': 'métodos',

    'públicos': 'públicos',

    'dicionário': 'dicionário',

    'integração': 'integração',

    'conexões': 'conexões',

    'transações': 'transações',

    'Características': 'Características',

    'características': 'características',

    'Validação': 'Validação',

    'configurável': 'configurável',

    'Instância': 'Instância',

    'Configuração': 'Configuração',

    'codificação': 'codificação',

    'Último': 'Último',

    'inválidos': 'inválidos',

    'válido': 'válido',

    'parâmetros': 'parâmetros',

    'encontradas': 'encontradas',

    'necessárias': 'necessárias',

    'Obtém': 'Obtém',

    'Devolve': 'Devolve',

    'Útil': 'Útil',

    'padronização': 'padronização',

    'bem-sucedida': 'bem-sucedida',

    'Número': 'Número',

    'inserção': 'inserção',

    'específicos': 'específicos',

    'consulta': 'consulta',

    'condições': 'condições',

    'ordenação': 'ordenação',

    'atualização': 'atualização',

    'exclusão': 'exclusão',

    'formação': 'formação',

    'possível': 'possível',

    'genérica': 'genérica',

    'têm': 'têm',

    'segurança': 'segurança',

    'rápidas': 'rápidas',

    'estatísticas': 'estatísticas',

    'histórico': 'histórico',

    'versões': 'versões',

    'versão': 'versão',

    'mudanças': 'mudanças',

    'Descrição': 'Descrição',

    'já': 'já',

    'médias': 'médias',

    'análises': 'análises',

    'verificação': 'verificação',

    'saúde': 'saúde',

    'execução': 'execução',

    'está': 'está',

    'deleção': 'deleção',

    'perigosa': 'perigosa',

}



def corrigir_arquivo(caminho_arquivo):

    """Corrige encoding em um arquivo."""

    try:

        # Lê o arquivo como bytes primeiro

        with open(caminho_arquivo, 'rb') as f:

            conteudo_bytes = f.read()

        

        # Tenta decodificar como UTF-8

        try:

            conteudo = conteudo_bytes.decode('utf-8')

        except UnicodeDecodeError:

            # Se falhar, tenta latin-1

            conteudo = conteudo_bytes.decode('latin-1')

        

        # Aplica correções

        conteudo_original = conteudo

        for errado, correto in CORRECOES.items():

            conteudo = conteudo.replace(errado, correto)

        

        # Se houve mudanças, salva o arquivo

        if conteudo != conteudo_original:

            with open(caminho_arquivo, 'w', encoding='utf-8') as f:

                f.write(conteudo)

            print(f"✓ Corrigido: {caminho_arquivo}")

            return True

        return False

        

    except Exception as e:

        print(f"✗ Erro ao processar {caminho_arquivo}: {e}")

        return False



def main():

    """Processa todos os arquivos Python do projeto."""

    base_dir = Path('.')

    arquivos_corrigidos = 0

    

    # Lista de arquivos Python para processar

    arquivos_python = list(base_dir.rglob('*.py'))

    

    print(f"Processando {len(arquivos_python)} arquivo(s) Python...")

    

    for arquivo in arquivos_python:

        # Ignora arquivos em venv e __pycache__

        if 'venv' in str(arquivo) or '__pycache__' in str(arquivo):

            continue

        

        if corrigir_arquivo(arquivo):

            arquivos_corrigidos += 1

    

    print(f"\n✓ Correção concluída! {arquivos_corrigidos} arquivo(s) corrigido(s).")



if __name__ == '__main__':

    main()



