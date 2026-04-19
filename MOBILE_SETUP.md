# Mobile Setup (Ngrok)

- Create an account at ngrok.com and copy your auth token.
- Open `.env` and set `NGROK_AUTH_TOKEN=<your_token>`.
- Install dependencies: `pip install -r requirements.txt`.
- Start mobile mode: `python start_mobile.py`.
- Copy the printed `MOBILE URL` to your phone's browser.
- Troubleshooting:
  - Ensure Windows Firewall allows ports 8501.
  - Use the Ngrok HTTPS URL to avoid mixed content issues.
  - Phone must be online; Ngrok requires internet access.
