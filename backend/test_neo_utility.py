import sys
sys.path.append(r"C:\Users\sbiet\.gemini\antigravity-ide\brain\e16155c8-02b0-495c-9a87-a8d5b84739a9\scratch\kotak_neo")
from neo_api_client.utils.neo_utility import NeoUtility

def main():
    # 1. No base_url set (just consumer key, like scrip_master.md example)
    conf = NeoUtility(consumer_key="test_key", host="prod")
    url = conf.get_url_details("scrip_master")
    print("scrip_master URL (no base_url):", url)
    
    # 2. With base_url set from tradeApiValidate (like our current state)
    conf2 = NeoUtility(consumer_key="test_key", host="prod")
    conf2.base_url = "https://e21.kotaksecurities.com"
    url2 = conf2.get_url_details("scrip_master")
    print("scrip_master URL (with base_url):", url2)

if __name__ == "__main__":
    main()
