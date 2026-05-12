# Human URL Audit — agent=smolagents task=dr_cross_deep_0012

For each row: tick `[x]` if the URL is reachable on the sandbox AND its content reasonably supports the surrounding claim. Tick `[?]` if uncertain (need to look longer). Leave blank if FAIL.

Sandbox URLs: shopping=`localhost:7770`, reddit=`localhost:9999`, wiki=`localhost:8090`.

| # | domain | URL | snippet | reachable | supports_claim | notes |
|---:|---|---|---|:---:|:---:|---|
| 1 | reddit | `http://localhost:9999/f/homeautomation` | ve) \| $30–$80 [↗](http://localhost:7770/electronics/security-surveillance.html) \| Good: "S2 is solid, avoid S0 devices" [↗](http://localhost:9999/f/homeautomation) \| \| **Z-Wave Plus** \| 908/868 MHz \| … | `404` | [ ] | |
| 2 | reddit | `http://localhost:9999/f/Hue` | encryption in Light Link profile; rejoin attacks \| [↗](http://localhost:7770/electronics/security-surveillance.html) \| [↗](http://localhost:9999/f/Hue) \| [Zigbee Light Link](http://localhost:8090/cont… | `404` | [ ] | |
| 3 | wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/Mesh_networking` | 090/content/wikipedia_en_all_nopic/A/Zigbee) \|  ## Supplementary References  Additional Wikipedia articles consulted: - [Mesh networking](http://localhost:8090/content/wikipedia_en_all_nopic/A/Mesh_ne… | `200` | [ ] | |
| 4 | reddit | `http://localhost:9999/f/smarthome` | http://localhost:7770/electronics/security-surveillance.html?price=4000-5000) \| Mixed: "WPA2 works but upgrade to WPA3" [↗](http://localhost:9999/f/smarthome) \| \| **Z-Wave** \| 908/868 MHz \| Yes (mesh)… | `404` | [ ] | |
| 5 | shopping | `http://localhost:7770/electronics/security-surveillance.html?price=4000-5000` | WPA2), Dragonblood (WPA3) [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Wi-Fi_Protected_Access) \| $25–$200 [↗](http://localhost:7770/electronics/security-surveillance.html?price=4000-5000… | `200` | [ ] | |
| 6 | wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth_Low_Energy` | \| **Bluetooth Low Energy** \| 2.4 GHz \| No (scatternet) \| GATT pairing \| AES-128 (CCM) \| BLESA, Sweyntooth, BLE Spoofing [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth_Low_Energy)… | `200` | [ ] | |
| 7 | shopping | `http://localhost:7770/electronics/security-surveillance.html` | AES-128 (S2) \| S0 legacy lacks encryption [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Z-Wave) \| $30–$80 [↗](http://localhost:7770/electronics/security-surveillance.html) \| Good: "S2 is … | `200` | [ ] | |
| 8 | wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/Thread_(network_protocol` | \| **Thread** \| 2.4 GHz \| Yes (mesh) \| Border Router (PKI) \| AES-CCM (IEEE 802.15.4) \| No public exploits; v1.3 enhanced [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Thread_(network_proto… | `404` | [ ] | |
| 9 | wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/Zigbee` | sh" \| \| **Zigbee** \| 2.4 GHz \| Yes (mesh) \| Touchlink / coordinator \| AES-128 (APS & NWK) \| Light Link vs Pro confusion [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Zigbee) \| $15–$50 \| G… | `200` | [ ] | |
| 10 | wikipedia | `http://localhost:8090/content/wikipedia_en_all_nopic/A/Insteon` | e Thread/Zigbee" \| \| **Insteon** \| 904 MHz \| Yes (dual-mesh) \| Set-button linking \| 128-bit AES \| Protocol discontinued [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Insteon) \| $40–$100 \|… | `200` | [ ] | |
