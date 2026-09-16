import httpx
from app.config import settings
import logging

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
    print("Performing tradeApiLogin...")
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
    print("Performing tradeApiValidate...")
    res_val = httpx.post(val_url, headers=val_headers, json=val_payload)
    if res_val.status_code != 200:
        print("Validate failed:", res_val.text)
        return
    val_data = res_val.json()["data"]
    trade_token = val_data["token"]
    
    print("Auth Success! Now testing Scrip Master Headers...\n")
    
    url = "https://mis.kotaksecurities.com/script-details/1.0/masterscrip/file-paths"
    
    headers_to_test = [
        {"Authorization": consumer_key, "neo-fin-key": "neotradeapi"},
        {"Authorization": consumer_key},
        {"Authorization": f"Bearer {consumer_key}"},
        {"Authorization": f"Bearer {view_token}"},
        {"Authorization": f"Bearer {trade_token}"},
        {"Authorization": view_token},
        {"Authorization": trade_token},
        {"Authorization": consumer_key, "Auth": view_token, "sid": view_sid},
        {"Authorization": consumer_key, "Auth": trade_token, "sid": view_sid}
    ]
    
    for headers in headers_to_test:
        print(f"Testing headers: {list(headers.keys())}")
        print(f"Auth header value preview: {headers['Authorization'][:15]}...")
        try:
            res = httpx.get(url, headers=headers)
            print(f"Status: {res.status_code}")
            if res.status_code == 200:
                print("SUCCESS!", res.json())
                return
            else:
                print("Error:", res.text[:100])
        except Exception as e:
            print("Exception:", str(e))
        print("-" * 40)

if __name__ == "__main__":
    main()
