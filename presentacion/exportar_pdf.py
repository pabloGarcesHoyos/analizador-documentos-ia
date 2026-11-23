import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CARPETA = Path(__file__).resolve().parent
FUENTE = CARPETA / "presentacion_proyecto.html"
DESTINO = CARPETA.parent / "app" / "presentacion_proyecto.pdf"


def exportar(destino: Path) -> None:
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1600, "height": 900})
        pagina.goto(FUENTE.as_uri(), wait_until="networkidle")
        pagina.emulate_media(media="print")
        pagina.pdf(path=str(destino), width="1600px", height="900px", print_background=True,
                   margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        navegador.close()


if __name__ == "__main__":
    exportar(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO)
