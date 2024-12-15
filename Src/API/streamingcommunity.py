from bs4 import BeautifulSoup
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie, get_info_imdb
import Src.Utilities.config as config
import json
import random
import re
from urllib.parse import urlparse, parse_qs
from fake_headers import Headers
import urllib.parse

# Helper function to generate headers
def generate_headers():
    random_headers = headers.generate()
    random_headers['Referer'] = "https://streamingcommunity.buzz/"
    random_headers['Origin'] = "https://streamingcommunity.buzz"
    return random_headers

# Get domain and instance info
SC_DOMAIN = config.SC_DOMAIN
Public_Instance = config.Public_Instance
Alternative_Link = env_vars.get('ALTERNATIVE_LINK')

# Define the version retrieval with minimal HTTP requests
async def get_version(client):
    try:
        random_headers = generate_headers()
        random_headers['Referer'] = f"https://streamingcommunity.{SC_DOMAIN}/"
        base_url = f'https://streamingcommunity.{SC_DOMAIN}/richiedi-un-titolo'
        response = await client.get(base_url, headers=random_headers, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(response.text, "lxml")
        version = json.loads(soup.find("div", {"id": "app"}).get("data-page"))['version']
        return version
    except Exception as e:
        print("Couldn't find the version", e)
        return "65e52dcf34d64173542cd2dc6b8bb75b"

# Helper function to parse iframe URLs
def parse_iframe(iframe):
    vixid = iframe.split("/embed/")[1].split("?")[0]
    parsed_url = urlparse(iframe)
    query_params = parse_qs(parsed_url.query)
    return vixid, query_params

# Get video URL
async def get_video_url(vixid, token, expires, quality, query_params):
    url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}'
    if 'canPlayFHD' in query_params:
        url += "&h=1"
    if 'b' in query_params:
        url += "&b=1"
    if quality == "1080":
        if "&b" in url:
            url = url.replace("&b=1", "&h=1")
        else:
            url += "&h=1"
    else:
        url += f"&token={token}"
    return url

# Get film streaming data
async def get_film(tid, version, client):
    random_headers = generate_headers()
    random_headers['x-inertia-version'] = version
    url = f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}'
    response = await client.get(url, headers=random_headers, allow_redirects=True, impersonate="chrome120")
    soup = BeautifulSoup(response.text, 'lxml')
    iframe = soup.find('iframe').get("src")
    
    # Extract token, expiration, and quality
    vixid, query_params = parse_iframe(iframe)
    resp = await client.get(iframe, headers=random_headers, allow_redirects=True, impersonate="chrome120")
    soup = BeautifulSoup(resp.text, "lxml")
    script = soup.find("body").find("script").text
    token = re.search(r"'token':\s*'(\w+)'", script).group(1)
    expires = re.search(r"'expires':\s*'(\d+)'", script).group(1)
    quality = re.search(r'"quality":(\d+)', script).group(1)
    
    url = await get_video_url(vixid, token, expires, quality, query_params)
    url720 = f'https://vixcloud.co/playlist/{vixid}.m3u8'
    return url, url720, quality

# Example of optimized async function
async def streaming_community(imdb, client, SC_FAST_SEARCH):
    try:
        # Simplify conditional checks for movie/TV
        ismovie, imdb_id, season, episode = is_movie(imdb)
        tmdba = imdb_id.replace("tmdb:", "") if "tmdb:" in imdb_id else imdb_id
        
        # Use fast search or normal search based on config
        query = f'https://streamingcommunity.{SC_DOMAIN}/api/search?q={urllib.parse.quote_plus(imdb)}'
        tid, slug, version = await search(query, None, ismovie, client, SC_FAST_SEARCH, imdb_id)
        
        if ismovie == 1:
            url, url720, quality = await get_film(tid, version, client)
            return url, url720, quality, slug
        else:
            episode_id = await get_season_episode_id(tid, slug, season, episode, version, client)
            url, url720, quality = await get_episode_link(episode_id, tid, version, client)
            return url, url720, quality, slug
    except Exception as e:
        print("StreamingCommunity failed:", e)
        return None, None, None, None
