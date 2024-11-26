import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import os
import time
from dotenv import load_dotenv

load_dotenv()

db_config = {
    'user': 'root',  
    'password': 'your_pass',  #Cambiar contraseña
    'host': 'localhost',
    'database': 'biobionoticias_db'
}

palabras_clave = os.getenv("PALABRAS_CLAVE", "").split(",")

def create_database_and_table():
    """Crear la base de datos y la tabla si no existen."""
    conn = mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password']
    )
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS biobionoticias_db")
    cursor.execute("USE biobionoticias_db")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS biobio_noticias (
            id INT AUTO_INCREMENT PRIMARY KEY,
            titulo TEXT,
            fecha_hora TEXT,
            enlace VARCHAR(255) UNIQUE
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()
    print("Base de datos y tabla creadas/verificadas correctamente.")


def save_to_database(noticias):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    for noticia in noticias:
        try:
            cursor.execute('''
                INSERT IGNORE INTO biobio_noticias (titulo, fecha_hora, enlace)
                VALUES (%s, %s, %s)
            ''', (noticia['titulo'], noticia['fecha_hora'], noticia['enlace']))
        except mysql.connector.Error as e:
            print(f"Error al guardar en la base de datos: {e}")
            continue
    conn.commit()
    cursor.close()
    conn.close()
    print("Datos guardados en la base de datos correctamente.")

def cerrar_publicidad(driver):
    time.sleep(5)
    try:
        close_button = driver.find_element(By.ID, "btnClose")
        if close_button.is_displayed():
            close_button.click()
    except Exception as e:
        print(f"No se encontró el botón de cierre de la publicidad: {e}")

def iniciar_driver():
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    
    adblock_path = "C:\\Program Files\\Selenium\\GIGHMMPIOBKLFEPJOCNAMGKKBIGLIDOM_6_10_0_0.crx"
    options.add_extension(adblock_path)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def extraer_noticias(driver, palabra_clave):
    noticias = []
    enlaces_guardados = set()  #Evitar duplicados
    driver.get("https://www.biobiochile.cl/lista/categorias/region-del-bio-bio")
    cerrar_publicidad(driver)

    try:
        search_icon = driver.find_element(By.CSS_SELECTOR, "i.fal.fa-fw.fa-search")
        search_icon.click()
        print("Ícono de búsqueda activado.")
    except Exception as e:
        print(f"Error al activar la búsqueda: {e}")
        return []

    try:
        search_box = driver.find_element(By.CLASS_NAME, "search-input")
        search_box.send_keys(palabra_clave)
        search_box.send_keys("\n")
        print(f"Búsqueda de '{palabra_clave}' enviada.")
    except Exception as e:
        print(f"Error al encontrar el campo de búsqueda: {e}")
        return []

    time.sleep(5)

    for _ in range(10):  
        articles = driver.find_elements(By.CLASS_NAME, "article-text-container")
        for article in articles:
            try:
                titulo_element = article.find_element(By.CLASS_NAME, "article-title")
                titulo = titulo_element.text.strip()
                enlace = article.find_element(By.XPATH, "../..").get_attribute("href")  
                fecha_hora = article.find_element(By.CLASS_NAME, "article-date-hour").text.strip()

                #Verificar duplicados
                if enlace not in enlaces_guardados:
                    noticias.append({
                        'titulo': titulo,
                        'fecha_hora': fecha_hora,
                        'enlace': enlace
                    })
                    enlaces_guardados.add(enlace)
            except Exception as e:
                print(f"Error al extraer información de la noticia: {e}")
                continue

        try:
            more_news_button = driver.find_element(By.CLASS_NAME, "fetch-btn")
            driver.execute_script("arguments[0].click();", more_news_button)
            print("Cargando más noticias...")
            time.sleep(5)
        except Exception as e:
            print(f"No se pudo cargar más noticias: {e}")
            break

    return noticias

def main():
    """Función principal."""
    if not palabras_clave or palabras_clave[0].strip() == "":
        print("No se encontraron palabras clave en el archivo .env.")
        return

    palabra_clave = palabras_clave[0].strip()
    driver = iniciar_driver()
    cerrar_pestana_instalacion_adblock(driver)

    noticias = extraer_noticias(driver, palabra_clave)

    if noticias:
        filename = f"extraccion_biobiochile_{palabra_clave}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            for noticia in noticias:
                f.write(f"Titulo: {noticia['titulo']}\n")
                f.write(f"Fecha y Hora: {noticia['fecha_hora']}\n")
                f.write(f"Enlace: {noticia['enlace']}\n\n")
        print(f"Noticias guardadas en '{filename}'.")

        save_to_database(noticias)
    else:
        print(f"No se encontraron noticias sobre '{palabra_clave}'.")

    driver.quit()

if __name__ == "__main__":
    create_database_and_table()
    main()