LSN PHARMA — Livraison V4.8

Principales évolutions :
- onglet KPI réservé au profil Pharmacien ; un profil Opérateur ne voit pas l’onglet et un accès direct est refusé ;
- archivage d’une tournée terminée avant remise à zéro opérationnelle ;
- conservation du parc de bacs : les bacs livrés restent chez le client et les bacs restitués redeviennent disponibles ;
- bouton « Retour LSN PHARMA — ouvrir Waze » en fin de tournée ;
- validation manuelle d’un bac annulable avant validation définitive de la livraison ;
- confirmation explicite en cas d’écart entre colis chargés et colis livrés ;
- traçabilité des sauts de pharmacie, saisies manuelles et anomalies ;
- KPI : durée moyenne de tournée, anomalies par opérateur, saisies manuelles, taux de récupération des bacs, historique par tournée et par opérateur ;
- mesure du temps réel de trajet quand Waze est ouvert depuis l’application ; la référence théorique Waze n’est pas simulée et nécessitera une API de navigation ;
- Back-office : Code porte / Interphone / Code alarme / Instructions d’accès à la place du « n° de clé » ;
- avertissement : cette version GitHub Pages est un prototype public, ne pas y saisir de vrais codes d’accès ou d’alarme.

Dans cette maquette, le profil par défaut est Pharmacien pour permettre le test des KPI.
Test du masquage KPI : ajouter ?role=operator à l’URL.
Retour au profil Pharmacien : ?role=pharmacist.

Pour GitHub Pages : remplacer index.html, sw.js, manifest.webmanifest et README.txt à la racine du dépôt.
