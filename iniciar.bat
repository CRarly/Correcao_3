@echo off
chcp 65001 >nul
title Brightspace Grader 3.0 - Especialista Integrado
cls
echo ===================================================================
echo             BRIGHTSPACE GRADER 3.0 - MOTOR INTEGRADO
echo ===================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao foi encontrado no PATH do sistema.
    pause
    exit /b 1
)

echo Iniciando o Painel do Brightspace Grader 3.0...
python main.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocorreu um erro durante a execucao. Pressione qualquer tecla para sair.
    pause
)

