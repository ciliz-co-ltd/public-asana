# Requirements
- Python 3.10
- requirements.txt (pip install -r requirements.txt)
- `.env.test` with env variables see `.env.test.sample`

# How it works
1) GitHub action clones this repository 
2) It sets all variables mentioned in `.env.test`
3) Then it launches `asana_sync.py` with the corresponding parameters (e.g. opened/closed/updated/approved/comment)

# How to debug
1) Set debug values in `.env.test`
2) Launch it as `python asana_sync.py <action>`, e.g.:
   1) `python asana_sync.py open`
   2) or configure your IDE for debug
