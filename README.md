# 🎮📺 Game'N'Watch

A Discord bot for tracking games and shows — with multi-profile support, to-do tasks, episode progress, weighted random picking, and automatic metadata from **Steam** and **TVMaze**.

---

## 📁 Project Structure

```
Game'N'Watch/
├── bot.py              # Entry point — loads cogs, syncs commands, startup message
├── db.py               # Google Sheets backend + Steam/TVMaze API + local user mapping
├── profiles.py         # ! commands for profile CRUD
├── games.py            # /newgame, /todo slash commands + ! game management
├── shows.py            # /newshow slash command + ! show management
├── tracker.py          # ! commands for summaries, search, currently playing
├── picker.py           # /random, /list slash commands with button UIs
├── requirements.txt
├── .env                # Environment variables (not committed)
├── credentials.json    # Google service account key (not committed)
└── data/
    └── users.json      # Local Discord ID → profile mapping (not committed)
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
**Requirements:** `discord.py`, `python-dotenv`, `gspread`, `google-auth`

### 2. Create your Discord bot
1. Go to https://discord.com/developers/applications
2. Create a new Application → Bot
3. Enable **Message Content Intent** under Bot → Privileged Gateway Intents
4. Copy your **Bot Token**
5. Invite the bot with scopes: `bot`, `applications.commands`

### 3. Set up Google Sheets
1. Create a Google Cloud project and enable the **Google Sheets API**
2. Create a **Service Account** and download the JSON key as `credentials.json`
3. Create a Google Sheet and share it with the service account email (Editor access)
4. Copy the **Sheet ID** from the URL

### 4. Configure environment
Create a `.env` file:
```env
DISCORD_TOKEN=your_bot_token
GOOGLE_CREDS_FILE=credentials.json
GOOGLE_SHEET_ID=your_sheet_id
STARTUP_CHANNEL_ID=your_channel_id
```

### 5. Run the bot
```bash
python bot.py
```

On first run the bot will automatically create **Games** and **Shows** tabs with the correct headers. If you add new features later, missing columns are auto-added on startup.

---

## 🗂️ Commands

### ⚡ Slash Commands
| Command | Description |
|---|---|
| `/newgame <search>` | Add a game — paste a Steam URL, search by name, or enter manually |
| `/newshow <search>` | Add a show — searches TVMaze by name, or adds manually |
| `/random [profile]` | Pick a random game/show (Random, Top 5, or Battle mode) |
| `/list [profile]` | View your full games or shows list |
| `/todo <game> [profile]` | View & toggle to-do items for a game |

> **Profile is optional** on all commands if you've created one with `!createprofile`. Your Discord account is automatically linked.

---

### 👤 Profile Commands (! prefix)
| Command | Description |
|---|---|
| `!createprofile <name>` | Create a profile (auto-links to your account) |
| `!deleteprofile <name>` | Delete a profile |
| `!renameprofile <old> <new>` | Rename a profile |
| `!profiles` | List all profiles with counts |
| `!profileinfo <name>` | Detailed profile stats |

---

### 🎮 Game Commands (! prefix)
| Command | Description |
|---|---|
| `!viewgame <title>` | View full game details |
| `!updategame <title> <field> <value>` | Update a field |
| `!removegame <title>` | Remove a game |
| `!addtodo <game> \| <task>` | Add a to-do task |
| `!removetodo <game> <id>` | Remove a to-do |

**Fields:** `status`, `priority`, `platform`, `rating`, `notes`, `release_date`, `price`, `developers`, `multiplayer`
**Statuses:** `backlog` · `playing` · `completed` · `dropped`

---

### 📺 Show Commands (! prefix)
| Command | Description |
|---|---|
| `!viewshow <title>` | View full show details |
| `!updateshow <title> <field> <value>` | Update a field |
| `!removeshow <title>` | Remove a show |
| `!progress <title> <episode> [season]` | Log episode progress |

**Fields:** `status`, `priority`, `genre`, `rating`, `notes`, `episode`, `season`, `total_episodes`, `platform`, `premiere_date`
**Statuses:** `backlog` · `watching` · `completed` · `dropped` · `on_hold`

---

### 📊 Tracker Commands (! prefix)
| Command | Description |
|---|---|
| `!summary [profile]` | Full stats overview |
| `!currently [profile]` | Currently playing/watching |
| `!completed [profile]` | All completed items |
| `!search <query>` | Search across all profiles |

---

## 🔌 API Integrations

### Steam (games)
When adding a game with `/newgame`, you can:
- Paste a **Steam store URL** (e.g. `https://store.steampowered.com/app/2868840/Slay_the_Spire_2/`)
- Type a **game name** to search Steam
- If multiple results are found, interactive buttons let you pick the right one

**Auto-filled fields:** Title, Platform (Steam), Release Date, Price, Developers, Multiplayer

### TVMaze (shows)
When adding a show with `/newshow`, you can:
- Type a **show name** to search TVMaze
- Pick from results with interactive buttons

**Auto-filled fields:** Title, Genre, Platform (network/streaming service), Premiere Date, Total Episodes

---

## 🎲 Weighted Random Picker

The `/random` command uses priority-weighted selection:
- **Random Pick** — weighted random from backlog + active items
- **Top 5** — highest priority items with pick probability %
- **Battle** — two weighted picks to choose between

Priority 5 items are 5× more likely to be picked than priority 1 items.

---

## 💾 Data Storage

| Data | Storage | Location |
|---|---|---|
| Games & Shows | Google Sheets | Two tabs: `Games` (12 columns), `Shows` (12 columns) |
| User-profile links | Local JSON | `data/users.json` (Discord IDs — not uploaded) |

### Game Columns
`Profile`, `Title`, `Status`, `Priority`, `Rating`, `Notes`, `Platform`, `Todos`, `Release Date`, `Price`, `Developers`, `Is Multiplayer`

### Show Columns
`Profile`, `Title`, `Status`, `Priority`, `Rating`, `Notes`, `Genre`, `Current Episode`, `Current Season`, `Total Episodes`, `Platform`, `Premiere Date`
```
