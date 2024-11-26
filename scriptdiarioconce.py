import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from dotenv import load_dotenv
import os
import time

load_dotenv()
palabras_clave = os.getenv("PALABRAS_CLAVE").split(',')

db_config = {
    'user': 'root',              
    'password': 'your_pass', #Cambiar contraseña
    'host': 'localhost',          
    'database': 'noticias_db'     
}

def create_database_and_table():
    conn = mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password']
    )
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS noticias_db")
    cursor.execute("USE noticias_db")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS noticias (
            id INT AUTO_INCREMENT PRIMARY KEY,
            titulo TEXT,
            fecha TEXT,
            descripcion TEXT,
            enlace TEXT,
            palabra_clave TEXT
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def save_to_database(noticias):
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    for noticia in noticias:
        # Verificar si el enlace existe en la base de datos
        cursor.execute("SELECT COUNT(*) FROM noticias WHERE enlace = %s", (noticia['enlace'],))
        result = cursor.fetchone()
        
        if result[0] == 0:  
            cursor.execute('''
                INSERT INTO noticias (titulo, fecha, descripcion, enlace, palabra_clave) 
                VALUES (%s, %s, %s, %s, %s)
            ''', (noticia['titulo'], noticia['fecha'], noticia['descripcion'], noticia['enlace'], noticia['palabra_clave']))
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Datos guardados en la base de datos.")

def extract_diario_concepcion(palabra_clave):
    options = Options()
    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    
    adblock_path = "C:\\Program Files\\Selenium\\GIGHMMPIOBKLFEPJOCNAMGKKBIGLIDOM_6_10_0_0.crx"
    options.add_extension(adblock_path)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    if len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[1])
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

    noticias = []
    enlaces_guardados = set()
    
    for page_num in range(1, 11):
        url = f"https://www.diarioconcepcion.cl/search?s={palabra_clave}&page={page_num}"
        driver.get(url)
        time.sleep(5)
        
        print(f"Extrayendo noticias para '{palabra_clave}' en la página {page_num}...")
        titulos = driver.find_elements(By.CLASS_NAME, "main-headline__title")
        fechas = driver.find_elements(By.CLASS_NAME, "main-headline__category--gray")
        descripciones = driver.find_elements(By.CLASS_NAME, "main-headline__text")
        
        for i in range(min(len(titulos), len(fechas), len(descripciones))):
            titulo_element = titulos[i]
            titulo = titulo_element.text.strip()
            fecha = fechas[i].text.strip()
            descripcion = descripciones[i].text.strip()
            
            try:
                enlace = titulo_element.find_element(By.TAG_NAME, 'a').get_attribute('href')
                if enlace not in enlaces_guardados:
                    noticias.append({
                        'titulo': titulo,
                        'fecha': fecha,
                        'descripcion': descripcion,
                        'enlace': enlace,
                        'palabra_clave': palabra_clave
                    })
                    enlaces_guardados.add(enlace)
            except:
                enlace = "No disponible"
        
    driver.quit()
    return noticias

create_database_and_table()

for palabra in palabras_clave:
    noticias_diario_concepcion = extract_diario_concepcion(palabra)
    if noticias_diario_concepcion:
        save_to_database(noticias_diario_concepcion)
        print(f"Noticias guardadas en la base de datos para '{palabra}'.")
    else:
        print(f"No se encontraron noticias para '{palabra}'.")