@echo off
title Assistente de Resumos MedCel
color 0A

echo Ativando o ambiente virtual da IA...
call venv\Scripts\activate

cls
echo Iniciando o servidor web local...
python -m streamlit run pipeline_medcel.py

pause