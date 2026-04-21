import json
import os
import re
import urllib.request
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials

# ── Google Sheets setup ─────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_gc = None
_sh = None


def _get_sheet():
    global _gc, _sh
    if _sh is None:
        creds_file = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
        _gc = gspread.authorize(creds)
        _sh = _gc.open_by_key(sheet_id)
        _ensure_worksheets()
    return _sh


USER_HEADERS = ["Discord_ID", "Profile"]

_USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")


def _ensure_worksheets():
    """Create Games and Shows tabs with headers if they don't exist, and add any missing columns."""
    existing = [ws.title for ws in _sh.worksheets()]

    if "Games" not in existing:
        ws = _sh.add_worksheet(title="Games", rows=1000, cols=20)
        ws.append_row(GAME_HEADERS)
    else:
        _sync_headers(_sh.worksheet("Games"), GAME_HEADERS)

    if "Shows" not in existing:
        ws = _sh.add_worksheet(title="Shows", rows=1000, cols=20)
        ws.append_row(SHOW_HEADERS)
    else:
        _sync_headers(_sh.worksheet("Shows"), SHOW_HEADERS)

    # Remove default Sheet1 if our tabs exist
    if "Sheet1" in existing and "Games" in [w.title for w in _sh.worksheets()]:
        try:
            _sh.del_worksheet(_sh.worksheet("Sheet1"))
        except Exception:
            pass


def _sync_headers(ws, expected_headers: list[str]):
    """Add any missing columns to the end of a worksheet's header row."""
    current = ws.row_values(1)
    missing = [h for h in expected_headers if h not in current]
    if not missing:
        return
    start_col = len(current) + 1
    for i, header in enumerate(missing):
        ws.update_cell(1, start_col + i, header)


# ── Column layouts ──────────────────────────────────────────────────────────

GAME_HEADERS = [
    "Profile", "Title", "Status", "Priority", "Rating",
    "Notes", "Platform", "Todos",
    "Release Date", "Price", "Developers", "Is Multiplayer"
]

SHOW_HEADERS = [
    "Profile", "Title", "Status", "Priority", "Rating",
    "Notes", "Genre", "Current Episode", "Current Season", "Total Episodes",
    "Platform", "Premiere Date"
]

DEFAULT_GAME = {
    "status": "backlog",
    "priority": 3,
    "rating": None,
    "notes": "",
    "todos": [],
    "platform": "",
    "release_date": "",
    "price": "",
    "developers": "",
    "is_multiplayer": False
}

DEFAULT_SHOW = {
    "status": "backlog",
    "priority": 3,
    "rating": None,
    "notes": "",
    "current_episode": 0,
    "total_episodes": None,
    "current_season": 1,
    "genre": "",
    "platform": "",
    "premiere_date": ""
}


# ── Row <-> dict conversion ────────────────────────────────────────────────

def _game_row_to_dict(row: list) -> dict:
    """Convert a Games sheet row to a game dict."""
    def _get(idx, default=""):
        return row[idx] if idx < len(row) and row[idx] != "" else default

    todos_raw = _get(7, "[]")
    try:
        todos = json.loads(todos_raw) if isinstance(todos_raw, str) else []
    except (json.JSONDecodeError, TypeError):
        todos = []

    rating = _get(4, None)
    priority = _get(3, 3)

    is_mp = _get(11, "False")
    if isinstance(is_mp, str):
        is_mp = is_mp.lower() in ("true", "yes", "1")

    return {
        "status": _get(2, "backlog"),
        "priority": int(priority) if priority is not None else 3,
        "rating": int(rating) if rating is not None and str(rating).strip() else None,
        "notes": _get(5, ""),
        "platform": _get(6, ""),
        "todos": todos,
        "release_date": _get(8, ""),
        "price": _get(9, ""),
        "developers": _get(10, ""),
        "is_multiplayer": is_mp,
    }


def _game_dict_to_row(profile: str, title: str, game: dict) -> list:
    return [
        profile,
        title,
        game.get("status", "backlog"),
        game.get("priority", 3),
        game.get("rating") if game.get("rating") is not None else "",
        game.get("notes", ""),
        game.get("platform", ""),
        json.dumps(game.get("todos", [])),
        game.get("release_date", ""),
        game.get("price", ""),
        game.get("developers", ""),
        str(game.get("is_multiplayer", False)),
    ]


def _show_row_to_dict(row: list) -> dict:
    def _get(idx, default=""):
        return row[idx] if idx < len(row) and row[idx] != "" else default

    rating = _get(4, None)
    priority = _get(3, 3)
    cur_ep = _get(7, 0)
    cur_season = _get(8, 1)
    total_ep = _get(9, None)

    return {
        "status": _get(2, "backlog"),
        "priority": int(priority) if priority is not None else 3,
        "rating": int(rating) if rating is not None and str(rating).strip() else None,
        "notes": _get(5, ""),
        "genre": _get(6, ""),
        "current_episode": int(cur_ep) if cur_ep else 0,
        "current_season": int(cur_season) if cur_season else 1,
        "total_episodes": int(total_ep) if total_ep is not None and str(total_ep).strip() else None,
        "platform": _get(10, ""),
        "premiere_date": _get(11, ""),
    }


def _show_dict_to_row(profile: str, title: str, show: dict) -> list:
    return [
        profile,
        title,
        show.get("status", "backlog"),
        show.get("priority", 3),
        show.get("rating") if show.get("rating") is not None else "",
        show.get("notes", ""),
        show.get("genre", ""),
        show.get("current_episode", 0),
        show.get("current_season", 1),
        show.get("total_episodes") if show.get("total_episodes") is not None else "",
        show.get("platform", ""),
        show.get("premiere_date", ""),
    ]


# ── Internal helpers ────────────────────────────────────────────────────────

def _ws(section: str):
    """Get the worksheet for games or shows."""
    sheet = _get_sheet()
    return sheet.worksheet("Games" if section == "games" else "Shows")


def _find_row(section: str, profile: str, title: str) -> int | None:
    """Find the 1-based row index for a profile+title (case-insensitive). None if not found."""
    ws = _ws(section)
    records = ws.get_all_values()
    for i, row in enumerate(records[1:], start=2):  # skip header
        if (row[0].lower() == profile.lower() and
                len(row) > 1 and row[1].lower() == title.lower()):
            return i
    return None


# ── Profile helpers ─────────────────────────────────────────────────────────

def get_profiles() -> dict:
    """Build a profiles dict from both sheets."""
    profiles = {}

    for section in ("games", "shows"):
        ws = _ws(section)
        records = ws.get_all_values()
        row_to_dict = _game_row_to_dict if section == "games" else _show_row_to_dict

        for row in records[1:]:
            if not row or not row[0]:
                continue
            pname = row[0]
            title = row[1] if len(row) > 1 else ""
            if pname not in profiles:
                profiles[pname] = {"games": {}, "shows": {}}
            if title:
                profiles[pname][section][title] = row_to_dict(row)

    return profiles


def profile_exists(name: str) -> bool:
    return name.lower() in {p.lower() for p in get_profiles()}


def create_profile(name: str) -> bool:
    if profile_exists(name):
        return False
    # Add a marker row in the Games sheet so the profile shows up
    ws = _ws("games")
    ws.append_row([name, "", "", "", "", "", "", "", "", "", "", ""])
    return True


def delete_profile(name: str) -> bool:
    if not profile_exists(name):
        return False

    for section in ("games", "shows"):
        ws = _ws(section)
        records = ws.get_all_values()
        # Delete rows bottom-up to keep indices stable
        rows_to_delete = [
            i for i, row in enumerate(records[1:], start=2)
            if row and row[0].lower() == name.lower()
        ]
        for row_idx in reversed(rows_to_delete):
            ws.delete_rows(row_idx)

    return True


def rename_profile(old: str, new: str) -> bool:
    if not profile_exists(old) or profile_exists(new):
        return False

    for section in ("games", "shows"):
        ws = _ws(section)
        records = ws.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if row and row[0].lower() == old.lower():
                ws.update_cell(i, 1, new)

    return True


# ── Generic item helpers ─────────────────────────────────────────────────────

def get_items(profile: str, section: str) -> dict:
    ws = _ws(section)
    records = ws.get_all_values()
    row_to_dict = _game_row_to_dict if section == "games" else _show_row_to_dict
    items = {}
    for row in records[1:]:
        if (row and row[0].lower() == profile.lower()
                and len(row) > 1 and row[1].strip()):
            items[row[1]] = row_to_dict(row)
    return items


def item_exists(profile: str, section: str, title: str) -> bool:
    return title.lower() in {k.lower() for k in get_items(profile, section)}


def add_item(profile: str, section: str, title: str, **kwargs) -> bool:
    if not profile_exists(profile):
        return False
    if item_exists(profile, section, title):
        return False

    default = DEFAULT_GAME.copy() if section == "games" else DEFAULT_SHOW.copy()
    default.update(kwargs)

    ws = _ws(section)
    to_row = _game_dict_to_row if section == "games" else _show_dict_to_row

    # If there's a placeholder row (empty title) for this profile, replace it
    records = ws.get_all_values()
    for i, row in enumerate(records[1:], start=2):
        if (row and row[0].lower() == profile.lower()
                and (len(row) < 2 or not row[1].strip())):
            ws.delete_rows(i)
            break

    ws.append_row(to_row(profile, title, default))
    return True


def remove_item(profile: str, section: str, title: str) -> bool:
    row_idx = _find_row(section, profile, title)
    if not row_idx:
        return False
    ws = _ws(section)
    ws.delete_rows(row_idx)
    return True


def update_item(profile: str, section: str, title: str, **kwargs) -> bool:
    row_idx = _find_row(section, profile, title)
    if not row_idx:
        return False

    ws = _ws(section)
    row = ws.row_values(row_idx)
    row_to_dict = _game_row_to_dict if section == "games" else _show_row_to_dict
    to_row = _game_dict_to_row if section == "games" else _show_dict_to_row

    item = row_to_dict(row)
    item.update(kwargs)
    new_row = to_row(row[0], row[1], item)

    # Update entire row
    cell_range = f"A{row_idx}:{chr(64 + len(new_row))}{row_idx}"
    ws.update(cell_range, [new_row])
    return True


def get_item(profile: str, section: str, title: str) -> dict | None:
    row_idx = _find_row(section, profile, title)
    if not row_idx:
        return None
    ws = _ws(section)
    row = ws.row_values(row_idx)
    row_to_dict = _game_row_to_dict if section == "games" else _show_row_to_dict
    return row_to_dict(row)


# ── To-do helpers (games only) ────────────────────────────────────────────────

def add_todo(profile: str, game_title: str, task: str) -> int | None:
    row_idx = _find_row("games", profile, game_title)
    if not row_idx:
        return None
    ws = _ws("games")
    row = ws.row_values(row_idx)
    game = _game_row_to_dict(row)
    todos = game.get("todos", [])
    new_id = max((t["id"] for t in todos), default=0) + 1
    todos.append({"id": new_id, "task": task, "done": False})
    ws.update_cell(row_idx, 8, json.dumps(todos))  # col H = Todos
    return new_id


def toggle_todo(profile: str, game_title: str, todo_id: int) -> bool:
    row_idx = _find_row("games", profile, game_title)
    if not row_idx:
        return False
    ws = _ws("games")
    row = ws.row_values(row_idx)
    game = _game_row_to_dict(row)
    todos = game.get("todos", [])
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = not t["done"]
            ws.update_cell(row_idx, 8, json.dumps(todos))
            return True
    return False


def remove_todo(profile: str, game_title: str, todo_id: int) -> bool:
    row_idx = _find_row("games", profile, game_title)
    if not row_idx:
        return False
    ws = _ws("games")
    row = ws.row_values(row_idx)
    game = _game_row_to_dict(row)
    todos = game.get("todos", [])
    new_todos = [t for t in todos if t["id"] != todo_id]
    if len(new_todos) == len(todos):
        return False
    ws.update_cell(row_idx, 8, json.dumps(new_todos))
    return True


# ── Picker helper ───────────────────────────────────────────────────────────

def get_weighted_pool(profile: str, section: str, statuses: list[str]) -> list[dict]:
    items = get_items(profile, section)
    pool = []
    for title, data in items.items():
        if data.get("status") in statuses:
            entry = dict(data)
            entry["title"] = title
            pool.append(entry)
    return pool


# ── Steam lookup ────────────────────────────────────────────────────────────

_STEAM_URL_RE = re.compile(r"store\.steampowered\.com/app/(\d+)")


def parse_steam_input(text: str) -> int | None:
    """Extract a Steam app ID from a URL or plain app-ID string."""
    m = _STEAM_URL_RE.search(text)
    if m:
        return int(m.group(1))
    if text.strip().isdigit():
        return int(text.strip())
    return None


def steam_lookup(app_id: int) -> dict | None:
    """Fetch game info from the Steam store API. Returns a dict or None."""
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "GameNWatch-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    entry = data.get(str(app_id), {})
    if not entry.get("success"):
        return None

    d = entry["data"]

    # Determine multiplayer from categories
    mp_ids = {1, 9, 36, 37, 38, 39}  # Multi-player, Co-op, Online/Local variants
    categories = d.get("categories", [])
    is_mp = any(cat.get("id") in mp_ids for cat in categories)

    # Price
    price_info = d.get("price_overview")
    price_str = price_info["final_formatted"] if price_info else ("Free" if d.get("is_free") else "")

    # Platforms
    plats = d.get("platforms", {})
    platform_list = [p.title() for p in ("windows", "mac", "linux") if plats.get(p)]

    # Genres
    genres = [g["description"] for g in d.get("genres", [])]

    return {
        "name": d.get("name", ""),
        "release_date": d.get("release_date", {}).get("date", ""),
        "price": price_str,
        "developers": ", ".join(d.get("developers", [])),
        "is_multiplayer": is_mp,
        "platform": "Steam",
        "short_description": d.get("short_description", ""),
        "genres": ", ".join(genres),
        "header_image": d.get("header_image", ""),
    }


def steam_search(query: str) -> list[dict]:
    """Search Steam for games by name. Returns list of {app_id, name}."""
    encoded = urllib.parse.quote(query)
    url = f"https://store.steampowered.com/api/storesearch/?term={encoded}&l=en&cc=US"
    req = urllib.request.Request(url, headers={"User-Agent": "GameNWatch-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    results = []
    for item in data.get("items", [])[:5]:
        results.append({"app_id": item["id"], "name": item["name"]})
    return results


# ── TVMaze lookup ───────────────────────────────────────────────────────────

def tvmaze_search(query: str) -> list[dict]:
    """Search TVMaze for shows. Returns list of {id, name, year, network}."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.tvmaze.com/search/shows?q={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "GameNWatch-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    results = []
    for entry in data[:5]:
        show = entry.get("show", {})
        network = show.get("network") or show.get("webChannel")
        net_name = network.get("name", "") if network else ""
        year = show.get("premiered", "")[:4] if show.get("premiered") else ""
        results.append({
            "id": show["id"],
            "name": show.get("name", ""),
            "year": year,
            "network": net_name,
        })
    return results


def tvmaze_lookup(show_id: int) -> dict | None:
    """Fetch show details from TVMaze including episode count. Returns a dict or None."""
    url = f"https://api.tvmaze.com/shows/{show_id}?embed=episodes"
    req = urllib.request.Request(url, headers={"User-Agent": "GameNWatch-Bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
    except Exception:
        return None

    # Network / streaming platform
    network = d.get("network") or d.get("webChannel")
    platform = network.get("name", "") if network else ""

    # Genres
    genres = d.get("genres", [])

    # Episodes & seasons
    episodes = d.get("_embedded", {}).get("episodes", [])
    total_episodes = len(episodes)
    total_seasons = max((ep.get("season", 1) for ep in episodes), default=1) if episodes else 1

    # Image
    images = d.get("image") or {}
    image_url = images.get("medium", "") or images.get("original", "")

    return {
        "name": d.get("name", ""),
        "genre": ", ".join(genres),
        "platform": platform,
        "premiere_date": d.get("premiered", ""),
        "total_episodes": total_episodes,
        "total_seasons": total_seasons,
        "image_url": image_url,
        "summary": (d.get("summary") or "").replace("<p>", "").replace("</p>", "").replace("<b>", "**").replace("</b>", "**").strip(),
    }


# ── User-profile mapping (local JSON) ────────────────────────────────────────

def _load_users() -> dict:
    """Load the Discord ID -> profile mapping from local JSON."""
    if os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_users(data: dict) -> None:
    """Save the Discord ID -> profile mapping to local JSON."""
    os.makedirs(os.path.dirname(_USERS_FILE), exist_ok=True)
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def link_user(discord_id: int, profile: str) -> None:
    """Link a Discord user ID to a profile. Overwrites any existing link."""
    users = _load_users()
    users[str(discord_id)] = profile
    _save_users(users)


def get_profile_for_user(discord_id: int) -> str | None:
    """Get the profile name linked to a Discord user, or None."""
    users = _load_users()
    return users.get(str(discord_id))


def unlink_user(discord_id: int) -> bool:
    """Remove the user-profile link. Returns True if found."""
    users = _load_users()
    if str(discord_id) in users:
        del users[str(discord_id)]
        _save_users(users)
        return True
    return False
