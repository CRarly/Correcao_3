@echo off
chcp 65001 >nul
title Brightspace Grader 2.0 - Especialista
cls
echo ===================================================================
echo             BRIGHTSPACE GRADER 2.0 - MOTOR ESPECIALISTA
echo ===================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao foi encontrado no PATH do sistema.
    pause
    exit /b 1
)

echo Iniciando o Painel do Brightspace Grader 2.0...
python main.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocorreu um erro durante a execucao. Pressione qualquer tecla para sair.
    pause
)

