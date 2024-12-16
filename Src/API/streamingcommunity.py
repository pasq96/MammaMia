from bs4 import BeautifulSoup
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie, get_info_imdb
import Src.Utilities.config as config
import json
import random
import re
from urllib.parse import urlparse, parse_qs, quote_plus
from fake_headers import Headers
from Src.Utilities.loadenv import load_env

# Load environment variables
env_vars = load_env()
SC_DOMAIN = config.SC_DOMAIN
Public_Instance = config.Public_Instance
Alternative_Link = env_vars.get('ALTERNATIVE_LINK')
headers = Headers()

# Utility function to generate headers
def generate_headers():
    random_headers = headers.generate()
    random_headers.update({
        'Referer': f"https://streamingcommunity.{SC_DOMAIN}/",
        'Origin': f"https://streamingcommunity.{SC_DOMAIN}",
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    })
    return random_headers

# Get version of Streaming Community
async def get_version(client):
    try:
        response = await client.get(
            f'https://streamingcommunity.{SC_DOMAIN}/richiedi-un-titolo',
            headers=generate_headers(), allow_redirects=True, impersonate="chrome120"
        )
        soup = BeautifulSoup(response.text, "lxml")
        version = json.loads(soup.find("div", {"id": "app"}).get("data-page"))['version']
        return version
    except Exception:
        return "65e52dcf34d64173542cd2dc6b8bb75b"

# Search for the title async
def extract_tid_slug_type(item):
    tid, slug, type = item['id'], item['slug'], 0 if item['type'] == "tv" else 1
    return tid, slug, type

async def search(query, ismovie, client, SC_FAST_SEARCH, movie_id):
    try:
        response = await client.get(query, headers=generate_headers(), allow_redirects=True)
        for item in response.json()['data']:
            tid, slug, type = extract_tid_slug_type(item)
            if type == ismovie:
                if SC_FAST_SEARCH == "0":
                    data, version = await fetch_title_data(client, tid, slug)
                    if validate_tmdb_id(movie_id, data):
                        return tid, slug, version
                else:
                    version = await get_version(client)
                    return tid, slug, version
    except Exception as e:
        print("Search failed:", e)
    return None, None, None

async def fetch_title_data(client, tid, slug):
    response = await client.get(f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}',
                                headers=generate_headers(), allow_redirects=True, impersonate="chrome120")
    data = json.loads(BeautifulSoup(response.text, "lxml").find("div", {"id": "app"}).get("data-page"))
    return data, data['version']

def validate_tmdb_id(movie_id, data):
    return str(data['props']['title']['tmdb_id']) == str(movie_id)

# Fetch streaming URLs
async def get_film(tid, version, client):
    iframe_src, vixid, query_params = await fetch_iframe_data(tid, version, client)
    token, expires, quality = await fetch_token_data(client, iframe_src)
    return build_streaming_urls(vixid, expires, token, query_params, quality)

async def fetch_iframe_data(tid, version, client):
    response = await client.get(f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}',
                                headers=generate_headers(), allow_redirects=True, impersonate="chrome120")
    iframe_src = BeautifulSoup(response.text, 'lxml').find('iframe').get("src")
    parsed_url = urlparse(iframe_src)
    return iframe_src, iframe_src.split("/embed/")[1].split("?")[0], parse_qs(parsed_url.query)

async def fetch_token_data(client, iframe_src):
    response = await client.get(iframe_src, headers=generate_headers(), allow_redirects=True, impersonate="chrome120")
    script = BeautifulSoup(response.text, "lxml").find("body").find("script").text
    token = re.search(r"'token':\s*'(\w+)'", script).group(1)
    expires = re.search(r"'expires':\s*'(\d+)'", script).group(1)
    quality = re.search(r'"quality":(\d+)', script).group(1)
    return token, expires, quality

def build_streaming_urls(vixid, expires, token, query_params, quality):
    base_url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}&token={token}'
    if quality == "1080" and 'canPlayFHD' in query_params:
        base_url += "&h=1"
    elif 'b' in query_params:
        base_url += "&b=1"
    return base_url, f'https://vixcloud.co/playlist/{vixid}.m3u8', quality

async def get_episode_id(tid, slug, season, episode, version, client):
    """
    Ottiene l'ID di un episodio specifico basato su stagione ed episodio.
    """
    try:
        # Effettua una richiesta per recuperare i dati della serie TV
        response = await client.get(
            f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}',
            headers=generate_headers(), allow_redirects=True, impersonate="chrome120"
        )
        data = json.loads(BeautifulSoup(response.text, "lxml").find("div", {"id": "app"}).get("data-page"))
        
        # Estrae gli episodi dalla stagione specificata
        seasons = data['props']['title']['seasons']
        season_data = seasons.get(str(season))  # La chiave è la stringa del numero della stagione

        if not season_data:
            print(f"Stagione {season} non trovata.")
            return None
        
        # Cerca l'episodio con il numero corretto
        for ep in season_data['episodes']:
            if ep['number'] == episode:
                return ep['id']  # Restituisce l'ID dell'episodio
        
        print(f"Episodio {episode} non trovato nella stagione {season}.")
    except Exception as e:
        print("Errore nel recupero dell'ID episodio:", e)
    
    return None



# Streaming Community Main Function
async def streaming_community(imdb, client, SC_FAST_SEARCH):
    try:
        if Public_Instance == "1":
            return await fetch_public_instance(client, SC_FAST_SEARCH, imdb)

        ismovie, imdb_id, season, episode = parse_imdb_data(imdb)
        showname, date = await get_show_info(SC_FAST_SEARCH, ismovie, imdb_id, client)
        tid, slug, version = await search(build_query(showname), ismovie, client, SC_FAST_SEARCH, imdb_id)

        if ismovie:
            return await get_film(tid, version, client)
        else:
            episode_id = await get_episode_id(tid, slug, season, episode, version, client)
            return await get_episode_link(episode_id, tid, version, client)
    except Exception as e:
        print("StreamingCommunity failed:", e)
    return None, None, None, None

def build_query(showname):
    return f'https://streamingcommunity.{SC_DOMAIN}/api/search?q={quote_plus(showname)}'

def parse_imdb_data(imdb):
    general = is_movie(imdb)
    return general[0], general[1], int(general[2] or 0), int(general[3] or 0)

async def get_show_info(SC_FAST_SEARCH, ismovie, imdb_id, client):
    type = "StreamingCommunityFS" if SC_FAST_SEARCH == "1" else "StreamingCommunity"
    if "tt" in imdb_id:
        return await get_info_imdb(imdb_id, ismovie, type, client), None
    else:
        tmdba = imdb_id.replace("tmdb:", "")
        return get_info_tmdb(tmdba, ismovie, type)

async def fetch_public_instance(client, SC_FAST_SEARCH, imdb):
    link_post = random.choice(json.loads(Alternative_Link))
    response = await client.get(f"{link_post}fetch-data/{SC_FAST_SEARCH}/{SC_DOMAIN}/{imdb}")
    return response.headers.get('x-url-streaming-community'), \
           response.headers.get('x-url-720-streaming-community'), \
           response.headers.get('x-quality-sc')