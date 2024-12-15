from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from Src.API.filmpertutti import filmpertutti
from Src.API.streamingcommunity import streaming_community
from Src.API.tantifilm import tantifilm
from Src.API.lordchannel import lordchannel
from Src.API.streamingwatch import streamingwatch
import Src.Utilities.config as config
import logging
from Src.API.okru import okru_get_url
from Src.API.animeworld import animeworld
from Src.Utilities.dictionaries import okru, STREAM, extra_sources, webru_vary, webru_dlhd, provider_map, skystreaming
from Src.API.epg import tivu, tivu_get, epg_guide, convert_bho_1, convert_bho_2, convert_bho_3
from Src.API.webru import webru, get_skystreaming
from curl_cffi.requests import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from static.static import HTML
import asyncio

# Initial configuration
MYSTERIUS = config.MYSTERIUS
DLHD = config.DLHD
HOST = config.HOST
PORT = int(config.PORT)
HF = config.HF
if HF == "1":
    HF = "🤗️"
    #Cool code to set the hugging face if the service is hosted there.
else:
    HF = ""
if MYSTERIUS == "1":
    from Src.API.cool import cool

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Manifest for the addon
MANIFEST = {
    "id": "org.stremio.mammamia",
    "version": "1.1.0",
    "catalogs": [
        {
            "type": "tv",
            "id": "tv_channels",
            "name": "TV Channels",
            "behaviorHints": {"configurable": True, "configurationRequired": True},
            "extra": [{"name": "genre", "isRequired": False, "options": ["Rai", "Mediaset", "Sky", "Euronews", "La7", "Warner Bros", "FIT", "Sportitalia", "RSI", "DAZN", "Rakuten", "Pluto", "A+E", "Paramount", "Chill"]}]
        }
    ],
    "resources": ["stream", "catalog", "meta"],
    "types": ["movie", "series", "tv"],
    "name": "Mamma Mia",
    "description": "Addon providing HTTPS Streams for Italian Movies, Series, and Live TV! Note that you need to have Kitsu Addon installed in order to watch Anime",
    "logo": "https://creazilla-store.fra1.digitaloceanspaces.com/emojis/49647/pizza-emoji-clipart-md.png"
}

def respond_with(data):
    # Function to respond with a JSON response
    resp = JSONResponse(data)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = '*'
    return resp

# Route to get the manifest for the addon
@app.get('/{config}/manifest.json')
def addon_manifest(config: str):
    manifest_copy = MANIFEST.copy()
    if "LIVETV" in config:
        return respond_with(manifest_copy)
    else:
        manifest_copy["catalogs"] = []
        if "catalog" in manifest_copy["resources"]:
            manifest_copy["resources"].remove("catalog")
        return respond_with(manifest_copy)

@app.get('/', response_class=HTMLResponse)
def root(request: Request):
    # Handle the root URL and dynamically inject instance URL into HTML content
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = forwarded_proto if forwarded_proto else request.url.scheme
    instance_url = f"{scheme}://{request.url.netloc}"
    html_content = HTML.replace("{instance_url}", instance_url)
    return html_content

# Optimized function to fetch catalog
async def addon_catalog(type: str, id: str, genre: str = None):
    # Function to fetch catalog of channels
    if type != "tv":
        raise HTTPException(status_code=404)
    
    catalogs = {"metas": []}
    for channel in STREAM["channels"]:
        # Filter by genre if specified
        if genre and genre not in channel.get("genres", []):
            continue
        description = f'Watch {channel["title"]}'
        catalogs["metas"].append({
            "id": channel["id"],
            "type": "tv",
            "name": channel["title"],
            "poster": channel["poster"],
            "description": description,
            "genres": channel.get("genres", [])
        })
    return catalogs

# Optimized function for handling streaming requests concurrently
@app.get('/{config}/stream/{type}/{id}.json')
@limiter.limit("5/second")
async def addon_stream(request: Request, config, type, id):
    # Handle stream request with rate limiting
    if type not in MANIFEST['types']:
        raise HTTPException(status_code=404)
    
    streams = {'streams': []}
    config_providers = config.split('|')
    provider_maps = {name: "0" for name in provider_map.values()}
    
    # Set the active providers based on configuration
    for provider in config_providers:
        if provider in provider_map:
            provider_name = provider_map[provider]
            provider_maps[provider_name] = "1"
    
    # Asynchronous client for parallel API requests
    async with AsyncSession() as client:
        tasks = []
        if type == "tv":
            # Add a task for each provider to handle streams
            tasks.append(asyncio.create_task(handle_stream_provider(client, id, provider_maps, streams)))
            # Await all tasks concurrently
            await asyncio.gather(*tasks)

        # If no streams were found, return an error
        if not streams['streams']:
            raise HTTPException(status_code=404)
        
    return respond_with(streams)

async def handle_stream_provider(client, id, provider_maps, streams):
    i = 0
    # Add streams from different providers
    if provider_maps['STREAMINGCOMMUNITY'] == "1":
        SC_FAST_SEARCH = provider_maps.get('SC_FAST_SEARCH', "")
        url_streaming_community, url_720_streaming_community, quality_sc, slug_sc = await streaming_community(id, client, SC_FAST_SEARCH)
        if url_streaming_community:
            # Append streams for 1080p or 720p based on quality
            if quality_sc == "1080":
                streams['streams'].append({"name": f'MammaMia 1080p Max', 'title': f'{HF}StreamingCommunity {slug_sc}', 'url': url_streaming_community})
                streams['streams'].append({"name": f'MammaMia 720p Max', 'title': f'{HF}StreamingCommunity {slug_sc}', 'url': url_720_streaming_community})
            else:
                streams['streams'].append({"name": f'MammaMia 720p Max', 'title': f'{HF}StreamingCommunity {slug_sc}', 'url': url_streaming_community})

    # Additional providers (e.g., Filmpertutti, LordChannel) can be handled similarly to StreamingCommunity
