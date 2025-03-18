# VRChat World Showcase Bot

A Discord bot for creating and managing a VRChat world showcase in your server. This bot creates a forum channel where users can easily share VRChat worlds, complete with details fetched directly from the VRChat API.

## Features

- Creates a dedicated forum channel for showcasing VRChat worlds
- Extracts detailed information from VRChat API (size, platform, capacity, etc.)
- Organizes worlds with tags for easy filtering and discovery
- Sets up proper permissions to prevent spam
- Prevents duplicate world submissions
- Supports scanning and fixing issues automatically
- Uses a modern, modular architecture for maintainability

## Requirements

- Python 3.8+
- discord.py 2.0+
- A Discord bot token
- VRChat API authentication credentials

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/vrchat-showcase-bot.git
cd vrchat-showcase-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your credentials:
```
DISCORD_TOKEN=your_discord_bot_token_here
VRCHAT_AUTH=your_vrchat_auth_token_here
VRCHAT_API_KEY=your_vrchat_api_key_here
```

4. Run the bot:
```bash
python main.py
```

## Getting VRChat API Credentials

To get your VRChat API credentials:

1. Log in to VRChat website
2. Use browser developer tools to inspect your cookies
3. Find the `auth` cookie value and use it as `VRCHAT_AUTH`
4. Optionally, find the API key from network requests to use as `VRCHAT_API_KEY`

## Commands

### User Commands
- `/world` - Create a world submission button in the current channel
- `/test` - Check if the bot is online
- `/about` - Learn about the bot
- `/help` - Show available commands

### Admin Commands
- `/world-create` - Create a new forum channel for VRChat worlds
- `/world-set` - Set up an existing forum channel for VRChat worlds
- `/world-remove` - Remove a specific world post
- `/scan` - Scan forum for issues with interactive fix options
- `/clean-db` - Clean database entries for deleted channels
- `/sync` - Sync bot commands (admin only)

## World Submission Process

1. Users click the "World" button in the pinned thread
2. They enter a VRChat world URL
3. They select appropriate tags
4. The bot creates a new thread with world details and a visit link

## Project Structure

```
vrchat_showcase_bot/
├── main.py                 # Entry point for the bot
├── config.py               # Configuration and constants
├── database/               # Database modules
│   ├── db.py               # Database connection and setup
│   └── models.py           # Database models/operations
├── cogs/                   # Command modules
│   ├── admin_commands.py   # Admin commands
│   ├── user_commands.py    # User-facing commands
│   └── maintenance.py      # Maintenance commands
├── ui/                     # UI components
│   ├── buttons.py          # Button components
│   ├── modals.py           # Modal components
│   └── views.py            # View components
└── utils/                  # Utility modules
    ├── api.py              # VRChat API handling
    ├── formatters.py       # Text formatting utilities
    └── embed_builders.py   # Discord embed builders
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request