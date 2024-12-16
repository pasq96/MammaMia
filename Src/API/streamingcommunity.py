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

# Caricamento variabili
env_vars = load_env()
SC_DOMAIN = config.SC_DOMAIN
Public_Instance = config.Public_Instance
Alternative_Link = env_vars.get("ALTERNATIVE_LINK")
headers = Headers()

async def get_version(client):
    try:
        base_url = f'https://streamingcommunity.{SC_DOMAIN}/richiedi-un-titolo'
        response = await client.get(base_url, headers=headers.generate(), allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(response.text, "lxml")
        version = json.loads(soup.find("div", {"id": "app"}).get("data-page"))['version']
        return version
    except Exception:
        return "65e52dcf34d64173542cd2dc6b8bb75b"

async def search(query, date, ismovie, client, SC_FAST_SEARCH, movie_id):
    response = await client.get(query, headers=headers.generate(), allow_redirects=True)
    if response.status_code != 200:
        return None, None, None
    
    for item in response.json().get('data', []):
        if (type := 0 if item['type'] == "tv" else 1) == ismovie:
            tid, slug = item['id'], item['slug']
            if SC_FAST_SEARCH == "0":
                response = await client.get(f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}', headers=headers.generate(), allow_redirects=True, impersonate="chrome120")
                data = json.loads(BeautifulSoup(response.text, "lxml").find("div", {"id": "app"}).get("data-page"))
                if str(data['props']['title']['tmdb_id']) == movie_id:
                    return tid, slug, data['version']
            else:
                return tid, slug, await get_version(client)
    return None, None, None

async def get_film(tid, version, client):
    url = f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}'
    iframe_response = await client.get(url, headers=headers.generate(), allow_redirects=True, impersonate="chrome120")
    iframe_src = BeautifulSoup(iframe_response.text, 'lxml').find('iframe')['src']
    vixid, query_params = iframe_src.split("/embed/")[1].split("?")[0], parse_qs(urlparse(iframe_src).query)

    resp = await client.get(iframe_src, headers=headers.generate(), allow_redirects=True, impersonate="chrome120")
    script = BeautifulSoup(resp.text, "lxml").find("body").find("script").text
    token, expires = re.search(r"'token':\s*'(\w+)'", script).group(1), re.search(r"'expires':\s*'(\d+)'", script).group(1)
    quality = re.search(r'"quality":(\d+)', script).group(1)

    base_url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}'
    if 'canPlayFHD' in query_params:
        base_url += "&h=1"
    elif 'b' in query_params:
        base_url += "&b=1"

    if quality == "1080" and "&b=1" in base_url:
        base_url = base_url.replace("&b=1", "&h=1")
    return base_url + f"&token={token}", f'https://vixcloud.co/playlist/{vixid}.m3u8', quality

async def get_season_episode_id(tid, slug, season, episode, version, client):
    url = f'https://streamingcommunity.{SC_DOMAIN}/titles/{tid}-{slug}/stagione-{season}'
    episodes = (await client.get(url, headers=headers.generate(), impersonate="chrome120")).json()
    for e in episodes.get('props', {}).get('loadedSeason', {}).get('episodes', []):
        if e['number'] == episode:
            return e['id']
    return None

async def get_episode_link(episode_id, tid, version, client):
    url = f'https://streamingcommunity.{SC_DOMAIN}/iframe/{tid}'
    params = {'episode_id': episode_id, 'next_episode': '1'}
    iframe_src = BeautifulSoup((await client.get(url, params=params, headers=headers.generate(), impersonate="chrome120")).text, "lxml").find("iframe")['src']

    vixid, query_params = iframe_src.split("/embed/")[1].split("?")[0], parse_qs(urlparse(iframe_src).query)
    script = BeautifulSoup((await client.get(iframe_src, headers=headers.generate(), impersonate="chrome120")).text, "lxml").find("body").find("script").text
    token, expires = re.search(r"'token':\s*'(\w+)'", script).group(1), re.search(r"'expires':\s*'(\d+)'", script).group(1)
    quality = re.search(r'"quality":(\d+)', script).group(1)

    base_url = f'https://vixcloud.co/playlist/{vixid}.m3u8?expires={expires}'
    if 'canPlayFHD' in query_params:
        base_url += "&h=1"
    elif 'b' in query_params:
        base_url += "&b=1"

    return base_url + f"&token={token}", f'https://vixcloud.co/playlist/{vixid}.m3u8', quality

async def streaming_community(imdb, client, SC_FAST_SEARCH):
    try:
        if Public_Instance == "1":
            link_post = random.choice(json.loads(Alternative_Link))
            response = await client.get(f"{link_post}fetch-data/{SC_FAST_SEARCH}/{SC_DOMAIN}/{imdb}")
            return response.headers.get('x-url-streaming-community'), response.headers.get('x-url-720-streaming-community'), response.headers.get('x-quality-sc')

        ismovie, imdb_id, season, episode = is_movie(imdb)
        showname, date = (await get_info_imdb(imdb_id, ismovie, "StreamingCommunityFS", client), None) if "tt" in imdb else get_info_tmdb(imdb_id.replace("tmdb:", ""), ismovie, "StreamingCommunityFS")
        tid, slug, version = await search(f'https://streamingcommunity.{SC_DOMAIN}/api/search?q={quote_plus(showname)}', date, ismovie, client, SC_FAST_SEARCH, imdb_id)

        if ismovie:
            return await get_film(tid, version, client)
        else:
            episode_id = await get_season_episode_id(tid, slug, season, episode, version, client)
            return await get_episode_link(episode_id, tid, version, client)
    except Exception as e:
        print("StreamingCommunity failed:", e)
        return None, None, None