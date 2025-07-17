# GoogleSearch_Grayhound.py
# Grayhound's Lightweight Web Search & Content Extraction Module

import requests
import configparser
import logging
import urllib.parse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def Google_Search_api(query: str, num_results: int) -> list[str]:
    """Google Search API를 호출하여 검색 결과 URL 리스트를 반환"""
    try:
        config = configparser.ConfigParser()
        config.read('config.ini')
        google_api_key = config['DEFAULT']['google_api_key']
        cx = config['DEFAULT']['cx']
    except Exception as e:
        logging.error(f"Error reading config.ini: {e}")
        return []
    
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.googleapis.com/customsearch/v1?q={encoded_query}&key={google_api_key}&cx={cx}&num={num_results}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        search_results = response.json()
        
        if 'items' in search_results:
            return [item.get('link') for item in search_results['items']]
        else:
            logging.error(f"No search results found for query: {query}")
            return []
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Google Search API: {e}")
        return []
    
def extract_text_from_url(url: str) -> str:
    """주어진 url에서 주요 텍스트 내용을 추출"""
    if not url:
        return ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 인코딩 자동 감지
        response.encoding = response.apparent_encoding
        
        soup = BeautifulSoup(response.text, 'html.parser')

        # 불필요한 태그 제거
        for tag in soup(['script', 'style', 'header', 'footer', 'aside', 'nav']):
            tag.decompose()
            
        # 본문 영역으로 추정되는 태그를 우선 탐색
        main_content = soup.find('main') or soup.find('article') or soup.find('body')
        if main_content:
            text = main_content.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
            
        # 과도한 공백 및 줄바꿈 정리
        text = re.sub(r'\s{2,}', ' ', text)
        return text
    except Exception as e:
        logging.error(f"Error extracting text from {url}: {e}")
        return ""
    
def search_and_extract_text(queries: list[str], num_results_per_query: int = 3) -> str:
    """여러 쿼리로 검색하고, 각 결과 페이지의 텍스트를 병렬로 추출해 하나의 텍스트 덩어리로 합침."""
    all_urls = set()
    logging.info(f"Starting search for {len(queries)} queries with {num_results_per_query} results per query.")
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_query = {executor.submit(Google_Search_api, q, num_results_per_query): q for q in queries}            
        for future in as_completed(future_to_query):
            urls = future.result()
            all_urls.update(urls)
            
    if not all_urls:
        logging.warning("No URLs found in the search results.")
        return ""
                
    logging.info(f"Found {len(all_urls)} unique URLs from {len(queries)} queries. text extraction will start now.")
    all_texts = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(extract_text_from_url, url): url for url in all_urls}
        for future in as_completed(future_to_url):
            text = future.result()
            if text:
                all_texts.append(text)
                
    logging.info(f"Successfully extracted text from {len(all_texts)} URLs.")
    return " ".join(all_texts)