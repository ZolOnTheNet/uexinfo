# Demande d'autorisation à SCMDB (scmdb.net)

| | |
|---|---|
| Envoyé le | 2026-10-21 |
| À | info@scmdb.net (contact indiqué dans les mentions légales du site) |
| Objet | Permission request – using SCMDB contract data in uexinfo |
| Statut | **En attente de réponse** |

## Contexte

uexinfo reconnaît les contrats lus dans la liste du mobiGlas (`/mission offres`) grâce aux données de contrats
publiées par scmdb.net (`https://scmdb.net/data/versions.json` puis `merged-<version>.json`) : récompense,
cargaison, points d'événement (`completionTags` / `eventScopes`), partage des points en groupe.

Licence affichée par le site : **Creative Commons BY-NC-ND 4.0**, plus le droit d'auteur allemand sur le
contenu de l'opérateur (« Duplication, processing, distribution […] require the written consent »).

En attendant la réponse, usage de test convenu avec l'utilisateur :
- aucune donnée scmdb dans le dépôt (les tests utilisent un catalogue fictif) ;
- copie gardée dans le cache utilisateur (`appdirs.user_cache_dir('uexinfo')/scmdb/`) ;
- téléchargement seulement sur demande explicite (`/mission offres maj`), une fois par version du jeu,
  avec un User-Agent qui identifie uexinfo ;
- mention « Données : SCMDB (scmdb.net), CC BY-NC-ND 4.0 » sous chaque affichage.

Sans accord, uexinfo peut se passer de scmdb : le `global.ini` du jeu suffit à reconnaître les titres
(sans catégories ni récompenses).

## Version envoyée (anglais)

> **Subject:** Permission request – using SCMDB contract data in uexinfo (non-commercial Star Citizen tool)
>
> Hello,
>
> I'm a Star Citizen player and I develop **uexinfo**, a free, non-commercial in-game overlay that I use with my small group of friends. It helps with trading, navigation and missions, using the UEX Corp API, the game logs and OCR of in-game screenshots.
>
> We would like to use SCMDB's contract data (the `merged-<version>.json` files) to recognize the contracts listed in the mobiGlas and get their details: rewards, cargo, locations and event points (`completionTags` / `eventScopes`). The goal is to plan routes that combine several contracts with trading runs.
>
> Since your data is published under CC BY-NC-ND 4.0, this is how we would use it:
> - the application downloads the data on the user's machine and keeps a local cache; it is **never committed to our repository or redistributed**, in original or modified form;
> - **one download per game version**, after checking `versions.json`;
> - a clear credit **"Data: SCMDB (scmdb.net)"** with a link wherever the data is displayed;
> - strictly non-commercial use.
>
> Would this be acceptable to you? If you prefer us to access the data another way (dedicated endpoint, rate limits, specific attribution text), we will gladly follow your preferences. We are also happy to report any data issues we notice.
>
> Thank you for this great tool!
>
> Best regards,
> [prénom ou pseudo]
> [lien du projet, s'il est public]

*Texte du brouillon préparé le 2026-10-19. Si le mail envoyé a été modifié, remplacer ce texte par la version réellement envoyée.*

## Version française (pour référence, non envoyée)

> **Objet :** Demande d'autorisation – utilisation des données de contrats de SCMDB dans uexinfo (outil Star Citizen non commercial)
>
> Bonjour,
>
> Je suis joueur de Star Citizen et je développe **uexinfo**, un overlay gratuit et non commercial que j'utilise avec mon petit groupe d'amis. Il aide au commerce, à la navigation et aux missions, à partir de l'API UEX Corp, des logs du jeu et de l'OCR de captures d'écran.
>
> Nous aimerions utiliser les données de contrats de SCMDB (les fichiers `merged-<version>.json`) pour reconnaître les contrats affichés dans le mobiGlas et obtenir leurs détails : récompenses, cargaison, lieux et points d'événement (`completionTags` / `eventScopes`). Le but est de planifier des circuits qui combinent plusieurs contrats avec du commerce.
>
> Vos données étant publiées sous licence CC BY-NC-ND 4.0, voici comment nous les utiliserions :
> - l'application télécharge les données sur la machine de l'utilisateur et les garde en cache local ; elles ne sont **jamais versionnées dans notre dépôt ni redistribuées**, ni telles quelles ni modifiées ;
> - **un seul téléchargement par version du jeu**, après vérification de `versions.json` ;
> - une mention claire **« Données : SCMDB (scmdb.net) »** avec un lien partout où les données sont affichées ;
> - un usage strictement non commercial.
>
> Cela vous conviendrait-il ? Si vous préférez que nous accédions aux données autrement (adresse dédiée, limite de fréquence, texte d'attribution précis), nous suivrons volontiers vos préférences. Nous vous signalerons aussi avec plaisir les erreurs que nous pourrions repérer dans les données.
>
> Merci pour cet excellent outil !
>
> Cordialement,
> [prénom ou pseudo]

## Réponse

- 2026-10-22 : aucune réponse reçue.
