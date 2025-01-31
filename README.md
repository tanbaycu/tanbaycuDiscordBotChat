# Tanbaycu Discord Bot Chat

Tanbaycu Discord Bot Chat is a versatile and intelligent Discord bot designed to enhance your server experience with a variety of features including games, fun commands, and useful utilities.

## Features

- **Advanced Logging**: Detailed logging to `bot.log` for monitoring and debugging.
- **SSL Verification Disabled**: For aiohttp requests to avoid SSL verification issues.
- **SQLite Database**: Persistent storage for long-term memory.
- **Gemini API Integration**: Utilizes Gemini API for generating intelligent responses.
- **Word Chain Game**: A fun word chain game with specific rules.
- **Random Facts and Jokes**: Fetches random facts and jokes from various APIs.
- **Random Quotes**: Provides random quotes with translation support.
- **Random Images**: Fetches random images from multiple sources.
- **Coin Flip**: Simulates a coin flip.
- **Admin Commands**: Includes commands for server administration.

## Commands

### Main Commands
- `/ping`: Check the bot's latency.
- `/helpme`: Display the list of available commands.
- `/stop`: Stop the bot's activity for a specific user.
- `/continue`: Continue the bot's activity for a specific user.
- `/clearmemory`: Clear the short-term memory of the user.
- `/clearall`: Clear all memory of the user.

### General Commands
- `/invite`: Get the invite link for the bot.
- `/botinfo`: Display information about the bot.
- `/server`: Get the support server link.
- `/serverinfo`: Display information about the current server.

### Fun Commands
- `/fact`: Get a random fact or joke.
- `/stopfact`: Stop receiving random facts or jokes.
- `/quote`: Get a random quote with translation.
- `/randomimage`: Get a random image.
- `/coinflip`: Flip a coin.

### Game Commands
- `/noitu`: Start or continue the word chain game.
- `/stopnoitu`: Stop the word chain game.

### Admin Commands
- `/shutdown`: Shut down the bot (admin only).
- `/kick`: Kick a member from the server.
- `/ban`: Ban a member from the server.
- `/warning`: Warn a member.
- `/say`: Make the bot say something.
- `/embed`: Send an embedded message.
- `/reload`: Reload a bot extension.
- `/sendcontact`: Send a direct message to a user.

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/tanbaycu-discord-bot-chat.git
    cd tanbaycu-discord-bot-chat
    ```

2. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Configure the bot by updating the  file with your Discord bot token and Gemini API key.

4. Run the bot:
    ```sh
    python bot.py
    ```

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## Support

For support, join our [Discord server](https://discord.gg/GknzmQmX).

---

Thank you for using Tanbaycu Discord Bot Chat! We hope it enhances your Discord server experience.