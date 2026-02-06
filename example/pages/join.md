---
title: Join
slug: join
menu_order: 10
---

# Getting Started with MeshCore

MeshCore is an open-source off-grid LoRa mesh networking platform. This guide will help you get connected to the network.

For detailed documentation, see the [MeshCore FAQ](https://github.com/meshcore-dev/MeshCore/blob/main/docs/faq.md).

## Node Types

MeshCore devices operate in different modes:

| Mode | Description |
|------|-------------|
| **Companion** | Connects to your phone via Bluetooth. Use this for messaging and interacting with the network. |
| **Repeater** | Standalone node that extends network coverage. Place these in elevated locations for best results. |
| **Room Server** | Hosts chat rooms that persist messages for offline users. |

Most users start with a **Companion** node paired to their phone.

## Frequency Regulations

MeshCore uses LoRa radio, which operates on unlicensed ISM bands. You **must** use the correct frequency for your region:

| Region | Frequency | Notes |
|--------|-----------|-------|
| Europe (EU) | 868 MHz | EU868 band |
| United Kingdom | 868 MHz | Same as EU |
| North America | 915 MHz | US915 band |
| Australia | 915 MHz | AU915 band |

Using the wrong frequency is illegal and may cause interference. Check your local regulations.

## Compatible Hardware

MeshCore runs on inexpensive low-power LoRa devices. Popular options include:

### Recommended Devices

| Device | Manufacturer | Features |
|--------|--------------|----------|
| [Heltec V3](https://heltec.org/project/wifi-lora-32-v3/) | Heltec | Budget-friendly, OLED display |
| [T114](https://heltec.org/project/mesh-node-t114/) | Heltec | Compact, GPS, colour display |
| [T1000-E](https://www.seeedstudio.com/SenseCAP-Card-Tracker-T1000-E-for-Meshtastic-p-5913.html) | Seeed Studio | Credit-card sized, GPS, weatherproof |
| [T-Deck Plus](https://www.lilygo.cc/products/t-deck-plus) | LilyGO | Built-in keyboard, touchscreen, GPS |

Ensure you purchase the correct frequency variant (868MHz for EU/UK, 915MHz for US/AU).

### Where to Buy

- **Heltec**: [Official Store](https://heltec.org/) or AliExpress
- **LilyGO**: [Official Store](https://lilygo.cc/) or AliExpress
- **Seeed Studio**: [Official Store](https://www.seeedstudio.com/)
- **Amazon**: Search for device name + "LoRa 868" (or 915 for US)

## Mobile Apps

Connect to your Companion node using the official MeshCore apps:

| Platform | App | Link |
|----------|-----|------|
| Android | MeshCore | [Google Play](https://play.google.com/store/apps/details?id=com.liamcottle.meshcore.android) |
| iOS | MeshCore | [App Store](https://apps.apple.com/us/app/meshcore/id6742354151) |

The app connects via Bluetooth to your Companion node, allowing you to send messages, view the network, and configure your device.

## Flashing Firmware

1. Use the [MeshCore Web Flasher](https://flasher.meshcore.co.uk/) for easy browser-based flashing
2. Select your device type and region (frequency)
3. Connect via USB and flash

## Next Steps

Once your device is flashed and paired:

1. Open the MeshCore app on your phone
2. Enable Bluetooth and pair with your device
3. Set your node name in the app settings
4. Configure your radio settings/profile for your region
4. You should start seeing other nodes on the network

Welcome to the mesh!
