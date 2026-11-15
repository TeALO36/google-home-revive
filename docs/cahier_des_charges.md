# GH-Revive — Cahier des charges matériel

Seconde vie d'un **Google Home 1re génération (2016, FCC ID A4RH0ME)** — *pas* le Home Mini — en satellite vocal / enceinte
open source pour Home Assistant. Deux cartes de remplacement, au même format que les originales, prêtes pour JLCPCB.
Le firmware n'est **pas** fourni : ce document fixe le matériel et liste ce que le logiciel devra faire (§10).

---

## 1. Matériel d'origine (vérifié — iFixit, dossier FCC)

| Élément | Original | Devenir |
|---|---|---|
| Carte mère en T | Marvell 88DE3006 + 88W8887 (Wi-Fi/BT), TAS5720 (ampli), mute mécanique (bras ressort sur un poussoir), jack DC soudé | **remplacée** |
| Carte du dessus ronde | ATSAMD21, 2 × PCA9956B (LED), 2 × micros PDM INMP621, capteur de lumière, électrodes tactiles | **remplacée** |
| Haut-parleur | Peerless 2", 4 Ω, petit connecteur 2 broches | réutilisé |
| Alimentation | 16,5 V 2 A, fiche 3,5 × 1,35 mm, **centre +** | réutilisée |
| Jack DC | CMS, soudé sous la carte mère | **dessoudé et ressoudé** sur la nouvelle carte |
| Micro-USB de service | sur la tige de la carte mère | remplacé par un **USB-C vertical** (limer l'ouverture du plastique) |

Le bouton mute est bien **sur la carte mère** (bras ressort de la coque arrière qui appuie sur un poussoir). Le nouveau
poussoir SW1 est au même endroit (x = 10,2 mm sur l'axe de la carte).

## 2. Exigences fonctionnelles

| # | Exigence | Solution matérielle |
|---|---|---|
| F1 | Wi-Fi 2,4 GHz, satellite vocal Home Assistant | ESP32-S3-WROOM-1-N16R8 (16 Mo flash, 8 Mo PSRAM) |
| F2 | Enceinte Bluetooth (A2DP) | ESP32-WROOM-32E dédié au BT Classic (l'S3 n'a que le BLE), audio vers l'S3 en I2S |
| F3 | Mot d'activation « Jarvis » même musique forte | 2 micros PDM + **référence d'écho matérielle** (sortie SDOUT du TAS5805M renvoyée à l'S3) pour l'AEC |
| F4 | Musique / TTS / cast réseau | TAS5805M (DSP intégré), BTL 4 Ω, sous 16,5 V |
| F5 | Mute qui coupe **physiquement** les micros | Bascule matérielle 74LVC1G74 : coupe l'alimentation des micros (P-MOS) et l'horloge PDM (buffer 3 états) |
| F6 | Anneau lumineux | 12 LED RGB adressables WS2812B-MINI-V3J (3,5 mm, pattes apparentes, soudables au fer) sur la carte du dessus |
| F7 | Tactile à travers le plastique : rotation = volume, tap = pause, double tap = piste suivante | MPR121, 10 secteurs en anneau (dents interpénétrées pour l'interpolation) ; tap = appui bref sans rotation, n'importe où sur l'anneau ; touche ronde au centre (Ø 10 mm, dans l'anneau de LED) pour pause / lecture |
| F8 | Flash / debug | USB-C vertical (soudé en usine) sur l'USB natif de l'S3 : premier flash, journaux, puis OTA. Pastilles TP1-TP5 (EN, BOOT, TX, RX, GND) en secours |
| F9 | Mêmes formes, dimensions, vis | contours, trous et connecteurs repris des photos (photogrammétrie, voir §8) |

## 3. Architecture

```
 16,5 V ──► D1 (anti-inversion) ─► PVDD ──► TAS5805M ──► L/C ──► HP 4 Ω (J3 JST ZH ou pastilles J5)
                                   │            ▲ I2S        │ SDOUT (référence d'écho)
                                   ▼            │            ▼
                         TPS54302 → +5 V → TLV62569 → +3V3
                                   │                │
   USB-C ─ USBLC6 ─ D+/D- ─────────┼──────► ESP32-S3 ◄──── I2S ──── ESP32 (BT A2DP)
   (VBUS ─ B5819W ─► +5 V)         │          │  ▲  ▲          UART + EN/BOOT (flashé via l'S3)
                                   │          │  │  └── MUTE_STATE / MUTE_SET_N ── bascule mute ◄── SW1
                                   │          │  │                                   │
                                   ▼          ▼  │                         coupe VMIC + horloge PDM
                              10 fils ──────────► carte du dessus : MPR121, 12 LED, 2 micros PDM
```

## 4. Carte mère (`hardware/mainboard`)

* **2 couches** : F.Cu composants + signaux + masse coulée, B.Cu signaux courts + masse coulée, vias de couture GND.
  1,6 mm, cuivre 1 oz. (En 4 couches, cette taille coûte ~28 $ chez JLC au lieu de ~7 $ : voir §9.) Zones sans cuivre sous les deux antennes (Wi-Fi et BT), en bord des « ailes ».
* **Alimentation**
  * Entrée 16,5 V par le jack d'origine (J2, empreinte reproduisant ses pattes, à ressouder à la main).
  * SS54 anti-inversion, TVS SMAJ18A, 220 µF électrolytique.
  * TPS54302 16,5 → 5,07 V (3 A max) puis TLV62569 5 → 3,33 V (2 A max).
  * USB-C : 5,1 kΩ sur CC1/CC2 (puissance par défaut 5 V) ; VBUS → +5 V par une Schottky B5819W, ce qui suffit pour flasher sans le 16,5 V (ampli muet dans ce cas).
* **Audio**
  * TAS5805M en BTL sur la voie A, filtres LC 4,7 µH / 1 µF.
  * Sortie haut-parleur sur **J3, JST ZH 1,5 mm 2 broches** : le connecteur du HP d'origine s'y branche. Ou bien des pastilles J5 pour souder les fils.
  * Sous 16,5 V / 4 Ω, la puissance théorique dépasse ce que tolère le HP de 2". **Limiter à ~10 W** par le gain / volume numérique du TAS5805M (logiciel).
* **Mute**
  * SW1 appuyé (anti-rebond RC + trigger 74LVC1G14) → la bascule change d'état.
  * Mise sous tension = micros **actifs** (reset RC sur /CLR).
  * En mute : Q1 (AO3401A) coupe **VMIC** et U9 met l'horloge PDM en haute impédance ; la donnée PDM est tirée à 0.
  * L'S3 **lit** l'état (MUTE_STATE) et **peut forcer le mute** (MUTE_SET_N → /PRE). Il **ne peut pas** réactiver les micros : seul le bouton le peut (garantie de vie privée).
* **Points de test** (pastilles, non assemblées) : EN, BOOT, TX, RX, GND, 3V3, 5V, IO47, IO48.

### Sections de fil (carte mère)

| Liaison | Courant | Section conseillée |
|---|---|---|
| Haut-parleur (si on remplace les fils d'origine) | ~1,6 A eff. à 10 W | **AWG 22 (0,34 mm²)**, AWG 24 minimum |
| Jack DC | 2 A | soudé directement sur la carte (pas de fil) |
| Liaison carte du dessus | voir §6 | AWG 28–30 |

## 5. Carte du dessus (`hardware/topboard`)

* **2 couches** (F composants + signaux + masse maillée, B électrodes + LED), Ø 74,8 mm, 3 encoches de positionnement (2 en haut à ±8,17 mm, 1 en bas à 7,4 mm).
* **Face B.Cu (vers le plastique)**
  * Électrodes tactiles : anneau de 10 secteurs (r 14,8 → 35,6 mm) à dents interpénétrées. Pas d'électrode centrale : en 2 couches, le centre de cette face sert au routage.
  * Les **12 LED WS2812B-MINI-V3J** sont à l'intérieur de l'anneau (centre à r = 10,48 mm, comme l'anneau d'origine), pattes orientées vers le centre et vers l'extérieur. Découplage : 6 × 100 nF (1 pour 2 LED) + 22 µF à l'arrivée des fils.
* **Face F.Cu (vers l'intérieur)**
  * MPR121 au centre, les 2 micros IM69D130 à port inférieur (perçage Ø 0,6 mm sous chacun, en face des trous d'origine à ±34,46 mm).
  * Tampon 74AHCT1G125 (données LED 3,3 → 5 V), découplages, pastilles des 10 fils.
  * Masse **maillée** (hachurée, ~40 % de cuivre) sur F, derrière les électrodes : elle les isole de l'intérieur du boîtier sans écraser la sensibilité tactile.
    Les pistes F qui passent derrière un secteur (I2C, PDM vers les micros) ajoutent une capacité fixe que le MPR121 absorbe à l'étalonnage. Le MPR121 filtre aussi le bruit de l'horloge PDM (3 MHz, bien au-dessus de sa fréquence de mesure).
* **Micros** : MK1 = canal gauche (SELECT = GND), MK2 = canal droit (SELECT = VDD). Même horloge, même ligne de données (PDM stéréo).
* **MPR121** : I2C **0x5B** (ADDR au +3,3 V), ELE0–ELE9 = secteurs, ELE10 = touche centrale (disque Ø 10 mm sur B.Cu, au centre de l'anneau de LED), ELE11 libre.
  * IRQ non câblée : le firmware interroge le MPR121 (polling). La pastille de test a été retirée pour laisser le centre libre à la touche centrale.
* **Composants sur les deux faces** : les LED sont sur B (face vers le plastique, pour éclairer le diffuseur), le reste sur F.
  JLC assemble la face F seule (micros, MPR121, passifs) ; les 12 LED et le tampon 74AHCT1G125 se soudent au fer.
* **Micros IM69D130** (Infineon) : SNR 69 dB(A), point de saturation 130 dB SPL. Ils sont au moins aussi bons que les **InvenSense INMP621** d'origine (SNR 65 dB(A), saturation 133 dB SPL) : +4 dB de rapport signal/bruit, ce qui compte le plus pour la détection du mot d'activation.

### Repérage (vue côté composants F, y vers le bas)

* Secteur ELE*k* centré à l'angle −72° + 36°·*k*, compté en sens horaire depuis l'axe +x (ELE0 vers « 1 h », ELE2 côté MK1).
  **Vu de dessus, l'ordre est inversé** : les secteurs tournent dans le sens antihoraire.
* LED D1 à 6 h (côté des pastilles de fils), la chaîne D1→D12 suit le sens horaire en vue composants, donc le sens antihoraire vu de dessus.

## 6. Liaison entre cartes : 10 fils soudés

Valable sans dégradation, car tous les signaux sont lents : I2C 400 kHz, PDM ~3 MHz avec 33 Ω en série côté émetteur, données LED à 800 kHz.

| Broche | J4 carte mère | J1 carte du dessus | Signal |
|---|---|---|---|
| 1 | 5V | 5V | +5 V (LED, tampon) |
| 2 | GND | GND | masse |
| 3 | LED | LED | données LED (3,3 V) |
| 4 | 3V3 | 3V3 | +3,3 V (MPR121) |
| 5 | SDA | SDA | I2C |
| 6 | SCL | SCL | I2C |
| 7 | VMIC | VMIC | alimentation micros (coupée en mute) |
| 8 | DAT | DAT | données PDM |
| 9 | GND | GND | masse (blindage de l'horloge) |
| 10 | CLK | CLK | horloge PDM |

* Fil **AWG 28–30** (0,08–0,05 mm²), silicone ou PTFE. Pour 5V et GND, AWG 26 si la longueur dépasse 10 cm.
* Longueur **< 15 cm**, nappe de fils côte à côte dans cet ordre. **Torsader CLK (10) avec GND (9)**.
* Les pastilles sont au pas de 2,54 mm. Côté carte mère, J4 accepte aussi un connecteur 2,54 mm si l'on préfère démonter.

## 7. Traitement audio (AEC / bruit) — ce que le matériel fournit

* **Référence d'écho exacte** : le TAS5805M renvoie sur SDOUT le signal réellement joué (après DSP et volume). L'S3 le reçoit sur l'I2S, synchrone des micros.
  Cela permet l'AEC de l'AFE ESP-SR (ou équivalent) avec une référence alignée : c'est ce qui permet au mot d'activation de fonctionner musique forte.
* **Réseau de 2 micros espacés de ~69 mm** : formation de faisceau / séparation de sources (BSS), réduction de bruit (NS), AGC.
* **Atténuation progressive (ducking)** : volume numérique du TAS5805M piloté par l'S3, sans coupure.

## 8. Mécanique — À VÉRIFIER AVANT COMMANDE

Toutes les cotes viennent de **photos** (iFixit / FCC) calibrées sur des boîtiers connus. Précision estimée **±0,5 mm**.

1. Ouvrir `hardware/*/gh_*.kicad_pcb` dans KiCad 10, imprimer le contour à l'échelle 1:1 et le poser sur les cartes d'origine.
   Ou mesurer au pied à coulisse : entraxes des vis, largeurs (49,0 / 36,0 / 14,0 mm), longueur 107,6 mm, Ø 74,8 mm du dessus.
2. Corriger `tools/ghrevive/mechanical.py` (fichier unique), puis relancer :
   `"C:/Program Files/KiCad/10.0/bin/python.exe" tools/build.py all`. Tout est regénéré : placement, routage, Gerber, BOM, CPL.
3. Points critiques :
   * position du **poussoir mute** (bras ressort) ;
   * pattes du **jack DC** ;
   * position des **ports micro** (trous du plastique) ;
   * encoches de la carte du dessus ;
   * ouverture de l'**USB-C** : le connecteur vertical sort au même endroit que l'ancien micro-USB, il suffit de limer la coque à ~9 × 3,5 mm.

## 9. Fabrication JLCPCB

Fichiers dans `hardware/<carte>/fab/` : `*_gerbers.zip`, `*_bom.csv`, `*_cpl.csv`.

| Option | Carte mère | Carte du dessus |
|---|---|---|
| Couches | 2 | 2 |
| Épaisseur | 1,6 mm | 1,6 mm |
| Finition | HASL sans plomb (exigé pour l'assemblage) | HASL sans plomb |
| Vias | Tented (couverts) : l'option par défaut « epoxy filled » ajoute ~16 $ | idem |
| Quantité PCB | 5 (minimum JLC) | 5 |
| Assemblage (PCBA) | **Economic, 1 face** (TAS5805M, USB-C, passifs) | **Economic, face F seule** (micros, MPR121, passifs) |
| Quantité assemblée | 2 (minimum JLC) | 2 (minimum JLC) |
| Fichiers à téléverser | Gerber + `gh_mainboard_bom.csv` + `gh_mainboard_cpl.csv` | Gerber + `gh_topboard_bom.csv` + `gh_topboard_cpl.csv` |

* **Commande retenue : les pièces sensibles sont soudées en usine, le reste au fer.**
  * Carte mère : JLC soude le **TAS5805M** (plaque thermique sous le boîtier), l'**USB-C** (broches sous le boîtier) et tous les passifs 0603 / 0805 / SMA, le poussoir mute et le MOSFET.
  * Carte du dessus : JLC soude les 2 micros **IM69D130** (LGA, port acoustique) et le **MPR121** (QFN 0,4 mm), avec leurs passifs.
  * Le nombre de soudures ne coûte presque rien (0,0016 $ l'unité) ; ce qui coûte, ce sont les frais fixes par carte et par face, les 3,07 $ par référence « étendue », la radiographie des pièces sans pattes et le passage au-dessus de 150 EUR.
* JLC assemble au minimum **2 exemplaires** de chaque carte : le 2e jeu sert de réserve, ou de 2e appareil (seul un 2e kit LCSC s'ajoute).
* **Soudé au fer** (pièces de `gh_*_hand_bom.csv`, achetées chez LCSC) : modules ESP32 (pattes crénelées sur le côté), boîtiers SOT-23 / TSSOP-8, bobines 4 × 4 mm, électrolytique, connecteur haut-parleur, 12 LED WS2812B-MINI-V3J (pattes en J visibles) et le tampon de niveau. Guide pièce par pièce : `docs/manuel_soudure.md`.
* Le module **ESP32-S3-WROOM-1-N16R8** (C2913202) est parfois en rupture : toute variante S3-WROOM-1 avec PSRAM convient (N8R8, N16R2…).
* **IM69D130** (C536262) : pris dans le stock JLC (131 pièces commandables le 14/11/2026). Vérifier le stock au moment de commander.
* À la vérification des placements (étape « Component Placement » de JLC), contrôler l'orientation des micros et du MPR121.
* À la vérification des placements (étape « Component Placement » de JLC), contrôler aussi le TAS5805M et l'USB-C.
* Outillage : fer à panne fine, flux, tresse à dessouder, loupe. Pas d'air chaud nécessaire.
* Autres scénarios : tout assemblé par JLC (`tools/quote_assembled.py`, ~129 EUR par appareil) ou kit complet soudé à l'air chaud (`tools/quote.py`, ~71 EUR).

## 10. Exigences logicielles (base fournie dans `firmware/`)

| Fonction | Exigence |
|---|---|
| Wi-Fi | SSID / clé gravés au flash (secrets), facultatif. Sinon, ou si le réseau est injoignable 30 s : point d'accès **GH-Revive Setup** + portail captif (composant `gh_setup`). Page : 1) mot de passe administrateur (créé au premier usage, demandé ensuite), 2) réseau scanné ou saisi + clé, testé en direct ; « clé incorrecte », « réseau introuvable » ou « sécurité non prise en charge » s'affichent et l'on réessaie. WPA / WPA2 / WPA3 acceptés ; le WEP n'est pas géré par la pile Wi-Fi de l'ESP32. Une fois connecté, le haut-parleur **lit l'adresse IP** (et à la demande, bouton HA). |
| Mise à jour | OTA ; flash initial par l'USB-C (TP2 BOOT à la masse en branchant le câble), secours par adaptateur USB-série sur TP1-TP5. Le module BT se flashe **à travers l'S3** (pont USB ↔ UART1, BOOT/EN pilotés par IO1 / IO2 selon DTR / RTS). |
| Voix | ESPHome `voice_assistant` / `micro_wake_word`. Mot « Jarvis » : un modèle « hey jarvis » existe ; « Jarvis » seul demande d'entraîner un modèle. Pipeline HA → agent conversationnel (OpenClaw), TTS en streaming. |
| Multi-appareils | Modèles « hey jarvis » (actif par défaut), « okay nabu », « hey mycroft » choisis par appareil dans HA. Arbitrage de proximité : niveau RMS micro (`sound_level`, fenêtres de 100 ms, maximum sur 1,5 s) diffusé en UDP (port 18511, paquet `GHW1` + id MAC + niveau en 0,1 dB) ; le plus fort démarre après le délai d'arbitrage (400 ms réglable), égalité départagée par l'id. Le téléphone, hors arbitrage, gagne par la déduplication HA (premier flux reçu). Texte compris / réponse exposés en capteurs texte. |
| AEC | AFE ESP-SR (AEC + BSS + NS + AGC) avec les 2 micros PDM et la référence I2S du TAS5805M. |
| Média | lecteur réseau (cast / Snapcast / Sendspin / Music Assistant). Mélange avec le flux A2DP du module BT et ducking pendant la voix. |
| Bluetooth | ESP32 en puits A2DP (bibliothèque ESP32-A2DP), sortie I2S maître vers l'S3. Appairage déclenché depuis HA (commande UART `PAIR`). L'S3 n'a que **2 périphériques I2S** (I2S0 = micros PDM, I2S1 = ampli + référence AEC) : pour relayer le flux BT, I2S0 bascule en esclave sur IO38-40 pendant la lecture Bluetooth (mot d'activation suspendu pendant ce temps), ou le flux passe par l'UART. |
| Tactile | MPR121 : rotation horaire **vue de dessus** = volume +, antihoraire = volume − (pas = 1 secteur), simple tap (appui bref sans rotation, sur n'importe quel secteur) = pause/lecture, double tap = piste suivante ; la touche centrale (ELE10) fait de même (appui = pause/lecture, double appui = piste suivante). Seuils réglés **à travers le plastique**. |
| LED | WS2812B RGB adressables (GRB) sur IO6, effets arc-en-ciel / comète / scintillement / feu d'artifice / bougie, luminosité plafonnée (~50 %) : 12 LED blanches à 100 % ≈ 0,2 A sur le fil +5 V. |
| Mute | lire MUTE_STATE (IO7) pour l'afficher sur l'anneau ; MUTE_SET_N (IO15, actif bas) peut forcer le mute. |
| Ampli | TAS5805M en I2C (0x2C attendu, à confirmer par un scan I2C) : séquence PDN, configuration BTL, plafond ~10 W. AMP_FAULT en entrée. |

### Affectation des broches ESP32-S3

| GPIO | Signal | GPIO | Signal |
|---|---|---|---|
| IO4 | PDM_CLK (vers le tampon de mute) | IO9 | I2S_BCLK (TAS5805M) |
| IO5 | PDM_DAT | IO10 | I2S_LRCK |
| IO6 | LED_DATA | IO11 | I2S_DOUT → TAS5805M |
| IO7 | MUTE_STATE (1 = muet) | IO12 | I2S_REF ← SDOUT TAS5805M |
| IO15 | MUTE_SET_N | IO13 | AMP_PDN |
| IO16 / IO17 | I2C SDA / SCL (TAS5805M, MPR121) | IO14 | AMP_FAULT |
| IO19 / IO20 | USB D− / D+ | IO21 | BT_GPIO (IO22 du module BT) |
| IO38 / IO39 / IO40 | I2S BT : BCLK / LRCK / DATA (IO18/19/21 du module BT) | IO41 / IO42 | UART BT : RX / TX |
| IO2 / IO1 | EN / BOOT du module BT | IO47 / IO48 | libres (TP8 / TP9) |
| IO0 | BOOT de l'S3 (TP2) | IO43 / IO44 | UART0 TX / RX (TP3 / TP4) |

## 11. Régénérer les fichiers

```
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/build.py all            # placement + routage + fabrication
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/build.py all --stage place
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote_assembled.py      # devis assemblé -> docs/devis_assemble.md
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote.py                # devis kit -> docs/devis.md
"C:/Program Files/KiCad/10.0/bin/python.exe" tools/quote_partial.py        # devis retenu -> docs/devis_partiel.md
```
Routage automatique : FreeRouting (`%LOCALAPPDATA%/freerouting/freerouting.exe`). DRC KiCad : `hardware/*/gh_*_drc.json`.

## 12. Devis TTC - pièces sensibles soudées en usine (détail : `docs/devis_partiel.md`)

Taux 0,86 EUR / USD, site web JLCPCB, TVA 20 % et taxe petits colis incluses, commande unique sous 150 EUR.

| Poste | EUR |
|---|---:|
| Assemblage JLC carte mère (x2) : TAS5805M, USB-C, passifs | 22,99 |
| Assemblage JLC carte du dessus (x2) : micros, MPR121, passifs | 38,55 |
| Coupon SMT mensuel JLC | -7,74 |
| Pièces LCSC à souder soi-même (1 jeu) | 17,87 |
| PCB nus (5 de chaque) | 9,12 |
| Livraison JLC + colis LCSC fusionné | 10,09 |
| Total HT | 90,88 |
| TVA 20 % + taxe petits colis | 20,18 |
| **Total TTC, 1 appareil (+ 1 jeu de cartes en réserve)** | **111,06** |
| **Total TTC, 2 appareils (2e kit LCSC ajouté)** | **122,35**, soit **61,17 par appareil** |

Avec l'application de bureau JLCPCB (PCB 4 $ moins cher) : 106,93 EUR pour 1 appareil, 59,11 EUR par appareil pour 2.
