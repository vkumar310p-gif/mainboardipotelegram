# Mainboard IPO Telegram Report

A starter automation that runs daily at 4:00 PM IST using GitHub Actions and sends a Telegram message. It attempts to discover Chittorgarh pages for IPO/subscription data and uses InvestorGain's Live IPO GMP page for GMP and update timestamps. Website layouts and JavaScript-rendered tables can change, so verify the first few runs in Actions logs before relying on the figures.

## Setup

### 1. Create a Telegram bot
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, follow the instructions, and copy the bot token.
3. Open your new bot and press **Start** (or send `/start`).

### 2. Find your Telegram chat ID
1. Send a message to your bot.
2. Open this URL in a browser, replacing `BOT_TOKEN` with the token from BotFather:
   `https://api.telegram.org/botBOT_TOKEN/getUpdates`
3. In the JSON response, find `message` → `chat` → `id`. This is your chat ID.
4. Do not share the bot token publicly. If it leaks, revoke it through BotFather.

### 3. Create a GitHub repository
1. Sign in to GitHub and create a new repository, e.g. `mainboard-ipo-telegram`.
2. Upload all files from this folder, including the `.github/workflows/daily-ipo.yml` file.
3. In the repository, open **Settings → Secrets and variables → Actions → New repository secret**.
4. Add:
   - `TELEGRAM_BOT_TOKEN` = your BotFather token
   - `TELEGRAM_CHAT_ID` = your Telegram chat ID
5. Commit to the default branch. In **Actions**, enable workflows if prompted.

### 4. Test immediately
Open **Actions → Daily Mainboard IPO Telegram Report → Run workflow**. Confirm a message arrives in Telegram. Check the job logs if it fails or if fields are N/A.

### Schedule
The workflow uses `30 10 * * *` UTC, equivalent to 4:00 PM IST. GitHub scheduled workflows can be delayed occasionally and are not a guaranteed exact-time delivery service.

## Important data-quality note
This is a starter scraper, not an official API for either site. If Chittorgarh renders a table with JavaScript or changes its markup, the generic parser may not identify the correct columns. Validate extracted figures against the linked source pages before using them. GMP is unofficial; never treat it as a guaranteed listing price or investment recommendation. InvestorGain source: https://www.investorgain.com/report/ipo-gmp-live/331/ipo/
