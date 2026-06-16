"""
Scraper de cartas de Mitos y Leyendas a partir de la Wiki de Fandom.

Fuente: https://myl.fandom.com/es  (MediaWiki + Portable Infobox)
Estrategia:
  1. Recorrer el arbol de categorias desde una categoria raiz (por defecto
     "Categoria:Lista de Cartas") para descubrir todas las paginas de cartas.
  2. Para cada pagina, renderizar el HTML via la API (action=parse) y extraer
     los campos del infobox (tipo, raza, edicion, coste, fuerza, habilidad, etc.).
  3. Guardar el resultado en JSON y/o CSV.

No usa Selenium: la API de MediaWiki entrega datos estructurados directamente.

Uso:
    python scriptmitosyleyendas.py --formats json,csv --output-dir ./data

Requisitos: ver requirements.txt (requests, beautifulsoup4, lxml).
"""

import argparse
import csv
import json
import os
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

API_BASE = "https://myl.fandom.com/es/api.php"
WIKI_BASE = "https://myl.fandom.com/es/wiki/"

# User-Agent descriptivo (buena practica al consumir APIs de MediaWiki).
HEADERS = {
    "User-Agent": (
        "media-scrapper/1.0 (mitos y leyendas card scraper; "
        "https://github.com/diegoalrv/media-scrapper)"
    )
}


def crear_sesion():
    """Crea una sesion de requests con cabeceras y reintentos basicos."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def api_get(session, params, max_reintentos=4):
    """Llama a la API de MediaWiki devolviendo JSON, con reintentos y backoff."""
    params = dict(params)
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")

    espera = 2
    for intento in range(max_reintentos):
        try:
            resp = session.get(API_BASE, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if intento == max_reintentos - 1:
                raise
            print(f"  ! Error de red ({e}); reintentando en {espera}s...")
            time.sleep(espera)
            espera *= 2


def listar_miembros_categoria(session, categoria, tipos=("subcat", "page")):
    """Devuelve (subcategorias, paginas) de una categoria, manejando paginacion."""
    subcategorias = []
    paginas = []
    cmcontinue = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": categoria,
            "cmlimit": "500",
            "cmtype": "|".join(tipos),
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = api_get(session, params)
        for miembro in data.get("query", {}).get("categorymembers", []):
            # ns 14 = categoria, ns 0 = articulo normal
            if miembro.get("ns") == 14:
                subcategorias.append(miembro["title"])
            elif miembro.get("ns") == 0:
                paginas.append(miembro["title"])

        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break

    return subcategorias, paginas


def descubrir_paginas_cartas(session, categoria_raiz, max_profundidad):
    """Recorre el arbol de categorias (BFS) y junta todas las paginas candidatas."""
    visitadas = set()
    titulos_cartas = set()

    # cola de (categoria, profundidad)
    cola = [(categoria_raiz, 0)]
    while cola:
        categoria, profundidad = cola.pop(0)
        if categoria in visitadas:
            continue
        visitadas.add(categoria)

        print(f"Explorando categoria: {categoria} (profundidad {profundidad})")
        subcats, paginas = listar_miembros_categoria(session, categoria)

        for titulo in paginas:
            titulos_cartas.add(titulo)

        if profundidad < max_profundidad:
            for subcat in subcats:
                if subcat not in visitadas:
                    cola.append((subcat, profundidad + 1))

    return sorted(titulos_cartas)


def _texto_limpio(elemento):
    """Texto plano de un nodo BeautifulSoup, colapsando espacios."""
    return " ".join(elemento.get_text(" ", strip=True).split())


def parsear_carta(session, titulo):
    """Renderiza una pagina y extrae los campos del infobox.

    Devuelve un dict con los datos de la carta o None si la pagina no
    contiene un infobox (es decir, probablemente no es una carta).
    """
    data = api_get(
        session,
        {
            "action": "parse",
            "page": titulo,
            "prop": "text|categories",
            "redirects": "1",
        },
    )

    parse = data.get("parse")
    if not parse:
        return None

    html = parse.get("text", "")
    if isinstance(html, dict):  # formatversion 1 envuelve en {"*": ...}
        html = html.get("*", "")

    soup = BeautifulSoup(html, "lxml")

    carta = {
        "nombre": parse.get("title", titulo),
        "url": urljoin(WIKI_BASE, titulo.replace(" ", "_")),
    }

    # --- Portable Infobox (estructura estandar de Fandom) ---
    infobox = soup.select_one("aside.portable-infobox")
    encontrado = False
    if infobox:
        encontrado = True
        # Imagen principal
        img = infobox.select_one(".pi-image img")
        if img and img.get("src"):
            carta["imagen"] = img["src"]

        # Pares etiqueta/valor
        for item in infobox.select(".pi-item.pi-data"):
            label_el = item.select_one(".pi-data-label")
            value_el = item.select_one(".pi-data-value")
            if not value_el:
                continue
            clave = _texto_limpio(label_el) if label_el else item.get("data-source", "campo")
            clave = clave.rstrip(":").strip().lower() or "campo"
            carta[clave] = _texto_limpio(value_el)

        # Titulo interno del infobox (a veces difiere del titulo de pagina)
        titulo_ib = infobox.select_one(".pi-title")
        if titulo_ib:
            carta["nombre"] = _texto_limpio(titulo_ib)

    # --- Fallback: infobox clasico en tabla ---
    if not encontrado:
        tabla = soup.select_one("table.infobox")
        if tabla:
            encontrado = True
            for fila in tabla.select("tr"):
                th = fila.find("th")
                td = fila.find("td")
                if th and td:
                    clave = _texto_limpio(th).rstrip(":").strip().lower()
                    if clave:
                        carta[clave] = _texto_limpio(td)
            img = tabla.select_one("img")
            if img and img.get("src"):
                carta.setdefault("imagen", img["src"])

    if not encontrado:
        return None

    # Categorias (ediciones, tipos, etc.)
    categorias = [c.get("category") or c.get("*", "") for c in parse.get("categories", [])]
    categorias = [c.replace("_", " ") for c in categorias if c]
    if categorias:
        carta["categorias"] = categorias

    return carta


def guardar_json(cartas, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(cartas, f, ensure_ascii=False, indent=2)
    print(f"JSON guardado en {ruta} ({len(cartas)} cartas).")


def guardar_csv(cartas, ruta):
    # Union de todas las claves para tener columnas consistentes.
    columnas = []
    for carta in cartas:
        for clave in carta:
            if clave not in columnas:
                columnas.append(clave)

    with open(ruta, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        for carta in cartas:
            fila = {}
            for clave, valor in carta.items():
                # Listas (p.ej. categorias) -> texto separado por "; "
                fila[clave] = "; ".join(valor) if isinstance(valor, list) else valor
            writer.writerow(fila)
    print(f"CSV guardado en {ruta} ({len(cartas)} cartas).")


def main():
    parser = argparse.ArgumentParser(
        description="Scraper de cartas de Mitos y Leyendas (Wiki Fandom)."
    )
    parser.add_argument(
        "--root-category",
        default="Categoría:Lista de Cartas",
        help="Categoria raiz desde la que descubrir las cartas.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Profundidad maxima al recorrer el arbol de categorias.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limitar la cantidad de cartas a procesar (0 = sin limite). Util para pruebas.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Pausa en segundos entre peticiones para no saturar el servidor.",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directorio donde guardar los archivos de salida.",
    )
    parser.add_argument(
        "--formats",
        default="json,csv",
        help="Formatos de salida separados por coma: json,csv.",
    )
    args = parser.parse_args()

    formatos = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    os.makedirs(args.output_dir, exist_ok=True)

    session = crear_sesion()

    print("== Descubriendo paginas de cartas ==")
    titulos = descubrir_paginas_cartas(session, args.root_category, args.max_depth)
    print(f"Se encontraron {len(titulos)} paginas candidatas.\n")

    if args.limit > 0:
        titulos = titulos[: args.limit]
        print(f"(Limitando a {len(titulos)} por --limit)\n")

    cartas = []
    print("== Extrayendo datos de cada carta ==")
    for i, titulo in enumerate(titulos, 1):
        try:
            carta = parsear_carta(session, titulo)
        except Exception as e:  # no abortar todo por una carta problematica
            print(f"[{i}/{len(titulos)}] ERROR en '{titulo}': {e}")
            continue

        if carta:
            cartas.append(carta)
            print(f"[{i}/{len(titulos)}] OK  {carta['nombre']}")
        else:
            print(f"[{i}/{len(titulos)}] -- '{titulo}' sin infobox, omitida")

        time.sleep(args.delay)

    if not cartas:
        print("\nNo se extrajo ninguna carta. Revisa --root-category o el acceso de red.")
        sys.exit(1)

    print(f"\nTotal de cartas extraidas: {len(cartas)}")

    if "json" in formatos:
        guardar_json(cartas, os.path.join(args.output_dir, "cartas_mitos_y_leyendas.json"))
    if "csv" in formatos:
        guardar_csv(cartas, os.path.join(args.output_dir, "cartas_mitos_y_leyendas.csv"))


if __name__ == "__main__":
    main()
