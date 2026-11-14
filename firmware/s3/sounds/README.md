# Messages vocaux

Clips FLAC (22,05 kHz, mono) embarqués dans le firmware et joués par le haut-parleur :

| Fichier | Texte |
|---|---|
| `setup.flac` | « Mode configuration. Connectez-vous au réseau Wi-Fi, G H Revive Setup. » (toutes les 60 s tant que le point d'accès est ouvert) |
| `connected.flac` | « Connecté au Wi-Fi. Mon adresse est : » |
| `digit_0.flac` à `digit_9.flac`, `point.flac` | chiffres et « point », enchaînés pour lire l'adresse IP |

Régénération : `python firmware/s3/sounds/generate.py fr_FR-siwis-medium.onnx` (voir l'en-tête du script).

## Attribution

Voix synthétisée avec [Piper](https://github.com/rhasspy/piper), modèle `fr_FR-siwis-medium`, entraîné sur le
corpus SIWIS French Speech Synthesis Database (Honnet, Lazaridis, Garner, Yamagishi), diffusé sous licence
Creative Commons Attribution 4.0. Les clips générés sont redistribués sous les mêmes conditions d'attribution.
