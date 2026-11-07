# Vendored front-end files (master plan V2 DS1/DS2/LG2)

All files are served by our own server from `sindhu_web/static/vendor/` (no CDN at runtime). Downloaded once on 2026-11-06 from the
official npm registry (`registry.npmjs.org`), each tarball checked against the registry's sha512 `integrity` value before use, then only
the files below were extracted (nothing was executed). Licenses are kept next to the files.

| Package | Version | License | Use |
|---|---|---|---|
| three | 0.160.1 | MIT | login 3D scene (LG2), loaded after the form is usable |
| uplot | 1.6.31 | MIT | charts (U8): equity curve, drawdown, backtest charts |
| lucide-static | 0.460.0 | ISC | the one icon set (SVG sprite of the icons we use) |
| @fontsource-variable/inter | 5.1.0 | OFL-1.1 | UI font (latin subset, variable weight) |
| @fontsource/jetbrains-mono | 5.1.1 | OFL-1.1 | numbers, prices, IDs (latin, 400 + 600) |

| File | Bytes | SHA-256 | From |
|---|---|---|---|
| `three-0.160.1.module.min.js` | 670,681 | `3e690ac7d180b0aadf0891bea39eec643e29e2d3e75c99b18689518665f69ba6` | three-0.160.1.tgz |
| `LICENSE.three.txt` | 1,081 | `852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d` | three-0.160.1.tgz |
| `uplot-1.6.31.iife.min.js` | 50,312 | `2d27e8ad3d228164525ce213f9dc716f39b4e3aee0cc773fb3491c96cf4921a2` | uplot-1.6.31.tgz |
| `uplot-1.6.31.min.css` | 1,857 | `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04` | uplot-1.6.31.tgz |
| `LICENSE.uplot.txt` | 1,078 | `8f989229699b4fe2f1a0432d0e9edc338a8a911e250e2d1b01ecd770a5f5b1bd` | uplot-1.6.31.tgz |
| `fonts/inter-latin-wght-normal.woff2` | 48,444 | `f052ee44c3728dfd23aba8a4567150bc314d23903026fbb6ad089422c2df56af` | inter-5.1.0.tgz |
| `fonts/LICENSE.inter.txt` | 4,375 | `8c8fa881d9091ee315d2c80d207bb73afd4e90a66c9782ca445c5642f25db6dc` | inter-5.1.0.tgz |
| `fonts/jetbrains-mono-latin-400-normal.woff2` | 21,168 | `14425ba9c695763c1547f48a206b7aa60350a33ae23de09f0407877f3fcd89eb` | jetbrains-mono-5.1.1.tgz |
| `fonts/jetbrains-mono-latin-600-normal.woff2` | 21,860 | `400c6bfda18d5d14acad1c15d6dcb9f8e13c015e7286317e0b9a482539bef147` | jetbrains-mono-5.1.1.tgz |
| `fonts/LICENSE.jetbrains-mono.txt` | 4,397 | `bb1c26eb6fe1839e3759548777c8a35b9495ce4878a4b833b1b63d43ff313a4b` | jetbrains-mono-5.1.1.tgz |
| `lucide-sprite.svg` | 9,361 | `999084823f466b34751aa161b372226c79c59860803be0849d3fb752e4806d20` | lucide-static-0.460.0.tgz (52 icons) |
| `LICENSE.lucide.txt` | 880 | `1e7290b35280a048667bbf0ebabac1c7fd52a75300e8b2946ac165715997f2bc` | lucide-static-0.460.0.tgz |

Attribution: three.js (c) 2010-2023 three.js authors; uPlot (c) Leon Sorokin; Lucide (c) Lucide Contributors; Inter (c) The Inter Project Authors; JetBrains Mono (c) JetBrains s.r.o.
