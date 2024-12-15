
from bs4 import BeautifulSoup
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie, get_info_imdb
import Src.Utilities.config as config
import json
import random
import re
from urllib.parse import urlparse, parse_qs
from fake_headers import Headers  
from Src.Utilities.loadenv import load_env  
import urllib.parse

# Environment Variables
env_vars = load_env()
SC_DOMAIN = config.SC_DOMAIN
Public_Instance = config.Public_Instance
Alternative_Link = env_vars.get('ALTERNATIVE_LINK')

# Header generator and cache
headers = Headers()
version_cache = {}

def generate_headers(referer=None, origin=None, inertia_version=None):
    random_headers = headers.generate()
    if referer:
        random_headers['Referer'] = referer
    if origin:
        random_headers['Origin'] = origin
    if inertia_version:
        random_headers['x-inertia-version'] = inertia_version
    return random_headers

async def get_version(client):
    if "version" in version_cache:
        return version_cache["version"]
    try:
        referer = f"https://streamingcommunity.{SC_DOMAIN}/"
        headers = generate_headers(referer, referer)
        url = f'https://streamingcommunity.{SC_DOMAIN}/richiedi-un-titolo'
        response = await client.get(url, headers=headers, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(response.text, "lxml")
        version = json.loads(soup.find("div", {"id": "app"}).get("data-page", "{}")).get('version')
        version_cache["version"] = version
        return version
    except Exception as e:
        print(f"Couldn't find the version: {e}")
        return "65e52dcf34d64173542cd2dc6b8bb75b"

async def get_film(tid, version, client):  
    headers = generate_headers("https://streamingcommunity.buzz/", "https://streamingcommunity.buzz", version)
    url = f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}'
    response = await client.get(url, headers=headers, allow_redirects=True, impersonate="chrome120")
    iframe_src = BeautifulSoup(response.text, 'lxml').find('iframe').get("src")
    return await extract_stream_data(iframe_src, client, headers)

async def extract_stream_data(iframe_url, client, headers):
    parsed_url = urlparse(iframe_url)
    query_params = parse_qs(parsed_url.query)
    vixid = iframe_url.split("/embed/")[1].split("?")[0]

    response = await client.get(iframe_url, headers=headers, allow_redirects=True, impersonate="chrome120")
    script = BeautifulSoup(response.text, "lxml").find("body").find("script").text
    token = re.search(r"'token':\s*'(\w+)'", script).group(1)
    expires = re.search(r"'expires':\s*'(\d+)'", script).group(1)
    quality = re.search(r'"quality":(\d+)', script).group(1)

    base_url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}&token={token}'
    url_720 = f'https://vixcloud.co/playlist/{vixid}.m3u8'
    if quality == "1080":
        base_url += "&h=1"
    return base_url, url_720, quality

async def get_season_episode_id(tid, slug, season, episode, version, client):
    headers = generate_headers("https://streamingcommunity.buzz/", "https://streamingcommunity.buzz", version)
    url = f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}/stagione-{season}'
    response = await client.get(url, headers=headers, allow_redirects=True, impersonate="chrome120")
    episodes = response.json().get('props', {}).get('loadedSeason', {}).get('episodes', [])
    for ep in episodes:
        if ep['number'] == episode:
            return ep['id']

async def streaming_community(imdb, client, SC_FAST_SEARCH):
    try:
        if Public_Instance == "1":
            link_post = random.choice(json.loads(Alternative_Link))
            response = await client.get(f"{link_post}fetch-data/{SC_FAST_SEARCH}/{SC_DOMAIN}/{imdb}")
            return response.headers.get('x-url-streaming-community'), response.headers.get('x-url-720-streaming-community'), response.headers.get('x-quality-sc')

        ismovie, imdb_id, season, episode = is_movie(imdb)
        tmdba = imdb_id.replace("tmdb:", "")
        showname, date = (await get_info_imdb(imdb_id, ismovie, "StreamingCommunityFS", client)) if SC_FAST_SEARCH == "1" else get_info_tmdb(tmdba, ismovie, "StreamingCommunity")
        showname = urllib.parse.quote_plus(showname.replace(" ", "+").replace("–", "+").replace("—", "+"))
        query = f'https://streamingcommunity.{SC_DOMAIN}/api/search?q={showname}'
        tid, slug, version = await search(query, date, ismovie, client, SC_FAST_SEARCH, imdb_id)
        
        if ismovie:
            return await get_film(tid, version, client)
        episode_id = await get_season_episode_id(tid, slug, season, episode, version, client)
        return await get_episode_link(episode_id, tid, version, client)
    except Exception as e:
        print(f"Error in streaming_community: {e}")
        return None, None, None
