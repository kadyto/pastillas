"""Servidor de pruebas con respuestas sintéticas; nunca se incluye en la imagen."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import medicine_info
from medicine_fixture import fetch
medicine_info.fetch_json=fetch
from app.server import main
main()
