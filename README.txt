LSN PHARMA — Livraison V5.0

Évolutions principales :
- Historique simplifié et hiérarchisé : Jour > Tournée > Pharmacie ;
- KPI et Historique visibles uniquement avec le profil Pharmacien ;
- suppression du KPI « réel vs Waze » / ETA théorique ;
- règle stricte d’unicité des bacs : un bac déjà chez une pharmacie ne peut pas être chargé pour une autre ;
- un bac déjà affecté à un chargement actif ne peut pas être affecté ailleurs ;
- nouveau module « Restitué à l’entrepôt » dans Parc bacs pour corriger un oubli de scan de restitution ;
- la régularisation remet le bac en stock disponible et conserve une trace de l’ajustement ;
- un profil Opérateur/Livreur ayant une tournée en cours de livraison ne peut ni charger ni sélectionner une autre tournée avant clôture ;
- la tournée active peut être reprise directement depuis l’écran Tournées ;
- à la clôture, l’état opérationnel de la tournée est remis à zéro, tandis que le parc de bacs et l’historique restent conservés ;
- les fonctions V4.9 restent présentes : correction d’une livraison avant clôture, historique détaillé, anomalies, saisies manuelles, codes d’accès pharmacie, bouton ENREGISTRER du Back-office.

Prototype GitHub Pages : ne pas saisir de vrais codes d’alarme, porte ou interphone tant qu’une authentification et un stockage serveur sécurisés ne sont pas en place.

Pour GitHub Pages : remplacer index.html, sw.js, manifest.webmanifest et README.txt à la racine du dépôt.
