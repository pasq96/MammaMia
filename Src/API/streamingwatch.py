
from bs4 import BeautifulSoup, SoupStrainer
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie
import Src.Utilities.config as config
import re
import json
import urllib.parse
from functools import lru_cache

SW_DOMAIN = config.SW_DOMAIN

# Cache for repeated data
nonce_cache = {}

# Precompiled regular expressions for better performance
PATTERN_WPONCE = re.compile(r'"admin_ajax_nonce":"(\w+)"')
PATTERN_HLS_URL = re.compile(r'sources:\s*\[\s*\{\s*file\s*:\s*"([^"]*)"')
PATTERN_SRC = re.compile(r'src="([^"]+)"')

# Generate standard headers
def generate_headers():
    return {
        'authority': f'www.streamingwatch.{SW_DOMAIN}',
        'accept': '*/*',
        'accept-language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': f'https://www.streamingwatch.{SW_DOMAIN}',
        'referer': f'https://www.streamingwatch.{SW_DOMAIN}',
        'sec-ch-ua': '"Not-A.Brand";v="99", "Chromium";v="124"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

# LRU cache for category and episode data
@lru_cache(maxsize=50)
async def wponce_get(client):
    if "wponce" in nonce_cache:
        return nonce_cache["wponce"]
    response = await client.get(f"https://www.streamingwatch.{SW_DOMAIN}/contatto/")
    matches = PATTERN_WPONCE.findall(response.text)
    if not matches:
        raise ValueError("Nonce not found in response")
    nonce_cache["wponce"] = matches[1]
    return matches[1]

@lru_cache(maxsize=100)
async def fetch_category_id(showname, client):
    url = f'https://streamingwatch.{SW_DOMAIN}/wp-json/wp/v2/categories?search={showname}&_fields=id'
    response = await client.get(url, allow_redirects=True, impersonate="chrome120")
    data = json.loads(response.text)
    if not data:
        raise ValueError("Category ID not found")
    return data[0]['id']

async def search(showname, season, episode, date, ismovie, client):
    headers = generate_headers()
    if ismovie == 1:
        wponce = await wponce_get(client)
        data = {'action': 'data_fetch', 'keyword': showname, '_wpnonce': wponce}
        query = f'https://www.streamingwatch.{SW_DOMAIN}/wp-admin/admin-ajax.php'
        
        response = await client.post(query, headers=headers, data=data)
        soup = BeautifulSoup(response.content, 'lxml')
        page_date = soup.find(id='search-cat-year').text.strip()
        
        if page_date == date:
            href = soup.find('a')['href']
            response = await client.get(href, allow_redirects=True, impersonate="chrome120")
            iframe = BeautifulSoup(response.text, 'lxml', parse_only=SoupStrainer('iframe')).find('iframe')
            return iframe.get('data-lazy-src')
    elif ismovie == 0:
        category_id = await fetch_category_id(showname, client)
        query = f'https://streamingwatch.{SW_DOMAIN}/wp-json/wp/v2/posts?categories={category_id}&per_page=100'
        response = await client.get(query, allow_redirects=True, impersonate="chrome120")
        
        for entry in json.loads(response.text):
            slug = entry["slug"]
            if f"stagione-{season}-episodio-{episode}" in slug and f"episodio-{episode}0" not in slug:
                match = PATTERN_SRC.search(entry["content"]["rendered"])
                if match:
                    return match.group(1)

async def hls_url(hdplayer, client):
    response = await client.get(hdplayer, allow_redirects=True, impersonate="chrome120")
    match = PATTERN_HLS_URL.search(response.text)
    if not match:
        raise ValueError("HLS URL not found in player source")
    return match.group(1)

async def streamingwatch(imdb, client):
    try:
        ismovie, imdb_id, season, episode = is_movie(imdb)
        type = "StreamingWatch"
        
        tmdba = await get_TMDb_id_from_IMDb_id(imdb_id, client) if "tt" in imdb else imdb_id
        showname, date = get_info_tmdb(tmdba, ismovie, type)
        showname = urllib.parse.quote_plus(showname.replace(" ", "+").replace("–", "+").replace("—", "+"))
        
        hdplayer = await search(showname, season, episode, date, ismovie, client)
        url = await hls_url(hdplayer, client)
        
        print(f"MammaMia: StreamingWatch found results for {showname}")
        return url
    except Exception as e:
        print("MammaMia: StreamingWatch Failed", e)
        return None
