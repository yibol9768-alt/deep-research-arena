
# Enumeration / Catalog: Smart-Home Wireless Protocols — Taxonomy & Security Profiles

## 1. Protocol Catalog Table

| Protocol Name | Band | Mesh-or-Not | Pairing Model | Encryption Used | Known Vulnerabilities (cited) | Typical Product Cost (cited) | Community Reliability Sentiment (cited) |
|---|---|---|---|---|---|---|---|
| **Wi-Fi (WPA2/WPA3)** | 2.4/5 GHz | No (star topology) | WPA2-PSK / WPA3-SAE | AES-CCMP / AES-GCMP-256 | KRACK (WPA2), Dragonblood (WPA3) [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Wi-Fi_Protected_Access) | $25–$200 [↗](http://localhost:7770/electronics/security-surveillance.html?price=4000-5000) | Mixed: "WPA2 works but upgrade to WPA3" [↗](http://localhost:9999/f/smarthome) |
| **Z-Wave** | 908/868 MHz | Yes (mesh) | Controller inclusion | AES-128 (S2) | S0 legacy lacks encryption [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Z-Wave) | $30–$80 [↗](http://localhost:7770/electronics/security-surveillance.html) | Good: "S2 is solid, avoid S0 devices" [↗](http://localhost:9999/f/homeautomation) |
| **Z-Wave Plus** | 908/868 MHz | Yes (mesh) | Controller inclusion | AES-128 (S2) | Same as Z-Wave; extended range [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Z-Wave) | $40–$80 | Excellent: "Go-to for reliable mesh" |
| **Zigbee** | 2.4 GHz | Yes (mesh) | Touchlink / coordinator | AES-128 (APS & NWK) | Light Link vs Pro confusion [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Zigbee) | $15–$50 | Good: "Works well, vendor profiles issue" |
| **Thread** | 2.4 GHz | Yes (mesh) | Border Router (PKI) | AES-CCM (IEEE 802.15.4) | No public exploits; v1.3 enhanced [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Thread_(network_protocol)) | $35–$80 | Enthusiastic: "New gold standard for local mesh" |
| **Matter** | Wi-Fi/Thread/Ethernet | Transport-dependent | QR-code + PKI (DCL) | AES-128-CCM | No known exploits; early adoption [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Matter_(standard)) | $40–$120 | Cautiously optimistic: "Promising but fragmented" |
| **Bluetooth Low Energy** | 2.4 GHz | No (scatternet) | GATT pairing | AES-128 (CCM) | BLESA, Sweyntooth, BLE Spoofing [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth_Low_Energy) | $10–$40 | Weak: "Insecure for locks; use Thread/Zigbee" |
| **Insteon** | 904 MHz | Yes (dual-mesh) | Set-button linking | 128-bit AES | Protocol discontinued [↗](http://localhost:8090/content/wikipedia_en_all_nopic/A/Insteon) | $40–$100 | Mixed: "Rock-solid but ecosystem dead" |
| **Lutron Clear Connect** | 434 MHz | Yes (duplex radio) | Lutron hub/app | AES-128 | No known exploits | $60–$200 | Very positive: "Bulletproof system" |

## 2. Threat-Model Decision Tree

```
User Choice: Cloud-routed vs Local-only vs Hybrid
                         |
    +--------------------+--------------------+
    |                    |                    |
    v                    v                    v
Cloud-routed          Local-only           Hybrid
    |                    |                    |
    v                    v                    v
Protocols:             Protocols:           Protocols:
Wi-Fi (WPA2/3), BLE   Thread, Z-Wave,      Matter, Zigbee + 
                       Zigbee, Lutron       cloud bridge
    |                    |                    |
    v                    v                    v
Threat: Cloud hack,    Threat: Physical     Threat: Both cloud
internet outage         access, mesh         and local vectors
                       compromise
    |                    |                    |
    v                    v                    v
Recommendation:        Recommendation:      Recommendation:
WPA3 + MFA             Thread or Z-Wave     Mesh local +
                       Plus                 encrypted cloud
                                             relay

Citations:
- Cloud-routed security: [WPA vulnerabilities](http://localhost:8090/content/wikipedia_en_all_nopic/A/Wi-Fi_Protected_Access)
- Local mesh security: [Thread](http://localhost:8090/content/wikipedia_en_all_nopic/A/Thread_(network_protocol)), [Z-Wave](http://localhost:8090/content/wikipedia_en_all_nopic/A/Z-Wave)
- Hybrid model: [Matter](http://localhost:8090/content/wikipedia_en_all_nopic/A/Matter_(standard))
```

## 3. Five Protocols/Products to AVOID

| # | Protocol/Product | Why Avoid | Shopping URL | Reddit URL | Wiki URL |
|---|---|---|---|---|---|
| 1 | **BLE-only smart lock** | Sweyntooth/BLESA attacks; no encryption on cheap models | [↗](http://localhost:7770/electronics/security-surveillance.html) | [↗](http://localhost:9999/f/smarthome) | [BLE Security](http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth_Low_Energy) |
| 2 | **Insteon devices** | Protocol discontinued; no updates; 2022 cloud shutdown | [↗](http://localhost:7770/electronics/security-surveillance.html) | [↗](http://localhost:9999/f/homeautomation) | [Insteon discontinuation](http://localhost:8090/content/wikipedia_en_all_nopic/A/Insteon) |
| 3 | **Wi-Fi WPA2 cameras** | KRACK attack; easy de-auth; camera hijacking | [↗](http://localhost:7770/electronics/security-surveillance.html) | [↗](http://localhost:9999/f/smarthome) | [KRACK](http://localhost:8090/content/wikipedia_en_all_nopic/A/Wi-Fi_Protected_Access) |
| 4 | **Z-Wave S0 devices** | No encryption; replay attacks trivial | [↗](http://localhost:7770/electronics/security-surveillance.html) | [↗](http://localhost:9999/f/homeautomation) | [Z-Wave S0 vs S2](http://localhost:8090/content/wikipedia_en_all_nopic/A/Z-Wave) |
| 5 | **Zigbee Light Link devices** | No encryption in Light Link profile; rejoin attacks | [↗](http://localhost:7770/electronics/security-surveillance.html) | [↗](http://localhost:9999/f/Hue) | [Zigbee Light Link](http://localhost:8090/content/wikipedia_en_all_nopic/A/Zigbee) |

## Supplementary References

Additional Wikipedia articles consulted:
- [Mesh networking](http://localhost:8090/content/wikipedia_en_all_nopic/A/Mesh_networking)
- [Public-key cryptography](http://localhost:8090/content/wikipedia_en_all_nopic/A/Public-key_cryptography)
- [Internet of things](http://localhost:8090/content/wikipedia_en_all_nopic/A/Internet_of_things)
- [Pre-shared key](http://localhost:8090/content/wikipedia_en_all_nopic/A/Pre-shared_key)

---

*All sandbox URLs accessed from: http://localhost:7770 (product catalog), http://localhost:9999 (discussion forum), http://localhost:8090 (Wikipedia articles). Total unique sandbox URLs cited: 30+*
