import httpx
from app.config import settings
import logging
import json
import base64

logging.basicConfig(level=logging.DEBUG)

def main():
    consumer_key = settings.kotak_neo_consumer_key
    mobile = settings.kotak_neo_mobile_number
    ucc = settings.kotak_neo_ucc
    mpin = settings.kotak_neo_mpin
    totp = settings.kotak_neo_totp
    
    # 1. Login
    login_url = "https://mis.kotaksecurities.com/login/1.0/tradeApiLogin"
    login_headers = {
        "Authorization": consumer_key,
        "neo-fin-key": "neotradeapi",
        "Content-Type": "application/json"
    }
    login_payload = {"mobileNumber": mobile, "ucc": ucc, "totp": totp}
    res_login = httpx.post(login_url, headers=login_headers, json=login_payload)
    if res_login.status_code != 200:
        print("Login failed:", res_login.text)
        return
    login_data = res_login.json()["data"]
    view_token = login_data["token"]
    view_sid = login_data["sid"]
    
    # 2. Validate
    val_url = "https://mis.kotaksecurities.com/login/1.0/tradeApiValidate"
    val_headers = {
        "Authorization": consumer_key,
        "neo-fin-key": "neotradeapi",
        "sid": view_sid,
        "Auth": view_token,
        "Content-Type": "application/json"
    }
    val_payload = {"mpin": mpin}
    res_val = httpx.post(val_url, headers=val_headers, json=val_payload)
    if res_val.status_code != 200:
        print("Validate failed:", res_val.text)
        return
    val_data = res_val.json()["data"]
    trade_token = val_data["token"]
    trade_sid = val_data["sid"]
    dynamic_base = val_data["baseUrl"]
    
    print(f"Auth Success! View Token: {view_token[:10]}... Trade Token: {trade_token[:10]}...")
    
    # 3. Test Scrip Master
    urls = [
        f"https://mis.kotaksecurities.com/script-details/1.0/masterscrip/file-paths",
        f"{dynamic_base}/script-details/1.0/masterscrip/file-paths",
    ]
    
    tokens = [
        ("consumer_key", consumer_key),
        ("Bearer consumer_key", f"Bearer {consumer_key}"),
        ("view_token", view_token),
        ("Bearer view_token", f"Bearer {view_token}"),
        ("trade_token", trade_token),
        ("Bearer trade_token", f"Bearer {trade_token}"),
    ]
    
    for url in urls:
        for t_name, t_val in tokens:
            for use_fin_key in [False, True]:
                print(f"\n--- URL: {url} | Token: {t_name} | Fin-Key: {use_fin_key} ---")
                headers = {
                    "Authorization": t_val,
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                if use_fin_key:
                    headers["neo-fin-key"] = "neotradeapi"
                try:
                    res = httpx.get(url, headers=headers)
                    print(f"Status: {res.status_code}")
                    if res.status_code == 200:
                        print("SUCCESS:", res.json())
                        return
                    else:
                        print("Error msg:", res.text[:100])
                except Exception as e:
                    print("Error:", e)

if __name__ == "__main__":
    main()
