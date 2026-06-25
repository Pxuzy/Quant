@echo off
cd /d E:\hermes\workspace\Quant
set DATABASE_URL=sqlite:///E:/hermes/workspace/Quant/quant/storage/quant.db
E:\hermes\workspace\Quant\quant\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload
