import sys
from pathlib import Path

# Comentario: permite executar este arquivo chamando o app principal.
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from main import app  # noqa: E402
