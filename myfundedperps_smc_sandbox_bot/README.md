# MyFundedPerps 1m SMC Sandbox Bot

Sandbox-only starter for 1-minute SMC-style signal monitoring. It refuses non-sandbox API keys and never submits orders in this version.

## Run
1. Python 3.11+
2. pip install -r requirements.txt
3. Set FP_API_KEY and FP_ACCOUNT_ID as secure environment variables.
4. Keep DRY_RUN=true.
5. python bot.py

Do not put API keys in GitHub or chat. Validate the API schema and signals before any future execution work.
