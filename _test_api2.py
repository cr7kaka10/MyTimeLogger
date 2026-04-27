import json, asyncio, httpx

cfg = json.load(open('config.json'))
tt = cfg['ticktick_config']
token = tt['access_token']
host = tt['host']

async def test():
    async with httpx.AsyncClient(headers={'Authorization': f'Bearer {token}'}, verify=False) as c:
        # Get habits
        r = await c.get(f'https://api.{host}/open/v1/habit')
        habits = r.json()
        target = next((h for h in habits if '比亚迪' in h.get('name', '')), habits[0])
        print(f"Target habit: {target['name']} (id={target['id']}, type={target.get('type')}, goal={target.get('goal')}, step={target.get('step')})")
        
        # Checkin
        stamp = 20260426
        payload = {'stamp': stamp, 'status': 0, 'value': target.get('step', 1.0)}
        print('Sending payload:', payload)
        r2 = await c.post(f'https://api.{host}/open/v1/habit/{target["id"]}/checkin', json=payload)
        print('Checkin resp:', r2.status_code, r2.text)
        
        # Get checkins
        r3 = await c.get(f'https://api.{host}/open/v1/habit/checkins?habitIds={target["id"]}&from=20260426&to=20260426')
        print('Checkins:', r3.status_code, r3.json())

asyncio.run(test())
