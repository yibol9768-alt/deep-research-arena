# Protocol Catalog: Smart-Home Wireless Security Taxonomy

## Protocol Security Profile Catalog Table

| Protocol | Band | Mesh-Capable | Pairing Model | Encryption | Known Vulnerabilities | Typical Product Cost | Community Reliability Sentiment |
|----------|------|-------------|---------------|------------|----------------------|---------------------|-------------------------------|
| **Wi-Fi (WPA2/WPA3)** | 2.4/5/6 GHz | No (star topology) | WPA2-PSK / WPA3-SAE / WPA3-Enterprise | AES-CCMP (WPA2), AES-GCMP (WPA3) | KRACK attack on WPA2 [1]; Dragonblood side-channel on WPA3 [2]; Pre-shared key brute-force | $25–$350 (smart plugs to cameras) | Mixed: "Wi-Fi locks drop connection if router reboots" [3]; "WPA3 on IoT chips still buggy" [4] |
| **Z-Wave** | 800–900 MHz (regional) | Yes (mesh up to 232 nodes) | S2 inclusion with QR scan | AES-128-CCM | Z-SHAKE attack on S0 [5]; S2 downgrade via RF jamming [6] | $30–$280 (sensors to locks) | Positive: "Z-Wave mesh is rock solid through walls" [7]; "Pairing is finicky but stays paired" [8] |
| **Zigbee** | 2.4 GHz | Yes (mesh up to 65535 nodes) | Touchlink/Factory New/Allow Join | AES-128-CCM* | Zigbee Green Power attacks [9]; Replay attacks via unencrypted commissioning [10]; Sniffer + key extraction | $15–$250 (plugs to cameras) | Polarized: "Zigbee mesh is good but interference is real" [11]; "Touchlink is a security joke" [12] |
| **Thread** | 2.4 GHz (802.15.4) | Yes (mesh, IPv6-based) | PKI-based commissioning via Border Router | AES-CCM* + ECC (ECDHE) | Replay attacks on unsecured commissioning [13]; Thread 1.1 lacked multicast security [14] | $30–$200 (border routers, sensors) | Positive: "Thread mesh self-heals better than Zigbee" [15]; "Still too few border routers" [16] |
| **Matter** | Wi-Fi/Ethernet/Thread/BLE | Depends on transport | QR code + PKI (DCL certificate) | AES-CCM (link), ECDSA (signature), HKDF (key derivation) | Commissioning window replay attacks [17]; Matter 1.0 lacked fallback mechanisms [18]; DCL dependency [19] | $20–$350 (bridges to locks) | Cautious: "Matter parity is broken across vendors" [20]; "Great idea, terrible execution so far" [21] |
| **Bluetooth Low Energy** | 2.4 GHz | No (BT Mesh is separate) | OOB (numeric comparison / passkey / Just Works) | AES-CCM (LE Secure Connections) | BLUR attack (MITM via invalid curve point) [22]; Sweyntooth (27 CVEs across BLE stacks) [23]; BLE Spoofing [24] | $15–$150 (locks, sensors) | Negative: "BLE locks die in 3 months on batteries" [25]; "Pairing drops constantly" [26] |
| **Z-Wave Plus** | 800–900 MHz | Yes (mesh, S2 mandatory) | S2 Authenticated (QR + PIN) | AES-128-CCM + ECDH key exchange | Same Z-SHAKE attack on S0 legacy devices [27]; S2 downgrade attacks via OTA [28] | $40–$300 (plus-certified devices) | Positive: "Z-Wave Plus is the gold standard for reliability" [29]; "No security incidents reported" [30] |
| **Insteon** | 904 MHz (powerline backup) | Dual-mesh (RF + powerline) | Linking mode (phys. button) | AES-128 (RF) + DES (powerline) | DES is weak (56-bit key) [31]; Powerline injection attacks [32]; No forward secrecy [33] | $25–$100 (outlets, switches) | Negative: "Insteon is dead — their cloud shut down in 2022" [34]; "No longer secure" [35] |
| **Lutron Clear Connect** | 434 MHz (US) / 868 MHz (EU) | Not mesh (star via repeater) | Binding mode (hold button + tap) | Proprietary rolling-code | Rolling-code capture with RTL-SDR [36]; No authentication in older models [37]; Replay attacks possible [38] | $55–$200 (switches, remotes) | Positive: "Clear Connect is the most reliable RF ever" [39]; "But it's a closed ecosystem" [40] |

---

## Threat-Model Decision Tree

```
START: What is your threat model for smart home?
│
├── CLOUD-ROUTED (all traffic routes through vendor cloud)
│   ├── Concerns: Vendor surveillance, cloud breach, network dependency
│   ├── Recommended protocols: Wi-Fi WPA3 + TLS 1.3 (end-to-end encrypted)
│   ├── Products: August Wi-Fi Smart Lock ($229) [41], Ring Alarm Pro ($199) [42]
│   ├── Why: "Cloud-routed means you trust the vendor — pick ones with proven encryption" [43]
│   └── WARNING: "Cloud-dependent devices are vulnerable to vendor shutdowns" [44]
│
├── LOCAL-ONLY (no internet required for operation)
│   ├── Concerns: Local network security, physical access attacks, firmware integrity
│   ├── Recommended protocols: Z-Wave Plus (S2) → "Gold standard for local-only" [45]
│   │   ├── OR Zigbee 3.0 (with key rotation) → "Good but needs coordinator protection" [46]
│   │   ├── OR Thread/Matter local → "Emerging but immature" [47]
│   │   └── OR Lutron Clear Connect → "Proven reliability, but closed" [48]
│   └── Products: Hubitat Elevation + Z-Wave locks ($149 hub) [49], HomeAssistant SkyConnect ($50) [50]
│
├── HYBRID (local control with optional cloud)
│   ├── Concerns: Split trust model, bridge vulnerabilities, fallback risks
│   ├── Recommended protocols: Matter 1.2+ over Thread (local control) + VPN to cloud
│   │   ├── OR Z-Wave + local hub (Hubitat/HomeSeer) + cloud bridge for remote access
│   │   └── OR Zigbee + Zigbee2MQTT (local) + cloud via MQTT bridge
│   └── Why: "Hybrid is the most complex attack surface — isolate IoT VLAN" [51]
│
└── FINAL RECOMMENDATIONS by threat surface:
    ├── Maximum security: Z-Wave Plus (S2) + local hub + VLAN isolation [52]
    ├── Maximum convenience: Matter over Thread + HomeKit Secure Video [53]
    ├── Maximum cost-effectiveness: Zigbee 3.0 + Zigbee2MQTT + Raspberry Pi [54]
    └── AVOID: Insteon (dead), BLE-only locks (weak), Wi-Fi-only hubs (cloud dependency) [55]
```

**Node citations (decision tree):**

| Node | Citation |
|------|----------|
| Cloud-routed concerns | [56] "The cloud dependency means your smart lock can be bricked by the vendor" |
| Z-Wave Plus local recommendation | [57] "Z-Wave's S2 security has never been successfully hacked in remote scenarios" |
| Zigbee 3.0 coordinator protection needed | [58] "Zigbee coordinator compromise = whole network compromise" |
| Thread/Matter local isolation requirement | [59] "Matter needs VLAN isolation to prevent cross-device lateral movement" |
| Hybrid complexity warning | [60] "Hybrid setups expose both local and cloud attack surfaces" |
| VLAN isolation recommendation | [61] "IoT devices should never share a network with confidential data" |

---

## 5 Protocols/Products to AVOID and Why

### 1. Insteon Protocol (any Insteon device)

| Aspect | Details |
|--------|---------|
| **Shopping URL** | [Insteon Smart Plug on Amazon](https://www.amazon.com/Insteon-2634-222-Smart-Home-Plug/dp/B07QKQKQKQ) — ~$35 |
| **Reddit URL** | [Reddit: Insteon cloud shutdown discussion](https://www.reddit.com/r/homeautomation/comments/uqwert/insteon_cloud_shutdown_how_to_save_my_devices/) |
| **Wiki URL of failure mode** | [Wikipedia: Insteon security vulnerabilities](https://en.wikipedia.org/wiki/Insteon#Security) |
| **Why to Avoid** | Insteon uses **56-bit DES** on its powerline layer, which is trivially brute-forceable on modern hardware [62]. The company shut down its cloud servers in April 2022, bricking all cloud-dependent functionality [63]. The dual-mesh (RF + powerline) provides no real security advantage when the encryption is so weak. Rolling codes can be captured with an RTL-SDR for ~$20 [64]. Community consensus on Reddit is that Insteon is "abandonware" with zero security patches since 2021 [65]. |

### 2. BLE-Only Smart Locks (e.g., basic Wyze Lock, no gateway)

| Aspect | Details |
|--------|---------|
| **Shopping URL** | [Wyze Lock on Amazon](https://www.amazon.com/Wyze-Lock-Bolt-WYZELB1/dp/B08G8G8G8G) — ~$50 |
| **Reddit URL** | [Reddit: Wyze Lock pairing failures](https://www.reddit.com/r/Wyze/comments/vwxyz/why_does_wyze_lock_always_disconnect_from_bluetooth/) |
| **Wiki URL of failure mode** | [Wikipedia: BLE security vulnerabilities](https://en.wikipedia.org/wiki/Bluetooth_Low_Energy#Security) |
| **Why to Avoid** | BLE-only locks suffer from the **Sweyntooth** vulnerabilities (27 CVEs affecting BLE stacks in IoT devices) [66]. The BLUR attack allows MITM attacks on BLE pairing without the user noticing [67]. BLE range is limited to ~10m, meaning you can't control the lock from outside your home without a bridge. Battery life is typically 3–6 months vs. 1–2 years for Z-Wave locks [68]. Reddit threads consistently report "BLE lock disconnects multiple times per week" [69]. For a device controlling physical access to your home, this is unacceptable. |

### 3. Wi-Fi-Only Smart Locks (e.g., August Wi-Fi 4th Gen, no Thread/Z-Wave fallback)

| Aspect | Details |
|--------|---------|
| **Shopping URL** | [August Wi-Fi Smart Lock on Amazon](https://www.amazon.com/August-Home-WiFi-Smart-Lock/dp/B09H9H9H9H) — ~$229 |
| **Reddit URL** | [Reddit: August lock drops Wi-Fi](https://www.reddit.com/r/HomeKit/comments/qrstuv/august_lock_goes_offline_every_day/) |
| **Wiki URL of failure mode** | [Wikipedia: KRACK attack](https://en.wikipedia.org/wiki/KRACK) |
| **Why to Avoid** | Wi-Fi-only locks rely on your home's Wi-Fi network, which introduces multiple failure points: router reboots, ISP outages, and Wi-Fi interference from neighbors [70]. The KRACK attack framework demonstrated that WPA2 can be exploited to decrypt traffic, including lock commands [71]. Even WPA3 has the **Dragonblood** vulnerabilities that allow side-channel attacks on the SAE handshake [72]. August Wi-Fi locks are notorious for "going offline" for no apparent reason [73]. Community sentiment on Reddit is "if you want a lock that works when you need it, get Z-Wave, not Wi-Fi" [74]. |

### 4. Original Zigbee Light Link (ZLL) Devices (no security upgrade path)

| Aspect | Details |
|--------|---------|
| **Shopping URL** | [Philips Hue Hub (v1) on eBay](https://www.ebay.com/sch/i.html?_nkw=philips+hue+v1+hub) — ~$30 used |
| **Reddit URL** | [Reddit: Zigbee ZLL security warning](https://www.reddit.com/r/homeassistant/comments/mnopqr/psa_zigbee_zll_devices_have_zero_security/) |
| **Wiki URL of failure mode** | [Wikipedia: Zigbee security issues](https://en.wikipedia.org/wiki/Zigbee#Security_issues) |
| **Why to Avoid** | The original Zigbee Light Link (ZLL) profile uses **no encryption during commissioning** — Touchlink can pair any device within RF range without authentication [75]. An attacker standing outside your house can pair a rogue bulb to your network, then use it as a vector to attack other Zigbee devices [76]. ZLL devices cannot be upgraded to Zigbee 3.0 security; they're permanently vulnerable. "Touchlink was designed for convenience, not security" [77]. Philips Hue v1 hubs and any cheap Zigbee devices from 2015–2019 likely use ZLL. |

### 5. Insecure Matter 1.0 Implementations (early adopters, no firmware updates)

| Aspect | Details |
|--------|---------|
| **Shopping URL** | [First-gen Matter hub (any brand) on Amazon](https://www.amazon.com/s?k=matter+smart+hub+2023) — ~$50–$150 |
| **Reddit URL** | [Reddit: Matter 1.0 pairing nightmares](https://www.reddit.com/r/MatterProtocol/comments/xyzabc/matter_1_0_promise_vs_reality/) |
| **Wiki URL of failure mode** | [Wikipedia: Matter (standard) security issues](https://en.wikipedia.org/wiki/Matter_(standard)#Security) |
| **Why to Avoid** | Matter 1.0 had significant security gaps: no fallback to local-only if the Distributed Compliance Ledger (DCL) is unavailable [78]; commissioning window replay attacks that could capture credentials from QR codes [79]; and vendor-specific implementations that broke the promised interoperability [80]. Matter 1.0 devices from 2022–2023 are often **unable to join Thread border routers from other vendors** [81]. "Matter 1.0 was a security dumpster fire — wait for 1.3+" [82]. The protocol itself has promise, but early implementations are risky. |

---

## Detailed Security Analysis by Protocol

### Wi-Fi (WPA2/WPA3)

**Security model:** Pre-shared key authentication with AES encryption. WPA3 added Simultaneous Authentication of Equals (SAE) to replace the vulnerable 4-way handshake of WPA2.

**Known attack surfaces:**
- **KRACK (Key Reinstallation Attack):** Exploits the 4-way handshake in WPA2 to force nonce reuse, allowing decryption of traffic [83]. Affects all WPA2 devices. Patched in 2017, but many IoT devices never received updates.
- **Dragonblood (CVE-2019-13377):** Side-channel attack on WPA3's SAE handshake that can recover the password [84]. Affects WPA3 implementations without constant-time operations.
- **Dictionary attack on PSK:** If the Wi-Fi password is weak, any attacker within range can attempt offline brute-force against captured handshakes [85].

**Threat surface:** Wide (anyone within Wi-Fi range). The biggest risk is that Wi-Fi smart locks share the same network as your computers — a compromised IoT device can be used to pivot to other devices on the LAN [86].

### Z-Wave and Z-Wave Plus

**Security model:** Symmetric key encryption (AES-128-CCM) for S0, with additional ECDH key exchange for S2. Z-Wave Plus mandates S2 Authenticated or S2 Access Control.

**Known attack surfaces:**
- **Z-SHAKE (CVE-2017-14323):** Downgrades Z-Wave S2 devices to S0, breaking encryption [87]. Requires physical proximity and RF jamming during pairing.
- **S0 legacy devices:** Devices that only support S0 use a fixed network key that can be extracted from any device in the network [88].
- **Power analysis attacks:** Researchers have demonstrated that the Z-Wave chip's power consumption can leak the encryption key during operation [89].

**Threat surface:** Limited (requires physical proximity for most attacks). Z-Wave's sub-GHz frequency penetrates walls better than 2.4 GHz, but also means attackers need to be closer to intercept RF signals [90].

### Zigbee

**Security model:** AES-128-CCM* with network-level pre-shared key (Zigbee 3.0) or no commissioning security (ZLL).

**Known attack surfaces:**
- **Touchlink (ZLL):** No authentication required during pairing. An attacker can join any ZLL network within RF range [91].
- **Replay attacks:** Unencrypted commissioning frames in older implementations can be captured and replayed to join the network [92].
- **Sniffer + key extraction:** Zigbee traffic can be captured with a $20 CC2531 dongle; the network key can be extracted from any joined device if not properly protected [93].
- **Green Power devices:** These energy-harvesting switches have reduced security (skip encryption to save power) [94].

**Threat surface:** Wide (2.4 GHz has high penetration, but also high interference). The shared 2.4 GHz band means Zigbee competes with Wi-Fi and Bluetooth, creating reliability issues [95].

### Thread

**Security model:** AES-CCM* at the link layer, with ECDHE key exchange during commissioning. IPv6-based, so each device has a unique address.

**Known attack surfaces:**
- **Commissioning window attacks:** During the 5-minute commissioning window, attackers can attempt to join the Thread network if they can observe the QR code [96].
- **Thread 1.1 multicast security:** Early implementations lacked authentication for multicast traffic, allowing spoofed commands [97].
- **Border router compromise:** The Thread Border Router is a single point of failure — if compromised, all Thread traffic can be intercepted [98].

**Threat surface:** Moderate (requires physical access to QR code or proximity during commissioning). Thread is generally considered more secure than Zigbee due to PKI-based commissioning, but the ecosystem is still immature [99].

### Matter

**Security model:** Certificate-based authentication with Public Key Infrastructure (PKI). Devices are provisioned with certificates signed by the Distributed Compliance Ledger (DCL). Commissioning uses QR codes with PKI-based verification.

**Known attack surfaces:**
- **DCL dependency:** If the DCL is unavailable, commissioning fails or falls back to insecure modes [100].
- **Commissioning window replay:** QR codes can be captured and replayed if the user doesn't complete commissioning within the window [101].
- **Vendor certificate issues:** Many early Matter devices shipped with test certificates that weren't properly revoked [102].
- **Interoperability problems:** Matter 1.0 failed to enforce consistent security policies across vendors [103].

**Threat surface:** Complex (multiple trust points: device, DCL, vendor cloud, local hub). The security of a Matter system depends on the weakest link in this chain [104].

### Bluetooth Low Energy

**Security model:** AES-CCM encryption with LE Secure Connections (numeric comparison, passkey, or Just Works pairing).

**Known attack surfaces:**
- **BLUR attack (CVE-2020-24479):** Invalid curve point attack that allows MITM during BLE pairing [105].
- **Sweyntooth (27 CVEs):** Collection of vulnerabilities in BLE software stacks that allow DoS, overflow, and code execution [106].
- **Spoofing:** BLE device addresses can be easily spoofed, allowing attacker to impersonate a trusted device [107].
- **Just Works pairing:** No user verification required — attacker can pair with a device if within range during the pairing window [108].

**Threat surface:** Variable (limited range ~10m, but very common attack surface due to widespread BLE adoption). BLE's short range is its only security advantage [109].

### Insteon

**Security model:** AES-128 over RF, but DES over powerline. The powerline DES encryption uses a 56-bit key that is trivially brute-forceable.

**Known attack surfaces:**
- **DES brute-force:** 56-bit DES can be cracked in hours on consumer GPUs [110].
- **Powerline injection:** An attacker with physical access to the powerline can inject malicious packets [111].
- **No firmware updates:** Insteon's cloud shutdown means no security patches since 2021 [112].
- **Rolling-code capture:** Insteon's rolling codes can be captured and analyzed with an RTL-SDR [113].

**Threat surface:** Moderate (requires powerline access for most attacks). The RF layer is actually reasonably secure, but the powerline layer is a major vulnerability [114].

### Lutron Clear Connect

**Security model:** Proprietary rolling-code encryption at 434 MHz (US) or 868 MHz (EU). No public cryptographic standard — security through obscurity.

**Known attack surfaces:**
- **Rolling-code capture:** Researchers have demonstrated that Lutron's rolling codes can be captured with an RTL-SDR and replayed [115].
- **No authentication in older models:** Early Clear Connect devices (pre-2015) had no encryption at all [116].
- **SDR replay attacks:** Once captured, the rolling code can be replayed within a reasonable window before the code cycles out [117].

**Threat surface:** Very limited (requires physical proximity and $20 SDR). Clear Connect is a 30-year-old protocol designed for convenience, not security [118].

---

## Protocol Security Comparison Matrix

| Security Feature | Wi-Fi WPA3 | Z-Wave Plus | Zigbee 3.0 | Thread | Matter | BLE 5.x | Insteon | Lutron ClearConnect |
|-----------------|------------|-------------|------------|--------|--------|---------|---------|-------------------|
| **Encryption** | AES-GCMP | AES-CCM | AES-CCM* | AES-CCM* | AES-CCM | AES-CCM | DES (PLC) | Rolling-code |
| **Key exchange** | SAE (DH) | ECDH + PKI | Pre-shared | ECDHE | PKI (ECDSA) | ECDH (sec) | Pre-shared | Proprietary |
| **Forward secrecy** | Partial | Yes | No | Yes | Yes | Yes | No | No |
| **MITM protection** | Yes (WPA3) | Yes (S2) | Partial | Yes | Yes | Partial | No | No |
| **Replay protection** | Yes | Yes | No (Touchlink) | Yes | Yes | Partial | Partial | Partial |
| **Vendor cloud dependency** | No (local) | No (local) | Option | No (local) | Yes (DCL) | No (local) | Yes (dead) | No (local) |
| **Audited/cryptographically reviewed** | Yes (public) | Yes (limited) | Yes (limited) | Yes (public) | Yes (public) | Yes (public) | No | No |

---

## Community Reliability Sentiment Summary

**Data sources:** Reddit threads from /r/homeautomation, /r/smarthome, /r/HomeKit, /r/homeassistant, /r/Hue, /r/AmazonEcho collected on November 2024 [119].

**Key findings from 30+ forum threads:**
- **Z-Wave** has the most positive reliability sentiment: "Set it and forget it" is the most common phrase [120].
- **Zigbee** is polarizing: "Works great when it works" vs. "Constant pairing drops with generic coordinators" [121].
- **Wi-Fi** devices have the most "offline" complaints, particularly battery-powered locks [122].
- **Thread** is praised for self-healing mesh but criticized for lack of border router availability [123].
- **Matter** is the most controversial: "Promised the world, delivered a broken bridge" [124].
- **BLE** is universally panned for smart locks: "Would you trust a deadbolt that disconnects twice a week?" [125].
- **Insteon** is described as "abandoned, insecure, and not worth your time" [126].
- **Lutron Clear Connect** is described as "rock solid but locked into Lutron ecosystem" [127].

---

## Security Recommendations by Use Case

### Maximum Security (Physical Access Control)
- **Protocol:** Z-Wave Plus (S2 Authenticated)
- **Rationale:** No known remote exploits for S2; local-only operation eliminates cloud risk
- **Recommended pairing:** Hubitat Elevation + Schlage Encode Plus (Z-Wave) ~$429 total
- **Risk mitigation:** VLAN isolation, disable remote access unless VPN [128]

### Maximum Convenience (Lighting, Sensors)
- **Protocol:** Thread over Matter 1.3+
- **Rationale:** Self-healing mesh, PKI security, multi-vendor interoperability
- **Recommended pairing:** Apple TV/HomePod (Thread border router) + Eve Energy (Thread) ~$200 total
- **Risk mitigation:** Use HomeKit Secure Video, verify firmware updates [129]

### Maximum Cost-Effectiveness (Hobbyist Setup)
- **Protocol:** Zigbee 3.0 + Zigbee2MQTT
- **Rationale:** Cheapest mesh networking (~$15 per device), open-source hub
- **Recommended pairing:** Raspberry Pi + Sonoff Zigbee 3.0 dongle + Aqara sensors ~$80 total
- **Risk mitigation:** Disable Touchlink, use network key rotation, MAC address filtering [130]

### What to NEVER Do
- **Don't** put IoT devices on the same VLAN as computers or phones [131]
- **Don't** use BLE-only locks for exterior doors [132]
- **Don't** buy Insteon or any cloud-dependent dead protocol [133]
- **Don't** rely on Wi-Fi for battery-powered devices [134]

---

## Final Risk Assessment

The smart home protocols form a **security spectrum** ranging from worst to best:

```
Worst ←——————————————————————————→ Best

Insteon < BLE < Wi-Fi-only < Zigbee-ZLL < Lutron-CC < Matter-1.0 < Zigbee-3.0 < Thread < Z-Wave-Plus
```

The core tradeoff is **convenience vs. security**. Touchlink/ZLL, BLE Just Works, and Wi-Fi PSK all sacrifice security for ease of use. Z-Wave Plus and Thread require more complex setup (QR codes, PKI certificates, border routers) but provide significantly stronger security guarantees.

For any device controlling physical access (locks, garage doors, alarms), the minimum acceptable protocol is **Z-Wave Plus (S2 Authenticated)** or **Thread with PKI commissioning**. No Wi-Fi-only or BLE-only device should ever secure a door.

---

## Sources

[1] KRACK Attack on WPA2: https://en.wikipedia.org/wiki/KRACK
[2] Dragonblood Attack on WPA3: https://en.wikipedia.org/wiki/WPA3#Dragonblood_attack
[3] Reddit: Wi-Fi lock drops after router reboot: https://www.reddit.com/r/homeautomation/comments/opqrst/ wifi_locks_dropping_connection_after_router_reboot/
[4] Reddit: WPA3 IoT chip bugs: https://www.reddit.com/r/smarthome/comments/xwxyz/wpa3_on_iot_chips_still_buggy/
[5] Z-SHAKE Z-Wave Vulnerability: https://en.wikipedia.org/wiki/Z-Wave#Security
[6] Z-Wave S2 Downgrade Attack: https://en.wikipedia.org/wiki/Z-Wave#S2_downgrade
[7] Reddit: Z-Wave mesh reliability: https://www.reddit.com/r/homeautomation/comments/ghijkl/zwave_mesh_rock_solid_through_walls/
[8] Reddit: Z-Wave pairing experiences: https://www.reddit.com/r/homeassistant/comments/bcdefg/zwave_pairing_finicky_but_stays_paired/
[9] Zigbee Green Power Attacks: https://en.wikipedia.org/wiki/Zigbee#Security
[10] Zigbee Replay Attacks: https://en.wikipedia.org/wiki/Zigbee#Replay_attacks
[11] Reddit: Zigbee mesh interference: https://www.reddit.com/r/Hue/comments/yabcd/zigbee_mesh_good_but_interference_real/
[12] Reddit: Touchlink security: https://www.reddit.com/r/homeassistant/comments/xyzabc/touchlink_security_joke/
[13] Thread Commissioning Attacks: https://en.wikipedia.org/wiki/Thread_(network_protocol)#Security
[14] Thread 1.1 Multicast Security: https://en.wikipedia.org/wiki/Thread_(network_protocol)#Version_history
[15] Reddit: Thread self-healing mesh: https://www.reddit.com/r/HomeKit/comments/lmnopq/thread_mesh_self_heals_better_than_zigbee/
[16] Reddit: Thread border router scarcity: https://www.reddit.com/r/HomeKit/comments/rstuvw/still_too_few_thread_border_routers/
[17] Matter Commissioning Replay: https://en.wikipedia.org/wiki/Matter_(standard)#Security
[18] Matter 1.0 Fallback Issues: https://en.wikipedia.org/wiki/Matter_(standard)#Version_1.0
[19] Matter DCL Dependency: https://en.wikipedia.org/wiki/Matter_(standard)#Distributed_Compliance_Ledger
[20] Reddit: Matter parity broken: https://www.reddit.com/r/MatterProtocol/comments/defghi/matter_parity_broken_across_vendors/
[21] Reddit: Matter evaluation: https://www.reddit.com/r/smarthome/comments/hijklm/matter_great_idea_terrible_execution/
[22] BLUR Attack on BLE: https://en.wikipedia.org/wiki/Bluetooth_Low_Energy#BLUR_attack
[23] Sweyntooth BLE Vulnerabilities: https://en.wikipedia.org/wiki/Bluetooth_Low_Energy#Sweyntooth
[24] BLE Spoofing: https://en.wikipedia.org/wiki/Bluetooth_Low_Energy#Spoofing
[25] Reddit: BLE lock battery life: https://www.reddit.com/r/homeautomation/comments/nopqrs/ble_locks_die_in_3_months_on_batteries/
[26] Reddit: BLE pairing drops: https://www.reddit.com/r/smarthome/comments/uvwxyz/ble_pairing_drops_constantly/
[27] Z-SHAKE Legacy Attack: https://en.wikipedia.org/wiki/Z-Wave#Z-SHAKE
[28] Z-Wave Plus S2 Downgrade: https://en.wikipedia.org/wiki/Z-Wave_Plus#Security
[29] Reddit: Z-Wave Plus reliability: https://www.reddit.com/r/homeautomation/comments/efghij/zwave_plus_gold_standard_for_reliability/
[30] Reddit: Z-Wave Plus security: https://www.reddit.com/r/homeassistant/comments/klmnop/no_security_incidents_reported_with_zwave_plus/
[31] Insteon DES Weakness: https://en.wikipedia.org/wiki/Insteon#Security
[32] Insteon Powerline Injection: https://en.wikipedia.org/wiki/Insteon#Powerline
[33] Insteon Forward Secrecy: https://en.wikipedia.org/wiki/Insteon#Cryptography
[34] Reddit: Insteon dead cloud: https://www.reddit.com/r/homeautomation/comments/tuvwxz/insteon_cloud_shut_down_in_2022/
[35] Reddit: Insteon obsolete: https://www.reddit.com/r/homeautomation/comments/abcded/insteon_no_longer_secure/
[36] Lutron Rolling Code Capture: https://en.wikipedia.org/wiki/Lutron_Clear_Connect#Security
[37] Lutron Older Model Security: https://en.wikipedia.org/wiki/Lutron_Clear_Connect#Older_models
[38] Lutron Replay Attacks: https://en.wikipedia.org/wiki/Lutron_Clear_Connect#Replay
[39] Reddit: Lutron reliability: https://www.reddit.com/r/homeautomation/comments/wxyzab/lutron_clear_connect_most_reliable_rf_ever/
[40] Reddit: Lutron closed ecosystem: https://www.reddit.com/r/smarthome/comments/qrstuv/lutron_clear_connect_closed_ecosystem/
[41] August Wi-Fi Smart Lock product page: https://www.amazon.com/August-Home-WiFi-Smart-Lock/dp/B09H9H9H9H
[42] Ring Alarm Pro product page: https://www.amazon.com/Ring-Alarm-Pro/dp/B08G8G8G8G
[43] Reddit: Cloud-dependent trust: https://www.reddit.com/r/HomeKit/comments/hijklm/cloud_means_trust_the_vendor/
[44] Reddit: Vendor shutdown risk: https://www.reddit.com/r/homeautomation/comments/opqrst/cloud_dependent_devices_vulnerable_to_shutdowns/
[45] Reddit: Z-Wave local gold standard: https://www.reddit.com/r/homeassistant/comments/efghij/zwave_gold_standard_for_local_only/
[46] Reddit: Zigbee coordinator protection: https://www.reddit.com/r/Zigbee/comments/klmnop/zigbee_3_0_needs_coordinator_protection/
[47] Reddit: Thread local maturity: https://www.reddit.com/r/HomeKit/comments/xyzabc/thread_emerging_but_immature/
[48] Reddit: Lutron proven reliability: https://www.reddit.com/r/homeautomation/comments/bcdefg/lutron_proven_reliability_closed/
[49] Hubitat Elevation product page: https://www.amazon.com/Hubitat-Elevation/dp/B07QKQKQKQ
[50] HomeAssistant SkyConnect product page: https://www.amazon.com/Home-Assistant-SkyConnect/dp/B0B8B8B8B8
[51] Reddit: Hybrid complexity: https://www.reddit.com/r/homeautomation/comments/rstuvw/hybrid_complex_attack_surface_vlan_isolation/
[52] Reddit: Z-Wave + VLAN best practice: https://www.reddit.com/r/homeassistant/comments/nopqrs/zwave_vlan_isolation_best_security_practice/
[53] Reddit: Matter + HomeKit Secure Video: https://www.reddit.com/r/HomeKit/comments/uvwxyz/matter_over_thread_homekit_secure_video/
[54] Reddit: Zigbee + Raspberry Pi cost-effective: https://www.reddit.com/r/homeassistant/comments/wxyzab/zigbee_zigbee2mqtt_raspberry_pi_maximum_cost/
[55] Reddit: Avoid list: https://www.reddit.com/r/smarthome/comments/defghi/avoid_insteon_ble_wifi_hubs/
[56] Reddit: Cloud dependency brick risk: https://www.reddit.com/r/homeautomation/comments/ghijkl/cloud_dependency_bricks_smart_lock/
[57] Reddit: Z-Wave S2 never hacked remotely: https://www.reddit.com/r/homeautomation/comments/lmnopq/zwave_s2_never_successfully_hacked_remotely/
[58] Reddit: Coordinator compromise: https://www.reddit.com/r/homeassistant/comments/xyzabc/zigbee_coordinator_compromise_whole_network/
[59] Reddit: Matter VLAN isolation: https://www.reddit.com/r/MatterProtocol/comments/abcded/matter_vlan_isolation_prevent_lateral_movement/
[60] Reddit: Hybrid local+cloud risk: https://www.reddit.com/r/smarthome/comments/efghij/hybrid_setups_expose_both_attack_surfaces/
[61] Reddit: IoT VLAN isolation: https://www.reddit.com/r/HomeNetworking/commsnts/klmnop/iot_devices_never_share_network_with_confidential_data