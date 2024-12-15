from bs4 import BeautifulSoup
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie, get_info_imdb
import Src.Utilities.config as config
import json
import random
import re
import urllib.parse
from functools import lru_cache
from urllib.parse import urlparse, parse_qs
from fake_headers import Headers  

# Configuration and environment variables
SC_DOMAIN = config.SC_DOMAIN

# Header generator
headers = Headers()

# Cache
version_cache = {}

# Precompiled regex patterns for better performance
PATTERN_TOKEN = re.compile(r"'token':\s*'(\w+)'")
PATTERN_EXPIRES = re.compile(r"'expires':\s*'(\d+)'")
PATTERN_QUALITY = re.compile(r'"quality":(\d+)')

# Helper function to generate headers
def generate_headers(referer=None, origin=None, inertia_version=None):
    random_headers = headers.generate()
    if referer:
        random_headers["Referer"] = referer
    if origin:
        random_headers["Origin"] = origin
    if inertia_version:
        random_headers["x-inertia-version"] = inertia_version
    return random_headers

# Cache version lookup
@lru_cache(maxsize=10)
async def get_version(client):
    try:
        referer = f"https://streamingcommunity.{SC_DOMAIN}/"
        headers = generate_headers(referer, referer)
        response = await client.get(f'https://streamingcommunity.{SC_DOMAIN}/richiedi-un-titolo', headers=headers, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(response.text, "lxml")
        version = json.loads(soup.find("div", {"id": "app"}).get("data-page", "{}"))
        if version and 'version' in version:
            version_cache["version"] = version["version"]
            return version["version"]
        else:
            raise ValueError("Version not found in response")
    except Exception as e:
        print(f"Failed to get version: {e}")
        return "65e52dcf34d64173542cd2dc6b8bb75b"

async def get_film(tid, version, client):
    headers = generate_headers("https://streamingcommunity.buzz/", "https://streamingcommunity.buzz", version)
    iframe_url = f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}'
    response = await client.get(iframe_url, headers=headers, allow_redirects=True, impersonate="chrome120")
    iframe_src_tag = BeautifulSoup(response.text, "lxml").find("iframe")
    if iframe_src_tag and iframe_src_tag.get("src"):
        iframe_src = iframe_src_tag.get("src")
        return await extract_stream_data(iframe_src, client, headers)
    else:
        raise ValueError("Iframe src not found")

async def extract_stream_data(iframe_url, client, headers):
    parsed_url = urlparse(iframe_url)
    query_params = parse_qs(parsed_url.query)
    vixid = iframe_url.split("/embed/")[1].split("?")[0] if "/embed/" in iframe_url else None

    if not vixid:
        raise ValueError("vixid not found in iframe URL")

    response = await client.get(iframe_url, headers=headers, allow_redirects=True, impersonate="chrome120")
    script_tag = BeautifulSoup(response.text, "lxml").find("body").find("script")
    if script_tag and script_tag.text:
        script = script_tag.text
        token_match = PATTERN_TOKEN.search(script)
        expires_match = PATTERN_EXPIRES.search(script)
        quality_match = PATTERN_QUALITY.search(script)
        
        if not all([token_match, expires_match, quality_match]):
            raise ValueError("Required data not found in script")

        token = token_match.group(1)
        expires = expires_match.group(1)
        quality = quality_match.group(1)

        url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}&token={token}'
        if quality == "1080":
            url += "&h=1"
        return url, f'https://vixcloud.co/playlist/{vixid}.m3u8', quality
    else:
        raise ValueError("Script tag not found in iframe response")

async def get_season_episode_id(tid, slug, season, episode, version, client):
    headers = generate_headers("https://streamingcommunity.buzz/", "https://streamingcommunity.buzz", version)
    response = await client.get(f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}/stagione-{season}', headers=headers, allow_redirects=True, impersonate="chrome120")
    episodes = response.json().get('props', {}).get('loadedSeason', {}).get('episodes', [])
    if not episodes:
        raise ValueError("No episodes found for the requested season")
    for ep in episodes:
        if ep['number'] == episode:
            return ep['id']
    raise ValueError("Episode not found in the season data")

async def streaming_community(imdb, client, SC_FAST_SEARCH):
    try:
        ismovie, imdb_id, season, episode = is_movie(imdb)
        type = "StreamingCommunity"
        tmdba = await get_TMDb_id_from_IMDb_id(imdb_id, client) if "tt" in imdb else imdb_id

        showname, date = get_info_tmdb(tmdba, ismovie, type)
        showname = urllib.parse.quote_plus(showname.replace(" ", "+").replace("\u2013", "+").replace("\u2014", "+"))
        query = f'https://streamingcommunity.{SC_DOMAIN}/api/search?q={showname}'
        tid, slug, version = await search(query, date, ismovie, client, SC_FAST_SEARCH, imdb_id)
        
        if not all([tid, slug, version]):
            raise ValueError("Search did not return valid results")
        
        if ismovie:
            return await get_film(tid, version, client)
        episode_id = await get_season_episode_id(tid, slug, season, episode, version, client)
        return await get_episode_link(episode_id, tid, version, client)
    except Exception as e:
        print(f"Error in streaming_community: {e}")
        return None, None, None
