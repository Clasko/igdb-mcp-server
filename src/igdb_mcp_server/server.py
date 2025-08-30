"""
IGDB MCP Server - A Model Context Protocol server for the IGDB (Internet Game Database) API.

This server provides tools to interact with the IGDB API, allowing you to search and retrieve
information about games, platforms, companies, and more.
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any, List, Annotated
from pydantic import Field
from datetime import datetime, timedelta
import httpx
from fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("IGDB API Server")

# Configuration
IGDB_BASE_URL = "https://api.igdb.com/v4"
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"

# Cache for OAuth token
token_cache = {"access_token": None, "expires_at": None}


class IGDBClient:
    """Client for interacting with the IGDB API."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.http_client = httpx.AsyncClient()

    async def get_access_token(self) -> str:
        """Get or refresh the OAuth access token."""
        # Check if we have a valid cached token
        if token_cache["access_token"] and token_cache["expires_at"]:
            if datetime.now() < token_cache["expires_at"]:
                return token_cache["access_token"]

        # Get a new token from Twitch OAuth
        response = await self.http_client.post(
            TWITCH_AUTH_URL,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()

        data = response.json()
        token_cache["access_token"] = data["access_token"]
        # Set expiry slightly before actual expiry for safety
        token_cache["expires_at"] = datetime.now() + timedelta(
            seconds=data["expires_in"] - 300
        )

        return data["access_token"]

    async def make_request(self, endpoint: str, query: str) -> List[Dict[str, Any]]:
        """Make a request to the IGDB API."""
        token = await self.get_access_token()

        response = await self.http_client.post(
            f"{IGDB_BASE_URL}/{endpoint}",
            headers={
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            content=query,
            timeout=30.0,
        )
        response.raise_for_status()

        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()


def get_igdb_client() -> IGDBClient:
    """Get or create the IGDB client singleton."""
    global _igdb_client

    if "_igdb_client" not in globals():
        # Get credentials from environment variables
        client_id = os.getenv("IGDB_CLIENT_ID")
        client_secret = os.getenv("IGDB_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise ValueError(
                "IGDB_CLIENT_ID and IGDB_CLIENT_SECRET environment variables must be set. "
                "Get these from https://api-docs.igdb.com/#account-creation"
            )

        _igdb_client = IGDBClient(client_id, client_secret)

    return _igdb_client


@mcp.tool()
async def search_games(
    query: Annotated[str, Field(description="Search term for finding games")],
    fields: Annotated[
        str, Field(description="Comma-separated list of fields to return")
    ] = "name,summary,rating,first_release_date,platforms.name,cover.url",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 10,
) -> List[Dict[str, Any]]:
    """
    Search for games in the IGDB database.

    Args:
        query: Search term for finding games
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 10, max: 500)

    Returns:
        List of games matching the search criteria
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    search_query = f'search "{query}"; fields {fields}; limit {limit};'
    return await igdb_client.make_request("games", search_query)


@mcp.tool()
async def search_companies(
    name: Annotated[str, Field(description="Company name to search for")],
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,description,country,websites.url,logo.url",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 10,
) -> List[Dict[str, Any]]:
    """
    Search for game companies (publishers/developers).

    Args:
        name: Company name to search for
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 10, max: 500)

    Returns:
        List of companies matching the search criteria
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    query = f'search "{name}"; fields {fields}; limit {limit};'
    return await igdb_client.make_request("companies", query)


@mcp.tool()
async def search_characters(
    name: Annotated[str, Field(description="Character name to search for")],
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,description,games.name,gender,species",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 10,
) -> List[Dict[str, Any]]:
    """
    Search for video game characters.

    Args:
        name: Character name to search for
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 10, max: 500)

    Returns:
        List of characters matching the search criteria
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    query = f'search "{name}"; fields {fields}; limit {limit};'
    return await igdb_client.make_request("characters", query)


@mcp.tool()
async def get_game_details(
    game_id: Annotated[int, Field(description="The IGDB ID of the game")],
    fields: Annotated[
        Optional[str],
        Field(
            description="Comma-separated list of fields to return (default: all fields)"
        ),
    ] = "*",
) -> Dict[str, Any]:
    """
    Get detailed information about a specific game.

    Args:
        game_id: The IGDB ID of the game
        fields: Comma-separated list of fields to return (default: all fields)

    Returns:
        Detailed information about the game
    """
    igdb_client = get_igdb_client()

    query = f"fields {fields}; where id = {game_id};"
    results = await igdb_client.make_request("games", query)

    if not results:
        raise ValueError(f"Game with ID {game_id} not found")

    return results[0]


@mcp.tool()
async def get_platforms(
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,abbreviation,generation,category,summary",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 50,
) -> List[Dict[str, Any]]:
    """
    Get list of gaming platforms.

    Args:
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 50, max: 500)

    Returns:
        List of gaming platforms
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    query = f"fields {fields}; limit {limit}; sort name asc;"
    return await igdb_client.make_request("platforms", query)


@mcp.tool()
async def get_genres(
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,slug,url",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 50,
) -> List[Dict[str, Any]]:
    """
    Get list of game genres.

    Args:
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 50, max: 500)

    Returns:
        List of game genres
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    query = f"fields {fields}; limit {limit}; sort name asc;"
    return await igdb_client.make_request("genres", query)


@mcp.tool()
async def get_game_modes(
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,slug,url",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 50,
) -> List[Dict[str, Any]]:
    """
    Get list of game modes (single-player, multiplayer, etc.).

    Args:
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 50, max: 500)

    Returns:
        List of game modes
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    query = f"fields {fields}; limit {limit}; sort name asc;"
    return await igdb_client.make_request("game_modes", query)


@mcp.tool()
async def get_popular_games(
    fields: Annotated[
        Optional[str],
        Field(description="Comma-separated list of fields to return"),
    ] = "name,summary,rating,rating_count,total_rating,total_rating_count,follows",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 20,
) -> List[Dict[str, Any]]:
    """
    Get currently popular/trending games.

    Args:
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 20, max: 500)

    Returns:
        List of popular games
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    # Get games with high ratings and follows
    query = f"fields {fields}; where rating_count > 50; sort total_rating desc; limit {limit};"

    return await igdb_client.make_request("games", query)


@mcp.tool()
async def get_popularity_data(
    game_id: Annotated[
        Optional[int],
        Field(description="Optional game ID to get popularity data for a specific game"),
    ] = None,
    fields: Annotated[
        str,
        Field(description="Comma-separated list of fields to return"),
    ] = "game_id,value,popularity_type",
    limit: Annotated[
        int, Field(description="Maximum number of results to return", ge=1, le=500)
    ] = 20,
) -> List[Dict[str, Any]]:
    """
    Get list of popularity primitives (relative values), like 'Want to Play', 'IGDB Visits', etc.

    Args:
        game_id: Optional game ID to get popularity data for a specific game
        fields: Comma-separated list of fields to return
        limit: Maximum number of results to return (default: 20, max: 500)

    Returns:
        List of popularity primitives
    """
    igdb_client = get_igdb_client()

    if limit > 500:
        limit = 500

    if game_id:
        query = f"fields {fields}; where game_id = {game_id}; sort value desc; limit {limit};"
    else:
        query = f"fields {fields}; sort value desc; limit {limit};"
        
    return await igdb_client.make_request("popularity_primitives", query)


@mcp.tool()
async def custom_query(
    endpoint: Annotated[
        str,
        Field(
            description="The API endpoint to query (e.g., 'games', 'companies', 'platforms', 'people', 'characters')"
        ),
    ],
    query: Annotated[str, Field(description="The Apicalypse query string")],
) -> List[Dict[str, Any]]:
    """
    Execute a custom IGDB API query.

    This allows advanced users to write their own IGDB queries using the Apicalypse query language.
    See https://api-docs.igdb.com/#apicalypse for query syntax.

    Args:
        endpoint: The API endpoint to query (e.g., "games", "companies", "platforms")
        query: The Apicalypse query string

    Returns:
        Raw response from the IGDB API

    Example:
        endpoint: "games"
        query: "fields name,rating; where rating > 90; sort rating desc; limit 5;"
    """
    igdb_client = get_igdb_client()

    return await igdb_client.make_request(endpoint, query)


# Resources for API documentation
@mcp.resource("igdb://endpoints")
async def get_endpoints() -> str:
    """
    Get a list of available IGDB API endpoints and their descriptions.
    """
    return """
    Available IGDB API Endpoints:
    
    - games: Video game information
    - platforms: Gaming platforms (PC, PlayStation, Xbox, etc.)
    - companies: Game developers and publishers
    - genres: Game genres (Action, RPG, etc.)
    - themes: Game themes (Fantasy, Sci-fi, etc.)
    - game_modes: Game modes (Single-player, Multiplayer, etc.)
    - characters: Video game characters
    - franchises: Game franchises and series
    - collections: Game collections
    - game_engines: Game engines (Unreal, Unity, etc.)
    - artworks: Official game artworks
    - covers: Game cover art
    - screenshots: Game screenshots
    - videos: Game videos and trailers
    - websites: Game-related websites
    - release_dates: Game release dates by region
    - regions: Region for game localization
    - age_ratings: Age ratings from various organizations
    - multiplayer_modes: Multiplayer mode details
    - player_perspectives: Player perspectives (First-person, Third-person, etc.)
    - keywords: Game keywords and tags
    - involved_companies: Companies involved in game development
    - events: Gaming events (E3, GamesCom, etc.)
    - search: Multi-resource search endpoint
    - popularity_primitives: Popularity metrics for games (IGDB Visits, Want to Play, etc.)
    - popularity_types: Types of popularity metrics (Visits, Want to Play, Steam Total Reviews etc.)
    
    Use the custom_query tool to access any of these endpoints with custom queries.
    """


@mcp.resource("igdb://query-syntax")
async def get_query_syntax() -> str:
    """
    Get IGDB Apicalypse query language syntax guide.
    """
    return """
    IGDB Apicalypse Query Language Syntax:
    
    Basic Structure:
    - fields: Select which fields to return
    - exclude: Exclude specific fields
    - where: Filter results
    - sort: Sort results
    - limit: Limit number of results
    - offset: Skip results for pagination
    - search: Text search
    
    Examples:
    
    1. Basic query:
       fields name,rating,summary; limit 10;
    
    2. Filtering:
       fields name,rating; where rating > 80; limit 5;
    
    3. Sorting:
       fields name,first_release_date; sort first_release_date desc; limit 10;
    
    4. Text search:
       search "zelda"; fields name,summary; limit 10;
    
    5. Complex conditions:
       fields name,rating,platforms.name;
       where rating > 75 & platforms = (6,48,130);
       sort rating desc;
       limit 20;
    
    6. Nested fields:
       fields name,cover.url,involved_companies.company.name;
    
    Field Operators:
    - = : Equals
    - != : Not equals
    - > : Greater than
    - >= : Greater than or equal
    - < : Less than
    - <= : Less than or equal
    - ~ : Contains (for arrays)
    - !~ : Does not contain
    
    Logical Operators:
    - & : AND
    - | : OR
    - ! : NOT
    
    Special Values:
    - null : Check for null values
    - () : Array/tuple for multiple values
    - * : All fields (use sparingly)
    """


def run_server():
    """Main entry point for the server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    # Run the server
    run_server()
