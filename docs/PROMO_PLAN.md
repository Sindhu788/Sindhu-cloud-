# 7-day Instagram / TikTok plan (rewritten 5 Nov 2026)
## Storyline: "I built a trading research system as a student, tested it honestly, found no proven edge, and here is what I learned"

**This is a LEARNING story, not a trading promotion.** Nothing here is a signal, a tip or a promise. The honest result is the story: 42 strategies tested properly, none passed.

**The disclaimer (put it ON SCREEN for the whole video and as the FIRST line of every caption):**
> **Paper trading project. Educational only. Not financial advice. No real money.**

## 1. Numbers you may quote (each one is verified; source in brackets)
| Say this | Source |
|---|---|
| "I tested 42 trading rules" | docs/BACKTEST_RESULTS.md, STRATEGY_FORENSICS.md |
| "on 47 coins, over 10 months of real price data, with trading costs included" | same; dataset docs/DATA_QUALITY.md |
| "None of the 42 passed my tests" (0 robust; 1 'fragile'; 36 failed; 5 could not be judged) | STRATEGY_FORENSICS.md |
| "Trading costs of about 0.3 % per round trip are bigger than the tiny edge some rules showed" | cost model, docs/BACKTEST_PROTOCOL.md |
| "A counting bug made a losing rule look like a big winner (a statistic of +11 instead of -11)" | docs/BACKTEST_RESULTS.md "Metrics audit" |
| "For 40 of the 42 rules I could not tell them apart from random entries" | docs/STRATEGY_FORENSICS.md (null model) |
| "The best-looking rule earned everything in one 5-week window and lost when I changed one setting by 10 %" | STRATEGY_FORENSICS.md, Ichimoku dossier |
| "I pre-registered a forward test: the real answer comes in January 2027" | docs/BACKTEST_PROTOCOL.md section 9 |
**Do NOT quote:** any profit figure, win rate, "accuracy", the paper P&L of any group of trades, any single trade, any live signal, any coin name as a recommendation, the number of messages sent to any group, or anything about who receives them.

## 2. Seven-day calendar (each video 30-60 s, vertical 9:16, English with a one-line Roman-Urdu hook)
Spoken scripts are about 90-130 words. "Shots" use REAL dashboard screens; every screen must be masked as described in section 4.

### Day 1 - Who I am and what "paper trading" means
- **Hook (Roman Urdu on screen):** "Pretend paison se trading seekhi."
- **Script:** "I'm a student in Pakistan. A few months ago I started building a program that watches crypto charts and writes down what it WOULD trade, using pretend money. No real money, ever. Why? Because I wanted to learn how trading really works without losing anything. This week I'll show you what I built, what I tested, and the honest result. Spoiler: it did not work, and that's the interesting part."
- **On-screen text:** "Paper trading = pretend money" / the disclaimer.
- **Caption:** "Paper trading project. Educational only. Not financial advice. No real money. I'm a student building a trading research program and sharing the honest results all week."
- **Hashtags:** #papertrading #studentdeveloper #python #learning #buildinpublic
- **Shots:** (1) you at your desk or the laptop screen, no face required; (2) dashboard home page (masked); (3) a close-up of a candlestick chart (any public chart, no logos).
- **Text-to-video prompt:** "Vertical 9:16 cinematic shot, a student's desk at night, laptop showing abstract green and red candlestick charts, warm lamp light, shallow depth of field, no text, no logos, no people's faces, 6 seconds."

### Day 2 - The robot: what it actually does
- **Hook:** "Robot kya karta hai?"
- **Script:** "My program watches many coins. It has 42 rule sets, like 'wait for price to dip below a recent low, then look for a bounce'. When a rule fires it writes a pretend trade. But before anything counts it must pass safety checks: is the data fresh, is there enough evidence, is too much pretend money on one coin. Rules are cheap. Checks are what keep you honest."
- **On-screen text:** "42 rules" / "Safety checks first" / disclaimer.
- **Caption:** disclaimer first line, then: "Rules are easy to write. Honest testing is the hard part."
- **Hashtags:** #algotrading #coding #fastapi #riskmanagement #python
- **Shots:** strategy list page (names visible is fine, no private notes); the decision-trace table; the safety-gate settings page (hide any chat id or token fields).
- **Text-to-video prompt:** "Vertical 9:16 abstract animation: many small glowing rule cards on a dark background pass through three translucent gates in a row, only a few continue, calm blue palette, no text, no logos, 8 seconds."

### Day 3 - The honest test (this is the important one)
- **Hook:** "Test aisa jo mujhe jhoota na bana sake."
- **Script:** "A backtest can fool you. So I built a stricter test: ten months of real price data, 47 coins, trading costs included, the data split into time windows, and a rule must work in most windows and most coins. I also compare every rule with random entries, and with two boring textbook rules. If you can't beat luck, you have nothing."
- **On-screen text:** "47 coins / 10 months / costs included" / "Beat random entries or it's luck" / disclaimer.
- **Caption:** disclaimer, then: "How I try NOT to fool myself: costs, time windows, random baselines."
- **Hashtags:** #backtesting #datascience #statistics #honest #learning
- **Shots:** the results table (labels column), the protocol document headings, a terminal showing the evaluation running (masked paths are fine).
- **Text-to-video prompt:** "Vertical 9:16 infographic style animation: a long timeline split into eight coloured blocks, a magnifying glass moves over each block, a small dice rolls beside a line chart, clean minimal flat design, dark background, no readable text, 8 seconds."

### Day 4 - The scoreboard: 0 out of 42
- **Hook:** "42 mein se 0."
- **Script:** "Here is the result. Out of 42 rules, zero passed. 36 lost money after costs. 5 had too few trades to judge. One looked okay, but its profit came from one five-week stretch, and when I changed one setting by ten percent it turned into a loss. Trading costs of about 0.3 percent per trade were bigger than any edge I could find. That's not a failure of the project. That's the finding."
- **On-screen text:** "0 of 42 passed" / "Costs ate the edge" / disclaimer.
- **Caption:** disclaimer, then: "I would rather publish a zero than a lucky chart."
- **Hashtags:** #honesty #trading #datascience #results #student
- **Shots:** the label counts (or a simple bar chart you make from them), the Ichimoku per-window table (one big window, the rest negative).
- **Text-to-video prompt:** "Vertical 9:16 minimal animation: a scoreboard with 42 small squares, all of them fade from yellow to grey one by one, a calm voice-over friendly style, soft piano mood lighting, no numbers except a large '0', no logos, 8 seconds."

### Day 5 - The bug that made a loser look like a winner
- **Hook:** "Ek bug ne haari hui strategy ko jeeta hua dikha diya."
- **Script:** "One rule showed a super-strong statistic, plus eleven, while losing money. I checked it with a second, separate calculation. The cause: when a trade closes in two parts, my code counted the two parts as two trades and averaged the wrong thing. Fixed, tested, and the real number was minus eleven. Lesson: if a result looks too good, assume a bug first."
- **On-screen text:** "+11 → -11" / "Too good = check for bugs" / disclaimer.
- **Caption:** disclaimer, then: "The best debugging habit: recompute the number a different way."
- **Hashtags:** #debugging #python #bugs #softwareengineering #testing
- **Shots:** the 'Metrics audit' section of the results page; a split screen of two calculation outputs (use the independent recompute script's output); green tests.
- **Text-to-video prompt:** "Vertical 9:16 animation: a balance scale that tips the wrong way, then a hand adds a second scale beside it and both settle, clean flat design, warm colours, no text, no logos, 6 seconds."

### Day 6 - The luck test (and the boring safety work)
- **Hook:** "Kya sikka bhi itna hi kama leta?"
- **Script:** "My favourite test: I take a rule's trades and replay them at random times, same direction mix, same holding times, same costs. For 40 of 42 rules I could not tell the rule apart from the random version. That means there is no proof of timing skill. I also back up the database, restore it into a throw-away copy, and check every table count. Boring work, but it is what lets me trust a number."
- **On-screen text:** "Random entries vs the rule" / "Backup restored: all tables match" / disclaimer.
- **Caption:** disclaimer, then: "If a coin-flip does as well, the rule has no edge."
- **Hashtags:** #statistics #backup #devops #datascience #learning
- **Shots:** the null-model comparison table; the restore output (counts only, no names of private tables if you prefer).
- **Text-to-video prompt:** "Vertical 9:16 animation: a coin flipping in slow motion above a flat line chart, then a second chart appears with random dots, minimal dark theme, soft glow, no text, no logos, 6 seconds."

### Day 7 - What I learned and what is next
- **Hook:** "Sabse bada sabaq."
- **Script:** "Three lessons. One: most rules do not survive honest testing. Two: costs matter more than clever ideas. Three: your test must be able to say no. Next, I will collect more history, run a forward test whose rules I wrote down in advance, and only trust a result that survives it. I'm not offering signals or advice, this is a learning project. Ask me how I built it in the comments."
- **On-screen text:** "1) Most ideas fail 2) Costs matter 3) The test must be able to say NO" / disclaimer.
- **Caption:** disclaimer, then: "Follow the journey if you like learning, not tips. I will not post trading signals."
- **Hashtags:** #buildinpublic #lessonslearned #python #student #pakistan
- **Shots:** the 'go-live criteria' page (mostly 'not met': that is the point); the pre-registration text; you closing the laptop.
- **Text-to-video prompt:** "Vertical 9:16 calm closing shot: a student closes a laptop at sunrise, a window with soft light, a notebook with hand-drawn charts, shallow depth of field, no faces, no text, no logos, 6 seconds."

## 3. Compliance checklist (tick every line before posting each video)
- [ ] The disclaimer is on screen for the whole video AND is the first line of the caption: "Paper trading project. Educational only. Not financial advice. No real money."
- [ ] No profit claim, no "win rate", no "accuracy", no "guaranteed", no "easy money", no before/after profit screenshot.
- [ ] No signal, tip, entry, stop or target; no coin recommended; no "buy" or "sell" call to action. Do not show or read out any real message sent to any group.
- [ ] No mention of any Telegram group, channel, link or membership; no invitation to join anything.
- [ ] No exchange referral links, no brokers, no paid course, no donation request.
- [ ] Every number spoken is in section 1 of this file. If it is not there, do not say it.
- [ ] No secrets or identifiers visible (see section 4); every screen recording was checked frame by frame.
- [ ] AI-generated video or voice is labelled as AI-generated if the platform asks (Instagram "AI info", TikTok "AI-generated content" label). Check music licence (use the platform's own library).
- [ ] **Check the rules yourself before the first post:** Pakistan's rules on financial content and advertising (SECP guidance on investment advice and promotion; PTA rules) and the Instagram / TikTok financial-content policies. **NOT VERIFIED by me**: I could not read them; if a rule says educational content about trading needs a licence or a different wording, follow it and change the script.
- [ ] Comments: reply to requests for signals with "This project does not give signals or advice." Pin a comment repeating the disclaimer.

## 4. What NOT to show (mask or avoid completely)
- Telegram bot token, chat ids, channel/group names, invite links, member lists, any Telegram message text.
- Database URLs, API tokens, the sync secret, login pages with usernames or cookies, the Render dashboard Environment page, GitHub tokens.
- Your email address, phone number, bank or exchange account pages, real balances.
- The Telegram settings page of the dashboard and the dashboard's "signals" / "sent messages" pages.
- Real position lists of the live paper account (they look like signals): use the backtest results tables instead.
- Browser tabs, bookmarks and notifications on your screen (record only the dashboard window; turn on Do Not Disturb).
**How to make safe screenshots:** open the dashboard locally, go to the page, record only that window, then check each frame for the items above; blur or crop them. Prefer the documents (docs/BACKTEST_RESULTS.md tables) over live pages.

## 5. Production notes
Record screen at 1080x1920 or crop to 9:16; keep sentences short; read the script once at normal speed (aim for 35-55 seconds); captions on; same posting time each day; one idea per video. If a viewer asks "which coin should I buy?", the answer is always "this project does not give advice."
