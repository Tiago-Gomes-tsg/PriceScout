from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from urllib.parse import quote
from selenium import webdriver
from typing import TypedDict
import pandas as pd
import numpy as np
import unicodedata
import time
import re

class Produto(TypedDict):
    nome: str
    preco_original: float
    preco_atual: float
    loja: str
    link: str
    imagem: str

class HardwareScraper:
    def __init__(self) -> None:
        self.options = Options() #remover interface gráfica após uso teste
        self.options.set_preference("dom.webdriver.enabled", False)
        self.options.set_preference('useAutomationExtension', False)
        self.options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0")
        self.options.add_argument("-private")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument("--width=1920")
        self.options.add_argument("--height=1080")
        
        self.service = Service(GeckoDriverManager().install())

    def _iniciar_driver(self) -> webdriver:
        """Inicializa e retorna uma nova instância do WebDriver Firefox configurada."""
        return webdriver.Firefox(options = self.options ,service = self.service)

    def _normalizar(self, texto: str) -> str:
        """Remove acentos e converte a string para minúsculas."""
        nfkd = unicodedata.normalize('NFKD', texto.lower())
        return "".join([c for c in nfkd if not unicodedata.combining(c)])

    def _limpar_preco(self, texto:str) -> float:
        """Converte strings de preço (ex: 'R$ 1.200,50') para float (1200.50)."""
        if not texto or "Consultar" in texto:
            return 0.0
        try:
            apenas_numeros = re.sub(r'[^0-9,.]', '', texto)
            
            if ',' in apenas_numeros and '.' in apenas_numeros:
                apenas_numeros = apenas_numeros.replace('.', '').replace(',', '.')
            elif ',' in apenas_numeros:
                apenas_numeros = apenas_numeros.replace(',', '.')
                
            return float(apenas_numeros)
        except:
            return 0.0

    def processar_resultados(self, resultados_brutos: list[Produto], item_busca: str) -> list[Produto]:
        """
        Recebe a lista bruta, aplica a lógica de relevância ponderada,
        calcula o score de desconto e ordena os resultados.
        """
        if not resultados_brutos:
            return []
            
        df = pd.DataFrame(resultados_brutos)
        palavras_busca = self._normalizar(item_busca).split()

        def busca_relevante(nome_produto):
            nome_norm = self._normalizar(nome_produto)
            score = 0
            
            for p in palavras_busca:
                if p.isdigit():
                    pattern = fr'(?<!\d){p}(?!\d)'
                    if re.search(pattern, nome_norm):
                        score += 5
                else:
                    if p in nome_norm:
                        score += 1
            return score

        df['relevancia'] = df['nome'].apply(busca_relevante)
        
        df = df[df['relevancia'] > 0]
        
        if df.empty:
            return []

        df['preco_atual'] = pd.to_numeric(df['preco_atual'], errors='coerce')
        df['preco_original'] = pd.to_numeric(df['preco_original'], errors='coerce').fillna(df['preco_atual'])
        
        economia = df['preco_original'] - df['preco_atual']
        pct_desconto = (economia / df['preco_original'])
        economia_log = np.log10(economia.clip(lower=0) + 1) / 5
        
        df['score'] = ((pct_desconto * 0.6) + (economia_log * 0.4)) * 100
        df['score'] = df['score'].clip(0, 100).round(2)
        
        df = df.sort_values(by=['relevancia', 'score'], ascending=[False, False])
        
        return df.to_dict('records')

    def scraping_mercadolivre(self, item: str) -> list[Produto]:
        """Realiza busca no Mercado Livre, extrai dados básicos e processa relevância."""
        busca = quote(item)
        url = f"https://lista.mercadolivre.com.br/{busca}"
        driver = self._iniciar_driver()

        resultados = []

        try:
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ui-search-result__wrapper")))
            
            anuncios = driver.find_elements(By.CLASS_NAME, "ui-search-result__wrapper")

            for anuncio in anuncios:
                if len(resultados) >= 10:
                    break
                    
                try:
                    nome = anuncio.find_element(By.CLASS_NAME, "poly-component__title").text
                    
                    container_preco = anuncio.find_element(By.CLASS_NAME, "poly-component__price")
                    labels = container_preco.find_elements(By.CSS_SELECTOR, "[aria-label]")
                    
                    preco_atual = 0.0
                    preco_original = 0.0
                    
                    for label in labels:
                        texto = label.get_attribute("aria-label") or ""
                        valor = 0.0
                        
                        match = re.search(r'(\d+)\s*reais(?:\s*com\s*(\d+))?', texto)
                        if match:
                            reais = match.group(1)
                            centavos = match.group(2) if match.group(2) else "00"
                            valor = float(f"{reais}.{centavos}")
                        
                        if valor > 0:
                            if "Agora" in texto or ("Antes" not in texto and preco_atual == 0.0):
                                preco_atual = valor
                            elif "Antes" in texto:
                                preco_original = valor
                    
                    if preco_original == 0.0:
                        preco_original = preco_atual
                            
                    if preco_atual > 0:
                        resultados.append({
                            'nome': nome,
                            'preco_original': preco_original,
                            'preco_atual': preco_atual,
                            'loja': 'ML',
                            'link': anuncio.find_element(By.CLASS_NAME, "poly-component__title").get_attribute("href"),
                            'imagem': anuncio.find_element(By.TAG_NAME, "img").get_attribute("src")
                        })
                except Exception:
                    continue
            
            return self.processar_resultados(resultados, item)

        finally:
            driver.quit()

    def scraping_kabum(self, item: str) -> list[Produto]:
        """Realiza busca no KaBuM, extrai dados básicos e processa relevância."""
        busca = quote(item)
        url = f"https://www.kabum.com.br/busca/{busca}"
        driver = self._iniciar_driver()

        resultados = []

        try:
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.productCard")))
            
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            anuncios = driver.find_elements(By.CSS_SELECTOR, "article.productCard")

            for anuncio in anuncios:
                if len(resultados) >= 10:
                    break
                    
                try:
                    nome = anuncio.find_element(By.CSS_SELECTOR, "span.nameCard").text

                    preco_atual = self._limpar_preco(anuncio.find_element(By.CSS_SELECTOR, "span.priceCard").text)
                    tags_old = anuncio.find_elements(By.CSS_SELECTOR, "span.oldPriceCard")
                    preco_original = self._limpar_preco(tags_old[0].text) if tags_old else preco_atual

                    if preco_atual > 0:
                        resultados.append({
                            'nome': nome,
                            'preco_original': preco_original,
                            'preco_atual': preco_atual,
                            'loja': 'KB',
                            'link': anuncio.find_element(By.CSS_SELECTOR, "a.productLink").get_attribute("href"),
                            'imagem': anuncio.find_element(By.CSS_SELECTOR, "img.imageCard").get_attribute("src")
                        })
                except Exception:
                    continue

            return self.processar_resultados(resultados, item)

        finally:
            driver.quit()

    def scraping_terabyte(self, item: str) -> list[Produto]:
        """Realiza busca na Terabyte, extrai dados básicos e processa relevância."""
        busca = quote(item)
        url = f"https://www.terabyteshop.com.br/busca?str={busca}"
        driver = self._iniciar_driver()

        resultados = []

        try:
            driver.get(url)
            wait = WebDriverWait(driver, 10)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-item")))

            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(2)

            anuncios = driver.find_elements(By.CLASS_NAME, "product-item")

            for anuncio in anuncios:
                if len(resultados) >= 10:
                    break

                try:
                    nome = anuncio.find_element(By.CLASS_NAME, "product-item__name").text

                    preco_atual = self._limpar_preco(anuncio.find_element(By.CLASS_NAME, "product-item__new-price").text)
                    tags_old = anuncio.find_element(By.CLASS_NAME, "product-item__old-price").text.strip()
                    preco_original = self._limpar_preco(tags_old) if tags_old else preco_atual

                    if preco_atual > 0:
                        resultados.append({
                            'nome': nome,
                            'preco_original': preco_original,
                            'preco_atual': preco_atual,
                            'loja': 'TB',
                            'link': anuncio.find_element(By.CLASS_NAME, "product-item__image").get_attribute("href"),
                            'imagem': anuncio.find_element(By.TAG_NAME, "img").get_attribute("src")
                        })
                except Exception:
                    continue

            return self.processar_resultados(resultados, item)

        finally:
            driver.quit()
