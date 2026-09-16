import httpx
from datetime import datetime, timedelta

def main():
    dates_to_test = [
        datetime.utcnow().strftime('%Y-%m-%d'),
        (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d'),
        (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d'),
        "2026-07-14" # The example from the docs
    ]
    
    for date_str in dates_to_test:
        url = f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{date_str}/transformed-v1/nse_fo.csv"
        url2 = f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{date_str}/transformed-v1/nse_fo-v1.csv"
        
        for u in [url, url2]:
            print(f"Testing {u}")
            try:
                res = httpx.head(u, follow_redirects=False)
                print(f"Status: {res.status_code}")
                if res.status_code in [302, 303]:
                    print("Location:", res.headers.get("location"))
                if res.status_code == 200:
                    print(f"SUCCESS: {u}")
                    return
            except Exception as e:
                print(e)

if __name__ == "__main__":
    main()
