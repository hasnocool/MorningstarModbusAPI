# Official Morningstar PDF manifest

This directory is a manifest for the official Morningstar PDF sources used by MorningstarModbusAPI. The complete vendor PDFs themselves are not republished in the repository; obtain them from the official Morningstar URLs below or through:

```bash
python -m pip install -e '.[maintenance]'
python -m morningstar_modbus.maintenance scan
```

The scanner stores downloaded artifacts in `docs/vendor/morningstar/cache/` by default and records exact SHA-256 hashes in its generated report.

The canonical machine-readable metadata remains `../sources.json`.

| Source ID | Repository filename | Official Morningstar URL | Priority |
| --- | --- | --- | --- |
| `genstar-mppt-modbus-v03` | `genstar-mppt-modbus-v03.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-genstar-mppt-modbus-specification-en.pdf | primary |
| `readyedge-modbus-v01` | `readyedge-modbus-v01.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-readyedge-modbus-specification-en.pdf | primary |
| `tristar-mppt-modbus-v11` | `tristar-mppt-modbus-specification-v11.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-modbus-specification-en.pdf | primary |
| `tristar-mppt-600v-modbus` | `tristar-mppt-600v-modbus-specification.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-600v-modbus-specification-en.pdf | primary |
| `tristar-pwm-modbus-v07` | `tristar-pwm-modbus-specification-v07.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-modbus-specification-en.pdf | primary |
| `prostar-mppt-modbus-v05` | `prostar-mppt-modbus-v05.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-prostar-mppt-modbus-specification-en-1.pdf | primary |
| `prostar-pwm-modbus-v2` | `prostar-pwm-modbus-v2.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-prostar-modbus-specification-en.pdf | primary |
| `sunsaver-mppt-modbus-v11` | `sunsaver-mppt-modbus-v11.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-sunsaver-mppt-modbus-specification-en.pdf | primary |
| `sunsaver-duo-modbus-v04` | `sunsaver-duo-modbus-v04.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-sunsaver-duo-modbus-specification-en.pdf | primary |
| `suresine-classic-modbus-v03` | `suresine-classic-modbus-v03.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-suresine-modbus-specification-en.pdf | primary |
| `suresine-gen2-modbus` | `suresine-gen2-modbus.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-suresine-2-modbus-specification-en.pdf | primary |
| `relay-driver-modbus` | `relay-driver-modbus.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-relay-driver-modbus-specification-en.pdf | primary |
| `morningstar-product-connectivity-2024` | `morningstar-product-connectivity-manual-2024.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-morningstar-product-connectivity-manual-networking-communications-en.pdf | primary |
| `tristar-mppt-networking-companion` | `tristar-mppt-networking-companion.pdf` | https://www.morningstarcorp.com/wp-content/uploads/technical-doc-tristar-mppt-networking-companion-document-en.pdf | secondary |
| `rsc1-operation-manual` | `rsc1-rs232-eia485-operation-manual.pdf` | https://www.morningstarcorp.com/wp-content/uploads/operation-manual-rsc-eia-485-to-serial-en.pdf | primary |
| `tristar-mppt-operation-manual` | `tristar-mppt-operation-manual.pdf` | https://www.morningstarcorp.com/wp-content/uploads/operation-manual-tristar-mppt-en.pdf | primary |
| `tristar-mppt-eia485-bridge` | `tristar-mppt-eia485-modbus-tcp-bridging.pdf` | https://www.morningstarcorp.com/wp-content/uploads/2014/02/TSMPPT.REP_.485_bridging.01.EN_.pdf | secondary |

Non-PDF sources such as product pages and meter-map HTML remain indexed only in `../sources.json`.

## Verification note

The official links above were rechecked against Morningstar's public site/source index on 2026-08-14. Availability can change independently of this repository, so the maintenance scanner should be treated as the current validation mechanism when reviewing a catalog update.
